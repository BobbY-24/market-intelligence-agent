from __future__ import annotations

import csv
from datetime import datetime
from io import StringIO
from xml.etree import ElementTree

from src.collectors.http import CachedHttpClient
from src.models import TreasurySnapshot

TREASURY_XML_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value={year}"
)
TENOR_XML_FIELDS = {"2Y": "BC_2YEAR", "5Y": "BC_5YEAR", "10Y": "BC_10YEAR", "30Y": "BC_30YEAR"}
LEGACY_TENOR_COLUMNS = {"2Y": "2 Yr", "5Y": "5 Yr", "10Y": "10 Yr", "30Y": "30 Yr"}


class USTreasuryProvider:
    def __init__(self, http: CachedHttpClient, tenors: list[str]) -> None:
        self.http = http
        self.tenors = tenors

    def get_treasury_curve(self, as_of: datetime) -> TreasurySnapshot:
        source = TREASURY_XML_URL.format(year=as_of.year)
        text = self.http.get_text(source)
        if text.lstrip().startswith("<?xml") or "<feed" in text[:200]:
            return self._from_treasury_xml(text, as_of, source)
        return self._from_legacy_csv(text, as_of)

    def _from_treasury_xml(self, text: str, as_of: datetime, source: str) -> TreasurySnapshot:
        root = ElementTree.fromstring(text)
        records = []
        for properties in root.findall(".//{*}properties"):
            record: dict[str, str] = {}
            for child in list(properties):
                tag = child.tag.rsplit("}", 1)[-1]
                if child.text:
                    record[tag] = child.text
            if "NEW_DATE" in record:
                records.append(record)
        if not records:
            return TreasurySnapshot(as_of, {}, {}, {}, source, data_quality="missing")

        records.sort(key=lambda row: row["NEW_DATE"])
        latest = records[-1]
        previous = records[-2] if len(records) > 1 else {}
        latest_date = datetime.fromisoformat(latest["NEW_DATE"].replace("Z", "+00:00"))

        yields = {}
        for tenor in self.tenors:
            yields[tenor] = _float_or_none(latest.get(TENOR_XML_FIELDS[tenor]))
        previous_yields = {
            tenor: _float_or_none(previous.get(TENOR_XML_FIELDS[tenor])) for tenor in self.tenors
        }
        return self._snapshot(latest_date, yields, previous_yields, source)

    def _from_legacy_csv(self, text: str, as_of: datetime) -> TreasurySnapshot:
        rows = list(csv.DictReader(StringIO(text)))
        parsed = [row for row in rows if row.get("Date")]
        if not parsed:
            return TreasurySnapshot(as_of, {}, {}, {}, "legacy_csv", data_quality="missing")

        parsed.sort(key=lambda row: datetime.strptime(row["Date"], "%m/%d/%Y"))
        latest = parsed[-1]
        previous = parsed[-2] if len(parsed) > 1 else {}
        latest_date = datetime.strptime(latest["Date"], "%m/%d/%Y")

        yields = {
            tenor: _float_or_none(latest.get(LEGACY_TENOR_COLUMNS[tenor])) for tenor in self.tenors
        }
        previous_yields = {
            tenor: _float_or_none(previous.get(LEGACY_TENOR_COLUMNS[tenor]))
            for tenor in self.tenors
        }
        return self._snapshot(latest_date, yields, previous_yields, "legacy_csv")

    def _snapshot(
        self,
        latest_date: datetime,
        yields: dict[str, float | None],
        previous_yields: dict[str, float | None],
        source: str,
    ) -> TreasurySnapshot:
        changes = {}
        for tenor in self.tenors:
            changes[tenor] = _bp_change(yields.get(tenor), previous_yields.get(tenor))
        spreads = {
            "2s10s": _spread_bp(yields.get("10Y"), yields.get("2Y")),
            "10s30s": _spread_bp(yields.get("30Y"), yields.get("10Y")),
        }
        return TreasurySnapshot(latest_date, yields, changes, spreads, source)


def _float_or_none(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _bp_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return (current - previous) * 100


def _spread_bp(long_rate: float | None, short_rate: float | None) -> float | None:
    if long_rate is None or short_rate is None:
        return None
    return (long_rate - short_rate) * 100
