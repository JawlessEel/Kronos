"""
Multi-Timeframe Structural Analysis Engine for the 3R Rule Trading System.

Computes:
1. Pillar 1 — Trend Bias (1D 50-Period Simple Moving Average)
2. Pillar 2 — Premium Liquidity Zones (Range High/Low [PDH/PDL] and Swing High/Low pivots)
3. Pillar 3 — Range & Value Snapshot (1D 14-Period ATR, Intraday Expansion, ATR Consumed %, Exhaustion)
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class MarketStructure:
    trend_regime: str             # "BULLISH" or "BEARISH"
    sma_50: float                 # Daily 50-period SMA
    atr_14: float                 # Daily 14-period ATR
    range_high: float             # Previous Day High (PDH)
    range_low: float              # Previous Day Low (PDL)
    swing_high: float             # Prior multi-day pivot high above Range High
    swing_low: float              # Prior multi-day pivot low below Range Low
    intraday_expansion: float     # High of Day - Low of Day
    atr_consumed_pct: float       # (Intraday Expansion / ATR_14) * 100
    remaining_atr: float          # Remaining available ATR budget
    in_sell_zone: bool            # True if price is testing Range High to Swing High
    in_buy_zone: bool             # True if price is testing Range Low to Swing Low
    # Extended structural telemetry for dashboard visualization & setup screening
    current_price: float = 0.0
    high_of_day: float = 0.0
    low_of_day: float = 0.0
    open_of_day: float = 0.0
    prev_close: float = 0.0
    sma_distance: float = 0.0
    sma_distance_pct: float = 0.0
    is_overextended: bool = False
    is_exhausted_multi_atr: bool = False
    sell_zone_floor: float = 0.0
    buy_zone_ceiling: float = 0.0
    trade_directive: str = ""
    directional_quota: str = "80%–90%"
    risk_allocation_pct: int = 100
    contrarian_rule: str = ""
    optimal_archetypes: List[str] = field(default_factory=list)
    session_date: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StructuralAnalyzer:
    """
    Evaluates Daily (1D) and Intraday (5M) OHLCV series to produce a complete
    `MarketStructure` snapshot according to Doug's 3R Rule specification.
    """

    def __init__(
        self,
        sma_period: int = 50,
        atr_period: int = 14,
        swing_lookback_days: int = 30,
        zone_buffer_ratio: float = 0.15,
        overextended_threshold_pct: float = 85.0,
    ):
        self.sma_period = max(1, int(sma_period))
        self.atr_period = max(1, int(atr_period))
        self.swing_lookback_days = max(2, int(swing_lookback_days))
        self.zone_buffer_ratio = float(zone_buffer_ratio)
        self.overextended_threshold_pct = float(overextended_threshold_pct)

    @staticmethod
    def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            raise ValueError("OHLCV DataFrame cannot be empty.")
        clean = df.copy()
        col_map = {c.lower(): c for c in clean.columns}
        for req in ("open", "high", "low", "close"):
            if req not in col_map:
                raise ValueError(f"Missing required OHLC column '{req}'.")
            if col_map[req] != req:
                clean[req] = clean[col_map[req]]
            clean[req] = pd.to_numeric(clean[req], errors="coerce")

        # Normalize timestamps if present
        ts_col = None
        for candidate in ("timestamps", "timestamp", "date", "datetime"):
            if candidate in col_map:
                ts_col = col_map[candidate]
                break
        if ts_col is not None:
            ts = pd.to_datetime(clean[ts_col], errors="coerce")
            if getattr(ts.dt, "tz", None) is not None:
                ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
            clean["timestamps"] = ts
        else:
            clean["timestamps"] = pd.date_range("2025-01-01", periods=len(clean), freq="5min")

        clean = clean.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        if clean.empty:
            raise ValueError("OHLCV DataFrame has no valid numeric rows after dropping NaNs.")
        return clean

    def calculate_sma_series(self, daily_df: pd.DataFrame, period: Optional[int] = None) -> pd.Series:
        """Calculates rolling Simple Moving Average on daily close with fallback for short series."""
        w = period or self.sma_period
        closes = daily_df["close"].astype(float)
        return closes.rolling(window=w, min_periods=1).mean()

    def calculate_atr_series(self, daily_df: pd.DataFrame, period: Optional[int] = None) -> pd.Series:
        """Calculates True Range (TR) and rolling Average True Range (ATR)."""
        w = period or self.atr_period
        high = daily_df["high"].astype(float)
        low = daily_df["low"].astype(float)
        close = daily_df["close"].astype(float)
        prev_close = close.shift(1)

        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=w, min_periods=1).mean()

    def find_pivot_high_above(
        self,
        range_high: float,
        history_df: pd.DataFrame,
        fallback_atr: float,
        lookback_days: Optional[int] = None,
    ) -> float:
        """
        Scans backward across preceding candles (up to `lookback_days`) to find the next
        prominent overhead resistance pivot high strictly above `range_high`.
        """
        lb = lookback_days or self.swing_lookback_days
        if history_df is None or history_df.empty:
            return round(float(range_high + max(0.5 * fallback_atr, range_high * 0.005)), 4)

        window = history_df.tail(max(lb, 5)).copy()
        highs = window["high"].astype(float).values
        n = len(highs)

        # Look for local pivot highs (high[i] >= neighbors) strictly above range_high, scanning right-to-left
        pivot_candidates: List[float] = []
        for i in range(n - 2, 0, -1):
            val = float(highs[i])
            if val > range_high and val >= float(highs[i - 1]) and val >= float(highs[i + 1]):
                pivot_candidates.append(val)

        if pivot_candidates:
            # Next prominent overhead pivot above Range High (closest overhead major pivot first, or prominent peak)
            above_sorted = sorted(pivot_candidates)
            # Pick the first meaningful pivot at least 10% of ATR above range_high if available
            min_sep = 0.10 * max(fallback_atr, 1e-4)
            for cand in above_sorted:
                if cand - range_high >= min_sep:
                    return round(float(cand), 4)
            return round(float(above_sorted[0]), 4)

        # Fallback: any historical high above range_high in the lookback window
        strictly_above = [float(h) for h in highs if float(h) > range_high]
        if strictly_above:
            min_sep = 0.10 * max(fallback_atr, 1e-4)
            separated = [h for h in sorted(strictly_above) if h - range_high >= min_sep]
            chosen = separated[0] if separated else max(strictly_above)
            return round(float(chosen), 4)

        # All-time/window high case: project structural resistance band using 0.5x Daily ATR
        return round(float(range_high + max(0.5 * fallback_atr, range_high * 0.005)), 4)

    def find_pivot_low_below(
        self,
        range_low: float,
        history_df: pd.DataFrame,
        fallback_atr: float,
        lookback_days: Optional[int] = None,
    ) -> float:
        """
        Scans backward across preceding candles (up to `lookback_days`) to find the next
        prominent support pivot low strictly below `range_low`.
        """
        lb = lookback_days or self.swing_lookback_days
        if history_df is None or history_df.empty:
            return round(float(max(0.01, range_low - max(0.5 * fallback_atr, range_low * 0.005))), 4)

        window = history_df.tail(max(lb, 5)).copy()
        lows = window["low"].astype(float).values
        n = len(lows)

        pivot_candidates: List[float] = []
        for i in range(n - 2, 0, -1):
            val = float(lows[i])
            if val < range_low and val <= float(lows[i - 1]) and val <= float(lows[i + 1]):
                pivot_candidates.append(val)

        if pivot_candidates:
            below_sorted = sorted(pivot_candidates, reverse=True)  # closest below range_low first
            min_sep = 0.10 * max(fallback_atr, 1e-4)
            for cand in below_sorted:
                if range_low - cand >= min_sep:
                    return round(float(cand), 4)
            return round(float(below_sorted[0]), 4)

        strictly_below = [float(l) for l in lows if float(l) < range_low]
        if strictly_below:
            min_sep = 0.10 * max(fallback_atr, 1e-4)
            separated = [l for l in sorted(strictly_below, reverse=True) if range_low - l >= min_sep]
            chosen = separated[0] if separated else min(strictly_below)
            return round(float(chosen), 4)

        return round(float(max(0.01, range_low - max(0.5 * fallback_atr, range_low * 0.005))), 4)

    def extract_session_slices(
        self,
        daily_df: pd.DataFrame,
        intraday_5m_df: Optional[pd.DataFrame] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Partitions intraday and daily data into:
        - `current_session_df`: Intraday bars for the active trading day
        - `prev_day_df`: Bars for the previous trading day (for Range High / Range Low)
        - `prior_history_daily`: Daily bars prior to the active session for Swing High/Low lookback
        """
        d_clean = self._prepare_df(daily_df)

        if intraday_5m_df is not None and not intraday_5m_df.empty:
            m_clean = self._prepare_df(intraday_5m_df)
            m_clean["session_date"] = m_clean["timestamps"].dt.date
            unique_dates = sorted(m_clean["session_date"].unique())

            current_date = unique_dates[-1]
            current_session_df = m_clean[m_clean["session_date"] == current_date].copy()
            # If the final session has very few bars (e.g. midnight tick), include last 78 bars or previous session
            if len(current_session_df) < 3 and len(m_clean) >= 12:
                current_session_df = m_clean.tail(min(78, len(m_clean))).copy()

            # Determine previous trading day Range High / Range Low
            d_clean["session_date"] = d_clean["timestamps"].dt.date
            prior_daily = d_clean[d_clean["session_date"] < current_date]
            if len(prior_daily) >= 1:
                prev_day_row = prior_daily.iloc[[-1]].copy()
                prior_history_daily = prior_daily.iloc[:-1].copy() if len(prior_daily) > 1 else prior_daily.copy()
                return current_session_df, prev_day_row, prior_history_daily
            elif len(unique_dates) >= 2:
                prev_date = unique_dates[-2]
                prev_day_df = m_clean[m_clean["session_date"] == prev_date].copy()
                prior_history_daily = d_clean.iloc[:-1].copy() if len(d_clean) > 1 else d_clean.copy()
                return current_session_df, prev_day_df, prior_history_daily

        # Fallback when only daily_df or single-day intraday_5m_df is supplied
        current_session_df = (
            self._prepare_df(intraday_5m_df)
            if (intraday_5m_df is not None and not intraday_5m_df.empty)
            else d_clean.iloc[[-1]].copy()
        )
        if len(d_clean) >= 2:
            prev_day_df = d_clean.iloc[[-2]].copy()
            prior_history_daily = d_clean.iloc[:-2].copy() if len(d_clean) > 2 else d_clean.iloc[:-1].copy()
        else:
            prev_day_df = d_clean.iloc[[-1]].copy()
            prior_history_daily = d_clean.copy()

        return current_session_df, prev_day_df, prior_history_daily

    def analyze(
        self,
        daily_df: pd.DataFrame,
        intraday_5m_df: Optional[pd.DataFrame] = None,
        current_price_override: Optional[float] = None,
    ) -> MarketStructure:
        """
        Computes the full 3R Rule MarketStructure from Daily (1D) and Intraday (5M) OHLCV data.
        """
        d_clean = self._prepare_df(daily_df)
        sma_series = self.calculate_sma_series(d_clean, self.sma_period)
        atr_series = self.calculate_atr_series(d_clean, self.atr_period)

        sma_50 = float(sma_series.iloc[-1])
        atr_14 = float(atr_series.iloc[-1])
        if atr_14 <= 0 or np.isnan(atr_14):
            atr_14 = max(float((d_clean["high"] - d_clean["low"]).mean()), 0.01)

        current_session_df, prev_day_df, prior_history_daily = self.extract_session_slices(d_clean, intraday_5m_df)

        current_price = (
            float(current_price_override)
            if current_price_override is not None
            else float(current_session_df["close"].iloc[-1])
        )
        high_of_day = max(float(current_session_df["high"].max()), current_price)
        low_of_day = min(float(current_session_df["low"].min()), current_price)
        open_of_day = float(current_session_df["open"].iloc[0])
        prev_close = float(prev_day_df["close"].iloc[-1])

        # Pillar 1: Trend Bias (1D 50 SMA)
        trend_regime = "BULLISH" if current_price >= sma_50 else "BEARISH"
        sma_distance = current_price - sma_50
        sma_distance_pct = (sma_distance / sma_50 * 100.0) if sma_50 > 0 else 0.0

        if trend_regime == "BULLISH":
            trade_directive = "LONG / BUY (80%–90% Execution Quota)"
            contrarian_rule = "Contrarian shorts restricted to 50% size & fast scalps (30s–2m)"
            optimal_archetypes = ["Bullish Dip Reversal (Range/Swing Low Bounce)", "Breakout Continuation"]
        else:
            trade_directive = "SHORT / SELL (80%–90% Execution Quota)"
            contrarian_rule = "Contrarian longs restricted to 50% size & fast scalps (30s–2m)"
            optimal_archetypes = ["Topside Compression Reversal (Range/Swing High Reject)", "Breakdown Selling"]

        # Pillar 2: 4 Liquidity Horizontal Levels
        range_high = float(prev_day_df["high"].max())
        range_low = float(prev_day_df["low"].min())
        if range_high <= range_low:
            range_high = range_low + max(0.25 * atr_14, 0.01)

        swing_high = self.find_pivot_high_above(
            range_high=range_high,
            history_df=prior_history_daily,
            fallback_atr=atr_14,
            lookback_days=self.swing_lookback_days,
        )
        swing_low = self.find_pivot_low_below(
            range_low=range_low,
            history_df=prior_history_daily,
            fallback_atr=atr_14,
            lookback_days=self.swing_lookback_days,
        )

        # Proximity & Zone Detection per specification:
        # Sell Zone: price >= (range_high - 0.15 * (swing_high - range_high))
        # Buy Zone:  price <= (range_low + 0.15 * (range_low - swing_low))
        upper_band_width = max(swing_high - range_high, 0.10 * atr_14)
        lower_band_width = max(range_low - swing_low, 0.10 * atr_14)
        sell_zone_floor = range_high - (self.zone_buffer_ratio * upper_band_width)
        buy_zone_ceiling = range_low + (self.zone_buffer_ratio * lower_band_width)

        in_sell_zone = bool(current_price >= sell_zone_floor)
        in_buy_zone = bool(current_price <= buy_zone_ceiling)

        # Pillar 3: ATR Range & Exhaustion Math
        intraday_expansion = max(0.0, high_of_day - low_of_day)
        atr_consumed_pct = (intraday_expansion / atr_14) * 100.0 if atr_14 > 0 else 0.0
        remaining_atr = max(0.0, atr_14 - intraday_expansion)
        is_overextended = bool(atr_consumed_pct >= self.overextended_threshold_pct)
        is_exhausted_multi_atr = bool(atr_consumed_pct >= 150.0)

        session_ts = current_session_df["timestamps"].iloc[-1]
        session_date_str = str(session_ts.date()) if hasattr(session_ts, "date") else str(session_ts)

        return MarketStructure(
            trend_regime=trend_regime,
            sma_50=round(sma_50, 4),
            atr_14=round(atr_14, 4),
            range_high=round(range_high, 4),
            range_low=round(range_low, 4),
            swing_high=round(swing_high, 4),
            swing_low=round(swing_low, 4),
            intraday_expansion=round(intraday_expansion, 4),
            atr_consumed_pct=round(atr_consumed_pct, 2),
            remaining_atr=round(remaining_atr, 4),
            in_sell_zone=in_sell_zone,
            in_buy_zone=in_buy_zone,
            current_price=round(current_price, 4),
            high_of_day=round(high_of_day, 4),
            low_of_day=round(low_of_day, 4),
            open_of_day=round(open_of_day, 4),
            prev_close=round(prev_close, 4),
            sma_distance=round(sma_distance, 4),
            sma_distance_pct=round(sma_distance_pct, 2),
            is_overextended=is_overextended,
            is_exhausted_multi_atr=is_exhausted_multi_atr,
            sell_zone_floor=round(sell_zone_floor, 4),
            buy_zone_ceiling=round(buy_zone_ceiling, 4),
            trade_directive=trade_directive,
            directional_quota="80%–90%",
            risk_allocation_pct=100,
            contrarian_rule=contrarian_rule,
            optimal_archetypes=optimal_archetypes,
            session_date=session_date_str,
        )
