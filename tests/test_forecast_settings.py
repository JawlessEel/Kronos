from types import SimpleNamespace
import pytest
from webui.forecast_settings import validate_forecast, history_length
from webui import polygon_feed as live
from tests.test_polygon_feed import market_rows
import pandas as pd


@pytest.mark.parametrize('limit', [512, 2048])
def test_full_supported_context_and_horizon(limit):
    validate_forecast(SimpleNamespace(max_context=limit), limit, limit, 1, .9, 20)
    with pytest.raises(ValueError, match='lookback'):
        validate_forecast(SimpleNamespace(max_context=limit), limit + 1, 30, 1, .9, 1)
    with pytest.raises(ValueError, match='Forecast length'):
        validate_forecast(SimpleNamespace(max_context=limit), 400, limit + 1, 1, .9, 1)


@pytest.mark.parametrize('count', [0, 15, 10001])
def test_history_bounds(count):
    with pytest.raises(ValueError):
        history_length(count)


def test_indicator_history_can_exceed_model_context():
    df = live.normalize_bars(market_rows(), 5, pd.Timestamp('2026-10-04T12:00:00Z'), 1000)
    assert len(df) == 1000
    assert len(df.tail(512)) == 512
    assert df.timestamps.is_unique and df.timestamps.is_monotonic_increasing


def test_non_finite_sampling_rejected():
    with pytest.raises(ValueError):
        validate_forecast(SimpleNamespace(max_context=512), 400, 30, float('nan'), .9, 1)
