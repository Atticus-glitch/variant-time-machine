"""Focused mocked tests for bounded VCV EFetch history retrieval."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
import requests

import variant_time_machine.vcv_history as history
from variant_time_machine.vcv_history import (
    InvalidVCVAccession,
    RequestLimitError,
    TransferLimitError,
    VersionResult,
    compare_consecutive,
    fetch_current_vcv,
    fetch_vcv_history,
    parse_efetch_xml,
    plan_version_range,
    validate_vcv_accession,
)


def _xml(
    version: int,
    *,
    classification: str | None = "Uncertain significance",
    review: str = "criteria provided, single submitter",
    submissions: int = 1,
    somatic: str = "Tier II",
    status: str = "current",
    replaced_by: str | None = None,
) -> bytes:
    replacement = f'<ReplacedBy Accession="{replaced_by}" />' if replaced_by else ""
    germline_description = (
        f"<Description>{classification}</Description>" if classification else ""
    )
    return f"""<?xml version="1.0"?>
<ClinVarResult-Set xmlns="https://www.ncbi.nlm.nih.gov/clinvar/xml">
  <VariationArchive Accession="VCV000014206" Version="{version}"
      VariationID="14206" RecordType="classified" DateCreated="2020-01-01"
      DateLastUpdated="2024-02-03">
    <RecordStatus>{status}</RecordStatus>{replacement}
    <ClassifiedRecord><SimpleAllele AlleleID="99">
      <Name>NM_000001.2(CCL2):c.10A&gt;G</Name><Gene Symbol="CCL2" />
      <HGVSlist><HGVS><Expression>NM_000001.2:c.10A&gt;G</Expression></HGVS></HGVSlist>
    </SimpleAllele></ClassifiedRecord>
    <Classifications>
      <GermlineClassification DateLastEvaluated="2024-01-02"
          NumberOfSubmissions="{submissions}">
        {germline_description}<ReviewStatus>{review}</ReviewStatus>
        <ConditionList><Condition><Name>Condition G</Name></Condition></ConditionList>
      </GermlineClassification>
      <SomaticClinicalImpact NumberOfSubmissions="2">
        <Description>{somatic}</Description>
        <ReviewStatus>reviewed by expert panel</ReviewStatus>
        <TraitSet><Trait><Name>
          <ElementValue Type="Alternate">Cancer alias</ElementValue>
          <ElementValue Type="Preferred">Cancer S</ElementValue>
        </Name></Trait></TraitSet>
      </SomaticClinicalImpact>
      <OncogenicityClassification NumberOfSubmissions="3">
        <Description>Likely oncogenic</Description>
        <ConditionList><Condition><Name><ElementValue Type="Preferred">
          Cancer O
        </ElementValue></Name></Condition></ConditionList>
      </OncogenicityClassification>
    </Classifications>
  </VariationArchive>
</ClinVarResult-Set>""".encode()


def _minimal_xml(version: int) -> bytes:
    return (
        f'<VariationArchive Accession="VCV000014206" Version="{version}">'
        "<RecordStatus>current</RecordStatus></VariationArchive>"
    ).encode()


def _rcv_first_xml() -> bytes:
    """Representative official nesting with condition-specific blocks first."""
    return b"""<?xml version="1.0"?>
<ClinVarResult-Set xmlns="https://www.ncbi.nlm.nih.gov/clinvar/xml">
  <VariationArchive Accession="VCV000014026" Version="7" VariationID="14026"
      VariationName="aggregate variation name" DateCreated="2010-01-01"
      DateLastUpdated="2026-07-01">
    <RecordStatus>current</RecordStatus>
    <Warning>aggregate archive warning</Warning>
    <ClassifiedRecord>
      <SimpleAllele AlleleID="88"><Gene Symbol="AGG1" />
        <HGVSlist><HGVS><Expression>NM_AGG.1:c.10A&gt;G</Expression></HGVS></HGVSlist>
      </SimpleAllele>
      <RCVList>
        <RCVAccession Accession="RCV000000001">
          <HGVS><Expression>NM_RCV.1:c.20A&gt;G</Expression></HGVS>
          <Warning>RCV submission warning</Warning>
          <RCVClassifications>
            <GermlineClassification DateLastEvaluated="2001-01-01"
                NumberOfSubmissions="1">
              <Description>Pathogenic</Description>
              <ReviewStatus>no assertion criteria provided</ReviewStatus>
              <ConditionList><Condition><Name>RCV-only condition</Name></Condition>
              </ConditionList>
            </GermlineClassification>
          </RCVClassifications>
        </RCVAccession>
      </RCVList>
      <ClinicalAssertionList>
        <ClinicalAssertion>
          <HGVS><Expression>NM_ASSERT.1:c.30A&gt;G</Expression></HGVS>
          <Warning>clinical assertion warning</Warning>
          <GermlineClassification>
            <Description>Benign</Description>
            <ReviewStatus>no assertion criteria provided</ReviewStatus>
          </GermlineClassification>
        </ClinicalAssertion>
      </ClinicalAssertionList>
      <Classifications>
        <GermlineClassification>
          <Description DateLastEvaluated="2025-12-10" SubmissionCount="9">
            Uncertain significance
          </Description>
          <ReviewStatus>
            criteria provided, multiple submitters, no conflicts
          </ReviewStatus>
          <TraitSet><Trait><Name><ElementValue Type="Preferred">
            Aggregate condition
          </ElementValue></Name></Trait></TraitSet>
        </GermlineClassification>
        <SomaticClinicalImpact NumberOfSubmissions="3"
            DateLastEvaluated="2025-11-01">
          <Description>Tier II</Description>
          <ReviewStatus>criteria provided, single submitter</ReviewStatus>
          <ConditionList><Condition><Name>Aggregate somatic condition</Name>
          </Condition></ConditionList>
        </SomaticClinicalImpact>
        <OncogenicityClassification NumberOfSubmissions="2">
          <Description>Likely oncogenic</Description>
          <ReviewStatus>
            criteria provided, multiple submitters, no conflicts
          </ReviewStatus>
        </OncogenicityClassification>
      </Classifications>
    </ClassifiedRecord>
  </VariationArchive>
</ClinVarResult-Set>"""


class FakeResponse:
    """Small streaming response double with observable closure."""

    def __init__(
        self,
        content: bytes,
        *,
        error: requests.RequestException | None = None,
        content_length: int | None = None,
    ) -> None:
        self.content = content
        self.error = error
        self.encoding = "utf-8"
        self.closed = False
        self.headers = (
            {"Content-Length": str(content_length)}
            if content_length is not None
            else {}
        )

    def raise_for_status(self) -> None:
        if self.error:
            raise self.error

    def iter_content(self, chunk_size: int) -> Any:
        for start in range(0, len(self.content), chunk_size):
            yield self.content[start : start + chunk_size]

    def close(self) -> None:
        self.closed = True


class FakeSession:
    """Queue responses while recording exact request arguments."""

    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.all_responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.requests.append({"url": url, **kwargs})
        return self.responses.pop(0)


@pytest.mark.parametrize(
    "identifier",
    [
        "",
        "vcv000014206",
        "VCV14206",
        "VCV000014206.0",
        "VCV000014206.01",
        "VCV000000000",
        " VCV000014206",
    ],
)
def test_validation_is_strictly_canonical(identifier: str) -> None:
    with pytest.raises(InvalidVCVAccession):
        validate_vcv_accession(identifier)


def test_validation_preserves_optional_version() -> None:
    assert validate_vcv_accession("VCV000014206").version is None
    assert validate_vcv_accession("VCV000014206.12").version == 12


def test_version_ranges_allow_25_historical_requests() -> None:
    assert len(plan_version_range(25)) == 25
    assert plan_version_range(4, mode="custom", versions=[4, 2, 2]) == (2, 4)
    assert plan_version_range(4, mode="endpoints") == (1, 4)
    with pytest.raises(RequestLimitError, match="limit is 25"):
        plan_version_range(26)


def test_parser_separates_blocks_and_supports_both_condition_shapes() -> None:
    record = parse_efetch_xml(_xml(3))
    assert record.accession_version == "VCV000014206.3"
    assert record.variation_id == "14206"
    assert record.genes == ("CCL2",)
    assert record.hgvs == ("NM_000001.2:c.10A>G",)
    assert record.germline.classification == "Uncertain significance"
    assert record.somatic_clinical_impact.classification == "Tier II"
    assert record.oncogenicity.classification == "Likely oncogenic"
    assert record.conditions == ("Condition G", "Cancer S", "Cancer O")


def test_parser_uses_vcv_aggregate_when_rcv_classification_appears_first() -> None:
    record = parse_efetch_xml(_rcv_first_xml())
    assert record.name == "aggregate variation name"
    assert record.hgvs == ("NM_AGG.1:c.10A>G",)
    assert record.germline.classification == "Uncertain significance"
    assert record.germline.review_status == (
        "criteria provided, multiple submitters, no conflicts"
    )
    assert record.germline.submission_count == 9
    assert record.germline.date_last_evaluated == "2025-12-10"
    assert record.somatic_clinical_impact.classification == "Tier II"
    assert record.somatic_clinical_impact.submission_count == 3
    assert record.oncogenicity.classification == "Likely oncogenic"
    assert record.conditions == (
        "Aggregate condition",
        "Aggregate somatic condition",
    )
    assert "RCV-only condition" not in record.conditions
    assert "aggregate archive warning" in record.warnings
    assert "RCV submission warning" not in record.warnings
    assert "clinical assertion warning" not in record.warnings


@pytest.mark.parametrize(
    "xml",
    [
        b"<ClinVarResult-Set />",
        b"""<ClinVarResult-Set>
          <VariationArchive Accession="VCV000014206" Version="1" />
          <VariationArchive Accession="VCV000014206" Version="2" />
        </ClinVarResult-Set>""",
    ],
)
def test_parser_requires_exactly_one_variation_archive(xml: bytes) -> None:
    with pytest.raises(history.VCVHistoryError, match="exactly one VariationArchive"):
        parse_efetch_xml(xml)


def test_parser_warns_without_inferring_missing_scientific_fields() -> None:
    record = parse_efetch_xml(_minimal_xml(1))
    assert record.variation_id is None
    assert record.genes == ()
    assert record.germline.classification is None
    assert record.date_created is None
    assert record.date_last_updated is None
    assert set(record.warnings) >= {
        "Variation ID is missing.",
        "Genes are missing.",
        "Germline classification is missing.",
        "Record creation date is missing.",
        "Record last-updated date is missing.",
    }


def test_current_lookup_is_separate_from_25_version_budget() -> None:
    responses = [FakeResponse(_xml(25))]
    responses.extend(FakeResponse(_xml(version)) for version in range(1, 26))
    session = FakeSession(responses)
    result = fetch_vcv_history(
        "VCV000014206",
        session=session,  # type: ignore[arg-type]
        sleep=lambda _: None,
    )
    assert result.current_identifier == "VCV000014206.25"
    assert len(result.results) == 25
    assert len(session.requests) == 26
    assert all(response.closed for response in session.all_responses)


def test_public_current_fetch_uses_one_unversioned_bounded_request() -> None:
    response = FakeResponse(_xml(4))
    session = FakeSession([response])

    result = fetch_current_vcv(
        "VCV000014206.2",
        session=session,  # type: ignore[arg-type]
    )

    assert result.record is not None
    assert result.record.version == 4
    assert [request["params"]["id"] for request in session.requests] == ["VCV000014206"]
    assert session.requests[0]["params"]["rettype"] == "vcv"
    assert response.closed is True


def test_exact_requests_progress_events_and_response_closure() -> None:
    responses = [FakeResponse(_xml(2)), FakeResponse(_xml(1)), FakeResponse(_xml(2))]
    session = FakeSession(responses)
    events: list[dict[str, object]] = []
    sleeps: list[float] = []
    result = fetch_vcv_history(
        "VCV000014206",
        session=session,  # type: ignore[arg-type]
        sleep=sleeps.append,
        request_interval_seconds=0.25,
        progress=events.append,
    )
    assert [request["params"]["id"] for request in session.requests] == [
        "VCV000014206",
        "VCV000014206.1",
        "VCV000014206.2",
    ]
    assert [event["event"] for event in events] == [
        "requesting",
        "received",
        "parsed",
        "requesting",
        "received",
        "parsed",
        "requesting",
        "received",
        "parsed",
    ]
    assert result.results[0].source_request.endswith(
        "?db=clinvar&id=VCV000014206.1&rettype=vcv&retmode=xml"
        "&tool=variant_time_machine"
    )
    assert result.current_result.raw_xml is not None
    assert sleeps == [0.25, 0.25]
    assert all(response.closed for response in session.all_responses)


def test_explicit_suffix_fallback_is_missing_and_emits_missing() -> None:
    responses = [FakeResponse(_xml(5)), FakeResponse(_xml(5))]
    session = FakeSession(responses)
    events: list[dict[str, object]] = []
    result = fetch_vcv_history(
        "VCV000014206.2",
        session=session,  # type: ignore[arg-type]
        sleep=lambda _: None,
        progress=events.append,
    )
    assert result.version_plan == (2,)
    assert result.results[0].status == "missing"
    assert result.results[0].record is None
    assert "missing" in [event["event"] for event in events]


def test_future_explicit_suffix_stops_after_current_lookup() -> None:
    current = FakeResponse(_xml(3))
    unused = FakeResponse(_xml(4))
    session = FakeSession([current, unused])
    events: list[dict[str, object]] = []
    with pytest.raises(ValueError, match="current official version is 3"):
        fetch_vcv_history(
            "VCV000014206.4",
            session=session,  # type: ignore[arg-type]
            sleep=lambda _: None,
            progress=events.append,
        )
    assert [request["params"]["id"] for request in session.requests] == ["VCV000014206"]
    assert current.closed is True
    assert unused.closed is False
    assert events[-1]["event"] == "failed"


def test_failures_emit_events_and_close_obtained_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_response = FakeResponse(b"", error=requests.ConnectionError("offline"))
    failed_session = FakeSession([failed_response])
    events: list[dict[str, object]] = []
    result = fetch_vcv_history(
        "VCV000014206",
        session=failed_session,  # type: ignore[arg-type]
        sleep=lambda _: None,
        progress=events.append,
    )
    assert result.current_result.status == "request failure"
    assert events[-1]["event"] == "failed"
    assert failed_response.closed is True

    monkeypatch.setattr(history, "MAX_RESPONSE_BYTES", 20)
    oversized_response = FakeResponse(_xml(1), content_length=21)
    oversized = FakeSession([oversized_response])
    limit_events: list[dict[str, object]] = []
    with pytest.raises(TransferLimitError):
        fetch_vcv_history(
            "VCV000014206",
            session=oversized,  # type: ignore[arg-type]
            sleep=lambda _: None,
            progress=limit_events.append,
        )
    assert limit_events[-1]["event"] == "failed"
    assert oversized_response.closed is True


def test_total_transfer_limit_is_hard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(history, "MAX_RESPONSE_BYTES", 10_000)
    current = _xml(2)
    first = FakeResponse(current)
    second = FakeResponse(_xml(1))
    session = FakeSession([first, second])
    events: list[dict[str, object]] = []
    with pytest.raises(TransferLimitError):
        fetch_vcv_history(
            "VCV000014206",
            mode="custom",
            versions=[1],
            max_total_bytes=len(current) + 10,
            session=session,  # type: ignore[arg-type]
            sleep=lambda _: None,
            progress=events.append,
        )
    assert first.closed is True
    assert second.closed is True
    assert events[-1]["event"] == "failed"


def _outcome(version: int, **xml_kwargs: Any) -> VersionResult:
    raw = _xml(version, **xml_kwargs)
    record = parse_efetch_xml(raw)
    return VersionResult(
        requested_identifier=record.accession_version,
        source_request="mock",
        retrieved_at_utc="2026-01-01T00:00:00+00:00",
        response_bytes=len(raw),
        status="available",
        record=record,
        raw_xml=raw.decode(),
    )


@pytest.mark.parametrize(
    ("earlier", "later", "expected"),
    [
        ("Uncertain significance", "Pathogenic", "VUS_to_Pathogenic"),
        ("VUS", "LIKELY PATHOGENIC", "VUS_to_Likely_Pathogenic"),
        ("Variant of uncertain significance", "Benign", "VUS_to_Benign"),
        ("Uncertain significance", "Likely benign", "VUS_to_Likely_Benign"),
        ("Pathogenic", "Uncertain significance", "Pathogenic_to_VUS"),
        ("Benign", "VUS", "Benign_to_VUS"),
        ("VUS", "Conflicting classifications", "Became_Conflicting"),
        ("Conflicting interpretations", "Benign", "Conflict_Resolved"),
    ],
)
def test_exact_germline_change_mappings(
    earlier: str,
    later: str,
    expected: str,
) -> None:
    comparison = compare_consecutive(
        [_outcome(1, classification=earlier), _outcome(2, classification=later)]
    )[0]
    assert comparison.detected_classification_change == expected
    assert comparison.earlier_germline_classification == earlier
    assert comparison.later_germline_classification == later
    assert comparison.submissions_changed is False
    assert comparison.confidence == "high"


def test_non_germline_and_missing_classification_labels() -> None:
    unchanged = compare_consecutive([_outcome(1), _outcome(2)])[0]
    assert unchanged.detected_classification_change == "No_Classification_Change"
    non_germline = compare_consecutive(
        [_outcome(1, somatic="Tier II"), _outcome(2, somatic="Tier I")]
    )[0]
    assert non_germline.detected_classification_change == "Non_Germline_Change"
    missing = compare_consecutive([_outcome(1), _outcome(2, classification=None)])[0]
    assert missing.detected_classification_change == "Missing_Classification"
    assert missing.confidence == "limited"


def test_comparisons_skip_missing_holes_and_summary_is_honest() -> None:
    first = _outcome(1)
    missing = replace(_outcome(2), status="missing", record=None, message="missing v2")
    latest = _outcome(3, classification="Pathogenic", submissions=3)
    comparisons = compare_consecutive([first, missing, latest])
    assert len(comparisons) == 1
    assert comparisons[0].earlier_version == 1
    assert comparisons[0].later_version == 3
    assert comparisons[0].detected_classification_change == "VUS_to_Pathogenic"
    assert comparisons[0].confidence == "limited"
    assert "nonconsecutive" in comparisons[0].warnings[0]
    assert compare_consecutive([first, missing]) == ()


def test_retrieval_summary_reports_change_latest_and_warnings() -> None:
    responses = [
        FakeResponse(_xml(3, classification="Pathogenic")),
        FakeResponse(_xml(1)),
        FakeResponse(b"<ERROR>No items found</ERROR>"),
        FakeResponse(_xml(3, classification="Pathogenic")),
    ]
    result = fetch_vcv_history(
        "VCV000014206",
        session=FakeSession(responses),  # type: ignore[arg-type]
        sleep=lambda _: None,
    )
    summary = result.summary
    assert summary.first_available_version == 1
    assert summary.newest_available_version == 3
    assert summary.retrieved_version_count == 2
    assert summary.any_germline_classification_changed is True
    assert summary.first_detected_germline_change is not None
    assert (
        summary.first_detected_germline_change.detected_classification_change
        == "VUS_to_Pathogenic"
    )
    assert summary.latest_germline_classification == "Pathogenic"
    assert any(
        "no VariationArchive" in warning for warning in summary.unresolved_warnings
    )
    assert result.to_dict()["summary"]["first_detected_germline_change"] is not None  # type: ignore[index]


def test_summary_counts_parsed_replaced_records_without_comparing_them() -> None:
    session = FakeSession(
        [FakeResponse(_xml(2)), FakeResponse(_xml(1, replaced_by="VCV000000999.1"))]
    )
    result = fetch_vcv_history(
        "VCV000014206",
        mode="custom",
        versions=[1],
        session=session,  # type: ignore[arg-type]
        sleep=lambda _: None,
    )
    assert result.results[0].status == "deleted/replaced"
    assert result.summary.first_available_version == 1
    assert result.summary.newest_available_version == 1
    assert result.summary.retrieved_version_count == 1
    assert result.comparisons == ()
    assert any(
        "replacement" in warning for warning in result.summary.unresolved_warnings
    )


def test_cancellation_event_is_emitted_between_requests() -> None:
    session = FakeSession([FakeResponse(_xml(3)), FakeResponse(_xml(1))])
    checks = 0
    events: list[dict[str, object]] = []

    def cancel() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 3

    result = fetch_vcv_history(
        "VCV000014206",
        session=session,  # type: ignore[arg-type]
        sleep=lambda _: None,
        cancel=cancel,
        progress=events.append,
    )
    assert result.cancelled is True
    assert len(result.results) == 1
    assert events[-1]["event"] == "cancelled"
    assert any("cancelled" in warning for warning in result.summary.unresolved_warnings)
