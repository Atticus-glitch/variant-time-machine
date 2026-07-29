"use strict";

const state = {plan: null, digest: null, operationId: null, timer: null};
const byId = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {Accept: "application/json", "Content-Type": "application/json"},
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request returned ${response.status}`);
  return payload;
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes.toLocaleString()} bytes`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KiB (${bytes.toLocaleString()} bytes)`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(2)} MiB (${bytes.toLocaleString()} bytes)`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GiB (${bytes.toLocaleString()} bytes)`;
}

function addDefinition(list, label, value) {
  const item = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = String(value);
  item.append(term, detail);
  list.append(item);
}

function setStatus(message, error = false) {
  byId("plan-status").textContent = message;
  byId("plan-status").className = error ? "error-message" : "";
}

function renderPlan(plan) {
  const storage = byId("storage-plan");
  storage.replaceChildren();
  [
    ["Transfer required", formatBytes(plan.estimated_transfer_bytes)],
    ["Largest temporary partial", formatBytes(plan.estimated_temporary_bytes)],
    ["Current free space", formatBytes(plan.disk_free_bytes)],
    ["Estimated free after", formatBytes(plan.estimated_free_after_bytes)],
    ["Automatic safe limit", formatBytes(plan.safe_download_limit_bytes)],
    ["Minimum free reserve", formatBytes(plan.minimum_free_reserve_bytes)],
    ["Destination", plan.destination_dir],
    ["Decision", `${plan.allowed ? "Allowed" : "Blocked"}: ${plan.decision_reason}`],
  ].forEach(([label, value]) => addDefinition(storage, label, value));

  const rows = byId("release-plan");
  rows.replaceChildren();
  plan.releases.forEach((release) => {
    const row = document.createElement("tr");
    [release.role, release.release_date, release.source_url, formatBytes(release.expected_size_bytes), release.local_status].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });
    rows.append(row);
  });
  byId("plan-content").hidden = false;
  byId("approval-box").hidden = !plan.requires_approval || !plan.allowed;
  byId("download-confirmation").checked = false;
  byId("run-download").disabled = true;
}

async function calculatePlan() {
  try {
    state.plan = null;
    state.digest = null;
    setStatus("Calculating local storage plan...");
    const payload = await api("/api/historical-dataset/plan", {method: "POST", body: "{}"});
    state.plan = payload.plan;
    state.digest = payload.plan_digest;
    renderPlan(payload.plan);
    setStatus(payload.plan.requires_approval ? "Review every value below before approving." : payload.plan.decision_reason, !payload.plan.allowed);
  } catch (error) {
    byId("plan-content").hidden = true;
    setStatus(`Could not calculate plan: ${error.message}`, true);
  }
}

async function pollOperation() {
  try {
    const operation = await api(`/api/historical-dataset/operations/${state.operationId}`);
    byId("operation-status").textContent = `Download ${operation.state}`;
    const progress = operation.progress;
    byId("operation-progress").textContent = progress ? `${progress.filename}: ${progress.state} (${progress.index}/${progress.count})` : "Preparing storage preflight.";
    if (operation.state === "running") {
      state.timer = window.setTimeout(pollOperation, 750);
      return;
    }
    if (operation.error) setStatus(`Download failed: ${operation.error}`, true);
    else setStatus(`Download completed: ${formatBytes(operation.result.actual_bytes)} retrieved.`);
    await calculatePlan();
  } catch (error) {
    setStatus(`Could not read download progress: ${error.message}`, true);
  }
}

async function runDownload() {
  if (!state.plan || !state.digest || !byId("download-confirmation").checked) return;
  byId("run-download").disabled = true;
  try {
    const payload = await api("/api/historical-dataset/run", {
      method: "POST",
      body: JSON.stringify({approved: true, plan: state.plan, plan_digest: state.digest}),
    });
    if (!payload.operation_id) {
      setStatus(payload.message || "Release files are ready.");
      return;
    }
    state.operationId = payload.operation_id;
    byId("approval-box").hidden = true;
    byId("operation-panel").hidden = false;
    setStatus("Confirmed sequential download started.");
    await pollOperation();
  } catch (error) {
    byId("run-download").disabled = false;
    setStatus(`Could not start downloads: ${error.message}`, true);
  }
}

byId("plan-download").addEventListener("click", calculatePlan);
byId("download-confirmation").addEventListener("change", (event) => {
  byId("run-download").disabled = !event.target.checked;
});
byId("run-download").addEventListener("click", runDownload);
