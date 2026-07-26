"use strict";

const showValue = (value) => value || "Data unavailable";

function releaseCard(label, release) {
  const card = document.createElement("article");
  card.className = "release-card";
  const title = document.createElement("h3");
  title.textContent = `${label[0].toUpperCase()}${label.slice(1)}: ${release.release_date}`;
  const facts = document.createElement("p");
  facts.textContent = `${release.schema_version}; ${(release.compressed_size_bytes / 1e9).toFixed(2)} GB compressed`;
  const source = document.createElement("a");
  source.href = release.source_url;
  source.textContent = "Official NCBI archive";
  source.rel = "noreferrer";
  source.target = "_blank";
  card.append(title, facts, source);
  return card;
}

function detail(label, value) {
  const line = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = `${label}: `;
  line.append(strong, document.createTextNode(showValue(value)));
  return line;
}

async function saveReview(variationId, select, notes, message) {
  message.textContent = "Saving...";
  const response = await fetch(`/api/pilot/review/${encodeURIComponent(variationId)}`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({status: select.value, notes: notes.value}),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Review could not be saved.");
  message.textContent = "Saved locally.";
}

function reviewCell(row, statuses) {
  const cell = document.createElement("td");
  const form = document.createElement("form");
  form.className = "review-form";
  const select = document.createElement("select");
  select.setAttribute("aria-label", `Review status for Variation ID ${row.variation_id}`);
  statuses.forEach((status) => {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    option.selected = status === row.manual_review.status;
    select.append(option);
  });
  const notes = document.createElement("textarea");
  notes.value = row.manual_review.notes || "";
  notes.maxLength = 2000;
  notes.rows = 3;
  notes.placeholder = "Evidence checked and questions";
  notes.setAttribute("aria-label", `Review notes for Variation ID ${row.variation_id}`);
  const button = document.createElement("button");
  button.type = "submit";
  button.textContent = "Save review";
  const message = document.createElement("small");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveReview(row.variation_id, select, notes, message);
    } catch (error) {
      message.textContent = error.message;
    }
  });
  form.append(select, notes, button, message);
  cell.append(form);
  return cell;
}

function pilotRow(row, statuses) {
  const tableRow = document.createElement("tr");
  const variant = document.createElement("td");
  const link = document.createElement("a");
  link.href = row.current_source_url;
  link.target = "_blank";
  link.rel = "noreferrer";
  link.textContent = `Variation ID ${row.variation_id}`;
  variant.append(link, detail("Accession", row.current_accession));
  const current = document.createElement("td");
  current.append(
    detail("Gene", row.current_gene),
    detail("Germline", row.current_germline_classification),
    detail("Review", row.current_review_status),
  );
  const older = document.createElement("td");
  older.append(detail("Germline", row.older_germline_classification));
  const newer = document.createElement("td");
  newer.append(detail("Germline", row.newer_germline_classification));
  const automatic = document.createElement("td");
  automatic.append(
    detail("Match", row.match_status),
    detail("Change", row.classification_change),
    detail("Status", "Requires manual review"),
  );
  tableRow.append(variant, current, older, newer, automatic, reviewCell(row, statuses));
  return tableRow;
}

async function loadPilot() {
  const response = await fetch("/api/pilot");
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Pilot data could not be loaded.");
  document.querySelector("#pilot-notice").textContent = payload.notice;
  document.querySelector("#pilot-data-status").textContent = payload.historical_data_status;
  const releaseGrid = document.querySelector("#release-grid");
  releaseGrid.replaceChildren(
    ...Object.entries(payload.releases).map(([label, release]) => releaseCard(label, release)),
  );
  const body = document.querySelector("#pilot-body");
  body.replaceChildren(...payload.rows.map((row) => pilotRow(row, payload.review_statuses)));
}

loadPilot().catch((error) => {
  const body = document.querySelector("#pilot-body");
  body.innerHTML = '<tr><td colspan="6"></td></tr>';
  body.querySelector("td").textContent = error.message;
});
