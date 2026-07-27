#!/usr/bin/env python3
"""Add one manually selected variant to the low-bandwidth ClinVar pilot."""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from variant_time_machine.clinvar_api import (  # noqa: E402
    CLINVAR_ESUMMARY_URL,
    ClinVarAPIError,
    lookup_clinvar_variant,
    normalize_variant_identifier,
)
from variant_time_machine.config import (  # noqa: E402
    PILOT_CURRENT_API_ESTIMATE_BYTES,
    PILOT_HISTORICAL_API_LIMIT_BYTES,
    PILOT_VARIANTS_PATH,
)
from variant_time_machine.download import transfer_plan_message  # noqa: E402
from variant_time_machine.pilot import read_pilot_rows, write_pilot_rows  # noqa: E402
from variant_time_machine.remote_archive import parse_variation_archive  # noqa: E402

EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
USER_AGENT = "VariantTimeMachine/0.1 research-education"


def _historical_url(accession: str) -> str:
    query = urlencode({"db": "clinvar", "rettype": "vcv", "id": accession})
    return f"{EFETCH_URL}?{query}"


def lookup_historical_vcv(accession: str) -> tuple[str | None, str]:
    """Retrieve one explicit VCV version with a strict 10 MB response limit."""
    if not re.fullmatch(r"VCV\d{9}\.\d+", accession, flags=re.IGNORECASE):
        raise ValueError(
            "Historical VCV must include an explicit version, such as VCV000014206.1."
        )
    url = _historical_url(accession.upper())
    response = None
    try:
        response = requests.get(
            EFETCH_URL,
            params={"db": "clinvar", "rettype": "vcv", "id": accession.upper()},
            headers={"User-Agent": USER_AGENT},
            stream=True,
            timeout=(15, 60),
        )
        response.raise_for_status()
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > PILOT_HISTORICAL_API_LIMIT_BYTES:
                raise RuntimeError("Historical API response exceeded the 10 MB limit.")
            chunks.append(chunk)
    except requests.RequestException as exc:
        raise RuntimeError(f"Historical VCV request failed: {exc}") from exc
    finally:
        if response is not None:
            response.close()

    try:
        root = ET.fromstring(b"".join(chunks))
    except ET.ParseError as exc:
        raise RuntimeError("Historical VCV response was not valid XML.") from exc
    archive = (
        root if root.tag == "VariationArchive" else root.find(".//VariationArchive")
    )
    if archive is None:
        raise RuntimeError(
            "Historical VCV response contained no VariationArchive record."
        )
    expected = accession.upper().split(".")
    if archive.get("Accession") != expected[0] or archive.get("Version") != expected[1]:
        raise RuntimeError("NCBI did not return the requested VCV accession version.")
    return parse_variation_archive(archive).germline_classification, url


def _print_slots(path: Path) -> None:
    rows = read_pilot_rows(path)
    populated = sum(bool(row["variant_id"].strip()) for row in rows)
    print(f"Pilot slots: {populated} populated, {len(rows) - populated} empty")
    print(f"File: {path}")


def main(argv: list[str] | None = None) -> int:
    """Plan or perform one explicitly confirmed low-bandwidth pilot lookup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("variant_id", nargs="?")
    parser.add_argument("--reason", help="Why this variant was manually selected")
    parser.add_argument(
        "--historical-vcv",
        help="Optional explicit historical VCV version, such as VCV000014206.1",
    )
    parser.add_argument(
        "--confirm-api-requests",
        action="store_true",
        help="Confirm the displayed one-record API requests",
    )
    parser.add_argument("--pilot-csv", type=Path, default=PILOT_VARIANTS_PATH)
    args = parser.parse_args(argv)

    if args.variant_id is None:
        _print_slots(args.pilot_csv)
        return 0
    if not args.reason or not args.reason.strip():
        parser.error("--reason is required when selecting a variant")

    try:
        variation_id = normalize_variant_identifier(args.variant_id)
        historical_accession = (
            args.historical_vcv.upper() if args.historical_vcv else None
        )
        if historical_accession and not re.fullmatch(
            r"VCV\d{9}\.\d+", historical_accession
        ):
            raise ValueError("--historical-vcv must include an explicit VCV version.")
        if historical_accession and (
            normalize_variant_identifier(historical_accession) != variation_id
        ):
            raise ValueError("Historical VCV must identify the selected Variation ID.")
        rows = read_pilot_rows(args.pilot_csv)
    except (OSError, ValueError, ClinVarAPIError) as exc:
        print(f"Pilot input error: {exc}", file=sys.stderr)
        return 1

    current_source = f"{CLINVAR_ESUMMARY_URL}?db=clinvar&id={variation_id}&retmode=json"
    print(
        transfer_plan_message(
            current_source,
            PILOT_CURRENT_API_ESTIMATE_BYTES,
            "Retrieve the current summary for one manually selected pilot variant",
        )
    )
    if historical_accession:
        print()
        print(
            transfer_plan_message(
                _historical_url(historical_accession),
                PILOT_HISTORICAL_API_LIMIT_BYTES,
                "Retrieve one explicitly versioned VCV record for historical review",
            )
        )
    if not args.confirm_api_requests:
        print("No request started. Review the plan and add --confirm-api-requests.")
        return 0

    try:
        current = lookup_clinvar_variant(variation_id)
        historical_classification = ""
        sources = [current_source, current.source_url]
        verification = "Current API retrieved; historical pending"
        if historical_accession:
            historical_classification, historical_source = lookup_historical_vcv(
                historical_accession
            )
            historical_classification = historical_classification or ""
            sources.append(historical_source)
            verification = "Historical VCV retrieved; manual verification required"

        row_index = next(
            (
                index
                for index, row in enumerate(rows)
                if row["variant_id"].strip() == variation_id
            ),
            None,
        )
        if row_index is None:
            row_index = next(
                index for index, row in enumerate(rows) if not row["variant_id"].strip()
            )
        rows[row_index] = {
            "variant_id": variation_id,
            "VCV_accession": current.variant_identifier,
            "gene": current.gene_name or "",
            "reason_selected": args.reason.strip(),
            "current_classification": current.classification or "",
            "historical_classification": historical_classification,
            "source": " | ".join(sources),
            "verification_status": verification,
            "notes": (
                f"Retrieved {datetime.now(UTC).date().isoformat()}. "
                "A versioned VCV record is not an arbitrary monthly snapshot."
                if historical_accession
                else f"Current record retrieved {datetime.now(UTC).date().isoformat()}."
            ),
        }
        write_pilot_rows(args.pilot_csv, rows)
    except StopIteration:
        print(
            "Pilot has no empty slot. Keep the pilot between 5 and 10 rows.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError, RuntimeError, ClinVarAPIError) as exc:
        print(f"Pilot lookup failed: {exc}", file=sys.stderr)
        return 1

    print(f"Saved Variation ID {variation_id} to pilot slot {row_index + 1}.")
    print("Historical information remains unverified until a person checks its scope.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
