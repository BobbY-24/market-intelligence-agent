from datetime import datetime

from src.collectors.market_data import YFinanceMarketDataProvider
from src.models import Asset


class FakeTimestamp:
    def __init__(self, dt: datetime) -> None:
        self.dt = dt

    def to_pydatetime(self) -> datetime:
        return self.dt


class FakeSeries:
    def __init__(self, data: dict[str, float | int]) -> None:
        self.data = data

    def get(self, key: str) -> float | int | None:
        return self.data.get(key)


class FakeHistory:
    def iterrows(self):
        rows = [
            (datetime(2026, 1, 2), {"Close": 10, "Volume": 100}),
            (datetime(2026, 1, 5), {"Close": 11, "Volume": 200}),
            (datetime(2026, 1, 6), {"Close": 12, "Volume": 300}),
            (datetime(2026, 1, 7), {"Close": 13, "Volume": 400}),
            (datetime(2026, 1, 8), {"Close": 14, "Volume": 500}),
            (datetime(2026, 1, 9), {"Close": 15, "Volume": 600}),
        ]
        for dt, row in rows:
            yield FakeTimestamp(dt), FakeSeries(row)


class FakeTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def history(self, period: str, interval: str, auto_adjust: bool):
        assert period == "1y"
        assert interval == "1d"
        assert auto_adjust is False
        return FakeHistory()


def test_market_provider_computes_basic_changes(monkeypatch) -> None:
    monkeypatch.setattr("src.collectors.market_data.yf.Ticker", FakeTicker)
    provider = YFinanceMarketDataProvider()
    result = provider.collect(Asset("TEST", "Test", "equity", []), datetime(2026, 1, 9))
    snapshot = result.snapshot

    assert snapshot.latest_value == 15
    assert snapshot.daily_change_pct == 7.14285714285714
    assert snapshot.five_day_change_pct == 50
    assert snapshot.volume == 600
    assert len(result.price_history) == 6
