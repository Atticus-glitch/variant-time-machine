"use strict";

const byId = (id) => document.getElementById(id);
const MODELS = ["V4", "V5", "V6", "V7", "V8"];
let allRows = [];
let currentId = null;

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
  const modelResults = MODELS.map((model) => {
    const prefix = model.toLowerCase();
    return `${model}: ${label(row[`${prefix}_prediction`])} (${label(row[`${prefix}_correct`])})`;
  });
  visible.textContent = `Normalized later outcome: ${label(row.actual_outcome)} | ${modelResults.join(" | ")} | Review: ${row.manual_review_status}`;
  const button = document.createElement("button");
  button.textContent = "Open explanation";
  button.addEventListener("click", () => loadDetail(row.variation_id));
  article.append(title, visible, button);
  return article;
}

function renderRows() {
  const query = byId("explorer-search").value.trim().toLowerCase();
  const rows = allRows.filter((row) => !query
    || row.variation_id.includes(query)
    || row.gene.toLowerCase().includes(query));
  byId("explorer-list").replaceChildren(...rows.map(card));
  byId("explorer-status").textContent = `${rows.length} of ${allRows.length} frozen predictions shown.`;
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

async function loadDetail(id) {
  try {
    const row = await api(`/api/prediction-explorer/${id}`);
    currentId = id;
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
    byId("explorer-detail").scrollIntoView({behavior: "smooth"});
  } catch (error) {
    byId("explorer-status").textContent = error.message;
  }
}

async function saveReview() {
  if (!currentId) return;
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

byId("explorer-search").addEventListener("input", renderRows);
byId("close-explorer-detail").addEventListener("click", () => {
  byId("explorer-detail").hidden = true;
});
byId("error-model").addEventListener("change", async () => {
  if (!currentId) return;
  const row = await api(`/api/prediction-explorer/${currentId}`);
  const model = byId("error-model").value;
  applyReview(row.manual_reviews[`${model}:${currentId}`] || {});
});
byId("save-error-review").addEventListener("click", saveReview);
loadRows();
