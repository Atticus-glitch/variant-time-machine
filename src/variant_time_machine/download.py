"""Future ClinVar data acquisition functions."""


def download_clinvar_release() -> None:
    """Download a documented ClinVar release after archive research is complete."""
    raise NotImplementedError(
        "ClinVar downloading is intentionally not implemented during setup. "
        "Select release dates, archive formats, checksums, and provenance rules first."
    )
