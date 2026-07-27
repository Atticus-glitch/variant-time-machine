"""Bounded retrieval and comparison of versioned ClinVar VCV records."""

from __future__ import annotations

import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CLINVAR_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
USER_AGENT = "VariantTimeMachine/0.1 (research; contact: local-user)"
REQUEST_TIMEOUT = (10, 30)
DEFAULT_MAX_REQUESTS = 25
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 50 * 1024 * 1024
DEFAULT_REQUEST_INTERVAL_SECONDS = 0.34

ClassificationChange = Literal[
    "No_Classification_Change",
    "VUS_to_Pathogenic",
    "VUS_to_Likely_Pathogenic",
    "VUS_to_Benign",
    "VUS_to_Likely_Benign",
    "Pathogenic_to_VUS",
    "Benign_to_VUS",
    "Became_Conflicting",
    "Conflict_Resolved",
    "Other_Germline_Change",
    "Non_Germline_Change",
    "Missing_Classification",
    "Unable_to_Compare",
]
ComparisonConfidence = Literal["high", "limited", "unable"]
OutcomeStatus = Literal[
    "available",
    "missing",
    "deleted/replaced",
    "request failure",
    "parsing failure",
]


class VCVHistoryError(RuntimeError):
    """Base error for bounded VCV history operations."""


class InvalidVCVAccession(ValueError):
    """Raised when a VCV accession is not in strict canonical form."""


class RequestLimitError(VCVHistoryError):
    """Raised when a requested version plan exceeds its request budget."""


class TransferLimitError(VCVHistoryError):
    """Raised when an individual or total response limit is exceeded."""


class RetrievalCancelled(VCVHistoryError):
    """Raised when retrieval is cancelled between requests."""


@dataclass(frozen=True)
class VCVAccession:
    """A validated canonical VCV accession and optional version."""

    accession: str
    version: int | None = None

    @property
    def identifier(self) -> str:
        """Return the accession with its version when one was supplied."""
        if self.version is None:
            return self.accession
        return f"{self.accession}.{self.version}"


@dataclass(frozen=True)
class ClassificationBlock:
    """One classification type, deliberately kept separate from the others."""

    classification: str | None
    review_status: str | None
    date_last_evaluated: str | None
    submission_count: int | None


@dataclass(frozen=True)
class VCVRecord:
    """Stable JSON-friendly fields parsed from one EFetch XML record."""

    accession: str
    version: int
    accession_version: str
    variation_id: str | None
    record_type: str | None
    genes: tuple[str, ...]
    name: str | None
    hgvs: tuple[str, ...]
    date_created: str | None
    date_last_updated: str | None
    date_deleted: str | None
    germline: ClassificationBlock
    somatic_clinical_impact: ClassificationBlock
    oncogenicity: ClassificationBlock
    conditions: tuple[str, ...]
    record_status: str | None
    replaced_by: tuple[str, ...]
    replacements: tuple[str, ...]
    deleted: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation."""
        value = asdict(self)
        for field in ("genes", "hgvs", "conditions", "replaced_by", "replacements"):
            value[field] = list(value[field])
        value["warnings"] = list(self.warnings)
        return value


@dataclass(frozen=True)
class VersionResult:
    """Outcome and provenance for one exact source request."""

    requested_identifier: str
    source_request: str
    retrieved_at_utc: str
    response_bytes: int
    status: OutcomeStatus
    record: VCVRecord | None
    raw_xml: str | None
    message: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation including retained raw XML."""
        value = asdict(self)
        value["record"] = self.record.to_dict() if self.record else None
        return value


@dataclass(frozen=True)
class VersionComparison:
    """Detected classification change between consecutive available records."""

    earlier_version: int
    later_version: int
    earlier_identifier: str
    later_identifier: str
    earlier_germline_classification: str | None
    later_germline_classification: str | None
    earlier_review_status: str | None
    later_review_status: str | None
    detected_classification_change: ClassificationChange
    submissions_changed: bool | None
    warnings: tuple[str, ...]
    confidence: ComparisonConfidence

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation."""
        value = asdict(self)
        value["warnings"] = list(self.warnings)
        return value


@dataclass(frozen=True)
class VCVHistorySummary:
    """Small integration-oriented summary of retrieved available versions."""

    first_available_version: int | None
    newest_available_version: int | None
    retrieved_version_count: int
    any_germline_classification_changed: bool
    first_detected_germline_change: VersionComparison | None
    latest_germline_classification: str | None
    unresolved_warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation."""
        return {
            "first_available_version": self.first_available_version,
            "newest_available_version": self.newest_available_version,
            "retrieved_version_count": self.retrieved_version_count,
            "any_germline_classification_changed": (
                self.any_germline_classification_changed
            ),
            "first_detected_germline_change": (
                self.first_detected_germline_change.to_dict()
                if self.first_detected_germline_change
                else None
            ),
            "latest_germline_classification": self.latest_germline_classification,
            "unresolved_warnings": list(self.unresolved_warnings),
        }


@dataclass(frozen=True)
class VCVHistoryResult:
    """Complete bounded history result and its transfer accounting."""

    requested_accession: str
    current_identifier: str | None
    version_plan: tuple[int, ...]
    current_result: VersionResult
    results: tuple[VersionResult, ...]
    comparisons: tuple[VersionComparison, ...]
    summary: VCVHistorySummary
    total_response_bytes: int
    cancelled: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-friendly representation."""
        return {
            "requested_accession": self.requested_accession,
            "current_identifier": self.current_identifier,
            "version_plan": list(self.version_plan),
            "current_result": self.current_result.to_dict(),
            "results": [item.to_dict() for item in self.results],
            "comparisons": [item.to_dict() for item in self.comparisons],
            "summary": self.summary.to_dict(),
            "total_response_bytes": self.total_response_bytes,
            "cancelled": self.cancelled,
        }


class _CancellationEvent(Protocol):
    def is_set(self) -> bool: ...


ProgressCallback = Callable[[dict[str, object]], None]


def _emit(
    progress: ProgressCallback | None,
    event: str,
    **details: object,
) -> None:
    """Best-effort progress reporting must not break retrieval work."""
    if progress is None:
        return
    try:
        progress({"event": event, **details})
    except Exception:
        return


def validate_vcv_accession(identifier: str) -> VCVAccession:
    """Validate an uppercase, zero-padded VCV accession with optional version."""
    if not isinstance(identifier, str):
        raise InvalidVCVAccession("VCV accession must be text.")
    match = re.fullmatch(r"(VCV[0-9]{9})(?:\.([1-9][0-9]*))?", identifier)
    if match is None or match.group(1) == "VCV000000000":
        raise InvalidVCVAccession(
            "Use canonical VCV format VCV######### or VCV#########.version."
        )
    version = int(match.group(2)) if match.group(2) else None
    return VCVAccession(match.group(1), version)


def plan_version_range(
    current_version: int,
    *,
    mode: Literal["all", "custom", "endpoints"] = "all",
    versions: Iterable[int] | None = None,
    max_requests: int = DEFAULT_MAX_REQUESTS,
) -> tuple[int, ...]:
    """Plan bounded version requests from the current official record version."""
    if current_version < 1:
        raise ValueError("Current VCV version must be positive.")
    if max_requests < 1:
        raise ValueError("max_requests must be positive.")
    if mode == "all":
        planned = tuple(range(1, current_version + 1))
    elif mode == "endpoints":
        planned = (1,) if current_version == 1 else (1, current_version)
    elif mode == "custom":
        if versions is None:
            raise ValueError("Custom mode requires versions.")
        supplied = tuple(versions)
        if any(
            not isinstance(item, int) or isinstance(item, bool) for item in supplied
        ):
            raise ValueError("Custom versions must be integers.")
        planned = tuple(sorted(set(supplied)))
        if not planned or planned[0] < 1 or planned[-1] > current_version:
            raise ValueError("Custom versions must be between 1 and current version.")
    else:
        raise ValueError("mode must be 'all', 'custom', or 'endpoints'.")
    if len(planned) > max_requests:
        raise RequestLimitError(
            f"Version plan requires {len(planned)} requests; limit is {max_requests}."
        )
    return planned


def create_retrying_session() -> requests.Session:
    """Create a retrying session identified for responsible NCBI use."""
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _descendants(element: ET.Element, name: str) -> Iterator[ET.Element]:
    return (item for item in element.iter() if _local_name(item.tag) == name)


def _children(element: ET.Element, name: str) -> Iterator[ET.Element]:
    return (item for item in element if _local_name(item.tag) == name)


def _first_descendant(element: ET.Element, name: str) -> ET.Element | None:
    return next(_descendants(element, name), None)


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = " ".join(part.strip() for part in element.itertext() if part.strip())
    return value or None


def _unique(values: Iterable[str | None]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(value for value in values if value))


def _attribute(element: ET.Element, *names: str) -> str | None:
    for name in names:
        value = element.get(name)
        if value:
            return value.strip()
    return None


def _aggregate_classifications(record: ET.Element) -> ET.Element | None:
    """Select only the VCV aggregate classification container."""
    classified = next(_children(record, "ClassifiedRecord"), None)
    if classified is not None:
        classifications = next(_children(classified, "Classifications"), None)
        if classifications is not None:
            return classifications
    return next(_children(record, "Classifications"), None)


def _aggregate_variant(record: ET.Element) -> ET.Element | None:
    """Select only the variant represented by the aggregate VCV record."""
    classified = next(_children(record, "ClassifiedRecord"), None)
    scopes = (classified, record) if classified is not None else (record,)
    for scope in scopes:
        for name in ("SimpleAllele", "Haplotype", "Genotype"):
            variant = next(_children(scope, name), None)
            if variant is not None:
                return variant
    return None


def _classification(
    classifications: ET.Element | None,
    name: str,
) -> ClassificationBlock:
    block = (
        next(_children(classifications, name), None)
        if classifications is not None
        else None
    )
    if block is None:
        return ClassificationBlock(None, None, None, None)
    description_elements = tuple(_children(block, "Description"))
    descriptions = _unique(_text(item) for item in description_elements)
    description = description_elements[0] if description_elements else None
    count_text = _attribute(block, "NumberOfSubmissions", "SubmissionCount")
    if count_text is None and description is not None:
        count_text = _attribute(
            description,
            "NumberOfSubmissions",
            "SubmissionCount",
        )
    try:
        count = int(count_text) if count_text is not None else None
    except ValueError:
        count = None
    evaluated = _attribute(block, "DateLastEvaluated")
    if evaluated is None and description is not None:
        evaluated = _attribute(description, "DateLastEvaluated")
    return ClassificationBlock(
        classification=" | ".join(descriptions) if descriptions else None,
        review_status=_text(next(_children(block, "ReviewStatus"), None)),
        date_last_evaluated=evaluated,
        submission_count=count,
    )


def _preferred_name(element: ET.Element) -> str | None:
    """Read a ClinVar name, preferring explicitly preferred ElementValue text."""
    values = tuple(_descendants(element, "ElementValue"))
    preferred = tuple(
        item
        for item in values
        if (_attribute(item, "Type") or "").casefold() == "preferred"
    )
    selected = preferred or values
    if selected:
        return _text(selected[0])
    return _text(element)


def _condition_names(classifications: ET.Element | None) -> tuple[str, ...]:
    """Read conditions only from VCV aggregate classification blocks."""
    if classifications is None:
        return ()
    classification_names = {
        "GermlineClassification",
        "SomaticClinicalImpact",
        "OncogenicityClassification",
    }
    values: list[str | None] = []
    for block in classifications:
        if _local_name(block.tag) not in classification_names:
            continue
        for condition in _descendants(block, "Condition"):
            values.extend(
                _preferred_name(name) for name in _children(condition, "Name")
            )
        for trait in _descendants(block, "Trait"):
            values.extend(_preferred_name(name) for name in _children(trait, "Name"))
    return _unique(values)


def parse_efetch_xml(raw_xml: str | bytes) -> VCVRecord:
    """Parse one EFetch XML response without relying on namespace or wrapper shape."""
    try:
        root = ET.fromstring(raw_xml)
    except (ET.ParseError, ValueError) as exc:
        raise VCVHistoryError(f"Invalid ClinVar EFetch XML: {exc}") from exc
    records = tuple(_descendants(root, "VariationArchive"))
    if not records:
        raise VCVHistoryError(
            "ClinVar EFetch XML contained no VariationArchive; exactly one "
            "VariationArchive is required."
        )
    if len(records) > 1:
        raise VCVHistoryError(
            "ClinVar EFetch XML must contain exactly one VariationArchive; "
            f"found {len(records)}."
        )
    record = records[0]

    accession = _attribute(record, "Accession")
    version_text = _attribute(record, "Version")
    if accession is None or version_text is None:
        raise VCVHistoryError("VariationArchive lacked accession or version.")
    try:
        validated = validate_vcv_accession(f"{accession}.{version_text}")
    except InvalidVCVAccession as exc:
        raise VCVHistoryError(
            f"VariationArchive identifier was invalid: {exc}"
        ) from exc
    assert validated.version is not None

    variant = _aggregate_variant(record)
    names = list(_descendants(variant, "Name")) if variant is not None else []
    name = (
        _text(names[0])
        if names
        else (_attribute(variant, "VariationName") if variant is not None else None)
        or _attribute(record, "VariationName")
    )
    genes = _unique(
        _attribute(item, "Symbol")
        or _text(next(_descendants(item, "ElementValue"), None))
        for item in (_descendants(variant, "Gene") if variant is not None else ())
    )
    hgvs = _unique(
        _text(item)
        for item in (variant.iter() if variant is not None else ())
        if _local_name(item.tag) in {"Expression", "HGVS"}
        and (_text(item) or "").startswith(
            ("c.", "g.", "m.", "n.", "p.", "NC_", "NM_", "NP_")
        )
    )
    classifications = _aggregate_classifications(record)
    conditions = _condition_names(classifications)
    replaced_by = _unique(
        _attribute(item, "Accession") or _text(item)
        for item in _children(record, "ReplacedBy")
    )
    replacements = _unique(
        _attribute(item, "Accession") or _text(item)
        for replacement_list in _children(record, "ReplacedList")
        for item in replacement_list
        if _local_name(item.tag) == "Replaced"
    )
    status = _text(next(_children(record, "RecordStatus"), None))
    deleted = bool(
        _attribute(record, "DateDeleted") or (status and "delet" in status.casefold())
    )
    germline = _classification(classifications, "GermlineClassification")
    variation_id = _attribute(record, "VariationID")
    date_created = _attribute(record, "DateCreated")
    date_last_updated = _attribute(record, "DateLastUpdated", "DateLastEvaluated")
    warnings = list(
        _unique(
            _text(item)
            for name in ("Warning", "Error")
            for item in _children(record, name)
        )
    )
    if deleted:
        warnings.append("Record is marked deleted.")
    if replaced_by:
        warnings.append("Record has replacement metadata.")
    if variation_id is None:
        warnings.append("Variation ID is missing.")
    if not genes:
        warnings.append("Genes are missing.")
    if germline.classification is None:
        warnings.append("Germline classification is missing.")
    if date_created is None:
        warnings.append("Record creation date is missing.")
    if date_last_updated is None:
        warnings.append("Record last-updated date is missing.")
    return VCVRecord(
        accession=validated.accession,
        version=validated.version,
        accession_version=validated.identifier,
        variation_id=variation_id,
        record_type=_attribute(record, "RecordType"),
        genes=genes,
        name=name,
        hgvs=hgvs,
        date_created=date_created,
        date_last_updated=date_last_updated,
        date_deleted=_attribute(record, "DateDeleted"),
        germline=germline,
        somatic_clinical_impact=_classification(
            classifications, "SomaticClinicalImpact"
        ),
        oncogenicity=_classification(classifications, "OncogenicityClassification"),
        conditions=conditions,
        record_status=status,
        replaced_by=replaced_by,
        replacements=replacements,
        deleted=deleted,
        warnings=_unique(warnings),
    )


def _cancelled(cancel: Callable[[], bool] | _CancellationEvent | None) -> bool:
    if cancel is None:
        return False
    if callable(cancel):
        return bool(cancel())
    return bool(cancel.is_set())


def _read_response(response: requests.Response, limit: int) -> bytes:
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > limit:
        raise TransferLimitError(f"Response exceeds the {limit:,}-byte hard cap.")
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        size += len(chunk)
        if size > limit:
            raise TransferLimitError(f"Response exceeds the {limit:,}-byte hard cap.")
        chunks.append(chunk)
    return b"".join(chunks)


def _source_request(identifier: str) -> str:
    query = (
        f"db=clinvar&id={identifier}&rettype=vcv&retmode=xml&tool=variant_time_machine"
    )
    return f"{CLINVAR_EFETCH_URL}?{query}"


def _request_one(
    client: requests.Session,
    identifier: str,
    *,
    timeout: tuple[float, float] | float,
    remaining_bytes: int,
    progress: ProgressCallback | None,
) -> VersionResult:
    retrieved = datetime.now(UTC).isoformat()
    source = _source_request(identifier)
    _emit(progress, "requesting", identifier=identifier, source_request=source)
    response: requests.Response | None = None
    try:
        response = client.get(
            CLINVAR_EFETCH_URL,
            params={
                "db": "clinvar",
                "id": identifier,
                "rettype": "vcv",
                "retmode": "xml",
                "tool": "variant_time_machine",
            },
            timeout=timeout,
            stream=True,
        )
        response.raise_for_status()
        raw = _read_response(response, min(MAX_RESPONSE_BYTES, remaining_bytes))
        encoding = response.encoding or "utf-8"
    except TransferLimitError as exc:
        _emit(progress, "failed", identifier=identifier, message=str(exc))
        raise
    except requests.RequestException as exc:
        _emit(progress, "failed", identifier=identifier, message=str(exc))
        return VersionResult(
            identifier, source, retrieved, 0, "request failure", None, None, str(exc)
        )
    finally:
        if response is not None:
            response.close()
    _emit(progress, "received", identifier=identifier, response_bytes=len(raw))
    raw_text = raw.decode(encoding, errors="replace")
    try:
        record = parse_efetch_xml(raw)
    except VCVHistoryError as exc:
        missing_markers = ("no items found", "no record found", "cannot process id")
        status: OutcomeStatus = (
            "missing"
            if any(marker in raw_text.casefold() for marker in missing_markers)
            else "parsing failure"
        )
        event = "missing" if status == "missing" else "failed"
        _emit(
            progress,
            event,
            identifier=identifier,
            response_bytes=len(raw),
            message=str(exc),
        )
        return VersionResult(
            identifier, source, retrieved, len(raw), status, None, raw_text, str(exc)
        )
    if record.accession_version != identifier and "." in identifier:
        message = (
            f"NCBI returned {record.accession_version}, not explicitly requested "
            f"{identifier}."
        )
        _emit(
            progress,
            "missing",
            identifier=identifier,
            response_bytes=len(raw),
            message=message,
        )
        return VersionResult(
            identifier,
            source,
            retrieved,
            len(raw),
            "missing",
            None,
            raw_text,
            message,
        )
    status = "deleted/replaced" if record.deleted or record.replaced_by else "available"
    _emit(
        progress,
        "parsed",
        identifier=identifier,
        returned_identifier=record.accession_version,
        response_bytes=len(raw),
        status=status,
    )
    return VersionResult(
        identifier, source, retrieved, len(raw), status, record, raw_text
    )


def fetch_current_vcv(
    identifier: str,
    *,
    timeout: tuple[float, float] | float = REQUEST_TIMEOUT,
    session: requests.Session | None = None,
    progress: ProgressCallback | None = None,
) -> VersionResult:
    """Fetch one unversioned official VCV record with the per-response hard cap."""
    requested = validate_vcv_accession(identifier)
    own_session = session is None
    client = session or create_retrying_session()
    try:
        return _request_one(
            client,
            requested.accession,
            timeout=timeout,
            remaining_bytes=MAX_RESPONSE_BYTES,
            progress=progress,
        )
    finally:
        if own_session:
            client.close()


def _normalized_classification(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.casefold().split())


def _classification_kind(value: str) -> str:
    normalized = _normalized_classification(value) or ""
    if "conflict" in normalized:
        return "conflicting"
    if normalized in {
        "vus",
        "uncertain significance",
        "variant of uncertain significance",
    }:
        return "vus"
    if normalized == "likely pathogenic":
        return "likely pathogenic"
    if normalized == "pathogenic":
        return "pathogenic"
    if normalized == "likely benign":
        return "likely benign"
    if normalized == "benign":
        return "benign"
    return "other"


def _detected_change(earlier: VCVRecord, later: VCVRecord) -> ClassificationChange:
    earlier_value = earlier.germline.classification
    later_value = later.germline.classification
    if earlier_value is None or later_value is None:
        return "Missing_Classification"
    earlier_normalized = _normalized_classification(earlier_value)
    later_normalized = _normalized_classification(later_value)
    if earlier_normalized == later_normalized:
        non_germline_changed = (
            earlier.somatic_clinical_impact != later.somatic_clinical_impact
            or earlier.oncogenicity != later.oncogenicity
        )
        return (
            "Non_Germline_Change"
            if non_germline_changed
            else "No_Classification_Change"
        )
    earlier_kind = _classification_kind(earlier_value)
    later_kind = _classification_kind(later_value)
    if later_kind == "conflicting" and earlier_kind != "conflicting":
        return "Became_Conflicting"
    if earlier_kind == "conflicting" and later_kind != "conflicting":
        return "Conflict_Resolved"
    transitions: dict[tuple[str, str], ClassificationChange] = {
        ("vus", "pathogenic"): "VUS_to_Pathogenic",
        ("vus", "likely pathogenic"): "VUS_to_Likely_Pathogenic",
        ("vus", "benign"): "VUS_to_Benign",
        ("vus", "likely benign"): "VUS_to_Likely_Benign",
        ("pathogenic", "vus"): "Pathogenic_to_VUS",
        ("benign", "vus"): "Benign_to_VUS",
    }
    return transitions.get((earlier_kind, later_kind), "Other_Germline_Change")


def compare_consecutive(
    results: Iterable[VersionResult],
) -> tuple[VersionComparison, ...]:
    """Compare consecutive available records, skipping unavailable version holes."""
    available = sorted(
        (
            item
            for item in results
            if item.status == "available" and item.record is not None
        ),
        key=lambda item: item.record.version if item.record else 0,
    )
    comparisons: list[VersionComparison] = []
    for earlier_result, later_result in zip(available, available[1:], strict=False):
        earlier = earlier_result.record
        later = later_result.record
        assert earlier is not None and later is not None
        warnings = list(_unique((*earlier.warnings, *later.warnings)))
        if later.version != earlier.version + 1:
            warnings.append(
                f"Available versions are nonconsecutive ({earlier.version} to "
                f"{later.version}); intervening versions were not compared."
            )
        earlier_count = earlier.germline.submission_count
        later_count = later.germline.submission_count
        submissions_changed = (
            None
            if earlier_count is None or later_count is None
            else earlier_count != later_count
        )
        change = _detected_change(earlier, later)
        confidence: ComparisonConfidence = "limited" if warnings else "high"
        comparisons.append(
            VersionComparison(
                earlier_version=earlier.version,
                later_version=later.version,
                earlier_identifier=earlier.accession_version,
                later_identifier=later.accession_version,
                earlier_germline_classification=earlier.germline.classification,
                later_germline_classification=later.germline.classification,
                earlier_review_status=earlier.germline.review_status,
                later_review_status=later.germline.review_status,
                detected_classification_change=change,
                submissions_changed=submissions_changed,
                warnings=tuple(warnings),
                confidence=confidence,
            )
        )
    return tuple(comparisons)


_GERMLINE_CHANGE_LABELS: frozenset[ClassificationChange] = frozenset(
    {
        "VUS_to_Pathogenic",
        "VUS_to_Likely_Pathogenic",
        "VUS_to_Benign",
        "VUS_to_Likely_Benign",
        "Pathogenic_to_VUS",
        "Benign_to_VUS",
        "Became_Conflicting",
        "Conflict_Resolved",
        "Other_Germline_Change",
    }
)


def _history_summary(
    current_result: VersionResult,
    results: tuple[VersionResult, ...],
    comparisons: tuple[VersionComparison, ...],
    *,
    cancelled: bool,
) -> VCVHistorySummary:
    retrieved = sorted(
        (
            item.record
            for item in results
            if item.status in {"available", "deleted/replaced"}
            and item.record is not None
        ),
        key=lambda record: record.version,
    )
    germline_changes = tuple(
        item
        for item in comparisons
        if item.detected_classification_change in _GERMLINE_CHANGE_LABELS
    )
    warnings: list[str | None] = []
    for item in (current_result, *results):
        if item.record is not None:
            warnings.extend(item.record.warnings)
        if item.status != "available":
            warnings.append(
                item.message or f"{item.requested_identifier} was {item.status}."
            )
    for comparison in comparisons:
        warnings.extend(comparison.warnings)
    if cancelled:
        warnings.append("Retrieval was cancelled before the version plan completed.")
    return VCVHistorySummary(
        first_available_version=retrieved[0].version if retrieved else None,
        newest_available_version=retrieved[-1].version if retrieved else None,
        retrieved_version_count=len(retrieved),
        any_germline_classification_changed=bool(germline_changes),
        first_detected_germline_change=(
            germline_changes[0] if germline_changes else None
        ),
        latest_germline_classification=(
            retrieved[-1].germline.classification if retrieved else None
        ),
        unresolved_warnings=_unique(warnings),
    )


def fetch_vcv_history(
    identifier: str,
    *,
    mode: Literal["all", "custom", "endpoints"] = "all",
    versions: Iterable[int] | None = None,
    max_requests: int = DEFAULT_MAX_REQUESTS,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    timeout: tuple[float, float] | float = REQUEST_TIMEOUT,
    request_interval_seconds: float = DEFAULT_REQUEST_INTERVAL_SECONDS,
    session: requests.Session | None = None,
    sleep: Callable[[float], None] = time.sleep,
    cancel: Callable[[], bool] | _CancellationEvent | None = None,
    progress: ProgressCallback | None = None,
    current_result: VersionResult | None = None,
) -> VCVHistoryResult:
    """Retrieve a small VCV history through official EFetch, sequentially and safely.

    The unversioned accession is fetched separately to establish the latest official
    version. ``max_requests`` limits only subsequent historical version requests.
    """
    try:
        requested = validate_vcv_accession(identifier)
    except InvalidVCVAccession as exc:
        _emit(progress, "failed", identifier=str(identifier), message=str(exc))
        raise
    if max_total_bytes < 1 or max_total_bytes > MAX_TOTAL_BYTES:
        message = f"max_total_bytes must be between 1 and {MAX_TOTAL_BYTES:,}."
        _emit(progress, "failed", identifier=requested.identifier, message=message)
        raise ValueError(message)
    if request_interval_seconds < 0:
        message = "request_interval_seconds cannot be negative."
        _emit(progress, "failed", identifier=requested.identifier, message=message)
        raise ValueError(message)
    if max_requests < 1:
        message = "max_requests must be positive."
        _emit(progress, "failed", identifier=requested.identifier, message=message)
        raise ValueError(message)
    own_session = session is None
    client = session or create_retrying_session()
    results: list[VersionResult] = []
    total = 0
    plan: tuple[int, ...] = ()
    current_identifier: str | None = None
    cancelled = False
    try:
        if _cancelled(cancel):
            _emit(
                progress,
                "cancelled",
                identifier=requested.accession,
                completed_requests=0,
            )
            raise RetrievalCancelled("VCV history retrieval was cancelled.")
        current = current_result or _request_one(
            client,
            requested.accession,
            timeout=timeout,
            remaining_bytes=max_total_bytes,
            progress=progress,
        )
        if (
            current.record is not None
            and current.record.accession != requested.accession
        ):
            raise ValueError("Current result belongs to a different VCV accession.")
        total += current.response_bytes
        if current.status != "available" or current.record is None:
            comparisons: tuple[VersionComparison, ...] = ()
            return VCVHistoryResult(
                requested.identifier,
                None,
                (),
                current,
                (),
                comparisons,
                _history_summary(current, (), comparisons, cancelled=False),
                total,
            )
        current_identifier = current.record.accession_version
        if requested.version is not None:
            if requested.version > current.record.version:
                message = (
                    f"Requested {requested.identifier}, but the current official "
                    f"version is {current.record.version}."
                )
                _emit(
                    progress,
                    "failed",
                    identifier=requested.identifier,
                    message=message,
                )
                raise ValueError(message)
            plan = (requested.version,)
        else:
            try:
                plan = plan_version_range(
                    current.record.version,
                    mode=mode,
                    versions=versions,
                    max_requests=max_requests,
                )
            except (RequestLimitError, ValueError) as exc:
                _emit(
                    progress,
                    "failed",
                    identifier=requested.accession,
                    message=str(exc),
                )
                raise
        for version in plan:
            if _cancelled(cancel):
                cancelled = True
                _emit(
                    progress,
                    "cancelled",
                    identifier=f"{requested.accession}.{version}",
                    completed_requests=len(results),
                )
                break
            sleep(request_interval_seconds)
            item = _request_one(
                client,
                f"{requested.accession}.{version}",
                timeout=timeout,
                remaining_bytes=max_total_bytes - total,
                progress=progress,
            )
            total += item.response_bytes
            results.append(item)
    finally:
        if own_session:
            client.close()
    result_items = tuple(results)
    comparisons = compare_consecutive(result_items)
    return VCVHistoryResult(
        requested.identifier,
        current_identifier,
        plan,
        current,
        result_items,
        comparisons,
        _history_summary(current, result_items, comparisons, cancelled=cancelled),
        total,
        cancelled,
    )
