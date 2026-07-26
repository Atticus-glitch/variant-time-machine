"""Future leakage-safe feature engineering functions."""


def build_historical_features() -> None:
    """Build features that were available by a defined historical cutoff."""
    raise NotImplementedError(
        "Feature construction requires a verified timeline dataset and explicit "
        "availability dates to prevent future-information leakage."
    )
