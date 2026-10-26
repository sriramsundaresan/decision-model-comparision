---
title: Excel intent-evaluation demo
description: Compare Microsoft-Decision-1 and Jev judgments of supplied classifier intents.
---

## Overview

This web demo compares Microsoft-Decision-1 and Jev on the
same Excel test cases. Each model judges whether a supplied classifier intent is
correct. Neither model generates a replacement intent or executes an action.

Only synthetic data is permitted. Messages and classifier predictions are sent
to Microsoft Azure and TypeSafe AI. Human reference labels and case IDs stay
within the application.

This is a temporary, single-instance demonstration, not a production
service or an independently validated benchmark.

## Source files

* [web_demo.py](web_demo.py): web routes, anonymous sessions, Excel validation,
  SQLite storage, and managed-identity inference runner
* [intent_evaluator.py](intent_evaluator.py): intent definitions, shared model
  question, response validation, transport, metrics, and HTML report
* [comparison.html](comparison.html), [comparison.css](comparison.css), and
  [comparison.js](comparison.js): customer upload and results interface
* [evaluation_cases.csv](evaluation_cases.csv): domain-neutral synthetic examples
  used for offline development tests, not included in the downloadable workbook
* [tests](tests): offline evaluator and web regression tests
* [pyproject.toml](pyproject.toml), [uv.lock](uv.lock), and
  [requirements.txt](requirements.txt): dependencies and deployment requirements

## Install and validate

Use Python 3.11 or later and [uv](https://docs.astral.sh/uv/getting-started/installation/).
From this directory:

```text
uv sync --python 3.11
uv run pytest -q
uv run ruff check intent_evaluator.py web_demo.py tests
uv run ruff format --check intent_evaluator.py web_demo.py tests
```

Tests use fake credentials and mock HTTP transports. They make no live inference
requests and require no Azure resource or TypeSafe key.

For an App Service deployment without uv:

```text
python -m pip install -r requirements.txt
```

After dependency changes, regenerate the deployment requirements:

```text
uv export --no-dev --no-hashes --no-emit-project --output-file requirements.txt
```

## Run the demo

1. Open the configured website. No password is required.
2. Select Download Excel template.
3. Add your synthetic cases, keeping one worksheet and the four text columns
   `id`, `message`, `predicted_intent`, and `expected_intent`, in that order.
4. Upload the workbook, confirm synthetic-data consent, and select Evaluate.
5. Wait for both models to finish, then download the JSON or HTML report.

`message` contains the conversation and relevant context. `predicted_intent` is
the supplied classifier output; `expected_intent` is the human-reviewed reference.
Both intent columns must use one of these labels:

* `create_request`
* `update_request`
* `check_request_status`
* `report_issue`
* `cancel_request`
* `view_history`
* `get_information`
* `other`
* `needs_clarification`

The precise definitions are in [intent_evaluator.py](intent_evaluator.py).
These domain-neutral labels replace the previous domain-specific labels.
Update existing workbooks to the labels above before uploading them.
The browser now saves active runs under `evaluation-job`; previously saved runs
will not reconnect automatically after this update.
Uploads allow 1-100 cases, unique IDs of up to 50 characters, messages of up to
1,000 characters, and a file size of up to 256 KiB. Empty cells, unknown labels,
formulas, macros, external workbook links, and oversized expanded archives are
rejected before inference.

The template contains only the four column headers, with no sample cases.
Add at least one synthetic case before uploading. Have domain reviewers approve
the labels before drawing conclusions.

## Interpret results

Both providers receive the same `intent_is_correct` Noul question and intent
definitions. Noul is the returned probability that the supplied prediction is
correct. A full-precision value of at least 0.5 is judged correct.
This illustrative boundary is not a calibrated production acceptance policy.

The page and HTML download display Noul to two decimals. Tooltips and JSON
preserve full precision. Rounding never changes judgments or metrics: a displayed
`0.50` can represent a value below the boundary.

* Evaluator accuracy measures agreement with the reference
  `predicted_intent == expected_intent`. Failed or unrun cases count as misses.
* Binary Brier score is the mean squared probability error over successful
  responses only. Lower is better.
* Median latency includes the provider HTTP request, not the queue or upload.
* Estimated input cost uses reported input tokens at an illustrative
  USD 0.042 per million tokens for each provider. It is not an invoice or a
  guarantee of current pricing; absent or incomplete usage yields Unavailable.

JSON also retains the question, dataset hash, requested and returned model names,
timestamps, raw scores, token usage, balanced accuracy, false acceptances, and
false rejections. Accuracy and Brier are calculated by the application, not
returned as model judgments.

## Operational limits and data handling

Only one evaluation runs globally at a time. The persistent quota is 1,000 rows
per UTC day, allowing up to 2,000 model calls. Each row reserves quota before
inference; failures and restarts do not restore it. Calls alternate provider order,
run sequentially, have a 30-second HTTP timeout, and are not retried automatically.
Authorization and rate-limit failures stop the run. Errors and partial results
are explicit, with no substitute probabilities.

Anonymous session cookies are created automatically, are HttpOnly, Secure,
SameSite Strict, and expire after two hours. Reports belong to the submitting
session. Refreshing the same browser can reconnect to an active evaluation.
Clearing cookies or letting the session expire starts a new session and does not
restore the previous session's reports. Download results before leaving.

Uploaded workbooks are parsed in memory and are not saved. Parsed messages and
results are stored in SQLite under `DEMO_DATA_DIR`. Reports expire after
24 hours and are purged on startup and by a minute-based cleanup task.
Logical deletion does not guarantee erasure from storage or backups.
Restarting the app marks unfinished evaluations failed; model calls do not resume.
Older unsupported report formats can be downloaded as raw JSON, but are not
rendered as evaluator reports.

Rotate the TypeSafe key after the demonstration.
Hosting charges can continue while the web app is stopped; review and remove
unused hosting resources after the demonstration.

## Share and deploy

Share the source files listed above together with this README and `.gitignore`.
Do not copy the entire working directory: exclude `.venv`, `__pycache__`,
`.pytest_cache`, `.ruff_cache`, `.env`, SQLite files, and any uploaded or downloaded
customer data.

For App Service, deploy only:

```text
web_demo.py
intent_evaluator.py
comparison.html
comparison.css
comparison.js
requirements.txt
```

The local RAG walkthrough, classifier-only CLI, their dataset, and their tests
are not part of this demo.
