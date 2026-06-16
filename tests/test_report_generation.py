from datetime import datetime
from pathlib import Path

from src.config import load_config
from src.models import Asset, MarketSnapshot, ReportBundle, TreasurySnapshot
from src.main import write_reports
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
    )

    markdown = render_markdown(bundle, [Asset("NVDA", "NVIDIA", "equity", ["ai"])])

    assert "# Daily Market Intelligence Report" in markdown
    assert "## 10. Bottom line" in markdown
    assert "NVDA" in markdown


def test_desktop_markdown_dir_supports_tilde_expansion(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "watchlist.yaml").write_text("assets: []\ntreasury: {}\n", encoding="utf-8")
    (config_dir / "sources.yaml").write_text("{}", encoding="utf-8")
    (config_dir / "report_settings.yaml").write_text(
        "desktop_markdown_dir: ~/Desktop\n",
        encoding="utf-8",
    )

    config = load_config(tmp_path)

    assert config.desktop_markdown_dir == Path("~/Desktop").expanduser()


def test_write_reports_publishes_markdown_to_secondary_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "watchlist.yaml").write_text("assets: []\ntreasury: {}\n", encoding="utf-8")
    (config_dir / "sources.yaml").write_text("{}", encoding="utf-8")
    (config_dir / "report_settings.yaml").write_text(
        "reports_dir: reports\ndatabase_path: data/test.sqlite3\ndesktop_markdown_dir: desktop\n",
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
    )

    markdown_path, json_path = write_reports(config, bundle)
    desktop_markdown_path = tmp_path / "desktop" / markdown_path.name

    assert markdown_path.exists()
    assert json_path.exists()
    assert desktop_markdown_path.exists()
    assert desktop_markdown_path.read_text(encoding="utf-8") == markdown_path.read_text(
        encoding="utf-8"
    )
