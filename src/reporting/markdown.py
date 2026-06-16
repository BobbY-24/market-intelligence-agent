from __future__ import annotations

from datetime import datetime

from src.analysis.market_analysis import main_development, treasury_theme
from src.models import Asset, ReportBundle


def render_markdown(bundle: ReportBundle, assets: list[Asset]) -> str:
    asset_by_symbol = {asset.symbol: asset for asset in assets}
    lines = [
        "# Daily Market Intelligence Report",
        "",
        f"Generated: {bundle.generated_at.isoformat()}",
        "",
        "## 1. Executive summary",
        "",
        _executive_summary(bundle),
        "",
        "## 2. Top developments",
        "",
        _top_developments(bundle),
        "",
        "## 3. Watchlist dashboard",
        "",
        (
            "| Asset | Latest value | Daily change | Five-day change | YTD change | "
            "Main development | Importance |"
        ),
        (
            "| ----- | -----------: | -----------: | --------------: | ---------: | "
            "---------------- | ---------: |"
        ),
    ]
    for snapshot in bundle.market_snapshots:
        asset = asset_by_symbol.get(snapshot.symbol)
        label = f"{snapshot.symbol} ({asset.asset_type if asset else 'asset'})"
        development, importance = main_development(snapshot)
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    _num(snapshot.latest_value, prefix="$"),
                    _pct(snapshot.daily_change_pct),
                    _pct(snapshot.five_day_change_pct),
                    _pct(snapshot.ytd_change_pct),
                    f"{development} [{snapshot.data_quality}]",
                    str(importance),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## 4. Company-by-company analysis",
            "",
            (
                "Stage 1 includes company sections only when price or volume anomalies "
                "are visible from market data."
            ),
        ]
    )
    for snapshot in bundle.market_snapshots:
        asset = asset_by_symbol.get(snapshot.symbol)
        if asset and asset.asset_type == "equity":
            development, importance = main_development(snapshot)
            if importance >= 60:
                lines.extend(
                    [
                        "",
                        f"### {snapshot.symbol} - {asset.name}",
                        "",
                        f"- Most important new event: {development}.",
                        "- Fundamental significance: requires Stage 2 news and filing collection.",
                        (
                            "- Short-term market significance: price/volume anomaly flagged "
                            "from available data."
                        ),
                        (
                            "- Risks: market data can be delayed and does not explain "
                            "causality by itself."
                        ),
                        "- Counterarguments: moves may reflect broad market or sector factors.",
                        (
                            "- What to watch next: confirm with primary sources, filings, "
                            "and authoritative news."
                        ),
                    ]
                )

    lines.extend(
        [
            "",
            "## 5. ETF and mutual-fund analysis",
            "",
            (
                "VOO and SWPPX provide overlapping S&P 500 exposure. AGG and VBTLX "
                "provide overlapping broad U.S. bond-market exposure. Mutual fund values "
                "are labeled as NAV/prior-day when configured as NAV-only."
            ),
            "",
            "## 6. Treasury and bond-market analysis",
            "",
            _treasury_section(bundle),
            "",
            "## 7. Cross-asset signals",
            "",
            (
                "Higher long-term Treasury yields can pressure long-duration growth equities, "
                "including AI and technology names. Lower yields can support valuation "
                "multiples while affecting bond funds through duration exposure. Gold "
                "exposure through IAU can react to real yields, inflation expectations, "
                "the U.S. dollar, and geopolitical risk. BX and SPCX can be sensitive to "
                "credit conditions, capital-market activity, IPO windows, and speculative "
                "risk appetite."
            ),
            "",
            "## 8. Upcoming catalysts",
            "",
            (
                "Stage 1 does not yet collect forward calendars. Stage 3 will add earnings, "
                "macro releases, Treasury auctions, Fed meetings, and fund distributions."
            ),
            "",
            "## 9. Risks and anomalies",
            "",
            _warnings(bundle),
            "",
            "## 10. Bottom line",
            "",
            _bottom_line(bundle),
        ]
    )
    return "\n".join(lines) + "\n"


def _executive_summary(bundle: ReportBundle) -> str:
    missing = sum(1 for snapshot in bundle.market_snapshots if snapshot.latest_value is None)
    market_sentence = (
        f"Market data was collected for {len(bundle.market_snapshots)} watchlist "
        f"assets, with {missing} missing snapshots. "
    )
    return (
        f"{treasury_theme(bundle.treasury_snapshot)} "
        f"{market_sentence}"
        "Stage 1 emphasizes anomaly detection and reliable labeling of unavailable data. "
        "Source-linked company and macro news analysis will be added in Stage 2."
    )


def _top_developments(bundle: ReportBundle) -> str:
    ranked = sorted(
        ((snapshot, *main_development(snapshot)) for snapshot in bundle.market_snapshots),
        key=lambda item: item[2],
        reverse=True,
    )[:5]
    lines = []
    for snapshot, development, importance in ranked:
        reaction = (
            f"Market reaction: daily {_pct(snapshot.daily_change_pct)}, "
            f"five-day {_pct(snapshot.five_day_change_pct)}. "
        )
        lines.append(
            f"- **{snapshot.symbol}**: {development}. Importance {importance}. "
            f"{reaction}"
            f"Source: {snapshot.source}."
        )
    if bundle.treasury_snapshot:
        lines.append(
            f"- **Treasuries**: {treasury_theme(bundle.treasury_snapshot)} "
            f"Source: {bundle.treasury_snapshot.source}."
        )
    return "\n".join(lines) if lines else "No developments available from Stage 1 data."


def _treasury_section(bundle: ReportBundle) -> str:
    snapshot = bundle.treasury_snapshot
    if snapshot is None:
        return "Treasury data unavailable."
    lines = ["| Tenor | Yield | Daily bp change |", "| ----- | ----: | --------------: |"]
    for tenor in ["2Y", "5Y", "10Y", "30Y"]:
        lines.append(
            f"| {tenor} | {_pct_points(snapshot.yields.get(tenor))} | "
            f"{_bp(snapshot.daily_changes_bp.get(tenor))} |"
        )
    lines.extend(
        [
            "",
            (
                f"2s10s spread: {_bp(snapshot.spreads_bp.get('2s10s'))}. "
                f"10s30s spread: {_bp(snapshot.spreads_bp.get('10s30s'))}."
            ),
            (
                "Implications: higher yields can weigh on long-duration growth stocks "
                "and bond-fund prices; lower yields can do the reverse, depending on "
                "credit spreads and duration."
            ),
        ]
    )
    return "\n".join(lines)


def _warnings(bundle: ReportBundle) -> str:
    warnings = list(bundle.warnings)
    warnings.extend(
        f"{snapshot.symbol}: {snapshot.data_quality}"
        for snapshot in bundle.market_snapshots
        if snapshot.latest_value is None or "missing" in snapshot.data_quality
    )
    if warnings:
        return "\n".join(f"- {warning}" for warning in warnings)
    return "- No Stage 1 anomalies beyond source delay limitations."


def _bottom_line(bundle: ReportBundle) -> str:
    ranked = sorted(
        ((snapshot.symbol, *main_development(snapshot)) for snapshot in bundle.market_snapshots),
        key=lambda item: item[2],
        reverse=True,
    )[:3]
    if not ranked:
        return "No asset-level bottom line is available."
    return "\n".join(
        (
            f"- {symbol}: {development}. Next catalyst: verify with news, filings, "
            "and scheduled events in later stages."
        )
        for symbol, development, _importance in ranked
    )


def report_filename(generated_at: datetime, suffix: str) -> str:
    return f"market-intelligence-{generated_at.strftime('%Y-%m-%d')}.{suffix}"


def _pct(value: float | None) -> str:
    return "missing" if value is None else f"{value:.2f}%"


def _pct_points(value: float | None) -> str:
    return "missing" if value is None else f"{value:.2f}%"


def _bp(value: float | None) -> str:
    return "missing" if value is None else f"{value:.1f} bp"


def _num(value: float | None, prefix: str = "") -> str:
    return "missing" if value is None else f"{prefix}{value:,.2f}"
