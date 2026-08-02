"use strict";

const byId = (id) => document.getElementById(id);
const percent = (value, digits = 2) => `${(Number(value) * 100).toFixed(digits)}%`;
const safe = (value, fallback = "Not recorded") => {
  if (["string", "number", "boolean"].includes(typeof value)) return String(value);
  return fallback;
};

async function getJson(path) {
  const response = await fetch(path, {headers: {Accept: "application/json"}});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function addMetric(container, label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = value;
  wrapper.append(term, detail);
  container.append(wrapper);
}

function officialClinvarUrl(item) {
  const fallback = `https://www.ncbi.nlm.nih.gov/clinvar/variation/${encodeURIComponent(safe(item.variation_id))}/`;
  try {
    const candidate = new URL(item.source_links?.[0]?.url || fallback);
    if (candidate.protocol === "https:" && candidate.hostname === "www.ncbi.nlm.nih.gov" && candidate.pathname.startsWith("/clinvar/variation/")) {
      return candidate.href;
    }
  } catch (_) {
    // Use the deterministic official URL below.
  }
  return fallback;
}

function renderSummary(summary) {
  const metrics = byId("v8-metrics");
  metrics.replaceChildren();
  addMetric(metrics, "Model type", safe(summary.model_type));
  addMetric(metrics, "Test size", Number(summary.n).toLocaleString());
  addMetric(metrics, "Accuracy", percent(summary.accuracy, 1));
  addMetric(metrics, "Balanced accuracy", percent(summary.balanced_accuracy));
  addMetric(metrics, "Macro F1", percent(summary.macro_f1));
  addMetric(metrics, "Benign-direction recall", percent(summary.recalls.benign));
  addMetric(metrics, "Pathogenic-direction recall", percent(summary.recalls.pathogenic));
  addMetric(metrics, "Wrong predictions", Number(summary.wrong).toLocaleString());
  byId("v8-audit").textContent = `Leakage audit: ${safe(summary.leakage_audit.status)}`;
  byId("strongest-claim").textContent = safe(summary.strongest_claim);
  const caveats = byId("v8-caveats");
  caveats.replaceChildren(...summary.caveats.map((value) => {
    const item = document.createElement("li");
    item.textContent = safe(value);
    return item;
  }));
  byId("v8-status").textContent = "Frozen public summary loaded.";

  const paired = byId("v7-comparison");
  paired.replaceChildren();
  addMetric(paired, "V7 accuracy", percent(summary.v7_same_record.accuracy, 1));
  addMetric(paired, "V7 balanced accuracy", percent(summary.v7_same_record.balanced_accuracy));
  addMetric(paired, "V8 minus V7", `${(summary.v7_same_record.v8_minus_v7_balanced_accuracy * 100).toFixed(2)} percentage points`);
  addMetric(paired, "95% component-bootstrap interval", `${(summary.v7_same_record.paired_difference_95_percent[0] * 100).toFixed(2)} to +${(summary.v7_same_record.paired_difference_95_percent[1] * 100).toFixed(2)} points`);
}

function caseCard(item) {
  const article = document.createElement("article");
  article.className = "case-study-card";
  const heading = document.createElement("h3");
  heading.textContent = `${safe(item.confusion_group)} | ${safe(item.gene)} | Variation ${safe(item.variation_id)}`;
  const facts = document.createElement("dl");
  facts.className = "case-study-facts";
  addMetric(facts, "VCV accession", safe(item.vcv_accession));
  addMetric(facts, "Older classification", safe(item.old_classification));
  addMetric(facts, "Later classification", safe(item.later_classification));
  addMetric(facts, "V8 prediction", safe(item.predicted_direction).replaceAll("_", " "));
  addMetric(facts, "Actual later direction", safe(item.actual_direction).replaceAll("_", " "));
  addMetric(facts, "Pathogenic-direction probability", percent(item.v8_probability));
  addMetric(facts, "Model confidence", percent(item.confidence, 1));
  addMetric(facts, "Correct", item.correct ? "Yes" : "No");
  addMetric(facts, "Consequence", safe(item.consequence));
  addMetric(facts, "Key features", safe(item.key_features));
  addMetric(facts, "Match confidence", safe(item.match_confidence));
  addMetric(facts, "Source review status", safe(item.review_status));
  addMetric(facts, "Manual review", safe(item.manual_status));
  addMetric(facts, "Warnings", Array.isArray(item.warnings) ? item.warnings.join(" ") : safe(item.warnings));
  const link = document.createElement("a");
  link.href = officialClinvarUrl(item);
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Official ClinVar variation";
  article.append(heading, facts, link);
  return article;
}

function renderCases(payload) {
  const container = byId("case-study-groups");
  container.replaceChildren();
  const labels = {TN: "True negatives", FP: "False positives", FN: "False negatives", TP: "True positives"};
  ["TN", "FP", "FN", "TP"].forEach((group) => {
    const section = document.createElement("section");
    section.className = `case-study-group confusion-${group.toLowerCase()}`;
    const title = document.createElement("h3");
    const cases = payload.case_studies.filter((item) => item.confusion_group === group);
    title.textContent = `${group}: ${labels[group]} (${cases.length})`;
    const grid = document.createElement("div");
    grid.className = "case-study-grid";
    grid.append(...cases.map(caseCard));
    section.append(title, grid);
    container.append(section);
  });
}

Promise.all([getJson("/api/v8/summary"), getJson("/api/v8/case-studies")])
  .then(([summary, cases]) => { renderSummary(summary); renderCases(cases); })
  .catch((error) => { byId("v8-status").textContent = `Could not load V8 presentation data: ${error.message}`; });
