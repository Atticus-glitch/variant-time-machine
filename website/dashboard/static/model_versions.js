"use strict";

const byId = (id) => document.getElementById(id);
const pct = (value) => typeof value === "number" && Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "Not recorded";
const shown = (value) => {
  if (value === null || value === undefined || value === "unknown/not recorded") return "Not recorded";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "Not recorded";
  if (typeof value === "string" || typeof value === "boolean") return String(value);
  return "Not recorded";
};

const readableLabel = (value) => value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());

function evidenceRows(container, value, path = "") {
  if (Array.isArray(value)) {
    value.forEach((item, index) => evidenceRows(container, item, `${path} ${index + 1}`.trim()));
    return;
  }
  if (value && typeof value === "object") {
    Object.entries(value).forEach(([key, item]) => evidenceRows(container, item, `${path} ${readableLabel(key)}`.trim()));
    return;
  }
  metric(container, path || "Evidence", shown(value));
}

function presentationSanityCheck(root = document) {
  const rendered = root.body?.textContent || root.textContent || "";
  const forbidden = ["[object " + "Object]", "un" + "defined", "N" + "aN"];
  if (forbidden.some((sentinel) => rendered.includes(sentinel))) {
    throw new Error("Unsafe model presentation sentinel detected.");
  }
  return true;
}

function metric(container, label, value) { const box = document.createElement("div"); const term = document.createElement("dt"); const detail = document.createElement("dd"); term.textContent = label; detail.textContent = value; box.append(term, detail); container.append(box); }

function modelCard(model) {
  const card = document.createElement("article"); card.className = "prediction-card model-version-card";
  const heading = document.createElement("div"); heading.className = "prediction-card-heading"; const title = document.createElement("strong"); title.textContent = `${model.model_id}: ${model.name}`; const badge = document.createElement("span"); badge.textContent = model.effective_status; heading.append(title, badge);
  const metrics = document.createElement("dl"); metrics.className = "prediction-card-grid";
  metric(metrics, "Model type", model.model_type); metric(metrics, "Test size", shown(model.test_records)); metric(metrics, "Accuracy", pct(model.metrics.accuracy)); metric(metrics, "Balanced accuracy", pct(model.metrics.balanced_accuracy)); metric(metrics, "Macro F1", pct(model.metrics.macro_f1)); metric(metrics, "Leakage audit", model.leakage_audit_status); metric(metrics, "Created", shown(model.date_created)); metric(metrics, "Manual review", model.manual_review_status);
  const note = document.createElement("p"); note.className = "plain-language-note"; note.textContent = model.warnings.filter((warning) => warning !== "unknown/not recorded").join(" ") || "No additional recorded note.";
  card.append(heading, metrics, note); return card;
}

function confusion(model) { const matrix = model.confusion_matrix; if (!matrix || !matrix.actual_benign) return "Not recorded"; return `TN ${matrix.actual_benign.predicted_benign}, FP ${matrix.actual_benign.predicted_pathogenic}, FN ${matrix.actual_pathogenic.predicted_benign}, TP ${matrix.actual_pathogenic.predicted_pathogenic}`; }

function renderComparison(models, baselines) {
  const byVersion = Object.fromEntries(models.map((model) => [model.model_id, model]));
  const grid = document.createElement("dl"); grid.className = "prediction-summary-grid";
  ["V4", "V5", "V6", "V7", "V8"].forEach((modelId) => {
    const model = byVersion[modelId];
    if (!model) return;
    metric(grid, `${modelId} test`, `${shown(model.test_records)} records`);
    metric(grid, `${modelId} accuracy`, pct(model.metrics.accuracy));
    metric(grid, `${modelId} balanced accuracy`, pct(model.metrics.balanced_accuracy));
    metric(grid, `${modelId} benign recall`, pct(model.metrics.benign_recall));
    metric(grid, `${modelId} pathogenic recall`, pct(model.metrics.pathogenic_recall));
    metric(grid, `${modelId} confusion`, confusion(model));
  });
  metric(grid, "V8 vs same-record V7", "+0.4524 balanced-accuracy points; component-bootstrap CI -2.45 to +3.31; no overall superiority");
  metric(grid, "Missense subset", "n=230; V8 63.82% vs V7 55.88% balanced accuracy; paired CI includes zero");
  byId("version-comparison").replaceChildren(grid);
  const table = document.createElement("table"); const head = document.createElement("thead"); head.innerHTML = "<tr><th>Test cohort</th><th>Model/baseline</th><th>Records</th><th>Accuracy</th><th>Balanced accuracy</th><th>Benign recall</th><th>Pathogenic recall</th><th>Coverage</th><th>Provenance</th></tr>"; const body = document.createElement("tbody"); baselines.forEach((row) => { const tr = document.createElement("tr"); [row.test_set, row.model, row.records, pct(Number(row.accuracy)), pct(Number(row.balanced_accuracy)), pct(Number(row.benign_recall)), pct(Number(row.pathogenic_recall)), pct(Number(row.coverage)), row.provenance].forEach((value) => { const td = document.createElement("td"); td.textContent = value; tr.append(td); }); tr.title = row.warning; body.append(tr); }); table.append(head, body); byId("baseline-comparison").replaceChildren(table);
}

async function loadModels() { try { const response = await fetch("/api/model-versions", {headers: {Accept: "application/json"}}); const payload = await response.json(); if (!response.ok) throw new Error(shown(payload.error)); byId("model-registry").replaceChildren(...payload.model_records.map(modelCard)); byId("registry-status").textContent = `${payload.model_records.length} frozen model records loaded.`; renderComparison(payload.model_records, payload.baseline_comparisons); const ranking = byId("model-ranking"); const conclusion = document.createElement("h3"); conclusion.textContent = shown(payload.ranking.conclusion); const evidence = document.createElement("dl"); evidence.className = "evidence-summary-list"; evidenceRows(evidence, payload.ranking.evidence_summary); const criteria = document.createElement("p"); criteria.textContent = `Compared by ${payload.ranking.criteria.map(shown).join(", ")}; no total ranking is assigned across different evaluations.`; const warning = document.createElement("p"); warning.className = "plain-language-note"; warning.textContent = shown(payload.ranking.warning); ranking.replaceChildren(conclusion, evidence, criteria, warning); presentationSanityCheck(); } catch (error) { byId("registry-status").textContent = `Could not load model registry: ${shown(error.message)}`; } }

loadModels();
