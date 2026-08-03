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

loadV9Status();
