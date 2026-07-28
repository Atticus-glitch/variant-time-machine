"""Tests for pure real-pilot aggregation and fixed artifact exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from variant_time_machine.pilot_results import (
    MANUAL_REVIEW_FIELDS,
    NOTICE,
    OUTPUT_FILENAMES,
    RESULT_FIELDS,
    PilotResultsError,
    aggregate_pilot_results,
    download_content,
    export_pilot_results,
)
from variant_time_machine.vcv_history import (
    ClassificationBlock,
    VCVHistoryResult,
    VCVHistorySummary,
    VCVRecord,
    VersionResult,
    compare_consecutive,
)
from variant_time_machine.vcv_history_store import (
    VERIFICATION_REQUIREMENTS,
    load_history,
    save_history,
    update_review,
)

GENERATED = "2026-07-27T12:00:00+00:00"


def _accession(number: int) -> str:
    return f"VCV{number:09d}"


def _record(
    accession: str,
    version: int,
    classification: str | None,
    *,
    review_status: str | None = "criteria provided",
    submissions: int | None = 1,
    somatic: str | None = None,
    oncogenicity: str | None = None,
) -> VCVRecord:
    empty = ClassificationBlock(None, None, None, None)
    return VCVRecord(
        accession=accession,
        version=version,
        accession_version=f"{accession}.{version}",
        variation_id=str(int(accession[3:])),
        record_type="classified",
        genes=(f"GENE{int(accession[3:])}",),
        name="fixture",
        hgvs=(),
        date_created="2020-01-01",
        date_last_updated=f"202{version}-01-01",
        date_deleted=None,
        germline=ClassificationBlock(
            classification, review_status, "2024-01-01", submissions
        ),
        somatic_clinical_impact=(
            ClassificationBlock(somatic, None, None, None) if somatic else empty
        ),
        oncogenicity=(
            ClassificationBlock(oncogenicity, None, None, None)
            if oncogenicity
            else empty
        ),
        conditions=("Fixture condition",),
        record_status="current",
        replaced_by=(),
        replacements=(),
        deleted=False,
        warnings=(),
    )


def _result(identifier: str, record: VCVRecord) -> VersionResult:
    raw = (
        f'<VariationArchive Accession="{record.accession}" '
        f'Version="{record.version}" />'
    )
    return VersionResult(
        requested_identifier=identifier,
        source_request=(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
            f"db=clinvar&id={identifier}"
        ),
        retrieved_at_utc=GENERATED,
        response_bytes=len(raw.encode()),
        status="available",
        record=record,
        raw_xml=raw,
    )


def _save(
    root: Path,
    number: int,
    classifications: tuple[str | None, ...],
    *,
    reviews: tuple[str | None, ...] | None = None,
    submissions: tuple[int | None, ...] | None = None,
    somatic: tuple[str | None, ...] | None = None,
    oncogenicity: tuple[str | None, ...] | None = None,
) -> str:
    accession = _accession(number)
    records = tuple(
        _record(
            accession,
            index,
            classification,
            review_status=(reviews or ("criteria provided",) * len(classifications))[
                index - 1
            ],
            submissions=(submissions or (1,) * len(classifications))[index - 1],
            somatic=(somatic or (None,) * len(classifications))[index - 1],
            oncogenicity=(oncogenicity or (None,) * len(classifications))[index - 1],
        )
        for index, classification in enumerate(classifications, start=1)
    )
    results = tuple(_result(record.accession_version, record) for record in records)
    current = _result(accession, records[-1])
    comparisons = compare_consecutive(results)
    changes = [
        item
        for item in comparisons
        if item.detected_classification_change
        not in {
            "No_Classification_Change",
            "Non_Germline_Change",
            "Missing_Classification",
            "Unable_to_Compare",
        }
    ]
    summary = VCVHistorySummary(
        first_available_version=1,
        newest_available_version=len(records),
        retrieved_version_count=len(records),
        any_germline_classification_changed=bool(changes),
        first_detected_germline_change=changes[0] if changes else None,
        latest_germline_classification=classifications[-1],
        unresolved_warnings=(),
    )
    history = VCVHistoryResult(
        requested_accession=accession,
        current_identifier=records[-1].accession_version,
        version_plan=tuple(range(1, len(records) + 1)),
        current_result=current,
        results=results,
        comparisons=comparisons,
        summary=summary,
        total_response_bytes=sum(item.response_bytes for item in (current, *results)),
    )
    save_history(root, history, app_version="test", git_commit="fixture")
    return accession


def _rows(root: Path, output: Path) -> list[dict[str, object]]:
    result = aggregate_pilot_results(root, output, generated_at_utc=GENERATED)
    return result["rows"]  # type: ignore[return-value]


def test_zero_change_and_directional_change_are_aggregated(tmp_path: Path) -> None:
    histories = tmp_path / "histories"
    output = tmp_path / "output"
    unchanged = _save(
        histories, 1, ("Uncertain significance", "Uncertain significance")
    )
    changed = _save(histories, 2, ("Uncertain significance", "Pathogenic"))

    rows = {row["VCV accession"]: row for row in _rows(histories, output)}

    assert rows[unchanged]["automatic result"] == "No_Germline_Change"
    assert rows[unchanged]["classification change count"] == 0
    assert rows[changed]["automatic result"] == "VUS_to_Pathogenic"
    assert rows[changed]["Data label"] == NOTICE
    assert rows[changed]["classification change count"] == 1
    assert f"{changed}.1 to {changed}.2" in str(rows[changed]["first change"])
    assert rows[changed]["versions retrieved"] == 2


def test_missing_and_single_version_are_distinct_unable_results(tmp_path: Path) -> None:
    histories = tmp_path / "histories"
    output = tmp_path / "output"
    missing = _save(histories, 3, (None, "Pathogenic"))
    single = _save(histories, 4, ("Benign",))

    rows = {row["VCV accession"]: row for row in _rows(histories, output)}

    assert rows[missing]["automatic result"] == "Missing_Data"
    assert rows[single]["automatic result"] == "Unable_to_Compare"
    assert rows[single]["automatic confidence"] == "unable"


@pytest.mark.parametrize("changed_type", ["somatic", "oncogenicity"])
def test_non_germline_changes_are_not_mixed_into_germline_results(
    tmp_path: Path, changed_type: str
) -> None:
    histories = tmp_path / "histories"
    values = (None, "oncogenic")
    kwargs = {changed_type: values}
    accession = _save(
        histories,
        5,
        ("Uncertain significance", "Uncertain significance"),
        **kwargs,  # type: ignore[arg-type]
    )

    row = _rows(histories, tmp_path / "output")[0]

    assert row["VCV accession"] == accession
    assert row["automatic result"] == "No_Germline_Change"
    assert "Non_Germline_Change was normalized" in str(row["warnings"])


def test_summary_counts_real_categories_and_actual_bytes(tmp_path: Path) -> None:
    histories = tmp_path / "histories"
    _save(histories, 6, ("Uncertain significance", "Pathogenic"))
    _save(histories, 7, ("Benign", "Benign"))
    _save(histories, 8, ("Pathogenic",))

    result = aggregate_pilot_results(
        histories, tmp_path / "output", generated_at_utc=GENERATED
    )
    summary = result["summary"]

    assert summary["candidates_attempted"] == 3
    assert summary["candidates_successfully_retrieved"] == 3
    assert summary["total_official_versions_retrieved"] == 5
    assert summary["variants_with_germline_change"] == 1
    assert summary["variants_with_no_germline_change"] == 1
    assert summary["variants_unable_to_compare"] == 1
    assert summary["candidate_selection_bytes"] == 0
    assert summary["candidate_selection_request_count"] == 0
    assert summary["actual_new_batch_bytes"] == 0
    assert summary["history_response_bytes"] == sum(
        row["bytes transferred"] for row in result["rows"]
    )
    assert summary["total_bytes_transferred"] == sum(
        row["bytes transferred"] for row in result["rows"]
    )
    assert summary["total_local_storage_bytes"] > 0
    assert summary["generated_at_utc"] == GENERATED
    assert summary["notice"] == NOTICE
    assert summary["histories_needing_review"] == 3


def test_manual_result_stays_separate_and_corrections_are_never_applied(
    tmp_path: Path,
) -> None:
    histories = tmp_path / "histories"
    accession = _save(histories, 9, ("Uncertain significance", "Pathogenic"))
    update_review(
        histories,
        accession,
        status="manually_verified",
        reviewer_decision="Other_Germline_Change",
        notes="Checked against the retained official XML.",
        manual_corrections={"detected change category": "VUS_to_Benign"},
        verification={item: True for item in VERIFICATION_REQUIREMENTS},
    )

    result = aggregate_pilot_results(
        histories, tmp_path / "output", generated_at_utc=GENERATED
    )
    row = result["rows"][0]

    assert row["automatic result"] == "VUS_to_Pathogenic"
    assert row["detected change category"] == "VUS_to_Pathogenic"
    assert row["reviewer decision"] == "Other_Germline_Change"
    assert row["manual confirmed result"] == "Other_Germline_Change"
    assert row["review notes"] == "Checked against the retained official XML."
    assert row["verification complete"] == len(VERIFICATION_REQUIREMENTS)
    assert row["verification total"] == len(VERIFICATION_REQUIREMENTS)
    assert result["summary"]["manually_verified"] == 1

    output = tmp_path / "output"
    export_pilot_results(histories, output, generated_at_utc=GENERATED)
    with (output / "manual_review.csv").open(newline="", encoding="utf-8") as source:
        manual_row = next(csv.DictReader(source))
    assert manual_row["reviewer decision"] == "Other_Germline_Change"
    assert manual_row["manual confirmed result"] == "Other_Germline_Change"
    assert manual_row["review notes"] == "Checked against the retained official XML."


def test_unverified_reviewer_decision_is_not_a_confirmed_result(
    tmp_path: Path,
) -> None:
    histories = tmp_path / "histories"
    accession = _save(histories, 13, ("Benign", "Benign"))
    update_review(
        histories,
        accession,
        status="needs_review",
        reviewer_decision="Possible exclusion",
        notes="Decision remains provisional.",
    )

    row = aggregate_pilot_results(
        histories, tmp_path / "output", generated_at_utc=GENERATED
    )["rows"][0]

    assert row["reviewer decision"] == "Possible exclusion"
    assert row["manual confirmed result"] == ""
    assert row["review notes"] == "Decision remains provisional."


def test_batch_manifest_sets_attempts_failures_reuse_and_candidate_limit(
    tmp_path: Path,
) -> None:
    histories = tmp_path / "histories"
    output = tmp_path / "output"
    output.mkdir()
    saved = _save(histories, 10, ("Benign", "Benign"))
    saved_bytes = load_history(histories, saved)["manifest"]["total_bytes"]
    failed = _accession(11)
    selection_requests = [
        {
            "accession": saved,
            "source_request": f"https://example.ncbi.nlm.nih.gov/select/{saved}",
            "response_bytes": 11,
            "retrieved_at_utc": GENERATED,
        },
        {
            "accession": failed,
            "source_request": f"https://example.ncbi.nlm.nih.gov/select/{failed}",
            "response_bytes": 12,
            "retrieved_at_utc": GENERATED,
        },
    ]
    (output / "batch_manifest.json").write_text(
        json.dumps(
            {
                "candidate_selection_bytes": 23,
                "candidate_selection_requests": selection_requests,
                "candidates": [
                    {
                        "vcv_accession": saved,
                        "reused": True,
                        "bytes_transferred": 0,
                    },
                    {
                        "vcv_accession": failed,
                        "failure": "official request failed",
                        "bytes_transferred": 17,
                    },
                ],
            }
        )
    )

    result = aggregate_pilot_results(histories, output, generated_at_utc=GENERATED)

    assert [row["VCV accession"] for row in result["rows"]] == [saved, failed]
    assert result["rows"][1]["automatic result"] == "Unable_to_Compare"
    assert result["rows"][0]["bytes transferred"] == saved_bytes
    assert result["rows"][1]["bytes transferred"] == 17
    assert result["transfer_manifest"]["candidates"][0]["reused"] is True
    assert (
        result["transfer_manifest"]["candidates"][0]["history_response_bytes"]
        == saved_bytes
    )
    assert result["transfer_manifest"]["candidates"][0]["actual_new_batch_bytes"] == 0
    assert result["transfer_manifest"]["candidates"][1]["failure"] == (
        "official request failed"
    )
    summary = result["summary"]
    assert summary["candidate_selection_bytes"] == 23
    assert summary["candidate_selection_request_count"] == 2
    assert summary["history_response_bytes"] == saved_bytes + 17
    assert summary["actual_new_batch_bytes"] == 17
    assert summary["total_bytes_transferred"] == 23 + saved_bytes + 17
    assert (
        result["transfer_manifest"]["total_bytes_transferred"]
        == (summary["total_bytes_transferred"])
    )
    assert result["transfer_manifest"]["candidate_selection_requests"] == (
        selection_requests
    )
    assert result["transfer_manifest"]["candidate_selection_request_count"] == 2

    (output / "batch_manifest.json").write_text(
        json.dumps({"candidates": [_accession(index) for index in range(20, 31)]})
    )
    with pytest.raises(PilotResultsError, match="limited to 10"):
        aggregate_pilot_results(histories, output)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("candidate_selection_bytes", -1),
        ("candidate_selection_requests", -1),
        ("candidate_selection_bytes", True),
        ("candidate_selection_requests", "2"),
    ],
)
def test_batch_selection_accounting_requires_nonnegative_integers(
    tmp_path: Path, field: str, value: object
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "batch_manifest.json").write_text(
        json.dumps({"candidates": [], field: value})
    )

    with pytest.raises(PilotResultsError, match=field):
        aggregate_pilot_results(tmp_path / "histories", output)


def test_legacy_candidate_selection_request_count_is_accepted(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "batch_manifest.json").write_text(
        json.dumps(
            {
                "candidate_selection_bytes": 9,
                "candidate_selection_requests": 2,
                "candidates": [],
            }
        )
    )

    result = aggregate_pilot_results(tmp_path / "histories", output)

    assert result["summary"]["candidate_selection_request_count"] == 2
    assert result["transfer_manifest"]["candidate_selection_requests"] == []


@pytest.mark.parametrize(
    "requests",
    [
        [
            {
                "accession": _accession(15),
                "source_request": "https://example.ncbi.nlm.nih.gov/select",
                "response_bytes": -1,
                "retrieved_at_utc": GENERATED,
            }
        ],
        [
            {
                "accession": _accession(15),
                "source_request": "https://example.ncbi.nlm.nih.gov/select",
                "response_bytes": 1,
            }
        ],
    ],
)
def test_candidate_selection_request_objects_are_validated(
    tmp_path: Path, requests: list[dict[str, object]]
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "batch_manifest.json").write_text(
        json.dumps(
            {
                "candidate_selection_bytes": 1,
                "candidate_selection_requests": requests,
                "candidates": [],
            }
        )
    )

    with pytest.raises(PilotResultsError, match="Candidate selection|exactly"):
        aggregate_pilot_results(tmp_path / "histories", output)


def test_selection_request_bytes_must_match_selection_total(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    request = {
        "accession": _accession(16),
        "source_request": "https://example.ncbi.nlm.nih.gov/select",
        "response_bytes": 4,
        "retrieved_at_utc": GENERATED,
    }
    (output / "batch_manifest.json").write_text(
        json.dumps(
            {
                "candidate_selection_bytes": 5,
                "candidate_selection_requests": [request],
                "candidates": [],
            }
        )
    )

    with pytest.raises(PilotResultsError, match="must sum"):
        aggregate_pilot_results(tmp_path / "histories", output)


def test_selection_request_provenance_is_limited_to_ten(tmp_path: Path) -> None:
    output = tmp_path / "output"
    output.mkdir()
    requests = [
        {
            "accession": _accession(index),
            "source_request": f"https://example.ncbi.nlm.nih.gov/select/{index}",
            "response_bytes": 0,
            "retrieved_at_utc": GENERATED,
        }
        for index in range(30, 41)
    ]
    (output / "batch_manifest.json").write_text(
        json.dumps(
            {
                "candidate_selection_bytes": 0,
                "candidate_selection_requests": requests,
                "candidates": [],
            }
        )
    )

    with pytest.raises(PilotResultsError, match="limited to 10"):
        aggregate_pilot_results(tmp_path / "histories", output)


def test_failed_attempt_transfer_bytes_must_be_nonnegative_integer(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    output.mkdir()
    (output / "batch_manifest.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "vcv_accession": _accession(14),
                        "bytes_transferred": -1,
                    }
                ]
            }
        )
    )

    with pytest.raises(PilotResultsError, match="bytes_transferred"):
        aggregate_pilot_results(tmp_path / "histories", output)


def test_no_manifest_never_creates_synthetic_rows(tmp_path: Path) -> None:
    result = aggregate_pilot_results(
        tmp_path / "empty", tmp_path / "output", generated_at_utc=GENERATED
    )

    assert result["rows"] == []
    assert result["summary"]["candidates_attempted"] == 0


def test_real_label_requires_official_source_and_matching_raw_size(
    tmp_path: Path,
) -> None:
    histories = tmp_path / "histories"
    accession = _save(histories, 13, ("Benign", "Benign"))
    manifest_path = histories / accession / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["source_requests"][0]["request"] = "https://example.test/not-official"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(PilotResultsError, match="not official"):
        aggregate_pilot_results(histories, tmp_path / "output")

    manifest["source_requests"][0]["request"] = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    raw_path = histories / accession / "raw" / f"{accession}.xml"
    raw_path.write_bytes(raw_path.read_bytes() + b"x")
    with pytest.raises(PilotResultsError, match="size does not match"):
        aggregate_pilot_results(histories, tmp_path / "output")


def test_sources_raw_links_and_all_output_formats(tmp_path: Path) -> None:
    histories = tmp_path / "histories"
    output = tmp_path / "output"
    accession = _save(
        histories,
        12,
        ("Uncertain significance", "Pathogenic"),
        reviews=("no assertion criteria", "criteria provided"),
        submissions=(1, 2),
    )

    result = export_pilot_results(histories, output, generated_at_utc=GENERATED)

    assert {path.name for path in output.iterdir()} == set(OUTPUT_FILENAMES)
    with (output / "pilot_results.csv").open(newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        rows = list(reader)
    assert tuple(reader.fieldnames or ()) == RESULT_FIELDS
    assert rows[0]["review-status change"] == (
        "no assertion criteria to criteria provided"
    )
    assert rows[0]["submission change"] == "yes"
    source_information = json.loads(rows[0]["source information"])
    assert source_information["official_source_requests"][0].startswith(
        "https://eutils.ncbi.nlm.nih.gov/"
    )
    assert (
        f"{accession}/raw/{accession}.1.xml"
        in source_information["local_raw_artifacts"]
    )
    assert json.loads((output / "pilot_summary.json").read_text()) == result["summary"]
    transfer = json.loads((output / "transfer_manifest.json").read_text())
    assert transfer["candidates"][0]["bytes_transferred"] > 0
    with (output / "manual_review.csv").open(newline="", encoding="utf-8") as source:
        manual_reader = csv.DictReader(source)
        manual_rows = list(manual_reader)
    assert tuple(manual_reader.fieldnames or ()) == MANUAL_REVIEW_FIELDS
    assert manual_rows[0]["automatic result"] == "VUS_to_Pathogenic"
    assert manual_rows[0]["manual confirmed result"] == ""
    report = (output / "pilot_report.md").read_text()
    for heading in (
        "Research question",
        "Method",
        "Official source",
        "Sample size",
        "Results",
        "Transfer accounting",
        "Examples",
        "Limitations",
        "Next step",
    ):
        assert f"## {heading}" in report
    assert "pilot is not the final paper" in report
    assert "Manually verified: 0" in report
    assert "Unique history response bytes" in report
    assert "Actual bytes newly transferred in this batch" in report
    assert NOTICE in report

    content, mimetype, name = download_content(output, "pilot_results.csv")
    assert content == (output / name).read_bytes()
    assert mimetype == "text/csv; charset=utf-8"
    with pytest.raises(PilotResultsError, match="Unknown"):
        download_content(output, "../batch_manifest.json")
