"use strict";

const state = {page: 1, pageCount: 1, pageSize: 50};
const byId = (id) => document.getElementById(id);
let lastDetailTrigger = null;

async function api(path) {
  const response = await fetch(path, {headers: {Accept: "application/json"}});
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request returned ${response.status}`);
  return payload;
}

function display(value, fallback = "Not listed") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function short(value, length = 90) {
  const text = display(value);
  return text.length > length ? `${text.slice(0, length - 1)}...` : text;
}

function addCell(row, value, className = "") {
  const cell = document.createElement("td");
  cell.textContent = display(value);
  cell.title = display(value);
  if (className) cell.className = className;
  row.append(cell);
}

function renderRows(rows) {
  const body = byId("variant-rows");
  body.replaceChildren();
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "No variants matched this search.";
    row.append(cell);
    body.append(row);
    return;
  }
  rows.forEach((variant) => {
    const row = document.createElement("tr");
    addCell(row, variant.variation_id, "identifier-cell");
    const identity = document.createElement("td");
    identity.className = "variant-summary-cell";
    const gene = document.createElement("strong");
    gene.textContent = short(variant.old_gene_symbols || variant.new_gene_symbols, 35);
    const name = document.createElement("small");
    name.textContent = short(variant.old_names || variant.new_names, 52);
    identity.append(gene, name);
    row.append(identity);
    addCell(row, short(variant.old_classifications));
    addCell(row, short(variant.new_classifications));
    addCell(row, variant.change_status.replaceAll("_", " "), `change-${variant.change_status}`);
    const action = document.createElement("td");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "table-action";
    button.textContent = "Open timeline";
    button.addEventListener("click", () => {
      lastDetailTrigger = button;
      loadDetail(variant.variation_id);
    });
    action.append(button);
    row.append(action);
    body.append(row);
  });
}

function queryPath() {
  const parameters = new URLSearchParams({
    query: byId("variant-query").value.trim(),
    change_status: byId("change-filter").value,
    page: String(state.page),
    page_size: String(state.pageSize),
  });
  return `/api/historical-variants?${parameters}`;
}

async function loadRows() {
  byId("spreadsheet-status").textContent = "Loading variants...";
  try {
    const payload = await api(queryPath());
    state.pageCount = Math.max(1, payload.page_count);
    renderRows(payload.rows);
    byId("spreadsheet-status").textContent = `${payload.total.toLocaleString()} matching variants. Index contains ${Number(payload.metadata.variant_count).toLocaleString()} unique Variation IDs.`;
    byId("page-status").textContent = `Page ${payload.page.toLocaleString()} of ${state.pageCount.toLocaleString()}`;
    byId("previous-page").disabled = state.page <= 1;
    byId("next-page").disabled = state.page >= state.pageCount;
  } catch (error) {
    byId("variant-rows").replaceChildren();
    byId("spreadsheet-status").textContent = `Spreadsheet unavailable: ${error.message}`;
    byId("spreadsheet-status").className = "error-message";
  }
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

function snapshotCard(snapshot) {
  const card = document.createElement("article");
  card.className = "snapshot-card";
  const heading = document.createElement("h3");
  heading.textContent = `${snapshot.release_date} ${snapshot.release_role} snapshot`;
  const summary = document.createElement("dl");
  summary.className = "snapshot-fields";
  [
    ["Classification", snapshot.clinical_significances],
    ["Last evaluated", snapshot.last_evaluated_dates],
    ["Review status", snapshot.review_statuses],
    ["Submitter counts reported", snapshot.submitter_counts],
    ["Gene", snapshot.gene_symbols],
    ["Gene IDs", snapshot.gene_ids],
    ["HGNC IDs", snapshot.hgnc_ids],
    ["Name / HGVS", snapshot.names],
    ["Allele IDs", snapshot.allele_ids],
    ["dbSNP rs IDs", snapshot.rs_ids],
    ["dbVar IDs", snapshot.dbvar_ids],
    ["Variant type", snapshot.variant_types],
    ["Conditions", snapshot.phenotypes],
    ["Phenotype IDs", snapshot.phenotype_ids],
    ["RCV accessions", snapshot.rcv_accessions],
    ["Origins", snapshot.origins],
    ["Simplified origins", snapshot.origin_simple_values],
    ["Assemblies", snapshot.assemblies],
    ["Coordinates and alleles", snapshot.coordinates],
    ["Cytogenetic locations", snapshot.cytogenetic_values],
    ["Guidelines", snapshot.guidelines_values],
    ["Tested in GTR", snapshot.tested_in_gtr_values],
    ["Other IDs", snapshot.other_ids_values],
    ["Submitter categories", snapshot.submitter_categories_values],
    ["Source rows combined", snapshot.source_row_count],
  ].forEach(([label, value]) => addDefinition(summary, label, value));
  card.append(heading, summary);
  return card;
}

async function loadDetail(variationId) {
  const section = byId("variant-detail");
  const timeline = byId("snapshot-timeline");
  section.hidden = false;
  timeline.className = "snapshot-timeline";
  timeline.textContent = "Loading complete snapshot details...";
  section.scrollIntoView({behavior: "smooth", block: "start"});
  try {
    const payload = await api(`/api/historical-variants/${encodeURIComponent(variationId)}`);
    byId("detail-title").textContent = `Variation ID ${variationId}`;
    byId("detail-title").focus();
    byId("detail-note").replaceChildren();
    const source = document.createElement("a");
    source.href = `https://www.ncbi.nlm.nih.gov/clinvar/variation/${variationId}/`;
    source.target = "_blank";
    source.rel = "noreferrer";
    source.textContent = "Open the current official ClinVar variation page";
    byId("detail-note").append(document.createTextNode(`${payload.variant.change_status.replaceAll("_", " ")}. `), source, document.createTextNode(". Snapshot values below are preserved separately."));
    timeline.replaceChildren(...payload.snapshots.map(snapshotCard));
  } catch (error) {
    timeline.textContent = `Could not load this variant: ${error.message}`;
    timeline.className = "error-message";
  }
}

byId("variant-search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  state.page = 1;
  loadRows();
});
byId("clear-search").addEventListener("click", () => {
  byId("variant-query").value = "";
  byId("change-filter").value = "Resolved_direction";
  state.page = 1;
  loadRows();
});
byId("previous-page").addEventListener("click", () => { if (state.page > 1) { state.page -= 1; loadRows(); } });
byId("next-page").addEventListener("click", () => { if (state.page < state.pageCount) { state.page += 1; loadRows(); } });
byId("page-size").addEventListener("change", (event) => { state.pageSize = Number(event.target.value); state.page = 1; loadRows(); });
byId("close-detail").addEventListener("click", () => {
  byId("variant-detail").hidden = true;
  lastDetailTrigger?.focus();
});
const initialQuery = new URLSearchParams(window.location.search).get("query");
if (initialQuery) byId("variant-query").value = initialQuery;
loadRows();
