"use strict";

const byId = (id) => document.getElementById(id);

function addMetric(container, label, value) {
  const box = document.createElement("div");
  const term = document.createElement("dt"); term.textContent = label;
  const detail = document.createElement("dd"); detail.textContent = String(value);
  box.append(term, detail); container.append(box);
}

async function loadV9Status() {
  const status = byId("v9-status");
  if (!status) return;
  try {
    const response = await fetch("/api/v9/dataset-summary", {headers: {Accept: "application/json"}});
    const manifest = await response.json();
    if (!response.ok) throw new Error(manifest.error || `Request failed (${response.status})`);
    status.textContent = manifest.artifacts_stale
      ? `${manifest.headline} ${manifest.stale_reasons.join("; ")}. Rerun scripts/build_v9_dataset.py.`
      : manifest.headline;
    const metrics = byId("v9-metrics");
    if (metrics) {
      metrics.replaceChildren();
      [["Records considered", manifest.number_records_considered], ["Messy dataset", manifest.number_included_messy], ["Clean reviewed dataset", manifest.number_included_clean], ["Excluded or pending", manifest.number_excluded], ["Needs expert review", manifest.number_needing_expert_review], ["Corrected labels", manifest.number_corrected], ["Leakage audit", manifest.leakage_audit_status], ["Final V9 allowed", manifest.final_test_allowed ? "Yes" : "No"]].forEach(([label, value]) => addMetric(metrics, label, value));
    }
    const warnings = byId("v9-warnings");
    if (warnings) warnings.replaceChildren(...manifest.warnings.map((text) => { const item = document.createElement("p"); item.textContent = text; return item; }));
    const gate = byId("v9-gate");
    if (gate) {
      gate.replaceChildren(...Object.entries(manifest.manual_review_minimum.checks).map(([name, passed]) => {
        const item = document.createElement("li"); item.textContent = `${passed ? "Complete" : "Pending"}: ${name.replaceAll("_", " ")}`; return item;
      }));
    }
  } catch (error) { status.textContent = `V9 preparation status unavailable: ${error.message}`; }
}

function percent(value) { return `${(100 * value).toFixed(2)}%`; }

async function loadV9Exploration() {
  const tableBody = byId("v9-candidate-rows");
  if (!tableBody) return;
  const note = byId("v9-exploratory-status");
  try {
    const response = await fetch("/api/v9/exploratory-summary", {headers: {Accept: "application/json"}});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.stale_reasons?.join("; ") || payload.error || `Request failed (${response.status})`);
    const labels = {
      frozen_v8_reference: "Frozen V8 reference",
      elastic_net_logistic: "Elastic-net logistic",
      hist_gradient_boosting: "Histogram gradient boosting",
      extra_trees: "Extra Trees",
      consequence_only: "Consequence only",
      majority: "Majority"
    };
    const order = ["frozen_v8_reference", "elastic_net_logistic", "hist_gradient_boosting", "extra_trees", "consequence_only", "majority"];
    tableBody.replaceChildren(...order.map((name) => {
      const metric = payload.metrics[name];
      const row = document.createElement("tr");
      [labels[name], percent(metric.component_weighted_balanced_accuracy), percent(metric.balanced_accuracy), percent(metric.macro_f1), metric.brier_score.toFixed(4), `${metric.confusion_matrix.TN} / ${metric.confusion_matrix.FP} / ${metric.confusion_matrix.FN} / ${metric.confusion_matrix.TP}`].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
      return row;
    }));
    const interval = payload.bootstrap.paired_difference_from_frozen_v8_95_percent.elastic_net_logistic;
    note.textContent = payload.artifacts_stale
      ? `Exploratory artifacts are stale: ${payload.stale_reasons.join("; ")}.`
      : `Elastic net led the new candidate families, but frozen V8 had the higher point estimate. The paired component-bootstrap interval for elastic net minus V8 was ${percent(interval[0])} to ${percent(interval[1])}, so I cannot claim an improvement.`;
  } catch (error) { note.textContent = `Exploratory results unavailable: ${error.message}`; }
}

function metricPercent(value) {
  return percent(Number(value));
}

async function fetchV91Summary() {
  const response = await fetch("/api/v9-1/summary", {headers: {Accept: "application/json"}});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

async function loadV91Search() {
  const tableBody = byId("v9-1-candidate-rows");
  if (!tableBody) return;
  const status = byId("v9-1-search-status");
  try {
    const payload = await fetchV91Summary();
    status.textContent = `Authenticated fully nested procedure over ${payload.manifest.dataset_records} opened records and ${payload.manifest.dataset_components} components. The full-development artifact selected ${payload.manifest.full_development_selected_family.replaceAll("_", " ")}; it has no independent test score.`;
    tableBody.replaceChildren(...payload.candidates.map((metric) => {
      const row = document.createElement("tr");
      const statusLabel = metric.status === "invalid_protocol_mismatch_not_ranked" ? "Invalid, excluded" : metric.status.replaceAll("_", " ");
      [metric.candidate.replaceAll("_", " "), statusLabel, metric.component_weighted_balanced_accuracy ? metricPercent(metric.component_weighted_balanced_accuracy) : "Not ranked", metric.macro_f1 ? metricPercent(metric.macro_f1) : "-", metric.pathogenic_recall ? metricPercent(metric.pathogenic_recall) : "-", metric.brier_score ? Number(metric.brier_score).toFixed(4) : "-"].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
      return row;
    }));
    const ablations = byId("v9-1-ablation-rows");
    ablations.replaceChildren(...payload.feature_ablation.map((metric) => {
      const row = document.createElement("tr");
      [metric.feature_set.replaceAll("_", " "), metric.feature_count || "Not fit", metric.component_weighted_balanced_accuracy ? metricPercent(metric.component_weighted_balanced_accuracy) : "-", metric.balanced_accuracy ? metricPercent(metric.balanced_accuracy) : "-", metric.accuracy ? metricPercent(metric.accuracy) : "-"].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
      return row;
    }));
  } catch (error) {
    status.textContent = `V9.1 search unavailable: ${error.message}`;
  }
}

async function loadV91Results() {
  const metrics = byId("v9-1-metrics");
  if (!metrics) return;
  const status = byId("v9-1-result-status");
  try {
    const payload = await fetchV91Summary();
    const selected = payload.selected;
    status.textContent = "Internal development complete; official model false; final test evaluated false.";
    metrics.replaceChildren();
    [["Component-weighted BA", metricPercent(selected.component_weighted_balanced_accuracy)], ["Balanced accuracy", metricPercent(selected.balanced_accuracy)], ["Accuracy", metricPercent(selected.accuracy)], ["Macro F1", metricPercent(selected.macro_f1)], ["Pathogenic recall", metricPercent(selected.pathogenic_recall)], ["Benign recall", metricPercent(selected.benign_recall)], ["Brier score", Number(selected.brier_score).toFixed(4)]].forEach(([label, value]) => addMetric(metrics, label, value));
    const confusion = payload.confusion_matrix;
    byId("v9-1-confusion").textContent = `Confusion matrix: TN ${confusion.TN}, FP ${confusion.FP}, FN ${confusion.FN}, TP ${confusion.TP}.`;
    const comparisons = byId("v9-1-comparison-rows");
    comparisons.replaceChildren(...payload.comparisons.slice(0, 4).map((metric) => {
      const row = document.createElement("tr");
      [metric.model.replaceAll("_", " "), metricPercent(metric.component_weighted_balanced_accuracy), metricPercent(metric.balanced_accuracy), metricPercent(metric.accuracy), metricPercent(metric.macro_f1), metricPercent(metric.pathogenic_recall), metricPercent(metric.benign_recall)].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
      return row;
    }));
    const intervals = payload.bootstrap.selected_v9_1_paired_component_weighted_balanced_accuracy_difference;
    byId("v9-1-interval-note").textContent = `Paired 95% intervals: V9.1 minus original V9 ${metricPercent(intervals.original_v9[0])} to ${metricPercent(intervals.original_v9[1])}; V9.1 minus frozen V8 ${metricPercent(intervals.frozen_v8[0])} to ${metricPercent(intervals.frozen_v8[1])}. Both cross zero.`;
  } catch (error) {
    status.textContent = `V9.1 results unavailable: ${error.message}`;
  }
}

let v91CasePage = 1;

async function loadV91Cases() {
  const tableBody = byId("v9-1-case-rows");
  if (!tableBody) return;
  const parameters = new URLSearchParams({
    q: byId("v9-1-query").value,
    correctness: byId("v9-1-correctness").value,
    family: byId("v9-1-family").value,
    disagreement: byId("v9-1-disagreement").value,
    page: String(v91CasePage),
    page_size: "24"
  });
  const status = byId("v9-1-case-status");
  try {
    const response = await fetch(`/api/v9-1/cases?${parameters}`, {headers: {Accept: "application/json"}});
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    status.textContent = `${payload.total} internal out-of-fold cases match. ${payload.warning}`;
    tableBody.replaceChildren(...payload.items.map((item) => {
      const row = document.createElement("tr");
      [`${item.variation_id} / ${item.gene || "No gene"}`, item.actual_outcome.replaceAll("_", " "), `${item.v9_1_prediction.replaceAll("_", " ")} (${item.v9_1_correct === "True" ? "correct" : "wrong"})`, metricPercent(item.v9_1_probability), item.v9_1_outer_selected_family.replaceAll("_", " "), `${item.original_v9_prediction.replaceAll("moved_toward_", "")} / ${item.v8_prediction.replaceAll("moved_toward_", "")}`, item.review_state.replaceAll("_", " ")].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); });
      return row;
    }));
    byId("v9-1-page").textContent = `Page ${payload.page} of ${payload.pages}`;
    byId("v9-1-previous").disabled = payload.page <= 1;
    byId("v9-1-next").disabled = payload.page >= payload.pages;
  } catch (error) {
    status.textContent = `V9.1 cases unavailable: ${error.message}`;
  }
}

function initializeV91CaseControls() {
  if (!byId("v9-1-case-rows")) return;
  ["v9-1-query", "v9-1-correctness", "v9-1-family", "v9-1-disagreement"].forEach((id) => byId(id).addEventListener("input", () => { v91CasePage = 1; loadV91Cases(); }));
  byId("v9-1-previous").addEventListener("click", () => { v91CasePage -= 1; loadV91Cases(); });
  byId("v9-1-next").addEventListener("click", () => { v91CasePage += 1; loadV91Cases(); });
  loadV91Cases();
}

loadV9Status();
loadV9Exploration();
loadV91Search();
loadV91Results();
initializeV91CaseControls();
