"""Retrieve one current ClinVar variant summary through official NCBI E-utilities."""

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

import requests

CLINVAR_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CLINVAR_VARIATION_URL = "https://www.ncbi.nlm.nih.gov/clinvar/variation/{variation_id}/"
DEFAULT_TIMEOUT_SECONDS = 15
NCBI_TOOL_NAME = "variant_time_machine"


class ClinVarAPIError(RuntimeError):
    """Base error for a ClinVar API lookup."""


class InvalidVariantIdentifier(ClinVarAPIError):
    """Raised when an identifier is not a Variation ID or VCV accession."""


class ClinVarConnectionError(ClinVarAPIError):
    """Raised when NCBI cannot be reached or returns an HTTP error."""


class ClinVarRecordNotFound(ClinVarAPIError):
    """Raised when NCBI returns no ClinVar record for the identifier."""


class ClinVarResponseError(ClinVarAPIError):
    """Raised when the official API response is incomplete or malformed."""


@dataclass(frozen=True)
class ClinVarVariant:
    """Clean fields from one current ClinVar ESummary record."""

    variant_identifier: str
    variation_id: str
    gene_name: str | None
    classification: str | None
    associated_conditions: tuple[str, ...]
    review_status: str | None
    evidence_summary: str | None
    source_url: str
    retrieved_at_utc: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly dictionary."""
        result = asdict(self)
        result["associated_conditions"] = list(self.associated_conditions)
        return result


def normalize_variant_identifier(identifier: str) -> str:
    """Convert a numeric Variation ID or VCV accession to a numeric ID string."""
    cleaned = identifier.strip()
    if cleaned.isdigit():
        variation_id = str(int(cleaned))
    else:
        match = re.fullmatch(r"VCV0*(\d+)(?:\.\d+)?", cleaned, flags=re.IGNORECASE)
        if not match:
            raise InvalidVariantIdentifier(
                "Enter a numeric ClinVar Variation ID or a VCV accession such as "
                "VCV000014206."
            )
        variation_id = str(int(match.group(1)))

    if variation_id == "0":
        raise InvalidVariantIdentifier(
            "ClinVar Variation ID must be greater than zero."
        )
    return variation_id


def _clean_text(value: object) -> str | None:
    """Return stripped text or ``None`` for an empty value."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _unique_text(values: list[object]) -> tuple[str, ...]:
    """Return nonempty text values once, preserving their first order."""
    result: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _evidence_summary(record: dict[str, object]) -> str | None:
    """Summarize only evidence metadata present in the ESummary response."""
    parts: list[str] = []
    supporting = record.get("supporting_submissions")
    if isinstance(supporting, dict):
        scv_records = supporting.get("scv", [])
        rcv_records = supporting.get("rcv", [])
        if isinstance(scv_records, list):
            parts.append(f"SCV submissions listed: {len(scv_records)}")
        if isinstance(rcv_records, list):
            parts.append(f"RCV records listed: {len(rcv_records)}")

    germline = record.get("germline_classification")
    if isinstance(germline, dict):
        last_evaluated = _clean_text(germline.get("last_evaluated"))
        if last_evaluated:
            parts.append(f"Last evaluated: {last_evaluated}")

    consequences = record.get("molecular_consequence_list")
    if isinstance(consequences, list):
        consequence_values = _unique_text(consequences)
        if consequence_values:
            parts.append("Molecular consequence: " + ", ".join(consequence_values))

    return "; ".join(parts) if parts else None


def lookup_clinvar_variant(
    identifier: str,
    *,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    session: requests.Session | None = None,
) -> ClinVarVariant:
    """Retrieve one current ClinVar variant summary from NCBI E-utilities.

    This function performs one small JSON request. It does not scrape web pages and
    does not download a ClinVar release.
    """
    variation_id = normalize_variant_identifier(identifier)
    request_get = session.get if session is not None else requests.get

    try:
        response = request_get(
            CLINVAR_ESUMMARY_URL,
            params={
                "db": "clinvar",
                "id": variation_id,
                "retmode": "json",
                "tool": NCBI_TOOL_NAME,
            },
            headers={"User-Agent": "VariantTimeMachine/0.1 research-education"},
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ClinVarConnectionError(
            f"Could not connect to the NCBI ClinVar API: {exc}"
        ) from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise ClinVarResponseError(
            "NCBI returned a response that was not valid JSON."
        ) from exc

    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise ClinVarResponseError("NCBI response did not contain a result object.")
    uids = result.get("uids")
    if not isinstance(uids, list) or not uids:
        raise ClinVarRecordNotFound(
            f"No ClinVar record was found for Variation ID {variation_id}."
        )

    returned_id = str(uids[0])
    record = result.get(returned_id)
    if not isinstance(record, dict):
        raise ClinVarResponseError(
            "NCBI response did not contain the requested record."
        )

    genes = record.get("genes")
    gene_names: tuple[str, ...] = ()
    if isinstance(genes, list):
        gene_names = _unique_text(
            [gene.get("symbol") for gene in genes if isinstance(gene, dict)]
        )

    germline = record.get("germline_classification")
    classification = None
    review_status = None
    conditions: tuple[str, ...] = ()
    if isinstance(germline, dict):
        classification = _clean_text(germline.get("description"))
        review_status = _clean_text(germline.get("review_status"))
        trait_set = germline.get("trait_set")
        if isinstance(trait_set, list):
            conditions = _unique_text(
                [
                    trait.get("trait_name")
                    for trait in trait_set
                    if isinstance(trait, dict)
                ]
            )

    accession = _clean_text(record.get("accession_version"))
    if accession is None:
        accession = (
            _clean_text(record.get("accession")) or f"Variation ID {returned_id}"
        )

    return ClinVarVariant(
        variant_identifier=accession,
        variation_id=returned_id,
        gene_name=", ".join(gene_names) if gene_names else None,
        classification=classification,
        associated_conditions=conditions,
        review_status=review_status,
        evidence_summary=_evidence_summary(record),
        source_url=CLINVAR_VARIATION_URL.format(variation_id=returned_id),
        retrieved_at_utc=datetime.now(UTC).isoformat(),
    )
