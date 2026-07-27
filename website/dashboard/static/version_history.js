"use strict";

const state = {
  candidatePlan: null,
  accession: null,
  current: null,
  historyPlan: null,
  operationId: null,
  pollTimer: null,
  openHistory: null,
  savedReviewNotes: "",
};

const byId = (id) => document.getElementById(id);
const VCV_PATTERN = /^VCV[0-9]{9}(?:\.[1-9][0-9]*)?$/;
const GENUINE_CHANGES = new Set([
  "VUS_to_Pathogenic", "VUS_to_Likely_Pathogenic", "VUS_to_Benign",
  "VUS_to_Likely_Benign", "Pathogenic_to_VUS", "Benign_to_VUS",
  "Became_Conflicting", "Conflict_Resolved", "Other_Germline_Change",
]);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {Accept: "application/json", "Content-Type": "application/json"},
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request returned ${response.status}`);
  return payload;
}

function formatBytes(bytes) {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} bytes`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / (1024 * 1024)).toFixed(2)} MiB`;
}

function display(value, fallback = "Not recorded") {
  if (value === null || value === undefined || value === "") return fallback;
  if (Array.isArray(value)) return value.length ? value.join("; ") : fallback;
  return String(value);
}

function addDefinition(list, label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = display(value);
  wrapper.append(term, detail);
  list.append(wrapper);
}

function renderPlan(list, entries) {
  list.replaceChildren();
  entries.forEach(([label, value]) => addDefinition(list, label, value));
}

function setStatus(id, message, error = false) {
  const element = byId(id);
  element.className = error ? "error-message" : "";
  element.textContent = message;
}

function strictAccession() {
  const value = byId("vcv-accession").value.trim();
  if (!VCV_PATTERN.test(value)) {
    throw new Error("Enter an uppercase VCV accession with exactly nine digits and an optional positive version.");
  }
  return value;
}

async function planCandidates(event) {
  event.preventDefault();
  const query = byId("gene-query").value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9.-]{0,29}$/.test(query)) {
    setStatus("candidate-status", "Enter one gene symbol using letters, numbers, dots, or hyphens.", true);
    return;
  }
  try {
    const payload = await api("/api/clinvar/plan", {method: "POST", body: JSON.stringify({query})});
    state.candidatePlan = payload.plan;
    renderPlan(byId("candidate-plan-details"), [
      ["Source", payload.plan.source], ["Maximum transfer", formatBytes(payload.plan.estimated_max_bytes)],
      ["Purpose", payload.plan.purpose], ["Result cap", "Five current records"],
    ]);
    byId("candidate-plan").hidden = false;
    setStatus("candidate-status", "Review and explicitly confirm this current-record search.");
  } catch (error) {
    setStatus("candidate-status", `Could not plan search: ${error.message}`, true);
  }
}

function candidateCard(variant) {
  const card = document.createElement("article");
  card.className = "candidate-card";
  const title = document.createElement("h3");
  title.textContent = display(variant.variant_identifier, "VCV not returned");
  const versionMatch = String(variant.variant_identifier || "").match(/^(VCV[0-9]{9})\.([1-9][0-9]*)$/);
  const fields = document.createElement("dl");
  fields.className = "candidate-details";
  addDefinition(fields, "Gene", variant.gene_name);
  addDefinition(fields, "Current classification", variant.classification);
  addDefinition(fields, "Current review status", variant.review_status);
  addDefinition(fields, "Current conditions", variant.associated_conditions);
  addDefinition(fields, "Version hint", versionMatch && Number(versionMatch[2]) > 1 ? "Current VCV version is above 1" : "No version-above-1 hint");
  const note = document.createElement("p");
  note.className = "candidate-limit";
  note.textContent = "Current category only; no claim of a former VUS.";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = versionMatch ? "Use This VCV" : "VCV Unavailable";
  button.disabled = !versionMatch;
  button.addEventListener("click", () => {
    byId("vcv-accession").value = versionMatch[1];
    byId("current-form").scrollIntoView({behavior: "smooth"});
  });
  card.append(title, fields, note, button);
  return card;
}

async function fetchCandidates() {
  if (!state.candidatePlan) return;
  byId("approve-candidates").disabled = true;
  setStatus("candidate-status", "Requesting up to five current candidate records...");
  try {
    const payload = await api("/api/clinvar/lookup", {
      method: "POST", body: JSON.stringify({query: state.candidatePlan.query, approved: true}),
    });
    const variants = (payload.variants || []).slice(0, 5);
    byId("candidate-results").replaceChildren(...variants.map(candidateCard));
    byId("candidate-plan").hidden = true;
    setStatus("candidate-status", `${variants.length} current candidate record(s) received. No historical classification claim was made.`);
  } catch (error) {
    setStatus("candidate-status", `Candidate search failed: ${error.message}`, true);
  } finally {
    byId("approve-candidates").disabled = false;
  }
}

async function planCurrent(event) {
  event.preventDefault();
  try {
    const accession = strictAccession();
    const payload = await api("/api/vcv-history/current-plan", {
      method: "POST", body: JSON.stringify({accession}),
    });
    state.accession = payload.plan.accession;
    state.current = null;
    state.historyPlan = null;
    renderPlan(byId("current-plan-details"), [
      ["Official source", payload.plan.source], ["Request count", payload.plan.request_count],
      ["Maximum transfer", formatBytes(payload.plan.estimated_max_bytes)], ["Purpose", payload.plan.purpose],
    ]);
    byId("current-confirmation").checked = false;
    byId("fetch-current").disabled = true;
    byId("current-plan").hidden = false;
    byId("current-result").hidden = true;
    setStatus("current-status", "Confirm the exact current-record plan before EFetch.");
  } catch (error) {
    setStatus("current-status", `Current plan failed: ${error.message}`, true);
  }
}

async function fetchCurrent() {
  byId("fetch-current").disabled = true;
  setStatus("current-status", "Requesting the current official VCV record...");
  try {
    const payload = await api("/api/vcv-history/current", {
      method: "POST", body: JSON.stringify({accession: state.accession, approved: true}),
    });
    state.current = payload;
    state.accession = payload.accession;
    byId("current-plan").hidden = true;
    byId("current-result").hidden = false;
    byId("current-identifier").textContent = payload.current_identifier;
    renderPlan(byId("current-fields"), [
      ["Current version", payload.current_version],
      ["Germline classification", payload.record.germline.classification],
      ["Review status", payload.record.germline.review_status],
      ["Retrieved", payload.provenance.retrieved_at_utc],
      ["Actual transfer", formatBytes(payload.transfer.actual_bytes)],
    ]);
    byId("start-version").value = "1";
    byId("end-version").value = String(payload.current_version);
    setStatus("current-status", `Current EFetch confirmed ${payload.current_identifier}. Choose a bounded history range.`);
  } catch (error) {
    setStatus("current-status", `Current EFetch failed: ${error.message}`, true);
  }
}

async function buildHistoryPlan(event) {
  event.preventDefault();
  if (!state.current) {
    setStatus("plan-status", "Fetch and confirm the current VCV record first.", true);
    return;
  }
  const mode = document.querySelector('input[name="history-mode"]:checked').value;
  const body = {accession: state.accession, mode};
  if (mode === "custom") {
    body.start_version = Number(byId("start-version").value);
    body.end_version = Number(byId("end-version").value);
    if (!Number.isInteger(body.start_version) || !Number.isInteger(body.end_version)) {
      setStatus("plan-status", "Custom endpoints must be whole version numbers.", true);
      return;
    }
  }
  try {
    const payload = await api("/api/vcv-history/plan", {method: "POST", body: JSON.stringify(body)});
    state.historyPlan = payload.plan;
    renderPlan(byId("exact-plan-details"), [
      ["Official source", payload.plan.source], ["Request count", payload.plan.request_count],
      ["Maximum transfer", formatBytes(payload.plan.max_possible_transfer_bytes)],
      ["Storage estimate", formatBytes(payload.plan.estimated_storage_bytes)], ["Purpose", payload.plan.purpose],
    ]);
    byId("requested-versions").textContent = payload.plan.requested_versions.join(", ");
    byId("history-confirmation").checked = false;
    byId("explore-history").disabled = true;
    byId("exact-plan").hidden = false;
    setStatus("plan-status", "Review every requested version and confirm the exact plan.");
  } catch (error) {
    byId("exact-plan").hidden = true;
    setStatus("plan-status", `History plan failed: ${error.message}`, true);
  }
}

function renderEvents(events) {
  const items = events.map((event) => {
    const item = document.createElement("li");
    const eventName = String(event.event || "failed").toLowerCase();
    item.className = `event-${eventName.replace(/[^a-z]/g, "-")}`;
    const label = document.createElement("strong");
    label.textContent = eventName;
    const detail = document.createElement("span");
    detail.textContent = ` ${display(event.identifier, "operation")} ${display(event.message, "")}`;
    item.append(label, detail);
    return item;
  });
  byId("operation-events").replaceChildren(...items);
}

async function pollOperation() {
  if (!state.operationId) return;
  try {
    const operation = await api(`/api/vcv-history/operations/${state.operationId}`);
    renderEvents(operation.progress_events || []);
    setStatus("operation-status", operation.cancellation_requested ? "Cancellation requested; waiting for the active request to stop." : `Operation state: ${operation.state}`);
    if (operation.state === "running") {
      state.pollTimer = window.setTimeout(pollOperation, 700);
      return;
    }
    byId("cancel-operation").disabled = true;
    if (operation.error) setStatus("operation-status", `${operation.state}: ${operation.error}`, true);
    if (operation.result && operation.result.saved_accession) {
      await loadSavedHistories();
      await openHistory(operation.result.saved_accession);
    }
  } catch (error) {
    setStatus("operation-status", `Progress check failed: ${error.message}`, true);
  }
}

async function exploreHistory() {
  if (!state.historyPlan) return;
  byId("explore-history").disabled = true;
  byId("operation-panel").hidden = false;
  byId("operation-events").replaceChildren();
  byId("cancel-operation").disabled = false;
  setStatus("operation-status", "Starting approved background requests...");
  try {
    const payload = await api("/api/vcv-history/explore", {
      method: "POST", body: JSON.stringify({approved: true, plan: state.historyPlan}),
    });
    state.operationId = payload.operation_id;
    await pollOperation();
  } catch (error) {
    setStatus("operation-status", `Exploration failed: ${error.message}`, true);
  }
}

async function cancelOperation() {
  if (!state.operationId) return;
  byId("cancel-operation").disabled = true;
  try {
    await api(`/api/vcv-history/operations/${state.operationId}/cancel`, {method: "POST", body: "{}"});
    setStatus("operation-status", "Cancellation requested; the active request will finish safely.");
  } catch (error) {
    setStatus("operation-status", `Cancellation failed: ${error.message}`, true);
    byId("cancel-operation").disabled = false;
  }
}

function detailGroup(title, values) {
  const section = document.createElement("section");
  section.className = "parsed-group";
  const heading = document.createElement("h4");
  heading.textContent = title;
  const list = document.createElement("dl");
  list.className = "candidate-details";
  Object.entries(values).forEach(([label, value]) => addDefinition(list, label.replaceAll("_", " "), value));
  section.append(heading, list);
  return section;
}

function timelineCard(outcome, comparison, accession) {
  const card = document.createElement("article");
  const record = outcome.record;
  const changed = comparison && GENUINE_CHANGES.has(comparison.detected_classification_change);
  card.className = `version-card${changed ? " classification-changed" : ""}`;
  const heading = document.createElement("div");
  heading.className = "version-card-heading";
  const title = document.createElement("h3");
  title.textContent = record ? `Version ${record.version}` : outcome.requested_identifier;
  const badge = document.createElement("span");
  badge.className = `status-badge ${outcome.status === "available" ? "status-complete" : "status-in-progress"}`;
  badge.textContent = outcome.status;
  heading.append(title, badge);
  if (changed) {
    const changeBadge = document.createElement("strong");
    changeBadge.className = "classification-change-badge";
    changeBadge.textContent = "Germline classification changed";
    heading.append(changeBadge);
  }
  const summary = document.createElement("dl");
  summary.className = "version-summary";
  addDefinition(summary, "Dates", record ? `Created ${display(record.date_created)}; updated ${display(record.date_last_updated)}; deleted ${display(record.date_deleted, "No")}` : "Unavailable");
  addDefinition(summary, "Germline classification", record && record.germline.classification);
  addDefinition(summary, "Review", record && record.germline.review_status);
  addDefinition(summary, "Submissions", record && record.germline.submission_count);
  addDefinition(summary, "Detected change from preceding available version", comparison && comparison.detected_classification_change);
  const warnings = [...(record ? record.warnings || [] : []), ...(comparison ? comparison.warnings || [] : [])];
  if (outcome.message) warnings.push(outcome.message);
  const warning = document.createElement("span");
  warning.className = `warning-badge${warnings.length ? " has-warning" : ""}`;
  warning.textContent = warnings.length ? `${warnings.length} warning(s)` : "No warnings";
  const details = document.createElement("details");
  const detailsTitle = document.createElement("summary");
  detailsTitle.textContent = "Expand exact parsed fields and provenance";
  const groups = [];
  if (record) {
    groups.push(detailGroup("Record", {
      accession_version: record.accession_version, variation_id: record.variation_id,
      record_type: record.record_type, genes: record.genes, name: record.name, hgvs: record.hgvs,
      date_created: record.date_created, date_last_updated: record.date_last_updated,
      date_deleted: record.date_deleted, deleted: record.deleted,
      record_status: record.record_status, replaced_by: record.replaced_by, replacements: record.replacements,
      warnings: record.warnings,
    }));
    groups.push(detailGroup("Germline", record.germline));
    groups.push(detailGroup("Somatic clinical impact", record.somatic_clinical_impact));
    groups.push(detailGroup("Oncogenicity", record.oncogenicity));
    groups.push(detailGroup("Conditions", {conditions: record.conditions}));
  }
  groups.push(detailGroup("Source and retained artifact", {
    requested_identifier: outcome.requested_identifier, status: outcome.status,
    response_bytes: outcome.response_bytes, message: outcome.message,
    source: outcome.source_request, retrieval_timestamp: outcome.retrieved_at_utc,
    raw_record_filename: outcome.response_bytes > 0 ? `data/manual_review/vcv_history/${accession}/raw/${outcome.requested_identifier}.xml` : "No response body retained",
    warnings,
  }));
  details.append(detailsTitle, ...groups);
  card.append(heading, summary, warning, details);
  return card;
}

function fillReview(review) {
  state.savedReviewNotes = review.notes || "";
  byId("review-state").textContent = `Status: ${review.status}`;
  byId("history-notes").value = review.notes || "";
  byId("reviewer-decision").value = review.reviewer_decision || "";
  byId("manual-corrections").value = JSON.stringify(review.manual_corrections || {}, null, 2);
  byId("review-sources").value = (review.sources || []).join("\n");
  document.querySelectorAll("[data-verification]").forEach((box) => {
    box.checked = review.verification[box.dataset.verification] === true;
  });
}

function renderHistory(artifact) {
  const accession = artifact.metadata.requested_accession.split(".", 1)[0];
  const comparisons = new Map((artifact.comparisons.comparisons || []).map((item) => [item.later_version, item]));
  const cards = (artifact.versions.versions || []).map((outcome) => {
    const version = outcome.record ? outcome.record.version : null;
    return timelineCard(outcome, comparisons.get(version), accession);
  });
  byId("timeline").replaceChildren(...cards);
  const summary = artifact.metadata.summary;
  byId("result-summary").textContent = `${summary.retrieved_version_count} available version(s); germline change detected: ${summary.any_germline_classification_changed ? "yes" : "no"}.`;
  byId("history-result").hidden = false;
  byId("history-review").hidden = false;
  fillReview(artifact.review);
}

async function openHistory(accession) {
  try {
    const artifact = await api(`/api/vcv-histories/${encodeURIComponent(accession)}`);
    state.openHistory = accession;
    renderHistory(artifact);
    setStatus("review-status", `${accession} loaded. This exploration is already saved locally as a pilot case.`);
    byId("history-result").scrollIntoView({behavior: "smooth"});
  } catch (error) {
    setStatus("review-status", `Could not open saved history: ${error.message}`, true);
  }
}

async function loadSavedHistories() {
  try {
    const payload = await api("/api/vcv-histories");
    const cards = payload.histories.map((history) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "saved-history-card";
      button.textContent = `${history.accession}\n${history.summary.retrieved_version_count} version(s) | ${history.review.status}`;
      button.addEventListener("click", () => openHistory(history.accession));
      return button;
    });
    if (!cards.length) {
      const empty = document.createElement("p");
      empty.className = "loading";
      empty.textContent = "No version histories saved yet.";
      cards.push(empty);
    }
    byId("saved-history-list").replaceChildren(...cards);
  } catch (error) {
    byId("saved-history-list").textContent = `Saved histories unavailable: ${error.message}`;
  }
}

function reviewChanges() {
  let corrections;
  try {
    corrections = JSON.parse(byId("manual-corrections").value || "{}");
  } catch (error) {
    throw new Error(`Manual corrections must be valid JSON: ${error.message}`);
  }
  if (!corrections || Array.isArray(corrections) || typeof corrections !== "object") {
    throw new Error("Manual corrections JSON must be an object.");
  }
  const verification = {};
  document.querySelectorAll("[data-verification]").forEach((box) => {
    verification[box.dataset.verification] = box.checked;
  });
  return {
    notes: byId("history-notes").value,
    reviewer_decision: byId("reviewer-decision").value,
    manual_corrections: corrections,
    sources: byId("review-sources").value.split("\n").map((value) => value.trim()).filter(Boolean),
    verification,
  };
}

async function submitReview(event) {
  event.preventDefault();
  if (!state.openHistory) return;
  const action = event.submitter && event.submitter.dataset.reviewAction;
  if (!action) return;
  try {
    const changes = reviewChanges();
    if (action === "add_note") {
      let newNote = changes.notes.trim();
      if (state.savedReviewNotes && newNote.startsWith(state.savedReviewNotes)) {
        newNote = newNote.slice(state.savedReviewNotes.length).trim();
      }
      if (!newNote || newNote === state.savedReviewNotes) throw new Error("Add new text to Review notes before using Add Review Note.");
      changes.notes = newNote;
    }
    if (["mark_ambiguous", "exclude"].includes(action) && !changes.notes.trim()) throw new Error("Ambiguous and excluded reviews require notes.");
    if (action === "mark_manually_verified" && !Object.values(changes.verification).every(Boolean)) {
      throw new Error("Mark Manually Verified requires all ten verification checks.");
    }
    const payload = await api(`/api/vcv-histories/${state.openHistory}/review`, {
      method: "PATCH", body: JSON.stringify({action, changes}),
    });
    fillReview(payload.review);
    setStatus("review-status", `Review saved with action ${action.replaceAll("_", " ")}. Automatic parsed fields were not changed.`);
    await loadSavedHistories();
  } catch (error) {
    setStatus("review-status", `Review not saved: ${error.message}`, true);
  }
}

async function savePilotCase() {
  if (!state.openHistory) return;
  try {
    const payload = await api(`/api/vcv-histories/${state.openHistory}/review`, {
      method: "PATCH",
      body: JSON.stringify({action: "mark_needs_review", changes: reviewChanges()}),
    });
    fillReview(payload.review);
    setStatus("review-status", "Saved as a pilot case needing manual review. Automatic parsed fields were not changed.");
    await loadSavedHistories();
  } catch (error) {
    setStatus("review-status", `Pilot case not saved: ${error.message}`, true);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  byId("gene-form").addEventListener("submit", planCandidates);
  byId("approve-candidates").addEventListener("click", fetchCandidates);
  byId("dismiss-candidates").addEventListener("click", () => { byId("candidate-plan").hidden = true; });
  byId("current-form").addEventListener("submit", planCurrent);
  byId("current-confirmation").addEventListener("change", (event) => { byId("fetch-current").disabled = !event.target.checked; });
  byId("fetch-current").addEventListener("click", fetchCurrent);
  document.querySelectorAll('input[name="history-mode"]').forEach((radio) => radio.addEventListener("change", (event) => {
    byId("custom-range").hidden = event.target.value !== "custom";
    byId("exact-plan").hidden = true;
  }));
  byId("history-plan-form").addEventListener("submit", buildHistoryPlan);
  byId("history-confirmation").addEventListener("change", (event) => { byId("explore-history").disabled = !event.target.checked; });
  byId("explore-history").addEventListener("click", exploreHistory);
  byId("cancel-operation").addEventListener("click", cancelOperation);
  byId("refresh-histories").addEventListener("click", loadSavedHistories);
  byId("history-review-form").addEventListener("submit", submitReview);
  byId("save-pilot-case").addEventListener("click", savePilotCase);
  loadSavedHistories();
});
