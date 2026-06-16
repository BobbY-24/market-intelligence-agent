from src.models import Asset
from src.normalization.validation import validate_watchlist


def test_validate_watchlist_flags_duplicate_symbols() -> None:
    assets = [
        Asset("NVDA", "NVIDIA", "equity", ["ai"]),
        Asset("NVDA", "NVIDIA duplicate", "equity", ["ai"]),
    ]

    errors = validate_watchlist(assets)

    assert "NVDA: duplicate symbol" in errors


def test_tciex_identity_verification_is_non_blocking_warning() -> None:
    assets = [
        Asset(
            "TCIEX",
            "TCIEX - identity to verify",
            "mutual_fund",
            ["to_verify"],
            requires_identity_verification=True,
        )
    ]

    errors = validate_watchlist(assets)

    assert errors == ["TCIEX: identity, asset class, and benchmark require verification"]

