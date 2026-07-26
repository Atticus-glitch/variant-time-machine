"""Future leakage-safe feature engineering interfaces.

Possible later features include historical review status, submitter count,
classification age, population frequency, molecular consequence, conservation,
protein-region annotations, and gene constraint. None will be implemented until the
historical timeline has been validated and each feature has an availability date.
"""


def build_historical_features() -> None:
    """Provide the future interface for historical feature construction."""
    raise NotImplementedError(
        "Feature construction requires a verified timeline dataset and explicit "
        "availability dates to prevent future-information leakage."
    )
