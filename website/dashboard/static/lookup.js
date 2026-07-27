"use strict";

const display = (value) => {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }
  if (Array.isArray(value)) {
    return value.length ? value.join("; ") : "Not available";
  }
  return String(value);
};

const setText = (selector, value) => {
  document.querySelector(selector).textContent = display(value);
};

function showVariant(variant) {
  setText("#result-variant", variant.variant_identifier);
  setText("#result-variation-id", variant.variation_id);
  setText("#result-gene", variant.gene_name);
  setText("#result-classification", variant.classification);
  setText("#result-conditions", variant.associated_conditions);
  setText("#result-review", variant.review_status);
  setText("#result-evidence", variant.evidence_summary);

  const source = document.querySelector("#result-source");
  source.href = variant.source_url;
  source.textContent = variant.source_url;
  document.querySelector("#lookup-result").hidden = false;
}

async function runLookup(identifier) {
  const status = document.querySelector("#lookup-status");
  const result = document.querySelector("#lookup-result");
  status.className = "loading";
  status.textContent = "Contacting the official NCBI ClinVar API...";
  result.hidden = true;

  try {
    const planResponse = await fetch("/api/clinvar/plan", {
      method: "POST",
      headers: {Accept: "application/json", "Content-Type": "application/json"},
      body: JSON.stringify({query: identifier}),
    });
    const planPayload = await planResponse.json();
    if (!planResponse.ok) throw new Error(planPayload.error);
    const plan = planPayload.plan;
    const approved = window.confirm(
      `${plan.purpose}\n\nSource: ${plan.source}\nMaximum transfer: ${(plan.estimated_max_bytes / 1e6).toFixed(1)} MB\n\nStart this small request?`,
    );
    if (!approved) {
      status.textContent = "Lookup canceled. No network request started.";
      return;
    }
    const response = await fetch("/api/clinvar/lookup", {
      method: "POST",
      headers: {Accept: "application/json", "Content-Type": "application/json"},
      body: JSON.stringify({query: identifier, approved: true}),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Lookup returned ${response.status}`);
    showVariant(payload.variants[0]);
    status.className = "connection-success";
    status.textContent = `Connected. Current record received. Actual transfer: ${payload.transfer.actual_bytes} bytes.`;
  } catch (error) {
    status.className = "error-message";
    status.textContent = `Lookup failed: ${error.message}`;
  }
}

document.querySelector("#lookup-form").addEventListener("submit", (event) => {
  event.preventDefault();
  runLookup(document.querySelector("#variant-id").value);
});
