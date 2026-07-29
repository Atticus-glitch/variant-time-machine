"use strict";

const byId = (id) => document.getElementById(id);

async function loadOverview() {
  try {
    const [response, predictionResponse] = await Promise.all([
      fetch("/api/historical-variants?change_status=Resolved_direction&page_size=1", {headers: {Accept: "application/json"}}),
      fetch("/api/predictions/summary", {headers: {Accept: "application/json"}}),
    ]);
    const [payload, predictions] = await Promise.all([response.json(), predictionResponse.json()]);
    if (!response.ok) throw new Error(payload.error || `Request returned ${response.status}`);
    byId("overview-total").textContent = Number(payload.metadata.variant_count).toLocaleString();
    byId("overview-vus-updated").textContent = Number(payload.total).toLocaleString();
    byId("overview-database").textContent = "Ready";
    byId("overview-built").textContent = `Built ${payload.metadata.built_at_utc}`;
    byId("overview-status").textContent = `Live local index ready: ${Number(payload.total).toLocaleString()} older-VUS records with changed 2024 classification text.`;
    const baseline = byId("overview-baseline"); baseline.replaceChildren();
    if (predictionResponse.ok && predictions.available) {
      const summary = predictions.summary;
      byId("overview-vus-updated").textContent = summary.resolved_direction_records.toLocaleString();
      byId("overview-status").textContent = `Resolved Direction V2 is ready: ${summary.resolved_direction_records.toLocaleString()} clear pathogenic-or-benign outcomes.`;
      [["Resolved cohort", summary.resolved_direction_records.toLocaleString()], ["Actual pathogenic", summary.actual_pathogenic.toLocaleString()], ["Actual benign", summary.actual_benign.toLocaleString()], ["Predictions", summary.predictions_made.toLocaleString()], ["Correct", summary.correct.toLocaleString()], ["Wrong", summary.wrong.toLocaleString()], ["No prediction", summary.no_prediction.toLocaleString()], ["Accuracy", `${(summary.overall_accuracy * 100).toFixed(1)}%`], ["Balanced accuracy", `${(summary.balanced_accuracy * 100).toFixed(1)}%`]].forEach(([label, value]) => {
        const box = document.createElement("div"); const term = document.createElement("dt"); const detail = document.createElement("dd"); term.textContent = label; detail.textContent = value; box.append(term, detail); baseline.append(box);
      });
    } else {
      baseline.textContent = "Resolved Direction V2 has not been run yet.";
    }
  } catch (error) {
    byId("overview-database").textContent = "Unavailable";
    byId("overview-built").textContent = error.message;
    byId("overview-status").textContent = `Historical index unavailable: ${error.message}`;
  }
}

loadOverview();
