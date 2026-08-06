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

loadV9Status();
loadV9Exploration();
