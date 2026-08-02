"use strict";

const byId = (id) => document.getElementById(id);
const MODELS = ["V4", "V5", "V6", "V7", "V8"];
let allRows = [];
let currentId = null;
let currentGene = "";
let currentPage = 1;
let lastDetailTrigger = null;
const PAGE_SIZE = 24;

const label = (value) => value === null || value === undefined
  ? "Not evaluated in this model test"
  : String(value).replaceAll("_", " ");

function resultClass(correct, status) {
  if (["ambiguous", "unreviewed"].includes(status)) return "result-review";
  if (correct === true) return "result-correct";
  if (correct === false) return "result-wrong";
  return "result-neutral";
}

function card(row) {
  const article = document.createElement("article");
  const correctness = row.v8_correct ?? row.v7_correct ?? row.v6_correct
    ?? row.v5_correct ?? row.v4_correct;
  article.className = `prediction-card explorer-card ${resultClass(correctness, row.manual_review_status)}`;
  const title = document.createElement("strong");
  title.textContent = `Variation ${row.variation_id} | ${row.gene}`;
  const visible = document.createElement("p");
  const modelResults = MODELS.filter(
    (model) => row[`${model.toLowerCase()}_prediction`] !== null,
  ).map((model) => {
    const prefix = model.toLowerCase();
    return `${model}: ${label(row[`${prefix}_prediction`])} (${label(row[`${prefix}_correct`])})`;
  });
  visible.textContent = `Normalized later outcome: ${label(row.actual_outcome)} | ${modelResults.join(" | ")} | Review: ${row.manual_review_status}`;
  const button = document.createElement("button");
  button.textContent = "Open explanation";
  button.addEventListener("click", () => {
    lastDetailTrigger = button;
    loadDetail(row.variation_id);
  });
  article.append(title, visible, button);
  return article;
}

function renderRows() {
  const query = byId("explorer-search").value.trim().toLowerCase();
  const model = byId("explorer-model").value;
  const correctness = byId("explorer-correctness").value;
  const review = byId("explorer-review").value;
  const rows = allRows.filter((row) => {
    const matchesQuery = !query || row.variation_id.includes(query)
      || row.gene.toLowerCase().includes(query);
    const evaluatedModels = model === "all" ? MODELS : [model];
    const matchesModel = model === "all"
      || row[`${model.toLowerCase()}_prediction`] !== null;
    const matchesCorrectness = correctness === "all" || evaluatedModels.some((item) => {
      const value = row[`${item.toLowerCase()}_correct`];
      return correctness === "correct" ? value === true : value === false;
    });
    return matchesQuery && matchesModel && matchesCorrectness
      && (review === "all" || row.manual_review_status === review);
  });
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  currentPage = Math.min(currentPage, pageCount);
  const start = (currentPage - 1) * PAGE_SIZE;
  const visibleRows = rows.slice(start, start + PAGE_SIZE);
  byId("explorer-list").replaceChildren(...visibleRows.map(card));
  byId("explorer-status").textContent = `${rows.length.toLocaleString()} of ${allRows.length.toLocaleString()} frozen predictions match; showing ${visibleRows.length}.`;
  byId("explorer-page").textContent = `Page ${currentPage} of ${pageCount}`;
  byId("explorer-previous").disabled = currentPage <= 1;
  byId("explorer-next").disabled = currentPage >= pageCount;
}

function resetAndRender() {
  currentPage = 1;
  renderRows();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {Accept: "application/json", "Content-Type": "application/json"},
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error);
  return payload;
}

function definition(container, title, value) {
  const box = document.createElement("div");
  const term = document.createElement("strong");
  term.textContent = title;
  const detail = document.createElement("span");
  detail.textContent = label(value);
  box.append(term, detail);
  container.append(box);
}

function applyReview(review) {
  byId("error-status").value = review.status || "unreviewed";
  byId("error-category").value = review.error_category || "unknown";
  byId("error-notes").value = review.notes || "";
  byId("error-review-status").textContent = review.updated_at_utc
    ? `Last saved ${review.updated_at_utc}`
    : "No manual review saved for this model prediction.";
}

function configureReviewEditor(model) {
  const isV8 = model === "V8";
  byId("save-error-review").disabled = isV8;
  byId("error-status").disabled = isV8;
  byId("error-category").disabled = isV8;
  byId("error-notes").disabled = isV8;
  byId("v8-focused-review-link").hidden = !isV8;
  if (isV8) {
    byId("v8-focused-review-link").href = `/v8_review.html?gene=${encodeURIComponent(currentGene)}`;
    byId("error-review-status").textContent = "V8 decisions use one separate authoritative review store.";
  }
}

async function loadDetail(id) {
  try {
    const row = await api(`/api/prediction-explorer/${id}`);
    currentId = id;
    currentGene = row.old_gene_symbols || row.gene || "";
    byId("explorer-detail").hidden = false;
    byId("explorer-detail-title").textContent = `Variation ${id}`;
    const identity = byId("explorer-identity");
    identity.replaceChildren();
    [
      ["Gene", row.old_gene_symbols],
      ["Older classification", row.old_classification],
      ["Later classification", row.actual_later_classification],
      ["Outcome", row.actual_outcome],
      ["Match", `${row.match_method} (${row.match_confidence})`],
      ["Older name/HGVS", row.old_names],
    ].forEach((item) => definition(identity, ...item));

    const results = byId("explorer-model-results");
    results.replaceChildren();
    MODELS.forEach((model) => {
      const value = row.model_results[model];
      definition(
        results,
        model,
        value
          ? `${label(value.predicted_class)} | model output probability ${Number(value.pathogenic_probability).toFixed(3)} | ${value.correct === "true" ? "Correct" : "Wrong"}`
          : "Not in this test set",
      );
    });

    const availableModels = Object.keys(row.model_results);
    const modelSelect = byId("error-model");
    [...modelSelect.options].forEach((option) => {
      option.disabled = !availableModels.includes(option.value);
    });
    modelSelect.value = availableModels[0];
    configureReviewEditor(modelSelect.value);

    const features = byId("explorer-features");
    features.replaceChildren();
    row.older_features.forEach((feature) => {
      const tr = document.createElement("tr");
      [feature.clue, feature.older_value, feature.applied ? "Yes" : "No", feature.source_field]
        .forEach((value) => {
          const td = document.createElement("td");
          td.textContent = label(value);
          tr.append(td);
        });
      features.append(tr);
    });

    const audit = MODELS
      .filter((model) => row.leakage_check[model])
      .map((model) => `${model} ${row.leakage_check[model]}`)
      .join("; ");
    const warnings = [
      row.explanation_boundary,
      "Displayed probabilities are model outputs, not clinical confidence.",
      `Leakage audit: ${audit}`,
      ...row.warning_flags,
    ];
    byId("explorer-warnings").replaceChildren(...warnings.map((value) => {
      const p = document.createElement("p");
      p.textContent = value;
      return p;
    }));
    applyReview(row.manual_reviews[`${modelSelect.value}:${currentId}`] || {});
    byId("explorer-detail-title").focus();
    byId("explorer-detail").scrollIntoView({behavior: "smooth"});
  } catch (error) {
    byId("explorer-status").textContent = error.message;
  }
}

async function saveReview() {
  if (!currentId) return;
  if (byId("error-model").value === "V8") {
    byId("error-review-status").textContent = "Open the focused V8 Manual Review Queue to save this decision.";
    return;
  }
  try {
    const payload = await api(
      `/api/prediction-explorer/${byId("error-model").value}/${currentId}/review`,
      {
        method: "PATCH",
        body: JSON.stringify({
          status: byId("error-status").value,
          category: byId("error-category").value,
          notes: byId("error-notes").value,
        }),
      },
    );
    byId("error-review-status").textContent = `Saved ${payload.review.status}: ${payload.review.error_category}`;
    await loadRows();
  } catch (error) {
    byId("error-review-status").textContent = `Review not saved: ${error.message}`;
  }
}

async function loadRows() {
  try {
    const payload = await api("/api/prediction-explorer");
    allRows = payload.rows;
    const categories = byId("error-category");
    if (!categories.children.length) {
      payload.allowed_error_categories.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        categories.append(option);
      });
    }
    renderRows();
  } catch (error) {
    byId("explorer-status").textContent = `Explorer unavailable: ${error.message}`;
  }
}

byId("explorer-search").addEventListener("input", resetAndRender);
byId("explorer-model").addEventListener("change", resetAndRender);
byId("explorer-correctness").addEventListener("change", resetAndRender);
byId("explorer-review").addEventListener("change", resetAndRender);
byId("explorer-filters").addEventListener("submit", (event) => event.preventDefault());
byId("explorer-previous").addEventListener("click", () => {
  if (currentPage > 1) { currentPage -= 1; renderRows(); }
});
byId("explorer-next").addEventListener("click", () => {
  currentPage += 1;
  renderRows();
});
byId("close-explorer-detail").addEventListener("click", () => {
  byId("explorer-detail").hidden = true;
  lastDetailTrigger?.focus();
});
byId("error-model").addEventListener("change", async () => {
  if (!currentId) return;
  const row = await api(`/api/prediction-explorer/${currentId}`);
  const model = byId("error-model").value;
  configureReviewEditor(model);
  applyReview(row.manual_reviews[`${model}:${currentId}`] || {});
});
byId("save-error-review").addEventListener("click", saveReview);
loadRows();
