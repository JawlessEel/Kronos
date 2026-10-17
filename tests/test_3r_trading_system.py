"""
Comprehensive Unit & Integration Tests for the 3R Rule Structural Trading System:
1. Accurate calculation of 50 SMA and 14 ATR across edge cases (insufficient bars, missing data).
2. Proper detection of Range High/Low (PDH/PDL) and backward multi-day Swing High/Low pivots.
3. Accurate flagging of ATR exhaustion when intraday expansion exceeds 85% of ATR.
4. Correct position sizing preventing risk from exceeding the user-specified dollar budget.
5. Invalidation of setups when Kronos prediction contradicts the 50-SMA regime or exceeds ATR capacity.
6. Flask routes `/3r-trading-system`, `/api/3r/analyze`, and `/api/3r/calculate-sizing`.
"""
import numpy as np
import pandas as pd
import pytest

from webui.services.structural_analysis import MarketStructure, StructuralAnalyzer
from webui.services.confluence_engine import (
    evaluate_forecast_confluence,
    generate_and_evaluate_forecast,
)
from webui.services.sizing_calculator import (
    calculate_trade_sizing,
    calculate_wall_street_raise_ladder,
    evaluate_scaling_eligibility,
)


def _make_daily_series(
    n_days: int = 60,
    start_price: float = 500.0,
    end_price: float = 550.0,
    daily_range: float = 5.0,
) -> pd.DataFrame:
    dates = pd.date_range("2026-06-01", periods=n_days, freq="B")
    closes = np.linspace(start_price, end_price, n_days)
    opens = closes - 0.5
    highs = closes + (daily_range / 2.0)
    lows = closes - (daily_range / 2.0)
    return pd.DataFrame({
        "timestamps": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": np.full(n_days, 10_000_000.0),
    })


class DummyKronosPredictor:
    """Mock KronosPredictor returning a controlled trajectory for unit testing."""

    def __init__(self, target_close: float):
        self.target_close = float(target_close)

    def predict(self, df, x_timestamp, y_timestamp, pred_len=24, **kwargs) -> pd.DataFrame:
        last_close = float(df["close"].iloc[-1])
        closes = np.linspace(last_close, self.target_close, pred_len)
        opens = np.concatenate([[last_close], closes[:-1]])
        highs = np.maximum(opens, closes) + 0.15
        lows = np.minimum(opens, closes) - 0.15
        return pd.DataFrame(
            {
                "open": opens,
                "high": highs,
                "low": lows,
                "close": closes,
                "volume": np.full(pred_len, 50_000.0),
                "amount": closes * 50_000.0,
                "env_high": highs + 0.30,
                "env_low": lows - 0.30,
            },
            index=y_timestamp,
        )


def test_sma50_and_atr14_calculation_and_edge_cases():
    """1. Accurate calculation of 50 SMA and 14 ATR across normal and edge cases (insufficient bars, missing data)."""
    analyzer = StructuralAnalyzer(sma_period=50, atr_period=14)
    daily_df = _make_daily_series(n_days=60, start_price=500.0, end_price=559.0, daily_range=4.0)

    expected_sma50 = float(daily_df["close"].tail(50).mean())
    structure = analyzer.analyze(daily_df)

    assert structure.trend_regime == "BULLISH"
    assert pytest.approx(structure.sma_50, rel=1e-4) == expected_sma50
    assert structure.atr_14 > 0.0

    # Edge Case A: Insufficient bars (< 50 bars and < 14 bars)
    short_df = _make_daily_series(n_days=5, start_price=400.0, end_price=380.0, daily_range=6.0)
    short_struct = analyzer.analyze(short_df)
    assert short_struct.trend_regime == "BEARISH"
    assert pytest.approx(short_struct.sma_50, rel=1e-4) == float(short_df["close"].mean())
    assert short_struct.atr_14 > 0.0

    # Edge Case B: Missing / NaN rows in input DataFrame
    dirty_df = daily_df.copy()
    dirty_df.loc[10, "close"] = np.nan
    dirty_df.loc[25, "high"] = np.nan
    clean_struct = analyzer.analyze(dirty_df)
    assert np.isfinite(clean_struct.sma_50)
    assert np.isfinite(clean_struct.atr_14)


def test_range_high_low_and_backward_swing_pivots():
    """2. Proper detection of Range High/Low (PDH/PDL) and backward multi-day Swing High/Low pivots."""
    analyzer = StructuralAnalyzer(swing_lookback_days=30)
    daily_df = _make_daily_series(n_days=45, start_price=500.0, end_price=510.0, daily_range=4.0)

    # Inject a prominent historical Swing High 10 sessions back and Swing Low 15 sessions back
    daily_df.loc[len(daily_df) - 10, "high"] = 532.75
    daily_df.loc[len(daily_df) - 15, "low"] = 481.25

    # Set Previous Trading Day (-2) exact Range High (PDH) and Range Low (PDL)
    daily_df.loc[len(daily_df) - 2, "high"] = 518.50
    daily_df.loc[len(daily_df) - 2, "low"] = 504.00
    daily_df.loc[len(daily_df) - 2, "close"] = 511.00

    # Current session (-1)
    daily_df.loc[len(daily_df) - 1, "open"] = 512.00
    daily_df.loc[len(daily_df) - 1, "high"] = 519.00
    daily_df.loc[len(daily_df) - 1, "low"] = 511.50
    daily_df.loc[len(daily_df) - 1, "close"] = 518.60  # Testing Range High (in sell zone)

    structure = analyzer.analyze(daily_df)
    assert pytest.approx(structure.range_high, abs=1e-4) == 518.50
    assert pytest.approx(structure.range_low, abs=1e-4) == 504.00
    assert structure.swing_high > structure.range_high
    assert pytest.approx(structure.swing_high, abs=1e-4) == 532.75
    assert structure.swing_low < structure.range_low
    assert pytest.approx(structure.swing_low, abs=1e-4) == 481.25
    assert structure.in_sell_zone is True
    assert structure.in_buy_zone is False


def test_atr_exhaustion_flagging_above_85_percent():
    """3. Accurate flagging of ATR exhaustion when intraday expansion exceeds 85% of ATR."""
    analyzer = StructuralAnalyzer(overextended_threshold_pct=85.0)
    daily_df = _make_daily_series(n_days=55, start_price=200.0, end_price=200.0, daily_range=10.0)
    # Daily range is constant 10.0 -> ATR(14) == 10.0
    # Make current day expand by 9.0 points (90% of 10.0 ATR)
    daily_df.loc[len(daily_df) - 1, "high"] = 205.0
    daily_df.loc[len(daily_df) - 1, "low"] = 196.0
    daily_df.loc[len(daily_df) - 1, "close"] = 204.5

    structure = analyzer.analyze(daily_df)
    assert pytest.approx(structure.atr_14, abs=0.2) == 10.0
    assert pytest.approx(structure.intraday_expansion, abs=1e-4) == 9.0
    assert structure.atr_consumed_pct >= 85.0
    assert structure.is_overextended is True
    assert pytest.approx(structure.remaining_atr, abs=0.2) == 1.0


def test_position_sizing_prevents_exceeding_risk_budget():
    """4. Correct position sizing preventing risk from exceeding the user-specified dollar budget."""
    sizing = calculate_trade_sizing(
        account_balance=5000.0,
        max_risk_dollars=50.0,
        entry_price=578.00,
        structural_stop_price=579.35,  # $1.35 stop distance -> floor(50 / 1.35) = 37 shares
        target_price=572.60,           # $5.40 reward distance -> 4.0:1 R:R
    )
    assert "error" not in sizing
    assert sizing["position_size"] == 37
    assert sizing["total_risk_exposure"] <= 50.0
    assert pytest.approx(sizing["total_risk_exposure"], abs=1e-2) == 37 * 1.35
    assert pytest.approx(sizing["risk_reward_ratio"], abs=1e-2) == 4.0
    assert sizing["meets_3r_minimum"] is True
    assert sizing["trade_direction"] == "SHORT"

    # Zero stop distance edge case
    zero_stop = calculate_trade_sizing(
        account_balance=5000.0,
        max_risk_dollars=50.0,
        entry_price=100.0,
        structural_stop_price=100.0,
        target_price=105.0,
    )
    assert "error" in zero_stop

    # Wall Street Raise 10% Scaling Matrix verification
    scaling = evaluate_scaling_eligibility(
        base_balance=5000.0,
        current_balance=6050.0,  # +21% (+10% compounded twice)
        profitable_days_this_week=4,
        consecutive_consistent_weeks=2,
        base_shares=50,
        base_risk_dollars=50.0,
    )
    assert scaling["consistency_met"] is True
    assert scaling["steps_unlocked"] == 2
    assert scaling["recommended_shares"] in (60, 61)


def test_confluence_invalidation_on_regime_contradiction_or_atr_violation():
    """5. Invalidation of setups when Kronos prediction contradicts the 50-SMA regime or exceeds ATR capacity."""
    analyzer = StructuralAnalyzer()
    # Bearish regime (price dropping from 600 down to 570; 50-SMA ~ 585)
    daily_df = _make_daily_series(n_days=60, start_price=600.0, end_price=570.0, daily_range=6.0)
    daily_df.loc[len(daily_df) - 10, "high"] = 579.50  # Swing High
    daily_df.loc[len(daily_df) - 2, "high"] = 578.00   # Range High (PDH)
    daily_df.loc[len(daily_df) - 2, "low"] = 571.00    # Range Low (PDL)
    # Today rallies from 572.50 to 578.10 (5.60 expansion out of ~6.0 ATR -> remaining ATR ~0.40, in Sell Zone)
    daily_df.loc[len(daily_df) - 1, "open"] = 572.50
    daily_df.loc[len(daily_df) - 1, "low"] = 572.50
    daily_df.loc[len(daily_df) - 1, "high"] = 578.10
    daily_df.loc[len(daily_df) - 1, "close"] = 578.05

    intraday_5m_df = pd.DataFrame({
        "timestamps": pd.date_range("2026-08-21 15:00:00", periods=20, freq="5min"),
        "open": np.linspace(575.0, 578.0, 20),
        "high": np.linspace(575.2, 578.10, 20),
        "low": np.linspace(574.8, 577.95, 20),
        "close": np.linspace(575.1, 578.05, 20),
        "volume": np.full(20, 100_000.0),
    })

    structure = analyzer.analyze(daily_df, intraday_5m_df)
    assert structure.trend_regime == "BEARISH"
    assert structure.in_sell_zone is True

    # Case A: Kronos predicts a BULLISH breakout (+4.00 pts) that both contradicts the Bearish 50-SMA
    # and exceeds the remaining ATR (~0.40) -> Chased Breakout Trap & Invalid Trade!
    trap_predictor = DummyKronosPredictor(target_close=582.05)
    _, trap_score, trap_eval = generate_and_evaluate_forecast(
        predictor=trap_predictor,
        intraday_5m_df=intraday_5m_df,
        structure=structure,
        pred_len=12,
    )
    assert trap_eval.is_target_feasible is False
    assert trap_eval.chased_breakout_trap is True
    assert trap_eval.is_valid_trade is False
    assert any("CHASED BREAKOUT TRAP" in w for w in trap_eval.warnings)

    # Case B: Valid Topside Compression Reversal (Short Setup) within remaining ATR budget
    daily_df.loc[len(daily_df) - 1, "low"] = 574.20  # Expansion = 3.90 (65% of 6.0 ATR -> 2.10 remaining ATR)
    structure_valid = analyzer.analyze(daily_df, intraday_5m_df)
    short_predictor = DummyKronosPredictor(target_close=576.50)  # 1.55 delta <= 2.10 remaining ATR
    _, valid_score, valid_eval = generate_and_evaluate_forecast(
        predictor=short_predictor,
        intraday_5m_df=intraday_5m_df,
        structure=structure_valid,
        pred_len=12,
    )
    assert valid_eval.is_target_feasible is True
    assert valid_eval.setup_side == "SHORT"
    assert valid_eval.is_valid_trade is True
    assert valid_score >= 80
    assert valid_eval.structural_stop > structure_valid.swing_high


def test_3r_flask_page_and_api_endpoints():
    """6. Verifies the separate `/3r-trading-system` page and `/api/3r/*` endpoints."""
    from webui import app as ui_module
    client = ui_module.app.test_client()

    page_resp = client.get("/3r-trading-system")
    assert page_resp.status_code == 200
    html = page_resp.get_data(as_text=True)
    assert "The 3R Rule Structural Trading System" in html
    assert "panel-1-top-banner" in html
    assert "chart-intraday-5m" in html

    # Test Topside Compression Short Scenario via API
    api_resp = client.post(
        "/api/3r/analyze",
        json={
            "ticker": "SPY",
            "scenario_preset": "topside_short",
            "account_balance": 5000,
            "max_risk_dollars": 50,
            "use_kronos_model": False,
        },
    )
    assert api_resp.status_code == 200
    payload = api_resp.get_json()
    assert payload["success"] is True
    assert payload["structure"]["trend_regime"] == "BEARISH"
    assert payload["structure"]["in_sell_zone"] is True
    assert payload["sizing"]["total_risk_exposure"] <= 50.0
    assert "daily_macro_chart" in payload["charts"]
    assert "intraday_execution_chart" in payload["charts"]

    # Verify PDF exporter script supports 3R container, header, and charts
    pdf_js_resp = client.get("/static/ui_pdf_export.js")
    assert pdf_js_resp.status_code == 200
    pdf_js = pdf_js_resp.get_data(as_text=True)
    assert ".three-r-container" in pdf_js
    assert ".three-r-header" in pdf_js
    assert "chart-daily-macro" in pdf_js
    assert "chart-intraday-5m" in pdf_js
