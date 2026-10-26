---
title: Excel intent-evaluation demo
description: Compare Microsoft-Decision-1 and Jev judgments of supplied classifier intents.
---

## Overview

This web demo compares Microsoft-Decision-1 and Jev on the
same Excel test cases. Each model judges whether a supplied classifier intent is
correct. Neither model generates a replacement intent or executes a transaction.

Only synthetic data is permitted. Messages and classifier predictions are sent
to Microsoft Azure and TypeSafe AI. Human reference labels and case IDs stay
within the application.

This is a temporary, single-instance demonstration, not a production banking
service or an independently validated benchmark.

## Source files

* [web_demo.py](web_demo.py): web routes, anonymous sessions, Excel validation,
  SQLite storage, and managed-identity inference runner
* [intent_evaluator.py](intent_evaluator.py): intent definitions, shared model
  question, response validation, transport, metrics, and HTML report
* [comparison.html](comparison.html), [comparison.css](comparison.css), and
  [comparison.js](comparison.js): customer upload and results interface
* [banking_evaluation_cases.csv](banking_evaluation_cases.csv): synthetic examples
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

## Configure Azure hosting

Create a Linux Azure App Service with Python 3.11 or later and persistent storage.
Enable its system-assigned managed identity. Assign that identity the Cognitive
Services User role scoped to your Foundry model resource, with a deployed
Microsoft-Decision-1 model.

Configure the following App Service application settings. No resource endpoint,
deployment name, tenant ID, or API key is bundled with this source.

| Setting                              | Value                                                                    |
|--------------------------------------|--------------------------------------------------------------------------|
| `PUBLIC_ORIGIN`                       | Exact HTTPS website origin, with no path or trailing slash                |
| `AZURE_ENDPOINT`                     | Your root HTTPS Foundry resource endpoint                                 |
| `AZURE_DEPLOYMENT`                   | Your Microsoft-Decision-1 deployment name                                 |
| `JEV_API_KEY`                        | TypeSafe API key, provided through secure application settings             |
| `DEMO_DATA_DIR`                      | Persistent SQLite directory; defaults to `/home/intent-demo`               |
| `SCM_DO_BUILD_DURING_DEPLOYMENT`      | `true`                                                                   |
| `ENABLE_ORYX_BUILD`                   | `true`                                                                   |
| `WEBSITES_ENABLE_APP_SERVICE_STORAGE` | `true`                                                                   |

The Jev model is pinned to `jev-1.14.0`. Both providers use server-side
credentials; the browser never receives an Azure access token or TypeSafe key.
There is no customer Microsoft sign-in or tenant-ID setting.

The demo opens without a password. `DEMO_PASSWORD_HASH` is no longer used and can
be removed from existing App Service settings. Anyone who can reach the website
can submit evaluations against the shared daily quota. Use App Service access
restrictions if the demo should only be reachable by a limited audience.
Do not commit keys, environment files, or result databases.

Enable HTTPS-only mode, TLS 1.2 minimum, and Always On. Disable FTPS.
Use exactly one instance and one worker. Set the startup command to:

```text
python -m uvicorn web_demo:create_app --factory --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips 127.0.0.1
```

`GET /health` returns `{"status":"ok"}` for requests using the configured host.
Opening the HTML file directly is not supported; use the hosted website.
The default application factory requires HTTPS and an Azure managed identity
environment for live evaluation.

### Troubleshoot cross-site request errors

The homepage supports opening a link from another website in a top-level browser
tab. Cross-site API requests and embedded pages remain blocked.

If you see `Cross-site requests are not allowed.`, open the website directly in
your browser rather than inside a preview or iframe. For uploads,
the browser address must match `PUBLIC_ORIGIN` exactly, including the scheme,
hostname, and any port. Use one configured origin consistently rather than
switching between the App Service hostname and a custom domain.
After deploying application changes or updating `PUBLIC_ORIGIN`, restart the
App Service and reload the page.

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

* `transfer_money`
* `pay_bill`
* `check_transaction_status`
* `dispute_transaction`
* `cancel_transfer`
* `view_transaction_history`
* `check_balance`
* `other`
* `needs_clarification`

The precise definitions are in [intent_evaluator.py](intent_evaluator.py).
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
inference; failures and restarts do not refund it. Calls alternate provider order,
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
banking_evaluation_cases.csv
requirements.txt
```

The local RAG walkthrough, classifier-only CLI, their dataset, and their tests
are not part of this demo.
