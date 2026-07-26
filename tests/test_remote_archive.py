"""Tests for bounded remote ClinVar XML access without real network transfers."""

import gzip
import io

import pytest

from variant_time_machine.config import PILOT_XML_RELEASES
from variant_time_machine.remote_archive import (
    ConfirmationRequired,
    ExtractionLimitError,
    extract_remote_records,
    inspect_remote_release,
)


def _archive() -> bytes:
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<ClinVarVariationRelease>
  <VariationArchive VariationID="2" Accession="VCV000000002"
                    Version="4" RecordType="classified">
    <RecordStatus>current</RecordStatus>
    <Classifications>
      <GermlineClassification DateLastEvaluated="2023-01-02" NumberOfSubmissions="2">
        <ReviewStatus>criteria provided</ReviewStatus>
        <Description>Uncertain significance</Description>
        <ConditionList><Condition><Name>Condition A</Name></Condition></ConditionList>
      </GermlineClassification>
      <SomaticClinicalImpact><Description>Tier II</Description></SomaticClinicalImpact>
      <OncogenicityClassification>
        <Description>Oncogenic</Description>
      </OncogenicityClassification>
    </Classifications>
    <ClassifiedRecord>
      <SimpleAllele AlleleID="22">
        <Gene Symbol="GENE2"/><Name>variant two</Name>
      </SimpleAllele>
    </ClassifiedRecord>
  </VariationArchive>
  <VariationArchive VariationID="4" Accession="VCV000000004"
                    Version="1" RecordType="classified">
    <RecordStatus>current</RecordStatus>
    <Classifications>
      <GermlineClassification><Description>Pathogenic</Description></GermlineClassification>
    </Classifications>
    <ClassifiedRecord>
      <SimpleAllele AlleleID="44"><Name>variant four</Name></SimpleAllele>
    </ClassifiedRecord>
  </VariationArchive>
</ClinVarVariationRelease>"""
    return gzip.compress(xml)


class FakeResponse:
    """Small requests response substitute that rejects full content access."""

    def __init__(
        self, body: bytes = b"", headers: dict[str, str] | None = None
    ) -> None:
        self.raw = io.BytesIO(body)
        self.headers = headers or {}
        self.text = body.decode("ascii", errors="ignore")
        self.closed = False

    @property
    def content(self) -> bytes:
        raise AssertionError("Streaming code must not access response.content")

    def raise_for_status(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class FakeSession:
    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.last_response: FakeResponse | None = None

    def get(self, url: str, **_kwargs: object) -> FakeResponse:
        body = b"abc  archive.xml.gz\n" if url.endswith(".md5") else self.archive
        self.last_response = FakeResponse(body)
        return self.last_response

    def head(self, _url: str, **_kwargs: object) -> FakeResponse:
        return FakeResponse(headers={"Content-Length": "123"})


def test_extraction_requires_confirmation_before_request() -> None:
    session = FakeSession(_archive())
    with pytest.raises(ConfirmationRequired):
        extract_remote_records(
            PILOT_XML_RELEASES["older"], ["2"], confirmed=False, session=session
        )
    assert session.last_response is None


def test_stream_extracts_requested_fields_and_separates_classifications() -> None:
    session = FakeSession(_archive())
    result = extract_remote_records(
        PILOT_XML_RELEASES["older"],
        ["VCV000000002", "999"],
        confirmed=True,
        max_transfer_bytes=10_000,
        session=session,
    )
    assert result.requested_ids == ("2", "999")
    assert result.missing_ids == ("999",)
    assert result.completed_full_scan
    record = result.records[0]
    assert record.variation_id == "2"
    assert record.allele_ids == ("22",)
    assert record.genes == ("GENE2",)
    assert record.conditions == ("Condition A",)
    assert record.germline_classification == "Uncertain significance"
    assert record.somatic_clinical_impact == "Tier II"
    assert record.oncogenicity_classification == "Oncogenic"
    assert session.last_response is not None and session.last_response.closed


def test_stream_stops_when_all_requested_records_are_found() -> None:
    result = extract_remote_records(
        PILOT_XML_RELEASES["older"],
        ["2"],
        confirmed=True,
        max_transfer_bytes=10_000,
        session=FakeSession(_archive()),
    )
    assert not result.completed_full_scan
    assert result.missing_ids == ()


def test_limits_fail_cleanly() -> None:
    with pytest.raises(ExtractionLimitError, match="limit is 1"):
        extract_remote_records(
            PILOT_XML_RELEASES["older"],
            ["2", "4"],
            confirmed=True,
            max_records=1,
            session=FakeSession(_archive()),
        )
    with pytest.raises(ExtractionLimitError, match="Compressed transfer exceeded"):
        extract_remote_records(
            PILOT_XML_RELEASES["older"],
            ["999"],
            confirmed=True,
            max_transfer_bytes=10,
            session=FakeSession(_archive()),
        )


def test_dry_run_metadata_uses_only_head_and_small_md5() -> None:
    release = PILOT_XML_RELEASES["older"]
    metadata = inspect_remote_release(release, session=FakeSession(_archive()))
    assert metadata.reported_compressed_size_bytes == 123
    assert metadata.reported_md5 == "abc"
    assert metadata.size_matches is False
    assert metadata.md5_matches is False
