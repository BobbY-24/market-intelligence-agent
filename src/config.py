from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

from src.models import Asset


@dataclass(frozen=True)
class AppConfig:
    root: Path
    watchlist_path: Path
    sources_path: Path
    report_settings_path: Path
    watchlist: list[Asset]
    treasury_enabled: bool
    treasury_tenors: list[str]
    sources: dict[str, Any]
    report_settings: dict[str, Any]

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.report_settings.get("timezone", "America/New_York"))

    @property
    def database_path(self) -> Path:
        default_path = "data/market_intelligence.sqlite3"
        return self.root / self.report_settings.get("database_path", default_path)

    @property
    def reports_dir(self) -> Path:
        return self.root / self.report_settings.get("reports_dir", "reports")

    @property
    def desktop_markdown_dir(self) -> Path | None:
        raw_path = self.report_settings.get("desktop_markdown_dir")
        if not raw_path:
            return None
        path = Path(str(raw_path)).expanduser()
        return path if path.is_absolute() else self.root / path


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_config(root: Path | None = None) -> AppConfig:
    root = root or Path.cwd()
    watchlist_path = root / "config" / "watchlist.yaml"
    sources_path = root / "config" / "sources.yaml"
    report_settings_path = root / "config" / "report_settings.yaml"

    watchlist_data = load_yaml(watchlist_path)
    sources = load_yaml(sources_path)
    report_settings = load_yaml(report_settings_path)

    assets = [
        Asset(
            symbol=str(item["symbol"]).upper(),
            name=str(item["name"]),
            asset_type=item["asset_type"],
            themes=list(item.get("themes", [])),
            priority=item.get("priority", "medium"),
            nav_only=bool(item.get("nav_only", False)),
            requires_identity_verification=bool(item.get("requires_identity_verification", False)),
            metadata={k: v for k, v in item.items() if k not in {
                "symbol", "name", "asset_type", "themes", "priority", "nav_only",
                "requires_identity_verification",
            }},
        )
        for item in watchlist_data.get("assets", [])
    ]

    treasury = watchlist_data.get("treasury", {})
    return AppConfig(
        root=root,
        watchlist_path=watchlist_path,
        sources_path=sources_path,
        report_settings_path=report_settings_path,
        watchlist=assets,
        treasury_enabled=bool(treasury.get("enabled", True)),
        treasury_tenors=list(treasury.get("tenors", ["2Y", "5Y", "10Y", "30Y"])),
        sources=sources,
        report_settings=report_settings,
    )
