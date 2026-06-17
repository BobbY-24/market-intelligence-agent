from datetime import datetime
from pathlib import Path

from src.config import load_config
from src.main import write_reports
from src.models import Asset, MarketSnapshot, PricePoint, ReportBundle, TreasurySnapshot
from src.reporting.markdown import render_markdown
from src.storage.sqlite_store import SQLiteStore


def test_markdown_report_contains_required_sections() -> None:
    bundle = ReportBundle(
        generated_at=datetime(2026, 6, 16, 7, 30),
        market_snapshots=[
            MarketSnapshot("NVDA", datetime(2026, 6, 15), 100, daily_change_pct=4.0, source="test")
        ],
        treasury_snapshot=TreasurySnapshot(
            datetime(2026, 6, 15),
            {"2Y": 4.0, "5Y": 4.1, "10Y": 4.2, "30Y": 4.4},
            {"2Y": 1, "5Y": 2, "10Y": 3, "30Y": 4},
            {"2s10s": 20, "10s30s": 20},
            "test",
        ),
        warnings=[],
        price_histories={
            "NVDA": [
                PricePoint(datetime(2026, 1, 2), 90),
                PricePoint(datetime(2026, 6, 15), 100),
            ]
        },
    )

    markdown = render_markdown(
        bundle,
        [Asset("NVDA", "NVIDIA", "equity", ["ai"])],
        {"NVDA": "charts/2026-06-16/nvda-ytd.svg"},
    )

    assert "# Daily Market Intelligence Report" in markdown
    assert "## 11. Bottom line" in markdown
    assert "NVDA" in markdown
    assert "![NVDA YTD chart](charts/2026-06-16/nvda-ytd.svg)" in markdown


def test_reports_dir_defaults_to_workspace_reports(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "watchlist.yaml").write_text("assets: []\ntreasury: {}\n", encoding="utf-8")
    (config_dir / "sources.yaml").write_text("{}", encoding="utf-8")
    (config_dir / "report_settings.yaml").write_text(
        "timezone: America/New_York\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.reports_dir == tmp_path / "reports"


def test_write_reports_creates_repo_local_reports_and_charts(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "watchlist.yaml").write_text(
        "assets:\n"
        "  - symbol: NVDA\n"
        "    name: NVIDIA\n"
        "    asset_type: equity\n"
        "    themes: [ai]\n"
        "treasury: {}\n",
        encoding="utf-8",
    )
    (config_dir / "sources.yaml").write_text("{}", encoding="utf-8")
    (config_dir / "report_settings.yaml").write_text(
        "reports_dir: reports\ndatabase_path: data/test.sqlite3\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)
    SQLiteStore(config.database_path).initialize()
    bundle = ReportBundle(
        generated_at=datetime(2026, 6, 16, 7, 30),
        market_snapshots=[
            MarketSnapshot("NVDA", datetime(2026, 6, 15), 100, daily_change_pct=4.0, source="test")
        ],
        treasury_snapshot=None,
        warnings=[],
        price_histories={
            "NVDA": [
                PricePoint(datetime(2026, 1, 2), 90),
                PricePoint(datetime(2026, 3, 3), 95),
                PricePoint(datetime(2026, 6, 15), 100),
            ]
        },
    )

    markdown_path, json_path = write_reports(config, bundle)
    chart_path = tmp_path / "reports" / "charts" / "2026-06-16" / "nvda-ytd.svg"

    assert markdown_path.exists()
    assert json_path.exists()
    assert chart_path.exists()
    assert "![NVDA YTD chart](charts/2026-06-16/nvda-ytd.svg)" in markdown_path.read_text(
        encoding="utf-8"
    )
