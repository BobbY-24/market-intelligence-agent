# Market Intelligence Agent

This project generates a weekday morning market-intelligence report for a configurable watchlist. Stage 1 supports watchlist validation, basic market-data collection, Treasury yield collection, SQLite persistence, Markdown reports, JSON output, and tests.

## Installation

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Configuration

- Edit `config/watchlist.yaml` to add or remove assets.
- Edit `config/report_settings.yaml` to change report time, timezone, score thresholds, or output paths.
- Edit `config/sources.yaml` to adjust provider cache and timeout settings.
- Copy `.env.example` to `.env` only when optional email or webhook delivery is needed.

`TCIEX` is included as configurable and marked `requires_identity_verification: true`. Stage 1 validates the shape of the ticker and flags the identity-verification requirement; it does not assert fund identity until a reliable fund source is added.

## Data Sources

Stage 1 uses free public endpoints where available:

- Stooq CSV quotes and historical prices for listed equities and ETFs.
- U.S. Treasury daily yield curve CSV data for Treasury yields.

Limitations: quote data may be delayed, mutual fund NAVs may be prior-day only, and some symbols may be unavailable from the initial free provider. Missing fields are preserved and labeled in reports instead of failing the whole run.

## CLI Usage

```bash
python -m src.main validate-watchlist
python -m src.main collect
python -m src.main analyze
python -m src.main report
python -m src.main run-daily
python -m src.main backfill --days 30
```

## Scheduled Automation

GitHub Actions cannot express one timezone-aware cron that automatically follows daylight saving time. The included workflow runs at both possible UTC times for 7:30 a.m. Eastern:

- `11:30 UTC`, used during Eastern Daylight Time
- `12:30 UTC`, used during Eastern Standard Time

The workflow then checks the current America/New_York local time and only runs the report when the local hour/minute equals `07:30`.

## Testing

```bash
pytest
ruff check .
```

## Known Limitations

- Stage 1 does not yet collect SEC filings, news, catalysts, or source-linked factual claims.
- Stage 1 reports use deterministic templates rather than a language model.
- Historical duplicate suppression and event scoring are scaffolded for Stage 2 but not yet populated by real news events.
- Free market-data coverage varies by symbol and may not include all mutual funds.

## Adding Assets or Providers

Add assets to `config/watchlist.yaml`. Each entry should include `symbol`, `name`, `asset_type`, `themes`, and `priority`. Add new provider implementations under `src/collectors/` by implementing the provider protocols in `src/collectors/interfaces.py`.

