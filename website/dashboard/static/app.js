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
  renderClueScoreProgress(data.clue_score_baseline);
  renderModelValidation(data.model_validation);

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

function renderModelValidation(summary) {
  const list = document.querySelector("#model-validation-summary");
  const warnings = document.querySelector("#model-validation-warnings");
  list.replaceChildren(); warnings.replaceChildren();
  if (summary.available === false) { addStatusRow(list, "Status", "Registry unavailable"); }
  else {
    const pct = (value) => typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "Not recorded";
    const fields = [
      ["Project stage", summary.project_stage], ["Latest model", summary.latest_model_version], ["Current conclusion", summary.best_validated_model],
      ["V4 accuracy", pct(summary.v4?.accuracy)], ["V4 balanced accuracy", pct(summary.v4?.balanced_accuracy)],
      ["V5 accuracy", pct(summary.v5?.accuracy)], ["V5 balanced accuracy", pct(summary.v5?.balanced_accuracy)],
      ["V6 accuracy", pct(summary.v6?.accuracy)], ["V6 balanced accuracy", pct(summary.v6?.balanced_accuracy)],
      ["V7 accuracy", pct(summary.v7?.accuracy)], ["V7 balanced accuracy", pct(summary.v7?.balanced_accuracy)],
      ["V7 temporal boundary", "January 2024 predictions → July 2026 answers; 1,000 IDs absent from development"],
      ["Test sizes", "V4: 100; V5: 100; V6: 1,000; V7: 1,000 (different cohorts)"], ["Leakage audits", Object.entries(summary.leakage_audit_status || {}).map(([key, value]) => `${key}: ${value}`).join("; ")],
      ["Next validation", summary.next_required_validation_step], ["Upcoming deadline", summary.upcoming_deadline ? `${summary.upcoming_deadline.due_date}: ${summary.upcoming_deadline.title}` : "None"], ["GitHub", summary.github_status],
    ];
    fields.forEach(([label, value]) => addStatusRow(list, label, value));
  }
  (summary.warnings || []).forEach((value) => { const item = document.createElement("p"); item.textContent = value; warnings.append(item); });
}

function renderClueScoreProgress(progress) {
  const list = document.querySelector("#clue-score-progress");
  list.replaceChildren();
  const accuracy = progress.latest_baseline_accuracy === null ? "Not run" : `${(progress.latest_baseline_accuracy * 100).toFixed(1)}%`;
  const fields = [
    ["Cross-reference records", progress.cross_reference_records.toLocaleString()],
    ["Older VUS records", progress.older_vus_records.toLocaleString()],
    ["Eligible scoring records", progress.eligible_scoring_records.toLocaleString()],
    ["Predictions completed", progress.predictions_completed.toLocaleString()],
    ["Correct", progress.correct.toLocaleString()],
    ["Wrong", progress.wrong.toLocaleString()],
    ["No prediction", progress.no_prediction.toLocaleString()],
    ["Unscorable", progress.not_scorable.toLocaleString()],
    ["Latest baseline accuracy", accuracy],
    ["Formula version", progress.formula_version],
    ["Last run", text(progress.last_run_date, "Not run")],
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
    ["Pilot results file created", progress.pilot_results_file_created ? "Yes" : "No"],
    ["Total pilot bandwidth", `${progress.pilot_output_bandwidth_bytes.toLocaleString()} bytes`],
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
