from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.models import MarketSnapshot, TreasurySnapshot


class SQLiteStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                create table if not exists market_snapshots (
                    symbol text not null,
                    as_of text not null,
                    latest_value real,
                    daily_change_pct real,
                    five_day_change_pct real,
                    one_month_change_pct real,
                    ytd_change_pct real,
                    volume integer,
                    average_volume real,
                    fifty_day_ma real,
                    two_hundred_day_ma real,
                    fifty_two_week_high real,
                    fifty_two_week_low real,
                    data_quality text,
                    source text,
                    primary key (symbol, as_of)
                );
                create table if not exists treasury_snapshots (
                    as_of text primary key,
                    yields_json text not null,
                    daily_changes_bp_json text not null,
                    spreads_bp_json text not null,
                    source text not null,
                    data_quality text not null
                );
                create table if not exists report_runs (
                    generated_at text primary key,
                    markdown_path text,
                    json_path text,
                    warnings_json text not null
                );
                """
            )

    def save_market_snapshot(self, snapshot: MarketSnapshot) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert or replace into market_snapshots values (
                    :symbol, :as_of, :latest_value, :daily_change_pct, :five_day_change_pct,
                    :one_month_change_pct, :ytd_change_pct, :volume, :average_volume,
                    :fifty_day_ma, :two_hundred_day_ma, :fifty_two_week_high,
                    :fifty_two_week_low, :data_quality, :source
                )
                """,
                {
                    **snapshot.__dict__,
                    "as_of": snapshot.as_of.isoformat(),
                },
            )

    def save_treasury_snapshot(self, snapshot: TreasurySnapshot) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                insert or replace into treasury_snapshots values (?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.as_of.isoformat(),
                    json.dumps(snapshot.yields, sort_keys=True),
                    json.dumps(snapshot.daily_changes_bp, sort_keys=True),
                    json.dumps(snapshot.spreads_bp, sort_keys=True),
                    snapshot.source,
                    snapshot.data_quality,
                ),
            )

    def save_report_run(
        self,
        generated_at: str,
        markdown_path: str | None,
        json_path: str | None,
        warnings: list[str],
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "insert or replace into report_runs values (?, ?, ?, ?)",
                (generated_at, markdown_path, json_path, json.dumps(warnings)),
            )

