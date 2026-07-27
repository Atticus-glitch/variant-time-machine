"""Focused tests for bounded local VCV history and review storage."""

from __future__ import annotations

import json
import threading
from dataclasses import replace
from pathlib import Path

import pytest

import variant_time_machine.vcv_history_store as store
from variant_time_machine.vcv_history import (
    ClassificationBlock,
    ClassificationChange,
    VCVHistoryResult,
    VCVHistorySummary,
    VCVRecord,
    VersionComparison,
    VersionResult,
)
from variant_time_machine.vcv_history_store import (
    VERIFICATION_REQUIREMENTS,
    VCVHistoryStoreError,
    list_histories,
    load_history,
    load_review,
    progress_metrics,
    save_history,
    update_review,
)

ACCESSION = "VCV000014206"


def _record(version: int, classification: str) -> VCVRecord:
    empty = ClassificationBlock(None, None, None, None)
    return VCVRecord(
        accession=ACCESSION,
        version=version,
        accession_version=f"{ACCESSION}.{version}",
        variation_id="14206",
        record_type="classified",
        genes=("CCL2",),
        name="example",
        hgvs=("NM_000001.2:c.10A>G",),
        date_created="2020-01-01",
        date_last_updated=f"202{version}-01-02",
        date_deleted=None,
        germline=ClassificationBlock(
            classification, "criteria provided", "2024-01-02", 1
        ),
        somatic_clinical_impact=empty,
        oncogenicity=empty,
        conditions=("Condition G",),
        record_status="current",
        replaced_by=(),
        replacements=(),
        deleted=False,
        warnings=("parsed warning",) if version == 1 else (),
    )


def _outcome(
    identifier: str, record: VCVRecord, *, source_suffix: str = ""
) -> VersionResult:
    raw = f'<VariationArchive Accession="{ACCESSION}" Version="{record.version}" />'
    return VersionResult(
        requested_identifier=identifier,
        source_request=f"https://eutils.ncbi.nlm.nih.gov/efetch?{identifier}{source_suffix}",
        retrieved_at_utc=f"2026-07-2{record.version}T00:00:00+00:00",
        response_bytes=len(raw.encode()),
        status="available",
        record=record,
        raw_xml=raw,
    )


def _history(
    detected_change: ClassificationChange = "VUS_to_Pathogenic",
) -> VCVHistoryResult:
    first = _outcome(f"{ACCESSION}.1", _record(1, "Uncertain significance"))
    second = _outcome(f"{ACCESSION}.2", _record(2, "Pathogenic"))
    current = _outcome(ACCESSION, second.record, source_suffix="&current=true")
    comparison = VersionComparison(
        earlier_version=1,
        later_version=2,
        earlier_identifier=f"{ACCESSION}.1",
        later_identifier=f"{ACCESSION}.2",
        earlier_germline_classification="Uncertain significance",
        later_germline_classification="Pathogenic",
        earlier_review_status="criteria provided",
        later_review_status="criteria provided",
        detected_classification_change=detected_change,
        submissions_changed=False,
        warnings=(),
        confidence="high",
    )
    changed = detected_change not in {
        "No_Classification_Change",
        "Non_Germline_Change",
        "Missing_Classification",
        "Unable_to_Compare",
    }
    summary = VCVHistorySummary(
        first_available_version=1,
        newest_available_version=2,
        retrieved_version_count=2,
        any_germline_classification_changed=changed,
        first_detected_germline_change=comparison if changed else None,
        latest_germline_classification="Pathogenic",
        unresolved_warnings=("summary warning",),
    )
    return VCVHistoryResult(
        requested_accession=ACCESSION,
        current_identifier=f"{ACCESSION}.2",
        version_plan=(1, 2),
        current_result=current,
        results=(first, second),
        comparisons=(comparison,),
        summary=summary,
        total_response_bytes=sum(
            item.response_bytes for item in (current, first, second)
        ),
    )


def _save(root: Path) -> dict[str, object]:
    return save_history(
        root,
        _history(),
        app_version="0.1.0",
        git_commit="abc123",
        warnings=("caller warning",),
    )


def test_safe_paths_require_path_and_canonical_unversioned_accession(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="pathlib.Path"):
        list_histories(str(tmp_path))  # type: ignore[arg-type]
    for unsafe in ("../VCV000014206", "vcv000014206", f"{ACCESSION}.1"):
        with pytest.raises(VCVHistoryStoreError):
            load_review(tmp_path, unsafe)


def test_save_uses_small_atomic_separate_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacements: list[tuple[Path, Path]] = []
    real_replace = store.os.replace

    def recording_replace(source: Path, destination: Path) -> None:
        replacements.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(store.os, "replace", recording_replace)
    _save(tmp_path)
    directory = tmp_path / ACCESSION

    assert {item.name for item in directory.iterdir()} == {
        "metadata.json",
        "versions.json",
        "comparisons.json",
        "manifest.json",
        "review.json",
        "raw",
    }
    assert {item.name for item in (directory / "raw").iterdir()} == {
        f"{ACCESSION}.xml",
        f"{ACCESSION}.1.xml",
        f"{ACCESSION}.2.xml",
    }
    assert replacements
    assert all(source.name.endswith(".tmp") for source, _ in replacements)
    assert not list(directory.rglob("*.tmp"))
    assert all(
        item.stat().st_size < store.MAX_JSON_BYTES for item in directory.glob("*.json")
    )
    versions_text = (directory / "versions.json").read_text(encoding="utf-8")
    assert "raw_xml" not in versions_text
    for name in (
        "metadata.json",
        "versions.json",
        "comparisons.json",
        "manifest.json",
        "review.json",
    ):
        assert json.loads((directory / name).read_text())["schema_version"] == 1


def test_oversized_raw_xml_is_rejected_before_creating_accession_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history = _history()
    oversized = "x" * 101
    object.__setattr__(history.current_result, "raw_xml", oversized)
    monkeypatch.setattr(store, "MAX_RESPONSE_BYTES", 100)

    with pytest.raises(VCVHistoryStoreError, match="raw XML"):
        _save_result(tmp_path, history)
    assert not (tmp_path / ACCESSION).exists()


def _save_result(root: Path, history: VCVHistoryResult) -> dict[str, object]:
    return save_history(root, history, app_version="test", git_commit="test")


def test_review_has_exact_requirements_and_enforces_manual_verification(
    tmp_path: Path,
) -> None:
    _save(tmp_path)
    review = load_review(tmp_path, ACCESSION)
    assert set(review["verification"]) == set(VERIFICATION_REQUIREMENTS)
    assert set(review["verification"].values()) == {False}

    with pytest.raises(VCVHistoryStoreError, match="Every verification"):
        update_review(tmp_path, ACCESSION, status="manually_verified")

    verified = update_review(
        tmp_path,
        ACCESSION,
        status="manually_verified",
        reviewer_decision="include",
        verification={item: True for item in VERIFICATION_REQUIREMENTS},
        sources=["https://eutils.ncbi.nlm.nih.gov/efetch?VCV000014206.1"],
    )
    assert verified["status"] == "manually_verified"
    assert load_history(tmp_path, ACCESSION)["manifest"]["manual_verification"] is True


@pytest.mark.parametrize("status", ["ambiguous", "excluded"])
def test_ambiguous_and_excluded_reviews_require_notes(
    tmp_path: Path, status: str
) -> None:
    _save(tmp_path)
    with pytest.raises(VCVHistoryStoreError, match="require a note"):
        update_review(tmp_path, ACCESSION, status=status)  # type: ignore[arg-type]
    review = update_review(
        tmp_path,
        ACCESSION,
        status=status,  # type: ignore[arg-type]
        notes="Official records conflict.",
    )
    assert review["status"] == status


def test_manual_corrections_are_separate_and_originals_remain_unchanged(
    tmp_path: Path,
) -> None:
    _save(tmp_path)
    versions_path = tmp_path / ACCESSION / "versions.json"
    original = versions_path.read_bytes()

    review = update_review(
        tmp_path,
        ACCESSION,
        status="needs_review",
        manual_corrections={
            "versions.0.record.germline.classification": "Likely benign"
        },
        notes="Correction pending source verification.",
    )

    assert versions_path.read_bytes() == original
    assert review["manual_corrections"] == {
        "versions.0.record.germline.classification": "Likely benign"
    }
    parsed = load_history(tmp_path, ACCESSION)["versions"]
    assert parsed["versions"][0]["record"]["germline"]["classification"] == (
        "Uncertain significance"
    )


def test_manifest_records_provenance_sizes_timestamps_and_warnings(
    tmp_path: Path,
) -> None:
    manifest = _save(tmp_path)
    assert manifest["accession"] == ACCESSION
    assert manifest["app_version"] == "0.1.0"
    assert manifest["git_commit"] == "abc123"
    assert manifest["total_bytes"] == _history().total_response_bytes
    assert len(manifest["source_requests"]) == 3
    assert manifest["source_requests"][0]["status"] == "available"
    assert manifest["source_requests"][0]["message"] is None
    assert manifest["response_sizes"][ACCESSION] > 0
    assert manifest["retrieval_timestamps"][f"{ACCESSION}.1"].endswith("+00:00")
    assert manifest["warnings"] == [
        "caller warning",
        "summary warning",
        "parsed warning",
    ]
    assert manifest["manual_verification"] is False
    assert len(manifest["automatic_artifact_digest"]) == 64
    assert (
        manifest["automatic_artifact_digest"]
        == load_review(tmp_path, ACCESSION)["automatic_artifact_digest"]
    )


def test_list_load_and_progress_metrics(tmp_path: Path) -> None:
    _save(tmp_path)
    (tmp_path / "not-an-accession").mkdir()
    metrics = progress_metrics(tmp_path)

    assert list_histories(tmp_path) == (ACCESSION,)
    assert load_history(tmp_path, ACCESSION)["metadata"]["current_identifier"] == (
        f"{ACCESSION}.2"
    )
    assert load_history(tmp_path, ACCESSION)["metadata"]["summary"] == (
        _history().summary.to_dict()
    )
    assert metrics["histories"] == 1
    assert metrics["versions"] == 2
    assert metrics["changed_histories"] == 1
    assert metrics["verified"] == 0
    assert metrics["bytes"] > 0
    assert isinstance(metrics["storage"], str)
    assert json.loads((tmp_path / ACCESSION / "review.json").read_text())["status"] == (
        "unreviewed"
    )


@pytest.mark.parametrize(
    "detected_change",
    [
        "No_Classification_Change",
        "Non_Germline_Change",
        "Missing_Classification",
        "Unable_to_Compare",
    ],
)
def test_progress_does_not_count_non_germline_transition_values(
    tmp_path: Path, detected_change: ClassificationChange
) -> None:
    _save_result(tmp_path, _history(detected_change))

    assert progress_metrics(tmp_path)["changed_histories"] == 0


def test_refresh_preserves_identical_verification_and_resets_changed_evidence(
    tmp_path: Path,
) -> None:
    _save(tmp_path)
    verified = update_review(
        tmp_path,
        ACCESSION,
        status="manually_verified",
        reviewer_decision="include",
        notes="Human note that must remain.",
        manual_corrections={"gene": "CCL2"},
        verification={item: True for item in VERIFICATION_REQUIREMENTS},
        sources=["https://eutils.ncbi.nlm.nih.gov/efetch?VCV000014206.1"],
    )
    original_digest = verified["automatic_artifact_digest"]

    _save(tmp_path)
    unchanged = load_review(tmp_path, ACCESSION)
    assert unchanged["status"] == "manually_verified"
    assert unchanged["reviewer_decision"] == "include"
    assert all(unchanged["verification"].values())
    assert unchanged["automatic_artifact_digest"] == original_digest

    changed_manifest = _save_result(tmp_path, _history("Other_Germline_Change"))
    changed = load_review(tmp_path, ACCESSION)
    assert changed["status"] == "needs_review"
    assert changed["reviewer_decision"] == ""
    assert not any(changed["verification"].values())
    assert changed["manual_corrections"] == {"gene": "CCL2"}
    assert changed["sources"] == [
        "https://eutils.ncbi.nlm.nih.gov/efetch?VCV000014206.1"
    ]
    assert changed["notes"].startswith("Human note that must remain.")
    assert "Automatic evidence changed" in changed["notes"]
    assert changed["automatic_artifact_digest"] != original_digest
    assert (
        changed_manifest["automatic_artifact_digest"]
        == changed["automatic_artifact_digest"]
    )
    assert changed_manifest["manual_verification"] is False


def test_save_migrates_only_exact_legacy_review_and_forces_reverification(
    tmp_path: Path,
) -> None:
    _save(tmp_path)
    update_review(
        tmp_path,
        ACCESSION,
        status="manually_verified",
        reviewer_decision="include",
        notes="Legacy human note.",
        manual_corrections={"gene": "CCL2"},
        verification={item: True for item in VERIFICATION_REQUIREMENTS},
        sources=["https://eutils.ncbi.nlm.nih.gov/efetch?VCV000014206.1"],
    )
    review_path = tmp_path / ACCESSION / "review.json"
    legacy = json.loads(review_path.read_text(encoding="utf-8"))
    legacy.pop("automatic_artifact_digest")
    review_path.write_text(json.dumps(legacy), encoding="utf-8")

    with pytest.raises(VCVHistoryStoreError, match="schema version 1"):
        load_review(tmp_path, ACCESSION)

    manifest = _save(tmp_path)
    migrated = load_review(tmp_path, ACCESSION)
    assert migrated["status"] == "needs_review"
    assert migrated["reviewer_decision"] == ""
    assert not any(migrated["verification"].values())
    assert migrated["manual_corrections"] == {"gene": "CCL2"}
    assert migrated["sources"] == [
        "https://eutils.ncbi.nlm.nih.gov/efetch?VCV000014206.1"
    ]
    assert migrated["notes"].startswith("Legacy human note.")
    assert "Automatic evidence changed" in migrated["notes"]
    assert (
        migrated["automatic_artifact_digest"] == manifest["automatic_artifact_digest"]
    )

    malformed_root = tmp_path / "malformed"
    _save(malformed_root)
    malformed_path = malformed_root / ACCESSION / "review.json"
    malformed = json.loads(malformed_path.read_text(encoding="utf-8"))
    malformed.pop("automatic_artifact_digest")
    malformed["unexpected"] = True
    malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(VCVHistoryStoreError, match="schema version 1"):
        _save(malformed_root)


def test_load_history_holds_writer_lock_for_the_complete_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _save(tmp_path)
    metadata_read = threading.Event()
    release_reader = threading.Event()
    update_finished = threading.Event()
    original_read_json = store._read_json
    loaded: list[dict[str, object]] = []
    failures: list[BaseException] = []
    reader: threading.Thread

    def pausing_read(path: Path, **kwargs: object) -> object:
        value = original_read_json(path, **kwargs)  # type: ignore[arg-type]
        if path.name == "metadata.json" and threading.current_thread() is reader:
            metadata_read.set()
            release_reader.wait(timeout=2)
        return value

    monkeypatch.setattr(store, "_read_json", pausing_read)

    def read_history() -> None:
        try:
            loaded.append(load_history(tmp_path, ACCESSION))
        except BaseException as exc:
            failures.append(exc)

    def write_review() -> None:
        try:
            update_review(tmp_path, ACCESSION, status="needs_review")
            update_finished.set()
        except BaseException as exc:
            failures.append(exc)

    reader = threading.Thread(target=read_history)
    reader.start()
    assert metadata_read.wait(timeout=2)
    writer = threading.Thread(target=write_review)
    writer.start()
    assert not update_finished.wait(timeout=0.05)
    release_reader.set()
    reader.join(timeout=2)
    writer.join(timeout=2)

    assert not failures
    assert not reader.is_alive() and not writer.is_alive()
    assert loaded[0]["review"]["status"] == "unreviewed"
    assert load_review(tmp_path, ACCESSION)["status"] == "needs_review"


def test_refresh_removes_only_stale_raw_xml_after_successful_validation(
    tmp_path: Path,
) -> None:
    history = _history()
    _save_result(tmp_path, history)
    raw_directory = tmp_path / ACCESSION / "raw"
    unrelated = raw_directory / "research-note.txt"
    unrelated.write_text("keep", encoding="utf-8")
    reduced_summary = VCVHistorySummary(
        first_available_version=1,
        newest_available_version=1,
        retrieved_version_count=1,
        any_germline_classification_changed=False,
        first_detected_germline_change=None,
        latest_germline_classification="Uncertain significance",
        unresolved_warnings=(),
    )
    reduced = replace(
        history,
        version_plan=(1,),
        results=(history.results[0],),
        comparisons=(),
        summary=reduced_summary,
        total_response_bytes=(
            history.current_result.response_bytes + history.results[0].response_bytes
        ),
    )

    _save_result(tmp_path, reduced)

    assert {item.name for item in raw_directory.iterdir()} == {
        f"{ACCESSION}.xml",
        f"{ACCESSION}.1.xml",
        "research-note.txt",
    }
