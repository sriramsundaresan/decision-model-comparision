"use strict";
const $ = (id) => document.getElementById(id);
let polling = false;
let activeJob = null;
const xlsxType = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options, credentials: "same-origin",
    headers: { "X-Demo-Request": "1", ...options.headers },
  });
  const body = await response.json();
  if (!response.ok) {
    const error = new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return body;
}
function numeric(value, digits = 3) {
  return value === null || value === undefined ? "Unavailable" : Number(value).toFixed(digits);
}
function cell(row, text, className) {
  const td = document.createElement("td");
  td.textContent = String(text);
  if (className) td.className = className;
  row.append(td);
  return td;
}
function render(job) {
  const report = job.report;
  if (report.mode !== "intent_evaluation") {
    notice("This is an earlier classifier-only run. Download the new evaluator template and start a new evaluation.", true);
    $("results-panel").hidden = true;
    return false;
  }
  $("results-panel").hidden = false;
  $("run-state").textContent = job.status;
  $("summary-rows").replaceChildren();
  for (const provider of report.providers) {
    const s = report.summary[provider];
    const row = document.createElement("tr");
    [
      provider === "jev" ? "Jev" : "Microsoft-Decision-1",
      `${s.correct}/${report.cases.length}`, `${numeric(100 * s.evaluator_accuracy, 1)}%`,
      numeric(s.brier_successful_only), numeric(s.p50_ms, 1),
      s.errors, numeric(s.estimated_total_usd, 8),
    ].forEach((text) => cell(row, text));
    $("summary-rows").append(row);
  }
  const lookup = new Map(report.results.map((r) => [`${r.case_id}:${r.provider}`, r]));
  $("result-rows").replaceChildren();
  for (const test of report.cases) {
    const row = document.createElement("tr");
    cell(row, test.id);
    cell(row, test.message, "message");
    cell(row, test.predicted_intent);
    cell(row, test.expected_intent);
    for (const provider of report.providers) {
      const result = lookup.get(`${test.id}:${provider}`);
      if (!result) { cell(row, "Not evaluated"); continue; }
      if (result.status !== "ok") { cell(row, result.error, "incorrect"); continue; }
      const probability = result.answers.intent_is_correct.noul;
      const td = cell(row, "", result.evaluator_correct ? "correct" : "incorrect");
      td.title = `Full precision Noul: ${probability}`;
      for (const text of [
        numeric(probability, 2),
        `Intent judged ${result.judged_correct ? "correct" : "incorrect"}`,
        result.evaluator_correct ? "Matches reference" : "Does not match reference",
      ]) {
        const span = document.createElement("span");
        span.className = "result-line";
        span.textContent = text;
        td.append(span);
      }
    }
    $("result-rows").append(row);
  }
  const total = report.cases.length * report.providers.length;
  $("progress").value = 100 * report.results.length / total;
  $("progress-text").textContent = `${report.cases.length} test cases | ${report.results.length}/${total} model evaluations`;
  return true;
}
async function poll(id) {
  if (polling) return;
  polling = true;
  activeJob = id;
  $("evaluate").disabled = true;
  $("progress-panel").hidden = false;
  $("downloads").hidden = true;
  try {
    while (polling) {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
      if (!polling) break;
      if (!render(job)) {
        sessionStorage.removeItem("evaluation-job");
        activeJob = null;
        break;
      }
      if (job.status !== "queued" && job.status !== "running") {
        notice(job.error || "Evaluation complete.", job.status !== "completed");
        $("downloads").hidden = false;
        $("download-json").href = `/api/jobs/${encodeURIComponent(id)}/download?format=json`;
        $("download-html").href = `/api/jobs/${encodeURIComponent(id)}/download?format=html`;
        sessionStorage.removeItem("evaluation-job");
        activeJob = null;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 1500));
    }
  } catch (error) {
    if (error.status === 404) {
      sessionStorage.removeItem("evaluation-job");
      activeJob = null;
      notice(error.message, true);
    } else {
      notice(`${error.message} Refresh the page to reconnect to your saved run.`, true);
    }
  } finally {
    polling = false;
    $("evaluate").disabled = activeJob !== null;
  }
}
async function initialize() {
  await api("/api/config");
  $("workspace").hidden = false;
  const saved = sessionStorage.getItem("evaluation-job");
  if (saved) { notice("Reconnecting to your evaluation."); void poll(saved); }
}
$("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("workbook").files[0];
  if (!file || !file.name.toLowerCase().endsWith(".xlsx") || file.size > 262144 || file.size === 0) {
    notice("Choose a nonempty .xlsx file no larger than 256 KiB.", true); return;
  }
  if (!$("consent").checked) { notice("Confirm synthetic data only.", true); return; }
  $("evaluate").disabled = true;
  try {
    const result = await api("/api/jobs", {
      method: "POST", body: file,
      headers: { "Content-Type": xlsxType, "X-Synthetic-Data": "confirmed" },
    });
    sessionStorage.setItem("evaluation-job", result.id);
    notice("Evaluating...");
    await poll(result.id);
  } catch (error) { notice(error.message, true); }
  finally { $("evaluate").disabled = activeJob !== null; }
});
initialize().catch((error) => {
  notice(error.message, true);
});
