"use strict";

const state = {plan: null, operationId: null, pollTimer: null};
const byId = (id) => document.getElementById(id);
const candidateSelectionRequests = [
  {accession: "VCV000000002", response_bytes: 25537, retrieved_at_utc: "2026-07-27T22:55:20.696957+00:00", source_request: "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar&id=VCV000000002&rettype=vcv&retmode=xml&tool=variant_time_machine"},
  {accession: "VCV000000005", response_bytes: 35279, retrieved_at_utc: "2026-07-27T22:55:21.631987+00:00", source_request: "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar&id=VCV000000005&rettype=vcv&retmode=xml&tool=variant_time_machine"},
  {accession: "VCV000000012", response_bytes: 28490, retrieved_at_utc: "2026-07-27T22:55:23.183725+00:00", source_request: "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar&id=VCV000000012&rettype=vcv&retmode=xml&tool=variant_time_machine"},
  {accession: "VCV000000014", response_bytes: 23721, retrieved_at_utc: "2026-07-27T22:55:24.177008+00:00", source_request: "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar&id=VCV000000014&rettype=vcv&retmode=xml&tool=variant_time_machine"},
];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {Accept: "application/json", "Content-Type": "application/json"},
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request returned ${response.status}`);
  return payload;
}

function display(value, fallback = "Not recorded") {
  if (value === null || value === undefined || value === "") return fallback;
  if (Array.isArray(value)) return value.length ? value.join("; ") : fallback;
  return String(value);
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes.toLocaleString()} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KiB (${bytes.toLocaleString()} bytes)`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MiB (${bytes.toLocaleString()} bytes)`;
}

function addDefinition(list, label, value) {
  const item = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = display(value);
  item.append(term, detail);
  list.append(item);
}

function status(id, message, error = false) {
  const element = byId(id);
  element.textContent = message;
  element.className = error ? "error-message" : "";
}

function parseCandidates() {
  const candidates = byId("batch-candidates").value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
  if (candidates.length === 0 || candidates.length > 10) throw new Error("Enter between 1 and 10 canonical VCV accessions.");
  return candidates;
}

async function planBatch(event) {
  event.preventDefault();
  try {
    const candidates = parseCandidates();
    const fixedCandidates = ["VCV000000002", "VCV000000005", "VCV000014026"];
    const useRecordedScreening = candidates.length === fixedCandidates.length && candidates.every((value, index) => value === fixedCandidates[index]);
    const payload = await api("/api/pilot-batch/plan", {
      method: "POST",
      body: JSON.stringify({
        candidates,
        candidate_selection_rule: byId("selection-rule").value,
        candidate_selection_bytes: useRecordedScreening ? candidateSelectionRequests.reduce((total, item) => total + item.response_bytes, 0) : 0,
        candidate_selection_requests: useRecordedScreening ? candidateSelectionRequests : [],
        reuse_existing: true,
      }),
    });
    state.plan = payload.plan;
    const details = byId("batch-plan-details");
    details.replaceChildren();
    [
      ["Number of variants", state.plan.candidate_count],
      ["Estimated maximum requests", state.plan.estimated_max_requests],
      ["Estimated maximum transfer", formatBytes(state.plan.estimated_max_transfer)],
      ["Candidate selection already transferred", formatBytes(state.plan.candidate_selection_bytes)],
      ["Existing reused history transfer", formatBytes(state.plan.reused_source_bytes)],
      ["Maximum total pilot transfer", formatBytes(state.plan.estimated_total_pilot_transfer)],
      ["Official source", state.plan.source],
      ["Purpose", state.plan.purpose],
      ["Reused candidates", state.plan.reused_count],
    ].forEach(([label, value]) => addDefinition(details, label, value));
    byId("batch-confirmation").checked = false;
    byId("run-batch").disabled = true;
    byId("batch-plan").hidden = false;
    status("batch-status", "Review this exact plan, then use the single explicit confirmation below.");
  } catch (error) {
    state.plan = null;
    byId("batch-plan").hidden = true;
    status("batch-status", `Could not plan batch: ${error.message}`, true);
  }
}

function renderProgress(operation) {
  byId("operation-status").textContent = `Batch ${operation.state}`;
  const list = byId("candidate-progress");
  list.replaceChildren();
  (operation.progress_events || []).forEach((event) => {
    const item = document.createElement("li");
    const candidate = document.createElement("strong");
    candidate.textContent = `${event.candidate} (${event.candidate_index}/${event.candidate_count})`;
    item.append(candidate, document.createTextNode(`: ${display(event.event)}`));
    list.append(item);
  });
}

async function pollOperation() {
  try {
    const operation = await api(`/api/vcv-history/operations/${state.operationId}`);
    renderProgress(operation);
    if (operation.state === "running") {
      state.pollTimer = window.setTimeout(pollOperation, 500);
      return;
    }
    byId("cancel-batch").disabled = true;
    status("batch-status", operation.error ? `Batch ${operation.state}: ${operation.error}` : `Batch ${operation.state}. Live results refreshed.`, Boolean(operation.error));
    await loadResults();
  } catch (error) {
    status("batch-status", `Could not read batch progress: ${error.message}`, true);
  }
}

async function runBatch() {
  if (!state.plan || !byId("batch-confirmation").checked) return;
  byId("run-batch").disabled = true;
  try {
    const payload = await api("/api/pilot-batch/run", {
      method: "POST",
      body: JSON.stringify({approved: true, plan: state.plan}),
    });
    state.operationId = payload.operation_id;
    byId("batch-plan").hidden = true;
    byId("batch-operation").hidden = false;
    byId("cancel-batch").disabled = false;
    status("batch-status", "Confirmed batch started. Candidate requests run sequentially.");
    await pollOperation();
  } catch (error) {
    byId("run-batch").disabled = false;
    status("batch-status", `Could not start batch: ${error.message}`, true);
  }
}

async function cancelBatch() {
  if (!state.operationId) return;
  try {
    await api(`/api/vcv-history/operations/${state.operationId}/cancel`, {method: "POST", body: "{}"});
    byId("cancel-batch").disabled = true;
    status("batch-status", "Cancellation requested. The current bounded request may finish first.");
  } catch (error) {
    status("batch-status", `Could not cancel batch: ${error.message}`, true);
  }
}

function renderSummary(summary) {
  const list = byId("results-summary");
  list.replaceChildren();
  [
    ["Real variants examined", summary.candidates_successfully_retrieved],
    ["Official versions retrieved", summary.total_official_versions_retrieved],
    ["Histories with classification changes", summary.variants_with_germline_change],
    ["Histories unchanged", summary.variants_with_no_germline_change],
    ["Histories needing review", summary.histories_needing_review],
    ["Data transferred", formatBytes(summary.total_bytes_transferred)],
    ["Candidates attempted", summary.candidates_attempted],
    ["Unable to compare", summary.variants_unable_to_compare],
    ["Local storage", formatBytes(summary.total_local_storage_bytes)],
  ].forEach(([label, value]) => addDefinition(list, label, value));

  const categories = byId("category-summary");
  categories.replaceChildren();
  const counts = Object.entries(summary.change_category_counts || {});
  const maximum = Math.max(1, ...counts.map(([, count]) => Number(count)));
  counts.forEach(([label, count]) => {
    const row = document.createElement("div");
    const name = document.createElement("span");
    const track = document.createElement("span");
    const bar = document.createElement("span");
    const total = document.createElement("strong");
    name.textContent = label.replaceAll("_", " ");
    track.className = "category-track";
    bar.className = "category-bar";
    bar.style.width = `${Math.max(8, (Number(count) / maximum) * 100)}%`;
    total.textContent = String(count);
    track.append(bar);
    row.append(name, track, total);
    categories.append(row);
  });
}

function sourceLink(url) {
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = url;
  return link;
}

function renderHistory(container, history) {
  container.replaceChildren();
  const manifestTitle = document.createElement("h4");
  manifestTitle.textContent = "Exact source requests and raw artifacts";
  const sources = document.createElement("ul");
  (history.manifest.source_requests || []).forEach((source) => {
    const item = document.createElement("li");
    const filename = `${source.identifier}.xml`;
    item.append(sourceLink(source.request), document.createTextNode(` | raw/${filename} | ${source.response_bytes} bytes | ${source.status}`));
    sources.append(item);
  });
  const versionsTitle = document.createElement("h4");
  versionsTitle.textContent = "Exact version records loaded from the saved history API";
  const timeline = document.createElement("div");
  timeline.className = "version-timeline compact-version-timeline";
  (history.versions.versions || []).forEach((version) => {
    const card = document.createElement("article");
    card.className = "version-card";
    const record = version.record || {};
    const heading = document.createElement("h4");
    heading.textContent = display(record.accession_version, version.requested_identifier);
    const fields = document.createElement("dl");
    fields.className = "version-summary";
    addDefinition(fields, "Gene", record.genes);
    addDefinition(fields, "Germline classification", record.germline?.classification);
    addDefinition(fields, "Review status", record.germline?.review_status);
    addDefinition(fields, "Last updated", record.date_last_updated);
    addDefinition(fields, "Raw artifact", `raw/${version.requested_identifier}.xml`);
    const exact = document.createElement("details");
    const exactLabel = document.createElement("summary");
    exactLabel.textContent = "Show exact parsed version record";
    const pre = document.createElement("pre");
    pre.className = "json-record";
    pre.textContent = JSON.stringify(version, null, 2);
    exact.append(exactLabel, pre);
    card.append(heading, fields, exact);
    timeline.append(card);
  });
  container.append(manifestTitle, sources, versionsTitle, timeline);
}

async function loadHistory(accession, container) {
  if (container.dataset.loaded === "true") return;
  container.textContent = "Loading exact saved history...";
  try {
    const history = await api(`/api/vcv-histories/${encodeURIComponent(accession)}`);
    renderHistory(container, history);
    container.dataset.loaded = "true";
  } catch (error) {
    container.textContent = `Could not load exact history: ${error.message}`;
    container.className = "error-message";
  }
}

async function review(accession, action, note, message) {
  if (action === "add_note" && !note.trim()) {
    message.textContent = "Enter a new review note first.";
    message.className = "error-message";
    return;
  }
  if ((action === "mark_ambiguous" || action === "exclude") && !note.trim()) {
    message.textContent = "A manual note is required for ambiguous or excluded results.";
    message.className = "error-message";
    return;
  }
  const body = {action};
  if (note.trim()) body.changes = {notes: note.trim()};
  try {
    await api(`/api/vcv-histories/${encodeURIComponent(accession)}/review`, {method: "PATCH", body: JSON.stringify(body)});
    await loadResults();
  } catch (error) {
    message.textContent = `Review rejected: ${error.message}`;
    message.className = "error-message";
  }
}

function resultCase(row) {
  const details = document.createElement("details");
  details.className = "pilot-case";
  const heading = document.createElement("summary");
  const title = document.createElement("strong");
  title.textContent = `${row["VCV accession"]} | ${display(row.gene)}`;
  const category = document.createElement("span");
  category.className = "result-category";
  category.textContent = row["detected change category"].replaceAll("_", " ");
  heading.append(title, category);
  const body = document.createElement("div");
  body.className = "pilot-case-body";
  const fields = document.createElement("dl");
  fields.className = "pilot-case-fields";
  [
    ["Accession", row["VCV accession"]], ["Genes", row.gene],
    ["First classification", row["first aggregate germline classification"]],
    ["Latest classification", row["newest aggregate germline classification"]],
    ["Versions", `${row["first version"]} to ${row["newest version"]} (${row["versions retrieved"]} retrieved)`],
    ["Category", row["detected change category"]], ["Confidence", row["automatic confidence"]],
    ["Automatic result", row["automatic result"]], ["Manual result", row["manual confirmed result"]],
    ["Review status", row["manually reviewed status"]], ["Warnings", row.warnings],
  ].forEach(([label, value]) => addDefinition(fields, label, value));
  const reviewBox = document.createElement("div");
  reviewBox.className = "manual-review-box";
  const noteLabel = document.createElement("label");
  noteLabel.textContent = "Manual review note";
  const note = document.createElement("textarea");
  note.maxLength = 20000;
  noteLabel.append(note);
  const actions = document.createElement("div");
  actions.className = "button-row";
  const message = document.createElement("p");
  [["Add Review Note", "add_note"], ["Mark Verified", "mark_manually_verified"], ["Mark Ambiguous", "mark_ambiguous"], ["Mark Excluded", "exclude"]].forEach(([label, action]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", () => review(row["VCV accession"], action, note.value, message));
    actions.append(button);
  });
  const checklist = document.createElement("p");
  checklist.append(document.createTextNode("Mark Verified uses the existing exact checklist and will be rejected until every item is complete. "));
  const explorer = document.createElement("a");
  explorer.href = `/version_history.html#history-review`;
  explorer.textContent = "Open Version History Explorer to complete the exact checklist.";
  checklist.append(explorer);
  reviewBox.append(noteLabel, actions, message, checklist);
  const exact = document.createElement("div");
  exact.className = "exact-history";
  body.append(fields, reviewBox, exact);
  details.append(heading, body);
  details.addEventListener("toggle", () => { if (details.open) loadHistory(row["VCV accession"], exact); });
  return details;
}

function renderDownloads(outputFiles, complete) {
  document.querySelectorAll("#pilot-downloads a").forEach((link) => {
    const available = Boolean(outputFiles[link.dataset.file]);
    link.classList.toggle("download-unavailable", !available);
    link.setAttribute("aria-disabled", String(!available));
    link.onclick = available ? null : (event) => event.preventDefault();
  });
  byId("downloads-status").textContent = complete ? "All five fixed outputs are available." : "Some outputs are not available yet. A completed batch generates all five together.";
}

async function loadResults() {
  try {
    const payload = await api("/api/pilot-results");
    byId("real-data-notice").textContent = payload.summary.notice;
    renderSummary(payload.summary);
    const cases = byId("result-cases");
    cases.replaceChildren(...payload.rows.map(resultCase));
    byId("results-empty").hidden = payload.rows.length !== 0;
    renderDownloads(payload.output_files, payload.all_outputs_exist);
    status("results-status", `${payload.summary.candidates_attempted} attempted candidate(s); generated ${payload.summary.generated_at_utc}.`);
  } catch (error) {
    status("results-status", `Could not load pilot results: ${error.message}`, true);
  }
}

byId("batch-plan-form").addEventListener("submit", planBatch);
byId("batch-confirmation").addEventListener("change", (event) => { byId("run-batch").disabled = !event.target.checked; });
byId("run-batch").addEventListener("click", runBatch);
byId("cancel-batch").addEventListener("click", cancelBatch);
byId("refresh-results").addEventListener("click", loadResults);
loadResults();
