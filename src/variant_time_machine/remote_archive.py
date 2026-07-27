"""Bounded streaming access to official compressed ClinVar VCV XML releases."""

import gzip
import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from typing import BinaryIO

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from variant_time_machine.clinvar_api import normalize_variant_identifier
from variant_time_machine.config import (
    LARGE_DOWNLOAD_THRESHOLD_BYTES,
    PILOT_MAX_RECORDS,
    PILOT_MAX_TEMP_BYTES,
    PILOT_PROGRESS_BYTES,
    ClinVarXMLRelease,
)
from variant_time_machine.download import require_transfer_confirmation

LOGGER = logging.getLogger(__name__)
USER_AGENT = "VariantTimeMachine/0.1 research-education"
REQUEST_TIMEOUT = (15, 120)


class RemoteArchiveError(RuntimeError):
    """Base error for safe remote archive access."""


class ConfirmationRequired(RemoteArchiveError):
    """Raised when a large transfer was not explicitly confirmed."""


class ExtractionLimitError(RemoteArchiveError):
    """Raised when a configured transfer or output limit is exceeded."""


@dataclass(frozen=True)
class RemoteReleaseMetadata:
    """Small remote metadata result from HEAD and MD5 requests."""

    label: str
    release_date: str
    source_url: str
    schema_version: str
    expected_compressed_size_bytes: int
    reported_compressed_size_bytes: int | None
    expected_md5: str
    reported_md5: str | None
    size_matches: bool | None
    md5_matches: bool | None


@dataclass(frozen=True)
class ExtractedVCVRecord:
    """Small set of auditable fields extracted from one VCV record."""

    variation_id: str
    accession: str | None
    version: str | None
    record_type: str | None
    record_status: str | None
    name: str | None
    allele_ids: tuple[str, ...]
    genes: tuple[str, ...]
    conditions: tuple[str, ...]
    germline_classification: str | None
    germline_review_status: str | None
    germline_last_evaluated: str | None
    germline_submission_count: str | None
    somatic_clinical_impact: str | None
    oncogenicity_classification: str | None
    replaced_by: tuple[str, ...]
    replacement_list: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return fields in a JSON-friendly form."""
        value = asdict(self)
        for field in (
            "allele_ids",
            "genes",
            "conditions",
            "replaced_by",
            "replacement_list",
        ):
            value[field] = list(value[field])
        return value


@dataclass(frozen=True)
class ExtractionResult:
    """Records and transfer facts from one bounded stream scan."""

    records: tuple[ExtractedVCVRecord, ...]
    requested_ids: tuple[str, ...]
    missing_ids: tuple[str, ...]
    compressed_bytes_read: int
    estimated_output_bytes: int
    completed_full_scan: bool


class _CountingReader:
    """Count compressed bytes and stop a stream at a hard transfer limit."""

    def __init__(
        self,
        raw: BinaryIO,
        max_bytes: int,
        progress_bytes: int,
        progress: Callable[[int], None],
    ) -> None:
        self.raw = raw
        self.max_bytes = max_bytes
        self.progress_bytes = max(1, progress_bytes)
        self.progress = progress
        self.bytes_read = 0
        self._next_progress = self.progress_bytes

    def read(self, size: int = -1) -> bytes:
        """Read without allowing the compressed stream to pass the limit."""
        remaining = self.max_bytes - self.bytes_read
        if remaining <= 0:
            raise ExtractionLimitError(
                f"Compressed transfer exceeded {self.max_bytes:,} bytes."
            )
        requested = remaining + 1 if size < 0 else min(size, remaining + 1)
        chunk = self.raw.read(requested)
        self.bytes_read += len(chunk)
        if self.bytes_read > self.max_bytes:
            raise ExtractionLimitError(
                f"Compressed transfer exceeded {self.max_bytes:,} bytes."
            )
        while self.bytes_read >= self._next_progress:
            self.progress(self.bytes_read)
            self._next_progress += self.progress_bytes
        return chunk


def _session() -> requests.Session:
    """Create a retrying HTTP session for read-only official NCBI requests."""
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "HEAD"}),
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def inspect_remote_release(
    release: ClinVarXMLRelease,
    *,
    session: requests.Session | None = None,
) -> RemoteReleaseMetadata:
    """Read only response headers and the release's small official MD5 file."""
    own_session = session is None
    client = session or _session()
    try:
        head = client.head(
            release.source_url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT,
        )
        head.raise_for_status()
        size_text = head.headers.get("Content-Length")
        reported_size = int(size_text) if size_text and size_text.isdigit() else None

        md5_response = client.get(
            f"{release.source_url}.md5",
            timeout=REQUEST_TIMEOUT,
        )
        md5_response.raise_for_status()
        md5_text = md5_response.text[:1024].strip().split()
        reported_md5 = md5_text[0].casefold() if md5_text else None
    except (requests.RequestException, ValueError) as exc:
        raise RemoteArchiveError(
            f"Could not inspect {release.source_url}: {exc}"
        ) from exc
    finally:
        if own_session:
            client.close()

    return RemoteReleaseMetadata(
        label=release.label,
        release_date=release.release_date.isoformat(),
        source_url=release.source_url,
        schema_version=release.schema_version,
        expected_compressed_size_bytes=release.compressed_size_bytes,
        reported_compressed_size_bytes=reported_size,
        expected_md5=release.md5,
        reported_md5=reported_md5,
        size_matches=(
            reported_size == release.compressed_size_bytes
            if reported_size is not None
            else None
        ),
        md5_matches=(reported_md5 == release.md5 if reported_md5 else None),
    )


def _text(element: ET.Element | None) -> str | None:
    """Return clean element text."""
    if element is None or element.text is None:
        return None
    value = element.text.strip()
    return value or None


def _unique(values: Iterable[str | None]) -> tuple[str, ...]:
    """Return unique nonempty strings while preserving their order."""
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return tuple(result)


def _classification(
    record: ET.Element, tag: str
) -> tuple[str | None, str | None, str | None, str | None]:
    """Read one classification type without mixing it with other types."""
    block = record.find(f"./Classifications/{tag}")
    if block is None:
        return None, None, None, None
    descriptions = _unique(_text(item) for item in block.findall("./Description"))
    return (
        " | ".join(descriptions) if descriptions else None,
        _text(block.find("./ReviewStatus")),
        block.get("DateLastEvaluated"),
        block.get("NumberOfSubmissions"),
    )


def parse_variation_archive(record: ET.Element) -> ExtractedVCVRecord:
    """Parse one VariationArchive element into a small stable representation."""
    classified = record.find("./ClassifiedRecord")
    variant = None
    if classified is not None:
        for tag in ("SimpleAllele", "Haplotype", "Genotype"):
            variant = classified.find(f"./{tag}")
            if variant is not None:
                break

    germline, review, evaluated, submissions = _classification(
        record, "GermlineClassification"
    )
    somatic, _, _, _ = _classification(record, "SomaticClinicalImpact")
    oncogenicity, _, _, _ = _classification(record, "OncogenicityClassification")

    conditions = _unique(
        _text(item)
        for path in (
            "./Classifications/GermlineClassification/ConditionList/Condition/Name",
            "./Classifications/SomaticClinicalImpact/ConditionList/Condition/Name",
            "./Classifications/OncogenicityClassification/ConditionList/Condition/Name",
        )
        for item in record.findall(path)
    )
    genes = _unique(
        item.get("Symbol") or _text(item.find("./Symbol/ElementValue"))
        for item in (variant.iter("Gene") if variant is not None else ())
    )
    allele_ids = _unique(
        item.get("AlleleID")
        for item in (variant.iter() if variant is not None else ())
        if item.tag == "SimpleAllele"
    )

    replaced_by = _unique(
        (item.get("Accession") or _text(item))
        for item in record.findall("./ReplacedBy")
    )
    replacement_list = _unique(
        (item.get("Accession") or _text(item))
        for item in record.findall("./ReplacedList/Replaced")
    )
    return ExtractedVCVRecord(
        variation_id=record.get("VariationID", ""),
        accession=record.get("Accession"),
        version=record.get("Version"),
        record_type=record.get("RecordType"),
        record_status=_text(record.find("./RecordStatus")),
        name=_text(variant.find("./Name")) if variant is not None else None,
        allele_ids=allele_ids,
        genes=genes,
        conditions=conditions,
        germline_classification=germline,
        germline_review_status=review,
        germline_last_evaluated=evaluated,
        germline_submission_count=submissions,
        somatic_clinical_impact=somatic,
        oncogenicity_classification=oncogenicity,
        replaced_by=replaced_by,
        replacement_list=replacement_list,
    )


def extract_remote_records(
    release: ClinVarXMLRelease,
    requested_ids: Iterable[str],
    *,
    confirmed: bool,
    max_records: int = PILOT_MAX_RECORDS,
    max_output_bytes: int = PILOT_MAX_TEMP_BYTES,
    max_transfer_bytes: int | None = None,
    progress_bytes: int = PILOT_PROGRESS_BYTES,
    session: requests.Session | None = None,
) -> ExtractionResult:
    """Stream one gzip archive and retain only explicitly requested records."""
    try:
        require_transfer_confirmation(
            release.source_url,
            release.compressed_size_bytes,
            "Read selected historical records from a fixed ClinVar XML release",
            confirmed=confirmed,
        )
    except ValueError as exc:
        raise ConfirmationRequired(str(exc)) from exc
    identifiers = tuple(
        dict.fromkeys(normalize_variant_identifier(value) for value in requested_ids)
    )
    if not identifiers:
        raise ValueError("At least one Variation ID is required.")
    if len(identifiers) > max_records:
        raise ExtractionLimitError(
            f"Requested {len(identifiers)} records; the limit is {max_records}."
        )
    transfer_limit = max_transfer_bytes or min(
        release.compressed_size_bytes + 1024,
        LARGE_DOWNLOAD_THRESHOLD_BYTES,
    )
    wanted = set(identifiers)
    found: dict[str, ExtractedVCVRecord] = {}
    output_bytes = 0
    completed_full_scan = False
    own_session = session is None
    client = session or _session()
    response = None

    try:
        response = client.get(
            release.source_url,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        response.raw.decode_content = False
        counted = _CountingReader(
            response.raw,
            transfer_limit,
            progress_bytes,
            lambda count: LOGGER.info(
                "%s: read %s compressed bytes", release.label, f"{count:,}"
            ),
        )
        with gzip.GzipFile(fileobj=counted, mode="rb") as decompressed:
            for _event, element in ET.iterparse(decompressed, events=("end",)):
                if element.tag != "VariationArchive":
                    continue
                variation_id = element.get("VariationID", "")
                if variation_id in wanted:
                    parsed = parse_variation_archive(element)
                    record_bytes = len(
                        json.dumps(parsed.to_dict(), sort_keys=True).encode("utf-8")
                    )
                    if output_bytes + record_bytes > max_output_bytes:
                        raise ExtractionLimitError(
                            f"Extracted output would exceed {max_output_bytes:,} bytes."
                        )
                    found[variation_id] = parsed
                    output_bytes += record_bytes
                element.clear()
                if wanted.issubset(found):
                    break
            else:
                completed_full_scan = True
    except (requests.RequestException, gzip.BadGzipFile, ET.ParseError, OSError) as exc:
        raise RemoteArchiveError(
            f"Could not stream {release.source_url}: {exc}"
        ) from exc
    finally:
        if response is not None:
            response.close()
        if own_session:
            client.close()

    ordered_records = tuple(found[value] for value in identifiers if value in found)
    missing = tuple(value for value in identifiers if value not in found)
    return ExtractionResult(
        records=ordered_records,
        requested_ids=identifiers,
        missing_ids=missing,
        compressed_bytes_read=counted.bytes_read,
        estimated_output_bytes=output_bytes,
        completed_full_scan=completed_full_scan,
    )


def calculate_md5(path: str) -> str:
    """Calculate a local file MD5 only when an explicit retained file exists."""
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
