"use strict";

const byId = (id) => document.getElementById(id);
const DECISIONS = [
  "match correct",
  "match ambiguous",
  "classification-scope problem",
  "model genuinely wrong",
  "exclude from final analysis",
];
let currentPage = 1;

async function getJson(path, options = {}) {
  const response = await fetch(path, {headers: {Accept: "application/json", "Content-Type": "application/json"}, ...options});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function display(value, fallback = "Not recorded") {
  return typeof value === "string" && value.trim() ? value : fallback;
}

function detail(label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = display(value);
  wrapper.append(term, description);
  return wrapper;
}

async function saveReview(row, decision, note, status) {
  status.textContent = "Saving separate review note...";
  try {
    const payload = await getJson(`/api/v8/review/${encodeURIComponent(row.variation_id)}`, {
      method: "PATCH",
      body: JSON.stringify({decision, note}),
    });
    status.textContent = `Saved: ${payload.review.decision}. Frozen prediction unchanged.`;
    status.className = "save-message save-success";
  } catch (error) {
    status.textContent = error.message;
    status.className = "save-message save-error";
  }
}

function reviewCard(row) {
  const article = document.createElement("article");
  article.className = `panel v8-review-card confusion-${row.confusion_group.toLowerCase()}`;
  const header = document.createElement("div");
  header.className = "prediction-card-heading";
  const heading = document.createElement("h3");
  heading.textContent = `#${row.queue_order} | ${display(row.gene)} | Variation ${row.variation_id}`;
  const badge = document.createElement("span");
  badge.textContent = `${row.confusion_group} | ${row.review_state}`;
  header.append(heading, badge);

  const reasons = document.createElement("p");
  reasons.className = "review-reasons";
  reasons.textContent = display(row.reasons);
  const facts = document.createElement("dl");
  facts.className = "review-facts";
  facts.append(
    detail("Older classification", row.old_classification),
    detail("Prediction", row.predicted_class.replaceAll("_", " ")),
    detail("Later direction", row.actual_outcome.replaceAll("_", " ")),
    detail("Later classification", row.actual_later_classification),
    detail("Pathogenic-direction probability", `${(Number(row.v8_probability) * 100).toFixed(1)}%`),
    detail("Probability assigned to predicted direction", `${(Number(row.confidence) * 100).toFixed(1)}%`),
    detail("Consequence", row.consequence),
    detail("Key features", row.key_features),
    detail("Match confidence", row.match_confidence),
    detail("Source review status", row.review_status),
    detail("Match warnings", row.warning_flags),
    detail("Suggested category", `Unverified: ${display(row.suggested_category)}`),
    detail("Correct control sample", row.correct_sample === "true" ? "Yes" : "No"),
    detail("V7 prediction", row.v7_prediction.replaceAll("_", " ")),
    detail("Frozen source hash", row.source_predictions_sha256),
  );

  const links = document.createElement("div");
  links.className = "button-row review-source-actions";
  const clinvar = document.createElement("a");
  clinvar.className = "button-link button-secondary";
  clinvar.href = `https://www.ncbi.nlm.nih.gov/clinvar/variation/${encodeURIComponent(row.variation_id)}/`;
  clinvar.target = "_blank";
  clinvar.rel = "noopener noreferrer";
  clinvar.textContent = "Official ClinVar variation";
  links.append(clinvar);
  const timeline = document.createElement("a");
  timeline.className = "button-link button-secondary";
  timeline.href = `/historical_variants.html?query=${encodeURIComponent(row.variation_id)}`;
  timeline.textContent = "Open snapshot timeline";
  links.append(timeline);
  if (row.vcv_accession && row.vcv_accession !== "not recorded") {
    const history = document.createElement("a");
    history.className = "button-link button-secondary";
    history.href = `/version_history.html?accession=${encodeURIComponent(row.vcv_accession)}`;
    history.textContent = "Open exact VCV history";
    links.append(history);
  } else {
    const unavailable = document.createElement("button");
    unavailable.type = "button";
    unavailable.disabled = true;
    unavailable.textContent = "Exact VCV history unavailable: no VCV recorded";
    links.append(unavailable);
  }

  const form = document.createElement("form");
  form.className = "review-decision-form";
  const decisionLabel = document.createElement("label");
  decisionLabel.textContent = "Decision";
  const decision = document.createElement("select");
  const empty = document.createElement("option");
  empty.value = "";
  empty.textContent = "Choose a decision";
  decision.append(empty);
  DECISIONS.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    option.selected = row.review.decision === value;
    decision.append(option);
  });
  decisionLabel.append(decision);
  const noteLabel = document.createElement("label");
  noteLabel.textContent = "Note (required for ambiguity, scope, or exclusion)";
  const note = document.createElement("textarea");
  note.maxLength = 5000;
  note.rows = 3;
  note.value = display(row.review.note, "");
  noteLabel.append(note);
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "Save review decision";
  const status = document.createElement("p");
  status.className = "save-message";
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!decision.value) { status.textContent = "Choose one exact decision first."; return; }
    saveReview(row, decision.value, note.value, status);
  });
  form.append(decisionLabel, noteLabel, submit, status);
  article.append(header, reasons, facts, links, form);
  return article;
}

function queryString() {
  const params = new URLSearchParams();
  const values = {
    confusion_group: byId("review-group").value,
    gene: byId("review-gene").value.trim(),
    consequence: byId("review-consequence").value.trim(),
    status: byId("review-status").value,
  };
  Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value); });
  if (byId("review-disagreement").checked) params.set("disagreement", "true");
  if (byId("review-high-confidence").checked) params.set("high_confidence", "true");
  if (byId("review-match-warning").checked) params.set("match_warning", "true");
  params.set("page", String(currentPage));
  params.set("page_size", "25");
  return params.toString();
}

async function loadQueue() {
  byId("review-status-message").textContent = "Loading review queue...";
  try {
    const query = queryString();
    const payload = await getJson(`/api/v8/review-queue${query ? `?${query}` : ""}`);
    byId("review-items").replaceChildren(...payload.rows.map(reviewCard));
    byId("review-count").textContent = `${payload.completed_review_count} reviewed / ${payload.total} queued`;
    byId("review-status-message").textContent = `${payload.filtered_total} of ${payload.total} records match; showing ${payload.rows.length} in source CSV order.`;
    byId("v8-review-page").textContent = `Page ${payload.page} of ${payload.page_count}`;
    byId("v8-review-previous").disabled = payload.page <= 1;
    byId("v8-review-next").disabled = payload.page >= payload.page_count;
    currentPage = payload.page;
  } catch (error) {
    byId("review-status-message").textContent = `Could not load review queue: ${error.message}`;
  }
}

byId("review-filters").addEventListener("submit", (event) => { event.preventDefault(); currentPage = 1; loadQueue(); });
byId("clear-review-filters").addEventListener("click", () => { byId("review-filters").reset(); currentPage = 1; loadQueue(); });
byId("v8-review-previous").addEventListener("click", () => { if (currentPage > 1) { currentPage -= 1; loadQueue(); } });
byId("v8-review-next").addEventListener("click", () => { currentPage += 1; loadQueue(); });
const initial = new URLSearchParams(window.location.search);
byId("review-group").value = initial.get("confusion_group") || "";
byId("review-gene").value = initial.get("gene") || "";
byId("review-consequence").value = initial.get("consequence") || "";
byId("review-status").value = initial.get("status") || "";
byId("review-disagreement").checked = initial.get("disagreement") === "true";
byId("review-high-confidence").checked = initial.get("high_confidence") === "true";
byId("review-match-warning").checked = initial.get("match_warning") === "true";
loadQueue();
