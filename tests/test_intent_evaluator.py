import json

import httpx
import pytest
from pydantic import ValidationError

from intent_evaluator import (
    MODE,
    QUESTION,
    ROOT,
    THRESHOLD,
    EvaluationCase,
    EvaluatorResponse,
    display_noul,
    evaluate,
    evaluation_report,
    load_cases,
    percentile,
    render_report,
    request_body,
    summarize,
)


def case(identifier="X", *, classifier_correct=True):
    return EvaluationCase(
        id=identifier,
        message="Cancel my scheduled transfer.",
        predicted_intent="cancel_transfer" if classifier_correct else "transfer_money",
        expected_intent="cancel_transfer",
    )


def payload(probability):
    return {
        "model": "actual-model",
        "answers": {"intent_is_correct": {"type": "noul", "noul": probability}},
        "usage": {"input_tokens": 1000, "output_tokens": 1},
    }


def score(test_case, probability):
    with httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload(probability)))
    ) as client:
        return evaluate(client, "https://test.invalid", "deployment", test_case, "jev")


def test_template_balances_correct_and_incorrect_classifier_predictions():
    cases = load_cases(ROOT / "banking_evaluation_cases.csv")
    assert len(cases) == 30
    assert len({c.id for c in cases}) == 30
    assert sum(c.classifier_is_correct for c in cases) == 15
    for correct, incorrect in zip(cases[::2], cases[1::2], strict=True):
        assert correct.message == incorrect.message
        assert correct.classifier_is_correct and not incorrect.classifier_is_correct


def test_ground_truth_and_ids_never_influence_the_model_request():
    test_case = case()
    changed = test_case.model_copy(update={"expected_intent": "other", "id": "SECRET-LABEL-ID"})
    assert request_body("deployment", test_case) == request_body("deployment", changed)
    assert "expected_intent" not in json.dumps(request_body("deployment", test_case))
    microsoft = request_body("deployment", test_case)
    jev = request_body("jev-1.14.0", test_case)
    microsoft.pop("model")
    jev.pop("model")
    assert microsoft == jev
    assert microsoft["questions"]["intent_is_correct"]["type"] == "noul"
    assert "intent_definitions" in microsoft["state"]


@pytest.mark.parametrize(
    "actual,probability,judgment,evaluator_correct",
    [
        (True, 0.9, True, True),
        (False, 0.1, False, True),
        (False, 0.9, True, False),
        (True, 0.1, False, False),
        (True, 0.5, True, True),
    ],
)
def test_binary_judgment_and_evaluator_correctness(
    actual, probability, judgment, evaluator_correct
):
    row = score(case(classifier_correct=actual), probability)
    assert row["correctness_probability"] == probability
    assert row["judged_correct"] is judgment
    assert row["evaluator_correct"] is evaluator_correct
    assert row["response_model"] == "actual-model"


@pytest.mark.parametrize("probability", [-0.1, 1.1, "0.9", True, None, float("nan")])
def test_rejects_invalid_noul_probabilities(probability):
    with pytest.raises(ValidationError):
        EvaluatorResponse.model_validate(payload(probability))


def test_rejects_wrong_question_or_question_type():
    for answer in (
        {"primary_intent": {"type": "noul", "noul": 0.9}},
        {"intent_is_correct": {"type": "choice", "choice": "correct"}},
        {},
    ):
        response = payload(0.9)
        response["answers"] = answer
        with pytest.raises(ValidationError):
            EvaluatorResponse.model_validate(response)


@pytest.mark.parametrize("value", [-1, "1000", True, 1.5])
def test_rejects_invalid_reported_token_usage(value):
    response = payload(0.9)
    response["usage"]["input_tokens"] = value
    with pytest.raises(ValidationError):
        EvaluatorResponse.model_validate(response)


def test_metrics_measure_the_evaluator_not_classifier_accuracy():
    cases = [
        case("A"),
        case("B"),
        case("C", classifier_correct=False),
        case("D", classifier_correct=False),
    ]
    results = [score(c, p) for c, p in zip(cases, [0.9, 0.1, 0.8, 0.2], strict=True)]
    summary = summarize(cases, results, "jev")
    assert summary["classifier_baseline_accuracy"] == 0.5
    assert summary["evaluator_accuracy"] == summary["balanced_accuracy"] == 0.5
    assert summary["correctly_validated"] == summary["incorrect_intents_detected"] == 1
    assert summary["false_acceptances"] == summary["false_rejections"] == 1
    assert summary["brier_successful_only"] == pytest.approx(0.375)
    assert summary["estimated_total_usd"] == pytest.approx(0.000168)
    perfect = [score(c, 0.99 if c.classifier_is_correct else 0.01) for c in cases]
    assert summarize(cases, perfect, "jev")["evaluator_accuracy"] == 1


def test_missing_results_and_usage_are_not_success_shaped():
    cases = [case("A"), case("B", classifier_correct=False)]
    row = score(cases[0], 0.9)
    summary = summarize(cases, [row], "jev")
    assert summary["evaluator_accuracy"] == summary["balanced_accuracy"] == 0.5
    assert summary["failed_or_unrun"] == 1
    assert summary["estimated_total_usd"] is None
    row["usage"] = None
    assert summarize([cases[0]], [row], "jev")["estimated_total_usd"] is None
    assert summarize([cases[0]], [row], "jev")["balanced_accuracy"] is None


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_upstream_error_records_no_probability(status):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status))) as client:
        row = evaluate(client, "https://test.invalid", "model", case(), "jev")
    assert row["status"] == "error"
    assert row["error"] == f"HTTP {status}"
    assert "correctness_probability" not in row
    assert summarize([case()], [row], "jev")["evaluator_accuracy"] == 0


def test_invalid_json_and_schema_are_explicit_errors():
    for response in (
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={"answers": {}}),
    ):
        with httpx.Client(transport=httpx.MockTransport(lambda r: response)) as client:
            row = evaluate(client, "https://test.invalid", "model", case(), "jev")
        assert row["status"] == "error"
        assert "correctness_probability" not in row


def test_report_restores_metrics_with_rounded_noul_and_full_precision_export():
    test_case = case(classifier_correct=False)
    test_case.message = "<script>bad()</script>"
    probability = 0.9975273749375825
    row = score(test_case, probability)
    report = {
        "mode": MODE,
        "judgment_threshold": THRESHOLD,
        "question": QUESTION,
        "created_at": "now",
        "dataset_sha256": "hash",
        "providers": ["jev"],
        "cases": [test_case.model_dump()],
        "results": [row],
        "summary": {"jev": summarize([test_case], [row], "jev")},
    }
    rendered = render_report(report)
    assert "banking" not in rendered.lower()
    assert str(probability) in rendered
    assert ">1.00<br>Intent judged correct" in rendered
    assert "Does not match reference" in rendered
    assert "Expected intent" in rendered
    assert "Accuracy" in rendered
    assert "Brier" in rendered
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered
    public = evaluation_report(report)
    assert public["results"][0]["answers"]["intent_is_correct"] == {
        "type": "noul",
        "noul": probability,
    }
    assert public["summary"] == report["summary"]
    assert public["cases"][0]["expected_intent"] == test_case.expected_intent
    assert public["results"][0]["judged_correct"] is True
    assert public["results"][0]["evaluator_correct"] is False
    assert json.loads(json.dumps(public))["results"][0]["correctness_probability"] == probability
    assert "answers" not in report["results"][0]


@pytest.mark.parametrize(
    "probability,expected",
    [
        (0.0, "0.00"),
        (0.004, "0.00"),
        (0.005, "0.01"),
        (0.125, "0.13"),
        (0.145, "0.14"),
        (0.4999, "0.50"),
        (0.5001, "0.50"),
        (0.9975273749375825, "1.00"),
        (1.0, "1.00"),
    ],
)
def test_noul_display_uses_exactly_two_decimal_places(probability, expected):
    assert display_noul(probability) == expected


def test_rounding_does_not_change_threshold_judgments_or_metrics():
    test_case = case(classifier_correct=False)
    below = score(test_case, 0.4999)
    above = score(test_case, 0.5001)
    assert display_noul(below["correctness_probability"]) == "0.50"
    assert display_noul(above["correctness_probability"]) == "0.50"
    assert below["judged_correct"] is False
    assert above["judged_correct"] is True
    assert summarize([test_case], [below], "jev")["evaluator_accuracy"] == 1
    assert summarize([test_case], [above], "jev")["evaluator_accuracy"] == 0


def test_probability_export_preserves_zero_and_one_and_explicit_failures():
    cases = [case("ZERO"), case("ONE"), case("FAIL")]
    rows = [
        score(cases[0], 0.0),
        score(cases[1], 1.0),
        {
            "provider": "jev",
            "case_id": "FAIL",
            "requested_model": "model",
            "status": "error",
            "error": "HTTP 429",
        },
    ]
    report = {
        "mode": MODE,
        "created_at": "now",
        "providers": ["jev"],
        "cases": [c.model_dump() for c in cases],
        "results": rows,
    }
    public = evaluation_report(report)
    assert public["results"][0]["answers"]["intent_is_correct"]["noul"] == 0
    assert public["results"][1]["answers"]["intent_is_correct"]["noul"] == 1
    assert public["results"][2]["error"] == "HTTP 429"
    assert "answers" not in public["results"][2]


def test_percentiles():
    assert percentile([], 0.95) is None
    assert percentile([10], 0.95) == 10
    assert percentile([10, 20, 30], 0.5) == 20
    assert percentile([10, 20, 30], 0.95) == 29


def test_network_errors_do_not_expose_provider_diagnostics():
    def timeout(request):
        raise httpx.ReadTimeout("private provider diagnostic")

    with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
        row = evaluate(client, "https://test.invalid", "model", case(), "jev")
    assert row["status"] == "error"
    assert row["error"] == "Network failure (ReadTimeout)"
    assert "private" not in json.dumps(row)


@pytest.mark.parametrize("label", ["predicted_intent", "expected_intent"])
def test_rejects_unknown_intents(label):
    data = case().model_dump()
    data[label] = "unknown"
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate(data)
