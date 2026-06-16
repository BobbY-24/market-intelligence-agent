from datetime import datetime

from src.collectors.treasury import USTreasuryProvider


class FakeHttp:
    def get_text(self, url: str) -> str:
        return "\n".join(
            [
                "Date,1 Mo,2 Mo,3 Mo,4 Mo,6 Mo,1 Yr,2 Yr,3 Yr,5 Yr,7 Yr,10 Yr,20 Yr,30 Yr",
                "06/12/2026,4,4,4,4,4,4,3.90,3.95,4.00,4.05,4.10,4.30,4.40",
                "06/15/2026,4,4,4,4,4,4,3.95,4.00,4.10,4.15,4.25,4.45,4.55",
            ]
        )


def test_treasury_provider_computes_spreads_and_bp_changes() -> None:
    provider = USTreasuryProvider(FakeHttp(), ["2Y", "5Y", "10Y", "30Y"])  # type: ignore[arg-type]
    snapshot = provider.get_treasury_curve(datetime(2026, 6, 16))

    assert snapshot.yields["10Y"] == 4.25
    assert round(snapshot.daily_changes_bp["10Y"], 2) == 15
    assert round(snapshot.spreads_bp["2s10s"], 2) == 30
    assert round(snapshot.spreads_bp["10s30s"], 2) == 30


class FakeXmlHttp:
    def get_text(self, url: str) -> str:
        return """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns:d="http://schemas.microsoft.com/ado/2007/08/dataservices"
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
  <entry><content><m:properties>
    <d:NEW_DATE>2026-06-12T00:00:00</d:NEW_DATE>
    <d:BC_2YEAR>3.90</d:BC_2YEAR><d:BC_5YEAR>4.00</d:BC_5YEAR>
    <d:BC_10YEAR>4.10</d:BC_10YEAR><d:BC_30YEAR>4.40</d:BC_30YEAR>
  </m:properties></content></entry>
  <entry><content><m:properties>
    <d:NEW_DATE>2026-06-15T00:00:00</d:NEW_DATE>
    <d:BC_2YEAR>3.95</d:BC_2YEAR><d:BC_5YEAR>4.10</d:BC_5YEAR>
    <d:BC_10YEAR>4.25</d:BC_10YEAR><d:BC_30YEAR>4.55</d:BC_30YEAR>
  </m:properties></content></entry>
</feed>"""


def test_treasury_provider_parses_official_xml_shape() -> None:
    provider = USTreasuryProvider(FakeXmlHttp(), ["2Y", "5Y", "10Y", "30Y"])  # type: ignore[arg-type]
    snapshot = provider.get_treasury_curve(datetime(2026, 6, 16))

    assert snapshot.yields["30Y"] == 4.55
    assert round(snapshot.daily_changes_bp["5Y"], 2) == 10
