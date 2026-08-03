"use strict";

const state = {formula: null, page: 1, pageCount: 1, filter: "all", operationId: null, selectedId: null, models: [], selectedModel: null, v2Loaded: false, v2Loading: false};
const byId = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {Accept: "application/json", "Content-Type": "application/json"}, ...options});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request returned ${response.status}`);
  return payload;
}

function display(value, fallback = "Not available") { return value === null || value === undefined || value === "" ? fallback : String(value); }
function percent(value) { return value === null || value === undefined ? "Not available" : `${(Number(value) * 100).toFixed(1)}%`; }
function direction(value) { return display(value).replaceAll("_", " "); }

function renderFormula(formula, parentFormula) {
  state.formula = formula;
  byId("formula-label").textContent = formula.label;
  byId("formula-thresholds").textContent = "Changed-outcome cohort only. Score +1 or higher = pathogenic direction; -1 or lower = benign direction; score 0 = no prediction. Remain uncertain is not allowed.";
  const rows = byId("formula-rows"); rows.replaceChildren();
  parentFormula.clues.forEach((clue) => {
    const row = document.createElement("tr");
    const points = formula.weights[clue.name];
    [clue.name.replaceAll("_", " "), clue.rule, Number(points) > 0 ? `+${points}` : points, clue.reason].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
    rows.append(row);
  });
}

function addMetric(list, label, value, help) {
  const item = document.createElement("div"); item.title = help;
  const term = document.createElement("dt"); term.textContent = label;
  const detail = document.createElement("dd"); detail.textContent = value;
  item.append(term, detail); list.append(item);
}

function registryValue(value, fallback = "Not recorded") {
  if (value === null || value === undefined || value === "" || value === "unknown/not recorded" || value === "not recorded") return fallback;
  if (typeof value === "number") return Number.isFinite(value) ? value.toLocaleString() : fallback;
  if (typeof value === "string" || typeof value === "boolean") return String(value).replaceAll("_", " ");
  return fallback;
}

function registryPercent(value) {
  return typeof value === "number" && Number.isFinite(value) ? percent(value) : registryValue(value);
}

function addRegistryLink(container, href, text, secondary = false) {
  const link = document.createElement("a");
  link.className = `button-link${secondary ? " button-secondary" : ""}`;
  link.href = href; link.textContent = text; container.append(link);
}

function setV2Visibility(visible) {
  document.querySelectorAll("[data-v2-only]").forEach((element) => {
    element.hidden = element.id === "prediction-detail" ? true : !visible;
  });
  if (!visible) state.selectedId = null;
}

function renderSelectedModel(model, comparisonWarning) {
  state.selectedModel = model.model_id;
  const modelName = `${registryValue(model.model_id)}: ${registryValue(model.name, "Unnamed model")}`;
  byId("results-page-title").textContent = `${model.model_id} Results`;
  byId("results-page-subtitle").textContent = registryValue(model.task, "Review this model's frozen registry record and available result surfaces.");
  byId("selected-model-name").textContent = modelName;
  byId("selected-model-boundary").textContent = registryValue(model.evaluation_reliability, "Evaluation design not recorded");
  byId("selected-summary-title").textContent = `${modelName} Summary`;
  byId("selected-model-status").textContent = registryValue(model.effective_status, registryValue(model.status));
  byId("selected-model-task").textContent = registryValue(model.task);

  const metadata = byId("selected-model-metadata"); metadata.replaceChildren();
  [
    ["Model type", model.model_type],
    ["Evaluation design", model.evaluation_reliability],
    ["Prediction snapshot", model.prediction_snapshot_date],
    ["Answer snapshot", model.answer_snapshot_date],
    ["Training records", model.train_records],
    ["Test records", model.test_records],
    ["Recorded inputs", model.feature_count],
    ["Interpretability", model.interpretability],
    ["Leakage audit", model.leakage_audit_status],
    ["Manual review", model.manual_review_status],
    ["Frozen", model.frozen_at_utc],
    ["Evaluation source", model.evaluation_source],
  ].forEach(([label, value]) => addMetric(metadata, label, registryValue(value), `Registry field: ${label}.`));

  const metrics = model.metrics || {};
  const metricList = byId("selected-model-metrics"); metricList.replaceChildren();
  [
    ["Accuracy", registryPercent(metrics.accuracy), "Recorded accuracy for this model's own evaluation."],
    ["Balanced accuracy", registryPercent(metrics.balanced_accuracy), "Recorded mean recall across outcome classes."],
    ["Macro F1", registryPercent(metrics.macro_f1), "Recorded unweighted mean class F1."],
    ["Benign recall", registryPercent(metrics.benign_recall), "Recorded benign-class recall."],
    ["Pathogenic recall", registryPercent(metrics.pathogenic_recall), "Recorded pathogenic-class recall."],
    ["Predictions", registryValue(metrics.number_of_predictions), "Number of recorded predictions."],
    ["Correct", registryValue(metrics.number_correct), "Number recorded correct."],
    ["Wrong", registryValue(metrics.number_wrong), "Number recorded wrong."],
    ["No prediction", registryValue(metrics.number_no_prediction), "Number recorded without a prediction."],
    ["Not scorable", registryValue(metrics.number_not_scorable), "Number recorded as not scorable."],
  ].forEach((item) => addMetric(metricList, ...item));

  const recordedWarnings = Array.isArray(model.warnings) ? model.warnings.filter((warning) => warning && warning !== "unknown/not recorded") : [];
  const warnings = recordedWarnings.length ? recordedWarnings : ["No model-specific warning was recorded in the registry."];
  byId("selected-model-warnings").replaceChildren(...warnings.map((warning) => { const item = document.createElement("p"); item.textContent = warning; return item; }));
  byId("model-comparison-warning").textContent = registryValue(comparisonWarning, "Do not rank models evaluated on different tasks or cohorts.");

  const links = byId("selected-model-links"); links.replaceChildren();
  addRegistryLink(links, "/model_versions.html", "Open Full Registry");
  if (["V1", "V2", "V3"].includes(model.model_id)) addRegistryLink(links, "/overview.html", "Open Project Context", true);
  if (["V4", "V5", "V6", "V7", "V8"].includes(model.model_id)) addRegistryLink(links, "/prediction_explorer.html", "Open Prediction Explorer", true);
  if (model.model_id === "V8") {
    addRegistryLink(links, "/v8_results.html", "Open V8 Result");
    addRegistryLink(links, "/v8_review.html", "Open V8 Review", true);
  }

  const isV2 = model.model_id === "V2";
  setV2Visibility(isV2);
  if (isV2) loadV2Workspace();
}

async function loadModelRegistry() {
  try {
    const payload = await api("/api/model-versions");
    state.models = Array.isArray(payload.model_records) ? payload.model_records : [];
    if (!state.models.length) throw new Error("No model records were returned.");
    const selector = byId("result-model"); selector.replaceChildren();
    state.models.forEach((model) => {
      const option = document.createElement("option"); option.value = model.model_id;
      option.textContent = `${model.model_id} - ${registryValue(model.name, "Unnamed model")}`; selector.append(option);
    });
    const requested = new URLSearchParams(window.location.search).get("model")?.toUpperCase();
    selector.value = state.models.some((model) => model.model_id === requested) ? requested : "V2";
    if (!selector.value) selector.value = state.models[0].model_id;
    selector.disabled = false;
    byId("model-registry-status").textContent = `${state.models.length} frozen model records loaded. Select a version to change this view.`;
    renderSelectedModel(state.models.find((model) => model.model_id === selector.value), payload.ranking?.warning || payload.warnings?.[0]);
  } catch (error) {
    byId("model-registry-status").textContent = `Could not load model versions: ${error.message}`;
    byId("selected-model-task").textContent = "The model registry is unavailable, so no model metrics are being shown.";
    byId("selected-model-metrics").replaceChildren();
    byId("selected-model-warnings").replaceChildren();
  }
}

async function loadV2Workspace() {
  if (state.v2Loaded || state.v2Loading) return;
  state.v2Loading = true;
  const [available] = await Promise.all([loadSummary(), loadAI(), loadV5()]);
  if (available) await loadList();
  state.v2Loaded = true; state.v2Loading = false;
}

function renderSummary(summary) {
  const list = byId("prediction-summary"); list.replaceChildren();
  [
    ["Resolved changed records", summary.resolved_direction_records.toLocaleString(), "Safely matched older VUS records with a clear pathogenic or benign newer outcome."],
    ["Actual pathogenic", summary.actual_pathogenic.toLocaleString(), "Cohort records that became pathogenic or likely pathogenic."],
    ["Actual benign", summary.actual_benign.toLocaleString(), "Cohort records that became benign or likely benign."],
    ["Predictions made", summary.predictions_made.toLocaleString(), "Records with at least one directional clue."],
    ["No prediction", summary.no_prediction.toLocaleString(), "Records without enough directional clue information."],
    ["Correct", summary.correct.toLocaleString(), "Directional prediction matched a scorable 2024 outcome."],
    ["Wrong", summary.wrong.toLocaleString(), "Directional prediction did not match a scorable 2024 outcome."],
    ["Overall accuracy", percent(summary.overall_accuracy), "Correct divided by correct plus wrong."],
    ["Balanced accuracy", percent(summary.balanced_accuracy), "Average recall across pathogenic and benign outcomes."],
    ["Pathogenic precision", percent(summary.pathogenic_direction_precision), "Among scorable pathogenic-direction predictions, the fraction actually pathogenic direction."],
    ["Benign precision", percent(summary.benign_direction_precision), "Among scorable benign-direction predictions, the fraction actually benign direction."],
    ["Pathogenic recall", percent(summary.pathogenic_direction_recall), "Fraction of actual pathogenic outcomes predicted pathogenic."],
    ["Benign recall", percent(summary.benign_direction_recall), "Fraction of actual benign outcomes predicted benign."],
    ["Formula version", summary.scoring_version, "Frozen scoring rule version."],
  ].forEach((item) => addMetric(list, ...item));
}

async function loadSummary() {
  try {
    const payload = await api("/api/predictions/summary"); renderFormula(payload.formula, payload.parent_formula);
    if (!payload.available) { byId("run-status").textContent = payload.message; byId("list-status").textContent = payload.message; return false; }
    renderSummary(payload.summary); byId("run-status").textContent = `Saved ${payload.summary.mode} run completed ${payload.summary.completed_at_utc}.`;
    return true;
  } catch (error) { byId("run-status").textContent = `Could not load results: ${error.message}`; return false; }
}

function resultSymbol(result) { return result === "Correct" ? "[OK]" : result === "Wrong" ? "[X]" : result === "Not Scorable" ? "[?]" : "[-]"; }
function resultCard(row) {
  const article = document.createElement("article"); article.className = `prediction-card result-${row.result.replaceAll(" ", "-").toLowerCase()}`;
  const heading = document.createElement("div"); heading.className = "prediction-card-heading";
  const title = document.createElement("strong"); title.textContent = `${resultSymbol(row.result)} Variation ${row.variation_id} | ${display(row.old_gene_symbols)}`;
  const label = document.createElement("span"); label.textContent = row.result; heading.append(title, label);
  const grid = document.createElement("dl"); grid.className = "prediction-card-grid";
  [["2022", row.old_classification], ["Prediction", direction(row.predicted_direction)], ["Score", Number(row.total_score) > 0 ? `+${row.total_score}` : row.total_score], ["2024", row.new_classification], ["Confidence", row.confidence], ["Manual review", row.manual_review_status]].forEach(([term, value]) => { const box = document.createElement("div"); const dt = document.createElement("dt"); dt.textContent = term; const dd = document.createElement("dd"); dd.textContent = display(value); box.append(dt, dd); grid.append(box); });
  const button = document.createElement("button"); button.type = "button"; button.textContent = "Open complete calculation"; button.addEventListener("click", () => loadDetail(row.variation_id));
  article.append(heading, grid, button); return article;
}

async function loadList() {
  const params = new URLSearchParams({query: byId("prediction-query").value.trim(), filter: state.filter, sort: byId("prediction-sort").value, page: String(state.page), page_size: "50"});
  try {
    const payload = await api(`/api/predictions?${params}`); state.pageCount = Math.max(1, payload.page_count);
    byId("prediction-list").replaceChildren(...payload.rows.map(resultCard));
    byId("list-status").textContent = `${payload.total.toLocaleString()} matching results.`; byId("prediction-page").textContent = `Page ${payload.page} of ${state.pageCount}`;
    byId("prediction-previous").disabled = state.page <= 1; byId("prediction-next").disabled = state.page >= state.pageCount;
  } catch (error) { byId("list-status").textContent = `Prediction list unavailable: ${error.message}`; byId("prediction-list").replaceChildren(); }
}

function definition(container, label, value) { const box = document.createElement("div"); const strong = document.createElement("strong"); strong.textContent = label; const span = document.createElement("span"); span.textContent = display(value); box.append(strong, span); container.append(box); }

async function loadDetail(id) {
  state.selectedId = id; const section = byId("prediction-detail"); section.hidden = false; section.scrollIntoView({behavior: "smooth"});
  try {
    const row = await api(`/api/predictions/${id}`); byId("prediction-detail-title").textContent = `Variation ID ${id}`;
    const identity = byId("prediction-identity"); identity.replaceChildren();
    [["Allele ID", row.old_allele_ids], ["Gene", row.old_gene_symbols], ["HGVS / name", row.old_names], ["Coordinates", row.old_coordinates], ["Conditions", row.old_phenotypes], ["Match method", row.match_method], ["Match confidence", row.match_confidence], ["VCV", row.vcv_note]].forEach((item) => definition(identity, ...item));
    const timeline = byId("prediction-timeline"); timeline.replaceChildren();
    [[row.old_release_date, "Older snapshot", row.old_classification, `ClinVar LastEvaluated field - not the snapshot date: ${display(row.old_last_evaluated)}`], ["Prediction", direction(row.predicted_direction), `Score ${row.total_score > 0 ? "+" : ""}${row.total_score}`, row.scoring_version], [row.new_release_date, "Newer snapshot", row.new_classification, `ClinVar LastEvaluated field - not the snapshot date: ${display(row.new_last_evaluated)}`], ["Result", `${resultSymbol(row.result)} ${row.result}`, row.result_reason_code, "Directional comparison"]].forEach((values) => { const card = document.createElement("article"); values.forEach((value, index) => { const item = document.createElement(index === 0 ? "small" : index === 1 ? "h3" : "p"); item.textContent = display(value); card.append(item); }); timeline.append(card); });
    const clues = byId("clue-calculation"); clues.replaceChildren(); row.clues.forEach((clue) => { const tr = document.createElement("tr"); [clue.clue.replaceAll("_", " "), clue.older_value, clue.points > 0 ? `+${clue.points}` : clue.points, clue.explanation, clue.source_field, clue.available ? clue.applied ? "Available and used" : "Available, not applied" : "Missing"].forEach((value) => { const td = document.createElement("td"); td.textContent = display(value); tr.append(td); }); clues.append(tr); });
    byId("prediction-arithmetic").textContent = `${row.arithmetic}. Binary threshold applied: +1 or higher pathogenic; -1 or lower benign; 0 no prediction. Therefore prediction = ${direction(row.predicted_direction)}.`;
    const comparison = byId("actual-comparison"); comparison.replaceChildren(); [["Original 2024 text", row.new_classification], ["Normalized outcome", row.outcome_group], ["Normalization rule", row.outcome_rule], ["Directional result", row.result]].forEach((item) => definition(comparison, ...item));
    const warnings = [...row.warnings, ...row.match_warnings]; byId("prediction-warnings").replaceChildren(...(warnings.length ? warnings : ["No automatic warnings recorded."]).map((text) => { const p = document.createElement("p"); p.textContent = text; return p; }));
    byId("prediction-review-status").textContent = `Manual status: ${display(row.manual_review.status, "unreviewed")}`;
    const links = byId("prediction-source-links"); links.replaceChildren(); [[`https://www.ncbi.nlm.nih.gov/clinvar/variation/${id}/`, "Open Official ClinVar Page"], ["/historical_variants.html", "Open Two-Snapshot Timeline"], ["/version_history.html", "Open VCV Version History"]].forEach(([href, text]) => { const link = document.createElement("a"); link.href = href; link.textContent = text; if (href.startsWith("http")) { link.target = "_blank"; link.rel = "noreferrer"; } links.append(link); });
  } catch (error) { byId("prediction-review-status").textContent = `Could not load explanation: ${error.message}`; }
}

async function saveReview(status) {
  if (!state.selectedId) return;
  try { const payload = await api(`/api/predictions/${state.selectedId}/review`, {method: "PATCH", body: JSON.stringify({status, note: byId("prediction-review-note").value})}); byId("prediction-review-status").textContent = `Manual status saved: ${payload.review.status}`; byId("prediction-review-note").value = ""; }
  catch (error) { byId("prediction-review-status").textContent = `Review not saved: ${error.message}`; }
}

function renderProgress(operation) { const list = byId("run-progress"); list.replaceChildren(...(operation.progress_events || []).map((event) => { const li = document.createElement("li"); li.textContent = `${event.stage.replaceAll("_", " ")}${event.count ? `: ${Number(event.count).toLocaleString()}` : ""}`; return li; })); }
async function pollRun() { const operation = await api(`/api/predictions/operations/${state.operationId}`); renderProgress(operation); if (operation.state === "running") { window.setTimeout(pollRun, 750); return; } byId("run-status").textContent = operation.error ? `Run failed: ${operation.error}` : "Resolved Direction V2 run completed."; byId("run-predictions").disabled = false; await loadSummary(); await loadList(); }
async function runPredictions() { try { byId("run-predictions").disabled = true; const payload = await api("/api/predictions/run", {method: "POST", body: JSON.stringify({approved: true, scoring_version: "Resolved Direction V2"})}); state.operationId = payload.operation_id; byId("run-status").textContent = "Frozen changed-outcome Version 2 run started."; pollRun(); } catch (error) { byId("run-status").textContent = `Could not start: ${error.message}`; byId("run-predictions").disabled = false; } }

function renderAI(summary) {
  const list = byId("ai-v4-summary"); list.replaceChildren();
  [["Training records", summary.training_records], ["Hidden test records", summary.hidden_test_records], ["Quarantined related records", summary.quarantined_records], ["Older-only hints", summary.feature_count]].forEach(([label, value]) => addMetric(list, label, Number(value).toLocaleString(), "Frozen AI Holdout V4 design."));
  if (summary.state === "tested") {
    [["Correct", summary.correct], ["Wrong", summary.wrong], ["Accuracy", percent(summary.accuracy)], ["Balanced accuracy", percent(summary.balanced_accuracy)]].forEach(([label, value]) => addMetric(list, label, value, "Result on exactly 100 records held out from V4 fitting."));
    byId("ai-v4-status").textContent = `Hidden test completed: ${summary.correct} of 100 correct (${percent(summary.accuracy)} accuracy).`;
    byId("ai-v4-test").disabled = true;
    byId("ai-v4-approval").disabled = true;
  } else {
    byId("ai-v4-status").textContent = "Model trained. The 100-record hidden test has not been opened.";
  }
}
async function loadAI() { try { const summary = await api("/api/ai-v4/summary"); if (!summary.available) { byId("ai-v4-status").textContent = "AI Holdout V4 has not been trained yet."; return; } renderAI(summary); } catch (error) { byId("ai-v4-status").textContent = `AI status unavailable: ${error.message}`; } }
async function testAI() { try { byId("ai-v4-test").disabled = true; byId("ai-v4-status").textContent = "Testing the trained model on 100 unseen records..."; await api("/api/ai-v4/test", {method: "POST", body: JSON.stringify({approved: true})}); await loadAI(); } catch (error) { byId("ai-v4-status").textContent = `AI test failed: ${error.message}`; } }

function renderV5(summary) {
  const list = byId("ai-v5-summary"); list.replaceChildren();
  [["Unique training records", summary.training_records], ["Balanced training rows", summary.effective_balanced_training_rows], ["Held-out test records", summary.hidden_test_records], ["Quarantined records", summary.quarantined_records], ["Older-only inputs", summary.feature_count]].forEach(([label, value]) => addMetric(list, label, Number(value).toLocaleString(), "Frozen AI Holdout V5 design."));
  if (summary.state === "tested") {
    [["Correct", summary.correct], ["Wrong", summary.wrong], ["Accuracy", percent(summary.accuracy)], ["Balanced accuracy", percent(summary.balanced_accuracy)]].forEach(([label, value]) => addMetric(list, label, value, "V5 result on its own 100-record held-out cohort."));
    byId("ai-v5-status").textContent = `Held-out test completed: ${summary.correct} of 100 correct (${percent(summary.accuracy)} accuracy; ${percent(summary.balanced_accuracy)} balanced accuracy).`;
    byId("ai-v5-test").disabled = true; byId("ai-v5-approval").disabled = true;
  } else { byId("ai-v5-status").textContent = "V5 trained. Its fresh 100-record test has not been opened."; }
}
async function loadV5() { try { const summary = await api("/api/ai-v5/summary"); if (!summary.available) { byId("ai-v5-status").textContent = "AI Holdout V5 has not been trained yet."; return; } renderV5(summary); } catch (error) { byId("ai-v5-status").textContent = `V5 status unavailable: ${error.message}`; } }
async function testV5() { try { byId("ai-v5-test").disabled = true; byId("ai-v5-status").textContent = "Testing V5 on 100 fresh records..."; await api("/api/ai-v5/test", {method: "POST", body: JSON.stringify({approved: true})}); await loadV5(); } catch (error) { byId("ai-v5-status").textContent = `V5 test failed: ${error.message}`; } }

byId("toggle-formula").addEventListener("click", () => { byId("formula-content").hidden = !byId("formula-content").hidden; });
byId("result-model").addEventListener("change", (event) => {
  const model = state.models.find((item) => item.model_id === event.target.value);
  if (!model) return;
  const url = new URL(window.location.href); url.searchParams.set("model", model.model_id); window.history.replaceState({}, "", url);
  renderSelectedModel(model, byId("model-comparison-warning").textContent);
});
byId("formula-approval").addEventListener("change", (event) => { byId("run-predictions").disabled = !event.target.checked; });
byId("run-predictions").addEventListener("click", runPredictions); byId("refresh-predictions").addEventListener("click", async () => { await loadSummary(); await loadList(); });
byId("ai-v4-approval").addEventListener("change", (event) => { byId("ai-v4-test").disabled = !event.target.checked; }); byId("ai-v4-test").addEventListener("click", testAI);
byId("ai-v5-approval").addEventListener("change", (event) => { byId("ai-v5-test").disabled = !event.target.checked; }); byId("ai-v5-test").addEventListener("click", testV5);
byId("prediction-search").addEventListener("submit", (event) => { event.preventDefault(); state.page = 1; loadList(); }); byId("prediction-sort").addEventListener("change", () => { state.page = 1; loadList(); });
byId("prediction-filters").addEventListener("click", (event) => { if (!event.target.dataset.filter) return; state.filter = event.target.dataset.filter; state.page = 1; document.querySelectorAll("#prediction-filters button").forEach((button) => button.classList.toggle("active", button === event.target)); loadList(); });
byId("prediction-previous").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; loadList(); } }); byId("prediction-next").addEventListener("click", () => { if (state.page < state.pageCount) { state.page += 1; loadList(); } });
byId("close-prediction-detail").addEventListener("click", () => { byId("prediction-detail").hidden = true; }); document.querySelectorAll("[data-review]").forEach((button) => button.addEventListener("click", () => saveReview(button.dataset.review)));

loadModelRegistry();
