"""Tests for the one-record official ClinVar API client."""

from typing import Any

import pytest
import requests

from variant_time_machine.clinvar_api import (
    ClinVarConnectionError,
    ClinVarRecordNotFound,
    InvalidVariantIdentifier,
    lookup_clinvar_variant,
    normalize_variant_identifier,
)


def _sample_payload() -> dict[str, object]:
    """Return a small representative ESummary response for offline tests."""
    return {
        "result": {
            "uids": ["14206"],
            "14206": {
                "uid": "14206",
                "accession": "VCV000014206",
                "accession_version": "VCV000014206.1",
                "genes": [{"symbol": "CCL2"}],
                "germline_classification": {
                    "description": "protective",
                    "review_status": "no assertion criteria provided",
                    "last_evaluated": "2003/11/07 00:00",
                    "trait_set": [{"trait_name": "Susceptibility to HIV infection"}],
                },
                "supporting_submissions": {
                    "scv": ["SCV000035529"],
                    "rcv": ["RCV000015270"],
                },
                "molecular_consequence_list": ["intron variant"],
            },
        }
    }


class FakeResponse:
    """Minimal requests response for a successful lookup."""

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class FakeSession:
    """Minimal session that records request details."""

    def __init__(
        self,
        payload: dict[str, object] | None = None,
        error: requests.RequestException | None = None,
    ) -> None:
        self.payload = payload or {}
        self.error = error
        self.last_request: dict[str, Any] | None = None

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.last_request = {"url": url, **kwargs}
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("14206", "14206"),
        ("00014206", "14206"),
        ("VCV000014206", "14206"),
        ("vcv000014206.1", "14206"),
    ],
)
def test_identifier_normalization(identifier: str, expected: str) -> None:
    """Supported numeric and VCV forms should normalize to a Variation ID."""
    assert normalize_variant_identifier(identifier) == expected


@pytest.mark.parametrize("identifier", ["", "rs123", "RCV0001", "VCV", "0"])
def test_invalid_identifiers_are_rejected_before_network(identifier: str) -> None:
    """Unsupported identifiers should produce clear local validation errors."""
    with pytest.raises(InvalidVariantIdentifier):
        normalize_variant_identifier(identifier)


def test_successful_lookup_returns_clean_structured_data() -> None:
    """A representative ESummary response should map to documented fields."""
    session = FakeSession(_sample_payload())

    result = lookup_clinvar_variant("VCV000014206", session=session)  # type: ignore[arg-type]

    assert result.variant_identifier == "VCV000014206.1"
    assert result.variation_id == "14206"
    assert result.gene_name == "CCL2"
    assert result.classification == "protective"
    assert result.associated_conditions == ("Susceptibility to HIV infection",)
    assert result.review_status == "no assertion criteria provided"
    assert "SCV submissions listed: 1" in str(result.evidence_summary)
    assert "Molecular consequence: intron variant" in str(result.evidence_summary)
    assert result.source_url.endswith("/clinvar/variation/14206/")
    assert session.last_request is not None
    assert session.last_request["params"]["db"] == "clinvar"
    assert session.last_request["params"]["id"] == "14206"


def test_network_failure_is_reported_without_fallback_data() -> None:
    """A connection error should remain an error and never create a result."""
    session = FakeSession(error=requests.ConnectionError("offline"))
    with pytest.raises(ClinVarConnectionError, match="offline"):
        lookup_clinvar_variant("14206", session=session)  # type: ignore[arg-type]


def test_missing_record_is_reported() -> None:
    """An empty official result should be reported as no record."""
    session = FakeSession({"result": {"uids": []}})
    with pytest.raises(ClinVarRecordNotFound, match="14206"):
        lookup_clinvar_variant("14206", session=session)  # type: ignore[arg-type]
