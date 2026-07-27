"use strict";

const text = (value, fallback = "Not available") => {
  if (value === null || value === undefined || value === "") {
    return fallback;
  }
  return String(value);
};

const statusClass = (status) =>
  `status-${status.toLowerCase().replaceAll(" ", "-")}`;

async function fetchJson(path) {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

function renderProgress(data) {
  const grid = document.querySelector("#progress-grid");
  grid.replaceChildren();

  for (const item of data.items) {
    const article = document.createElement("article");
    article.className = "progress-item";

    const heading = document.createElement("h3");
    heading.textContent = `Step ${item.step}: ${item.name}`;

    const badge = document.createElement("span");
    badge.className = `status-badge ${statusClass(item.status)}`;
    badge.textContent = item.status;

    const explanation = document.createElement("p");
    explanation.textContent = item.explanation;

    article.append(heading, badge, explanation);
    grid.append(article);
  }
}

function renderDataset(data) {
  document.querySelector("#dataset-notice").textContent = data.notice;
  document.querySelector("#dataset-source").textContent = `Source: ${data.source}`;

  const body = document.querySelector("#dataset-body");
  body.replaceChildren();
  for (const row of data.rows) {
    const tableRow = document.createElement("tr");
    const values = [
      row.variant_id,
      row.gene,
      row.old_classification,
      row.new_classification,
      row.result,
    ];
    for (const value of values) {
      const cell = document.createElement("td");
      cell.textContent = text(value);
      tableRow.append(cell);
    }
    body.append(tableRow);
  }
}

function renderFolders(folders) {
  const grid = document.querySelector("#folder-grid");
  grid.replaceChildren();
  for (const folder of folders) {
    const article = document.createElement("article");
    article.className = "folder-item";
    const name = document.createElement("code");
    name.textContent = folder.folder;
    const purpose = document.createElement("p");
    purpose.textContent = folder.purpose;
    article.append(name, purpose);
    grid.append(article);
  }
}

function renderNextTasks(tasks) {
  const list = document.querySelector("#next-tasks");
  list.replaceChildren();
  for (const task of tasks) {
    const item = document.createElement("li");
    item.textContent = task;
    list.append(item);
  }
}

function addStatusRow(list, label, value) {
  const wrapper = document.createElement("div");
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;

  if (Array.isArray(value)) {
    if (value.length === 0) {
      description.textContent = "None";
    } else {
      const items = document.createElement("ul");
      for (const entry of value) {
        const item = document.createElement("li");
        item.textContent = entry;
        items.append(item);
      }
      description.append(items);
    }
  } else {
    description.textContent = text(value);
  }

  wrapper.append(term, description);
  list.append(wrapper);
}

function renderStatus(data) {
  document.querySelector("#project-name").textContent = data.project_name;
  document.querySelector("#current-milestone").textContent =
    data.current_milestone;
  document.querySelector("#project-explanation").textContent =
    data.project_explanation;
  renderFolders(data.folders);
  renderNextTasks(data.next_tasks);
  renderClinVarConnection(data.clinvar_connection);
  renderHistoricalComparison(data.historical_comparison);
  renderTransferSafety(data.transfer_safety);
  renderCurrentPilot(data.current_pilot_variant);
  renderResearchProgress(data.research_progress);

  const list = document.querySelector("#system-status");
  list.replaceChildren();
  addStatusRow(list, "Python", data.system.python_environment);
  addStatusRow(list, "Data storage", data.system.database);
  addStatusRow(list, "Tests", data.system.tests);
  addStatusRow(list, "Last timeline", data.system.last_pipeline_run);
  addStatusRow(list, "Files shown", data.system.files_created);
  addStatusRow(list, "Large ClinVar files", data.system.raw_clinvar_files);

  document.querySelector("#notes-entry-title").textContent =
    data.research_notes.title;
  document.querySelector("#notes-entry-content").textContent =
    data.research_notes.content;
}

function renderResearchProgress(progress) {
  const list = document.querySelector("#research-progress");
  list.replaceChildren();
  const fields = [
    ["Candidates selected", progress.candidates_selected],
    ["Current VCV records retrieved", progress.current_records_retrieved],
    ["Histories explored", progress.histories_explored],
    ["Versions retrieved", progress.versions_retrieved],
    ["Histories with germline changes", progress.histories_with_germline_change],
    ["Histories manually verified", progress.manually_verified],
    ["Recorded history transfer", `${progress.total_recorded_history_transfer_bytes.toLocaleString()} bytes`],
    ["Local VCV pilot storage", progress.storage],
  ];
  for (const [label, value] of fields) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = value;
    wrapper.append(term, detail);
    list.append(wrapper);
  }
}

function renderCurrentPilot(pilot) {
  document.querySelector("#pilot-current-variant").textContent = pilot.variant;
  document.querySelector("#pilot-current-gene").textContent = pilot.gene;
  document.querySelector("#pilot-current-classification").textContent =
    pilot.current_classification;
  document.querySelector("#pilot-historical-status").textContent =
    pilot.historical_status;
  document.querySelector("#pilot-verification-status").textContent =
    pilot.verification_status;
  const timeline = document.querySelector("#pilot-timeline");
  timeline.replaceChildren();
  if (!pilot.selected) {
    const empty = document.createElement("li");
    empty.textContent = "No timeline exists until a pilot variant is selected.";
    timeline.append(empty);
    return;
  }
  if (pilot.timeline.older.classification) {
    const older = document.createElement("li");
    older.textContent = `${pilot.timeline.older.date}: ${pilot.timeline.older.classification}`;
    timeline.append(older);
  }
  const change = document.createElement("li");
  change.textContent = pilot.timeline.change_category;
  timeline.append(change);
}

function renderTransferSafety(safety) {
  const list = document.querySelector("#transfer-safety");
  list.replaceChildren();
  const fields = [
    ["Largest planned download", safety.largest_planned_download],
    ["Current transfer", safety.current_transfer],
    ["Total downloaded", safety.total_downloaded],
    ["Storage used", safety.storage_used],
    ["Large download protection", safety.large_download_protection],
  ];
  for (const [label, value] of fields) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const description = document.createElement("dd");
    term.textContent = label;
    description.textContent = value;
    if (label === "Large download protection") {
      description.className = "protection-on";
    }
    wrapper.append(term, description);
    list.append(wrapper);
  }
}

function renderHistoricalComparison(history) {
  document.querySelector("#verified-total").textContent =
    history.total_verified_variants;
  document.querySelector("#verified-changes").textContent =
    history.variants_with_classification_changes;
  document.querySelector("#last-comparison").textContent =
    history.last_verified_comparison;
}

function renderClinVarConnection(connection) {
  document.querySelector("#clinvar-connection-status").textContent =
    connection.connection_status;
  document.querySelector("#clinvar-connection-message").textContent =
    connection.message;
  const lookup = connection.last_lookup;
  document.querySelector("#last-variant").textContent = text(
    lookup?.variant,
    "No lookup yet",
  );
  document.querySelector("#last-gene").textContent = text(
    lookup?.gene,
    "No lookup yet",
  );
  document.querySelector("#last-classification").textContent = text(
    lookup?.classification,
    "No lookup yet",
  );
}

function renderError(error) {
  const health = document.querySelector("#dashboard-health");
  health.className = "error-message";
  health.textContent = `Local API error: ${error.message}`;
}

async function loadDashboard() {
  try {
    const [status, progress, dataset] = await Promise.all([
      fetchJson("/api/status"),
      fetchJson("/api/progress"),
      fetchJson("/api/dataset"),
    ]);
    renderStatus(status);
    renderProgress(progress);
    renderDataset(dataset);
    document.querySelector("#dashboard-health").textContent =
      "Local API connected";
  } catch (error) {
    renderError(error);
  }
}

loadDashboard();
