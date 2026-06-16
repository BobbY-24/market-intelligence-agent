from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from src.collectors.http import CachedHttpClient
from src.collectors.market_data import StooqMarketDataProvider
from src.collectors.treasury import USTreasuryProvider
from src.config import AppConfig, load_config
from src.logging_config import configure_logging
from src.models import ReportBundle
from src.normalization.validation import validate_watchlist
from src.reporting.json_report import render_json
from src.reporting.markdown import render_markdown, report_filename
from src.storage.sqlite_store import SQLiteStore


def build_http(config: AppConfig) -> CachedHttpClient:
    http_config = config.sources.get("http", {})
    return CachedHttpClient(
        cache_dir=config.root / "data" / "cache",
        timeout_seconds=int(http_config.get("timeout_seconds", 20)),
        max_retries=int(http_config.get("max_retries", 3)),
        backoff_seconds=float(http_config.get("backoff_seconds", 0.75)),
        cache_ttl_seconds=int(http_config.get("cache_ttl_seconds", 900)),
    )


def collect(config: AppConfig) -> ReportBundle:
    now = datetime.now(config.timezone)
    store = SQLiteStore(config.database_path)
    store.initialize()
    http = build_http(config)
    market_provider = StooqMarketDataProvider(http)
    snapshots = []
    warnings = validate_watchlist(config.watchlist)
    for asset in config.watchlist:
        snapshot = market_provider.get_snapshot(asset, now)
        snapshots.append(snapshot)
        store.save_market_snapshot(snapshot)

    treasury_snapshot = None
    if config.treasury_enabled:
        treasury_provider = USTreasuryProvider(http, config.treasury_tenors)
        try:
            treasury_snapshot = treasury_provider.get_treasury_curve(now)
            store.save_treasury_snapshot(treasury_snapshot)
        except Exception as exc:
            warnings.append(f"Treasury collection failed: {exc}")

    return ReportBundle(now, snapshots, treasury_snapshot, warnings)


def write_reports(config: AppConfig, bundle: ReportBundle) -> tuple[Path, Path]:
    config.reports_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = config.reports_dir / report_filename(bundle.generated_at, "md")
    json_path = config.reports_dir / report_filename(bundle.generated_at, "json")
    markdown = render_markdown(bundle, config.watchlist)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(render_json(bundle), encoding="utf-8")

    if config.desktop_markdown_dir:
        config.desktop_markdown_dir.mkdir(parents=True, exist_ok=True)
        desktop_markdown_path = config.desktop_markdown_dir / markdown_path.name
        desktop_markdown_path.write_text(markdown, encoding="utf-8")

    SQLiteStore(config.database_path).save_report_run(
        bundle.generated_at.isoformat(),
        str(markdown_path),
        str(json_path),
        bundle.warnings,
    )
    return markdown_path, json_path


def run_daily(config: AppConfig) -> tuple[Path, Path]:
    bundle = collect(config)
    return write_reports(config, bundle)


def cmd_validate(config: AppConfig) -> int:
    warnings = validate_watchlist(config.watchlist)
    blocking = [warning for warning in warnings if "requires" not in warning]
    if warnings:
        print("\n".join(warnings))
    else:
        print("Watchlist validation passed.")
    return 1 if blocking else 0


def cmd_collect(config: AppConfig) -> int:
    bundle = collect(config)
    print(f"Collected {len(bundle.market_snapshots)} market snapshots.")
    if bundle.treasury_snapshot:
        print("Collected Treasury snapshot.")
    for warning in bundle.warnings:
        print(f"WARNING: {warning}")
    return 0


def cmd_report(config: AppConfig) -> int:
    bundle = collect(config)
    markdown_path, json_path = write_reports(config, bundle)
    print(f"Wrote {markdown_path}")
    print(f"Wrote {json_path}")
    return 0


def cmd_analyze(config: AppConfig) -> int:
    bundle = collect(config)
    print(render_markdown(bundle, config.watchlist))
    return 0


def cmd_backfill(config: AppConfig, days: int) -> int:
    # Stage 1 keeps backfill intentionally simple: run today's pipeline and record intent.
    _ = datetime.now(config.timezone) - timedelta(days=days)
    markdown_path, json_path = run_daily(config)
    print(f"Backfill placeholder completed for {days} days using current provider snapshots.")
    print(f"Wrote {markdown_path}")
    print(f"Wrote {json_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily market intelligence agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ["collect", "analyze", "report", "run-daily", "validate-watchlist"]:
        subparsers.add_parser(command)
    backfill = subparsers.add_parser("backfill")
    backfill.add_argument("--days", type=int, default=30)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    args = build_parser().parse_args(argv)
    config = load_config(Path.cwd())
    match args.command:
        case "validate-watchlist":
            return cmd_validate(config)
        case "collect":
            return cmd_collect(config)
        case "analyze":
            return cmd_analyze(config)
        case "report":
            return cmd_report(config)
        case "run-daily":
            paths = run_daily(config)
            print(f"Wrote {paths[0]}")
            print(f"Wrote {paths[1]}")
            return 0
        case "backfill":
            return cmd_backfill(config, args.days)
    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
