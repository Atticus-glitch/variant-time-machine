"use strict";

const state = {
  plan: null,
  lookupVariants: [],
  selectedLookup: null,
  records: [],
  openRecord: null,
  options: null,
};

const byId = (id) => document.getElementById(id);
const valueOr = (value, fallback = "Not recorded") => value || fallback;

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {Accept: "application/json", "Content-Type": "application/json"},
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.error || `Request returned ${response.status}`);
    error.payload = payload;
    error.status = response.status;
    throw error;
  }
  return payload;
}

function formatBytes(bytes) {
  if (!bytes) return "0 bytes";
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB`;
  return `${(bytes / 1e6).toFixed(2)} MB`;
}

function renderTransfer(transfer) {
  if (!transfer) return;
  byId("transfer-source").textContent = transfer.source || "Not available";
  byId("transfer-estimate").textContent = formatBytes(transfer.estimated_max_bytes);
  byId("transfer-actual").textContent = formatBytes(transfer.actual_bytes);
  byId("transfer-purpose").textContent = transfer.purpose || "Not available";
  byId("transfer-size-status").textContent = transfer.is_small ? "Small request" : "Large request";
  byId("transfer-blocked").textContent = transfer.large_download_blocked ? "Blocked" : "Allowed after approval";
}

function option(select, value, label = value) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  select.append(item);
}

function setupSelects() {
  for (const id of ["older-classification", "newer-classification"]) {
    const select = byId(id);
    select.replaceChildren();
    option(select, "", "Not recorded");
    state.options.classification_options.forEach((entry) => option(select, entry));
  }
  const type = byId("classification-type");
  type.replaceChildren();
  option(type, "", "Not checked");
  state.options.classification_types.forEach((entry) => option(type, entry));
}

function clearChildren(element) {
  while (element.firstChild) element.firstChild.remove();
}

function addDefinition(list, label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = valueOr(value);
  wrapper.append(term, detail);
  list.append(wrapper);
}

function candidateCard(variant) {
  const card = document.createElement("article");
  card.className = "candidate-card";
  const title = document.createElement("h3");
  title.textContent = variant.variant_identifier;
  const fields = document.createElement("dl");
  fields.className = "candidate-details";
  addDefinition(fields, "Variation ID", variant.variation_id);
  addDefinition(fields, "Gene", variant.gene_name);
  addDefinition(fields, "Current classification", variant.classification);
  addDefinition(fields, "Review status", variant.review_status);
  addDefinition(fields, "Conditions", (variant.associated_conditions || []).join("; "));
  addDefinition(fields, "Last lookup", variant.retrieved_at_utc);
  addDefinition(fields, "Data transferred", formatBytes(variant.response_bytes));
  const source = document.createElement("a");
  source.href = variant.source_url;
  source.target = "_blank";
  source.rel = "noreferrer";
  source.textContent = "Open official ClinVar source";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Add to Pilot";
  button.addEventListener("click", () => chooseLookup(variant));
  card.append(title, fields, source, button);
  return card;
}

function chooseLookup(variant) {
  state.selectedLookup = variant;
  byId("add-panel").hidden = false;
  byId("add-candidate-name").textContent = `${variant.variant_identifier}, ${valueOr(variant.gene_name, "gene not listed")}`;
  byId("duplicate-panel").hidden = true;
  byId("add-status").textContent = "";
  byId("add-panel").scrollIntoView({behavior: "smooth"});
}

async function planLookup(query) {
  const payload = await api("/api/clinvar/plan", {
    method: "POST",
    body: JSON.stringify({query}),
  });
  state.plan = payload.plan;
  renderTransfer(payload.plan);
  byId("lookup-plan-message").textContent = `${payload.plan.purpose}. Maximum: ${formatBytes(payload.plan.estimated_max_bytes)}. Source: ${payload.plan.source}`;
  byId("lookup-plan").hidden = false;
  byId("workspace-lookup-status").textContent = "Review the transfer plan before approval.";
}

async function runApprovedLookup() {
  byId("approve-lookup").disabled = true;
  byId("workspace-lookup-status").className = "loading";
  byId("workspace-lookup-status").textContent = "Loading current official ClinVar information...";
  try {
    const payload = await api("/api/clinvar/lookup", {
      method: "POST",
      body: JSON.stringify({query: state.plan.query, approved: true}),
    });
    state.lookupVariants = payload.variants;
    renderTransfer(payload.transfer);
    byId("lookup-plan").hidden = true;
    byId("workspace-lookup-status").className = "connection-success";
    byId("workspace-lookup-status").textContent = `${payload.variants.length} current record(s) received. No historical claim was made.`;
    byId("lookup-results").replaceChildren(...payload.variants.map(candidateCard));
  } catch (error) {
    byId("workspace-lookup-status").className = "error-message";
    byId("workspace-lookup-status").textContent = `Lookup failed: ${error.message}`;
  } finally {
    byId("approve-lookup").disabled = false;
  }
}

async function addSelected(onDuplicate = "cancel") {
  if (!state.selectedLookup) return;
  const body = {
    variant_id: state.selectedLookup.variation_id,
    selection_reason: byId("selection-reason").value,
    notes: byId("selection-notes").value,
    intended_historical_date: byId("intended-date").value,
    understood_current_only: byId("current-only-confirmation").checked,
    on_duplicate: onDuplicate,
  };
  try {
    const payload = await api("/api/pilot", {method: "POST", body: JSON.stringify(body)});
    byId("duplicate-panel").hidden = true;
    byId("add-status").className = "connection-success";
    byId("add-status").textContent = payload.updated ? "Current lookup updated. Your historical notes were kept." : "Variant added. Past classification still needs checking.";
    await loadPilot();
    await openReview(payload.record.variant_id);
  } catch (error) {
    if (error.status === 409 && error.payload.duplicate) {
      byId("duplicate-panel").hidden = false;
      byId("add-status").textContent = error.message;
      return;
    }
    byId("add-status").className = "error-message";
    byId("add-status").textContent = error.message;
  }
}

function notesPreview(value) {
  if (!value) return "None";
  return value.length > 70 ? `${value.slice(0, 67)}...` : value;
}

function tableCell(value) {
  const cell = document.createElement("td");
  cell.textContent = valueOr(value, "Not recorded");
  return cell;
}

function filteredRecords() {
  const status = byId("status-filter").value;
  const query = byId("pilot-search").value.trim().toLowerCase();
  return state.records.filter((record) => {
    const statusMatch = status === "all" || record.review_status === status;
    const text = `${record.variant_id} ${record.vcv_accession} ${record.gene}`.toLowerCase();
    return statusMatch && text.includes(query);
  });
}

function renderPilotList() {
  const body = byId("workspace-pilot-body");
  clearChildren(body);
  const records = filteredRecords();
  if (!records.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 9;
    cell.textContent = state.records.length ? "No pilot records match these filters." : "Your pilot list is empty.";
    row.append(cell);
    body.append(row);
    return;
  }
  for (const record of records) {
    const row = document.createElement("tr");
    row.append(
      tableCell(`${record.vcv_accession} / ${record.variant_id}`),
      tableCell(record.gene),
      tableCell(record.current_classification),
      tableCell(record.older_classification),
      tableCell(record.review_status),
      tableCell(record.selected_date),
      tableCell(record.updated_at_utc),
      tableCell(notesPreview(record.notes)),
    );
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Open Review";
    button.addEventListener("click", () => openReview(record.variant_id));
    action.append(button);
    row.append(action);
    body.append(row);
  }
}

async function loadPilot() {
  const payload = await api("/api/pilot");
  state.records = payload.records;
  state.options = payload;
  setupSelects();
  byId("first-run-guide").hidden = !payload.first_run;
  renderPilotList();
}

function setInput(id, value) {
  byId(id).value = value || "";
}

function renderTimeline(record) {
  const target = byId("workspace-timeline");
  clearChildren(target);
  const timeline = record.timeline;
  if (!timeline.older.classification) {
    const missing = document.createElement("p");
    missing.className = "historical-missing";
    missing.textContent = "Historical classification not yet verified.";
    target.append(missing);
  } else {
    const old = document.createElement("p");
    old.textContent = `${timeline.older.date}: ${timeline.older.classification}`;
    target.append(old);
  }
  if (timeline.newer.classification) {
    const newer = document.createElement("p");
    newer.textContent = `${timeline.newer.date}: ${timeline.newer.classification}`;
    target.append(newer);
  }
  const change = document.createElement("p");
  change.textContent = `Change category: ${timeline.change_category}`;
  const status = document.createElement("p");
  status.textContent = `Verification state: ${timeline.verification_state}`;
  target.append(change, status);
}

function populateReview(record) {
  state.openRecord = record;
  byId("review-empty").hidden = true;
  byId("review-content").hidden = false;
  byId("review-heading-note").textContent = `${record.vcv_accession} / Variation ID ${record.variant_id}`;
  const current = byId("review-current");
  clearChildren(current);
  addDefinition(current, "Gene", record.gene);
  addDefinition(current, "Current classification", record.current_classification);
  addDefinition(current, "Current review status", record.current_review_status);
  addDefinition(current, "Conditions", record.conditions.join("; "));
  addDefinition(current, "Retrieved", record.current_retrieved_at_utc);
  byId("review-selection-reason").textContent = record.selection_reason;
  byId("review-current-source").href = record.current_source_url;
  byId("review-current-source").textContent = record.current_source_url;
  setInput("older-release-date", record.older_release_date);
  setInput("older-classification", record.older_classification);
  setInput("newer-comparison-date", record.newer_comparison_date);
  setInput("newer-classification", record.newer_classification);
  setInput("classification-type", record.historical_classification_type);
  setInput("historical-source-url", record.historical_source_url);
  setInput("review-notes", record.notes);
  setInput("verification-notes", record.verification_notes);
  setInput("ambiguity-reason", record.ambiguity_reason);
  document.querySelectorAll("[data-check]").forEach((box) => {
    box.checked = record.verification_checklist[box.dataset.check] === true;
  });
  byId("review-warnings").textContent = record.older_classification
    ? "Check that dates, category type, condition scope, and source all describe the same record."
    : "Historical classification not yet verified. Do not infer it from the current result.";
  renderTimeline(record);
  byId("review-save-status").textContent = "";
  byId("review-workspace").scrollIntoView({behavior: "smooth"});
}

async function openReview(variationId) {
  try {
    const payload = await api(`/api/pilot/${encodeURIComponent(variationId)}`);
    populateReview(payload.record);
  } catch (error) {
    byId("review-empty").textContent = error.message;
  }
}

function reviewChanges() {
  const checklist = {};
  document.querySelectorAll("[data-check]").forEach((box) => {
    checklist[box.dataset.check] = box.checked;
  });
  return {
    notes: byId("review-notes").value,
    older_release_date: byId("older-release-date").value,
    older_classification: byId("older-classification").value,
    newer_comparison_date: byId("newer-comparison-date").value,
    newer_classification: byId("newer-classification").value,
    historical_source_url: byId("historical-source-url").value,
    historical_classification_type: byId("classification-type").value,
    verification_notes: byId("verification-notes").value,
    ambiguity_reason: byId("ambiguity-reason").value,
    verification_checklist: checklist,
  };
}

async function saveReview(action) {
  if (!state.openRecord) return;
  byId("review-save-status").className = "loading";
  byId("review-save-status").textContent = "Saving your work...";
  try {
    const payload = await api(`/api/pilot/${state.openRecord.variant_id}`, {
      method: "PATCH",
      body: JSON.stringify({action, changes: reviewChanges()}),
    });
    await loadPilot();
    populateReview(payload.record);
    byId("review-save-status").className = "connection-success";
    byId("review-save-status").textContent = "Your work was saved locally.";
  } catch (error) {
    byId("review-save-status").className = "error-message";
    byId("review-save-status").textContent = error.message;
  }
}

byId("workspace-lookup-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  byId("lookup-results").replaceChildren();
  byId("workspace-lookup-status").className = "loading";
  byId("workspace-lookup-status").textContent = "Checking the request plan...";
  try {
    await planLookup(byId("workspace-query").value);
  } catch (error) {
    byId("workspace-lookup-status").className = "error-message";
    byId("workspace-lookup-status").textContent = error.message;
  }
});
byId("approve-lookup").addEventListener("click", runApprovedLookup);
byId("cancel-lookup").addEventListener("click", () => {
  state.plan = null;
  byId("lookup-plan").hidden = true;
  byId("workspace-lookup-status").textContent = "Lookup canceled. No network request started.";
});
byId("add-pilot-form").addEventListener("submit", (event) => {
  event.preventDefault();
  addSelected();
});
byId("cancel-add").addEventListener("click", () => {
  byId("add-panel").hidden = true;
});
byId("open-duplicate").addEventListener("click", () => openReview(state.selectedLookup.variation_id));
byId("update-duplicate").addEventListener("click", () => addSelected("update_current"));
byId("cancel-duplicate").addEventListener("click", () => {
  byId("duplicate-panel").hidden = true;
});
byId("status-filter").addEventListener("change", renderPilotList);
byId("pilot-search").addEventListener("input", renderPilotList);
byId("review-form").addEventListener("submit", (event) => {
  event.preventDefault();
  saveReview(event.submitter.dataset.action);
});

loadPilot().catch((error) => {
  byId("workspace-pilot-body").textContent = error.message;
});
