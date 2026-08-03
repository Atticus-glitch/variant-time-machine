"use strict";

const byId = (id) => document.getElementById(id);
let currentPage = 1;

async function getJson(path, options = {}) {
  const response = await fetch(path, {headers: {Accept: "application/json", "Content-Type": "application/json"}, ...options});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function display(value, fallback = "Not recorded") {
  return value === null || value === undefined || String(value).trim() === "" ? fallback : String(value);
}

function parsed(value, fallback) {
  try { return JSON.parse(value); } catch (_) { return fallback; }
}

function detail(label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt"); term.textContent = label;
  const description = document.createElement("dd"); description.textContent = display(value);
  wrapper.append(term, description); return wrapper;
}

function section(title, entries) {
  const wrapper = document.createElement("section"); wrapper.className = "review-evidence-section";
  const heading = document.createElement("h4"); heading.textContent = title;
  const facts = document.createElement("dl"); facts.className = "review-facts";
  facts.append(...entries.map(([label, value]) => detail(label, value)));
  wrapper.append(heading, facts); return wrapper;
}

function option(value, selected) {
  const item = document.createElement("option"); item.value = value;
  item.textContent = value.replaceAll("_", " "); item.selected = value === selected;
  return item;
}

function selectField(labelText, values, selected, allowBlank = false) {
  const label = document.createElement("label"); label.textContent = labelText;
  const select = document.createElement("select");
  if (allowBlank) select.append(option("", selected));
  select.append(...values.map((value) => option(value, selected)));
  label.append(select); return {label, select};
}

function checkboxField(labelText, checked) {
  const label = document.createElement("label"); label.className = "check-line";
  const input = document.createElement("input"); input.type = "checkbox"; input.checked = Boolean(checked);
  label.append(input, ` ${labelText}`); return {label, input};
}

function safeSourceLink(source) {
  try {
    const url = new URL(source.url);
    if (url.protocol !== "https:" || url.hostname !== "www.ncbi.nlm.nih.gov") return null;
    const link = document.createElement("a"); link.className = "button-link button-secondary";
    link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
    link.textContent = display(source.label, "Official ClinVar source"); return link;
  } catch (_) { return null; }
}

async function saveReview(row, controls, status) {
  status.textContent = "Saving structured review..."; status.className = "save-message";
  try {
    const body = {
      reviewer: controls.reviewer.value,
      manual_decision: controls.decision.value,
      manual_error_category: controls.category.value,
      exclude_from_v9_clean_dataset: controls.excludeClean.checked,
      include_in_v9_messy_dataset: controls.includeMessy.checked,
      include_in_v9_clean_dataset: controls.includeClean.checked,
      corrected_outcome: controls.corrected.value,
      cleared_automatic_flags: controls.flagInputs.filter((item) => item.checked).map((item) => item.value),
      reviewer_confidence: controls.confidence.value,
      note: controls.note.value,
      expected_revision: Number(row.review.revision || 0),
    };
    const payload = await getJson(`/api/v8/review/${encodeURIComponent(row.variation_id)}`, {method: "PATCH", body: JSON.stringify(body)});
    status.textContent = `Saved ${payload.review.manual_decision}. Original V8 evidence unchanged.`;
    status.className = "save-message save-success";
    await loadQueue();
  } catch (error) {
    status.textContent = error.message; status.className = "save-message save-error";
  }
}

function applyShortcut(kind, controls) {
  const presets = {
    genuine: ["match_correct_model_wrong", "genuine_model_error", false, true],
    ambiguous: ["uncertain_manual_review", "aggregate_label_ambiguous", true, false],
    badMatch: ["bad_match", "poor_match", true, false],
    exclude: ["missing_critical_fields", "unknown", true, false],
    expert: ["needs_expert_review", "unknown", true, false],
  };
  const [decision, category, exclude, clean] = presets[kind];
  controls.decision.value = decision; controls.category.value = category;
  controls.excludeClean.checked = exclude; controls.includeClean.checked = clean;
  controls.note.focus();
}

function reviewCard(row, payload) {
  const review = row.review || {};
  const article = document.createElement("article");
  article.className = `panel v8-review-card confusion-${row.confusion_group.toLowerCase()}`;
  const header = document.createElement("div"); header.className = "prediction-card-heading";
  const heading = document.createElement("h3"); heading.textContent = `#${row.queue_order} | ${display(row.gene)} | Variation ${row.variation_id}`;
  const badge = document.createElement("span"); badge.textContent = `${row.confusion_group} | ${row.review_state}`;
  header.append(heading, badge);
  const reasons = document.createElement("p"); reasons.className = "review-reasons";
  reasons.textContent = `Priority ${row.priority_score}: ${display(row.reasons)}`;

  const identity = section("Identity", [
    ["Variation ID", row.variation_id], ["VCV accession", row.vcv_accession],
    ["Allele ID", row.allele_id], ["RCV accession(s)", row.rcv_accessions],
    ["Gene", row.gene], ["Match method", row.match_method], ["Match confidence", row.match_confidence],
  ]);
  const timeline = section("Timeline", [
    ["Old snapshot", row.old_snapshot_date], ["Old classification", row.old_classification_text],
    ["Old review status", row.old_review_status], ["Old condition", row.old_condition_text],
    ["V8 prediction", row.predicted_class.replaceAll("_", " ")],
    ["V8 pathogenic probability", `${(Number(row.v8_probability) * 100).toFixed(1)}%`],
    ["V8 predicted-direction confidence", `${(Number(row.confidence) * 100).toFixed(1)}%`],
    ["V7 same-record prediction", row.v7_prediction.replaceAll("_", " ")],
    ["New snapshot", row.new_snapshot_date], ["New classification", row.new_classification_text],
    ["New review status", row.new_review_status], ["New condition", row.new_condition_text],
    ["Automatic correctness", row.correct === "true" ? "Correct" : `Wrong (${row.confusion_group})`],
  ]);

  const flags = parsed(row.automatic_review_flags, []);
  const contributions = parsed(row.feature_contributions, []);
  const featureValues = parsed(row.feature_values_used_by_v8, {});
  const activeFeatures = Object.entries(featureValues)
    .filter(([, value]) => Number(value) !== 0)
    .map(([name, value]) => `${name}=${value}`)
    .join("; ");
  const explanation = section("Model Explanation", [
    ["Consequence fields", row.old_consequence_fields],
    ["Nonzero V8 feature values", activeFeatures || "All recorded feature values are zero"],
    ["Top standardized contributions", contributions.map((item) => `${item.feature}: ${Number(item.standardized_logit_contribution).toFixed(3)} (coefficient ${Number(item.coefficient).toFixed(3)}, value ${item.value})`).join("; ")],
    ["Why V8 likely predicted this direction", row.model_explanation],
    ["Computer suggestions - not manual conclusions", flags.length ? flags.join("; ") : "None recorded"],
    ["Field provenance", row.field_provenance],
  ]);

  const links = document.createElement("div"); links.className = "button-row review-source-actions";
  parsed(row.official_source_links, []).map(safeSourceLink).filter(Boolean).forEach((link) => links.append(link));
  const snapshot = document.createElement("a"); snapshot.className = "button-link button-secondary";
  snapshot.href = `/historical_variants.html?query=${encodeURIComponent(row.variation_id)}`;
  snapshot.textContent = "Open snapshot timeline"; links.append(snapshot);

  const form = document.createElement("form"); form.className = "review-decision-form";
  const reviewerLabel = document.createElement("label"); reviewerLabel.textContent = "Reviewer";
  const reviewer = document.createElement("input"); reviewer.maxLength = 200; reviewer.required = true;
  reviewer.value = display(review.reviewer, ""); reviewerLabel.append(reviewer);
  const decisionField = selectField("Manual decision", payload.allowed_decisions, review.manual_decision || "not_reviewed");
  const categoryField = selectField("Manual error category", payload.allowed_error_categories, review.manual_error_category || "unknown");
  const confidenceField = selectField("Reviewer confidence", payload.reviewer_confidence_options, review.reviewer_confidence || "", true);
  const correctedField = selectField("Corrected outcome (only with evidence)", ["moved_toward_benign", "moved_toward_pathogenic"], review.corrected_outcome || "", true);
  const includeMessyField = checkboxField("Reviewer recommends inclusion in V9 messy dataset (all-record audit still retains the original row)", review.include_in_v9_messy_dataset !== false);
  const includeCleanField = checkboxField("Include in V9 clean reviewed dataset", review.include_in_v9_clean_dataset === true);
  const excludeCleanField = checkboxField("Exclude from V9 clean dataset", review.exclude_from_v9_clean_dataset === true);
  const cleared = new Set(review.cleared_automatic_flags || []);
  const flagResolution = document.createElement("fieldset");
  const flagLegend = document.createElement("legend"); flagLegend.textContent = "Computer flags resolved by manual evidence";
  flagResolution.append(flagLegend);
  const flagInputs = flags.map((flag) => {
    const field = checkboxField(`Resolved: ${flag}`, cleared.has(flag));
    field.input.value = flag; flagResolution.append(field.label); return field.input;
  });
  const noteLabel = document.createElement("label"); noteLabel.textContent = "Notes (required for bad match, label problem, correction, exclusion, uncertainty, or expert review)";
  const note = document.createElement("textarea"); note.maxLength = payload.note_max_length; note.rows = 5;
  note.value = display(review.note, ""); noteLabel.append(note);
  const controls = {reviewer, decision: decisionField.select, category: categoryField.select, confidence: confidenceField.select, corrected: correctedField.select, includeMessy: includeMessyField.input, includeClean: includeCleanField.input, excludeClean: excludeCleanField.input, flagInputs, note};
  const shortcuts = document.createElement("div"); shortcuts.className = "button-row review-shortcuts";
  [["Genuine Model Error", "genuine"], ["Ambiguous", "ambiguous"], ["Bad Match", "badMatch"], ["Exclude From V9 Clean Dataset", "exclude"], ["Needs Expert Review", "expert"]].forEach(([label, kind]) => {
    const button = document.createElement("button"); button.type = "button"; button.className = "button-secondary";
    button.textContent = `Mark as ${label}`; button.addEventListener("click", () => applyShortcut(kind, controls)); shortcuts.append(button);
  });
  const submit = document.createElement("button"); submit.type = "submit"; submit.textContent = "Save Review";
  const status = document.createElement("p"); status.className = "save-message";
  form.addEventListener("submit", (event) => { event.preventDefault(); saveReview(row, controls, status); });
  form.append(reviewerLabel, decisionField.label, categoryField.label, confidenceField.label, correctedField.label, includeMessyField.label, includeCleanField.label, excludeCleanField.label, flagResolution, noteLabel, shortcuts, submit, status);
  article.append(header, reasons, identity, timeline, explanation, links, form); return article;
}

function queryString() {
  const params = new URLSearchParams();
  const values = {confusion_group: byId("review-group").value, gene: byId("review-gene").value.trim(), consequence: byId("review-consequence").value.trim(), status: byId("review-status").value};
  Object.entries(values).forEach(([key, value]) => { if (value) params.set(key, value); });
  if (byId("review-disagreement").checked) params.set("disagreement", "true");
  if (byId("review-high-confidence").checked) params.set("high_confidence", "true");
  if (byId("review-match-warning").checked) params.set("match_warning", "true");
  params.set("page", String(currentPage)); params.set("page_size", "1"); return params.toString();
}

function renderProgress(progress) {
  const list = byId("review-progress"); list.replaceChildren();
  [["Total queued", progress.total_queued], ["Reviewed", progress.reviewed], ["Remaining", progress.remaining], ["False negatives reviewed", progress.false_negatives_reviewed], ["False positives reviewed", progress.false_positives_reviewed], ["V8/V7 disagreements reviewed", progress.disagreements_reviewed], ["Excluded from clean", progress.excluded_from_clean], ["Included in clean", progress.included_in_clean], ["Needs expert review", progress.needs_expert_review]].forEach(([label, value]) => list.append(detail(label, String(value))));
}

async function loadQueue() {
  byId("review-status-message").textContent = "Loading review case...";
  try {
    const payload = await getJson(`/api/v8/review-queue?${queryString()}`);
    byId("review-items").replaceChildren(...payload.rows.map((row) => reviewCard(row, payload)));
    byId("review-count").textContent = `${payload.progress.reviewed} / ${payload.total}`;
    renderProgress(payload.progress);
    byId("review-status-message").textContent = `${payload.filtered_total} of ${payload.total} records match. Computer flags remain suggestions.`;
    byId("v8-review-page").textContent = `Case ${payload.page} of ${payload.page_count}`;
    byId("v8-review-previous").disabled = payload.page <= 1;
    byId("v8-review-next").disabled = payload.page >= payload.page_count;
    currentPage = payload.page;
  } catch (error) { byId("review-status-message").textContent = `Could not load review queue: ${error.message}`; }
}

byId("review-filters").addEventListener("submit", (event) => { event.preventDefault(); currentPage = 1; loadQueue(); });
byId("clear-review-filters").addEventListener("click", () => { byId("review-filters").reset(); currentPage = 1; loadQueue(); });
byId("v8-review-previous").addEventListener("click", () => { if (currentPage > 1) { currentPage -= 1; loadQueue(); } });
byId("v8-review-next").addEventListener("click", () => { currentPage += 1; loadQueue(); });
loadQueue();
