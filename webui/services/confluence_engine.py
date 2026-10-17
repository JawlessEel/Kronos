"""
Engine B: Prediction & Confluence Evaluator for the 3R Rule Trading System.

Integrates Kronos autoregressive K-line forecasts (`KronosPredictor` / `EnhancedKronosPredictor`)
with Doug's 3R structural rules:
1. Trend Alignment (30 pts): Does Kronos forecast match 1D 50-SMA regime?
2. Liquidity Boundary (30 pts): Is entry occurring within a premium Buy/Sell zone?
3. Range Feasibility (20 pts): Does predicted move fit within the remaining daily ATR budget?
4. Price Action Compression (20 pts): Evidence of candle compression / wick rejection at structural level?

Also screens for:
- Primary Setup: Topside Compression Reversal (Short Setup)
- Alternative Setup: Bullish Dip Reversal / Range Low Bounce (Long Setup)
- Anti-Pattern 1: Chased Breakout Trap (`FALSE BREAKOUT WARNING - CONTRARIAN TRAP`)
- Anti-Pattern 2: Exhaustion Overextension (`ATR EXHAUSTION - REVERSAL WATCH`)
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

from webui.services.structural_analysis import MarketStructure


@dataclass
class ConfluenceEvaluation:
    setup_archetype: str                  # e.g. "TOPSIDE COMPRESSION REVERSAL (SHORT)", "BULLISH DIP REVERSAL (LONG)", "NO SETUP / WAIT"
    setup_side: str                       # "SHORT", "LONG", or "NEUTRAL"
    confluence_score: int                 # 0 to 100
    score_breakdown: Dict[str, int]       # {"trend_alignment": 30, "liquidity_boundary": 30, "range_feasibility": 20, "price_compression": 20}
    predicted_target: float               # Kronos terminal close forecast
    predicted_delta: float                # abs(predicted_target - current_price)
    predicted_direction: str              # "BULLISH" or "BEARISH"
    predicted_return_pct: float           # (predicted_target / current_price - 1) * 100
    is_target_feasible: bool              # True if predicted_delta <= remaining_atr (or reversal into range)
    feasibility_status: str               # "FEASIBLE WITHIN ATR BUDGET" or "MATHEMATICALLY INVALID / UNREALISTIC REWARD"
    structural_entry: float               # Recommended entry price
    structural_stop: float                # Structural invalidation stop price (above SH or below SL)
    structural_target: float              # Structural take-profit target (RL/early base or RH/SH)
    estimated_rr: float                   # Structural Reward : Risk ratio
    is_valid_trade: bool                  # True when setup conditions pass & no invalidation trap
    chased_breakout_trap: bool = False
    atr_exhaustion_warning: bool = False
    warnings: List[str] = field(default_factory=list)
    rationale: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def detect_candle_compression(intraday_5m_df: pd.DataFrame, lookback_bars: int = 6) -> Tuple[bool, float]:
    """
    Checks recent 5-minute candles for price compression or rejection wicks near a liquidity boundary.
    Returns `(is_compressed, compression_ratio)` where lower ratio means tighter range compression.
    """
    if intraday_5m_df is None or len(intraday_5m_df) < 4:
        return False, 1.0

    recent = intraday_5m_df.tail(max(3, lookback_bars))
    baseline = intraday_5m_df.tail(max(20, lookback_bars * 4))

    recent_ranges = (recent["high"].astype(float) - recent["low"].astype(float)).values
    base_ranges = (baseline["high"].astype(float) - baseline["low"].astype(float)).values
    mean_base = float(np.mean(base_ranges)) if len(base_ranges) > 0 else 0.0
    if mean_base <= 1e-8:
        return True, 0.5

    mean_recent = float(np.mean(recent_ranges))
    ratio = mean_recent / mean_base

    # Also check for upper/lower rejection wicks on last 3 bars
    bodies = (recent["close"].astype(float) - recent["open"].astype(float)).abs().values
    wicks = recent_ranges - bodies
    wick_dominance = float(np.mean(wicks / np.maximum(recent_ranges, 1e-6)))

    is_compressed = bool(ratio <= 0.85 or wick_dominance >= 0.50)
    return is_compressed, round(float(ratio), 3)


def evaluate_forecast_confluence(
    pred_df: pd.DataFrame,
    intraday_5m_df: pd.DataFrame,
    structure: MarketStructure,
) -> ConfluenceEvaluation:
    """
    Evaluates a generated Kronos forecast DataFrame (`pred_df`) against the 3R `MarketStructure`.
    """
    if pred_df is None or pred_df.empty:
        raise ValueError("pred_df cannot be empty.")

    current_price = float(structure.current_price or intraday_5m_df["close"].iloc[-1])
    predicted_target = float(pred_df["close"].iloc[-1])
    predicted_delta = abs(predicted_target - current_price)
    predicted_direction = "BULLISH" if predicted_target >= current_price else "BEARISH"
    predicted_return_pct = ((predicted_target - current_price) / current_price * 100.0) if current_price > 0 else 0.0

    # 1. Trend Alignment (30 pts): Does Kronos forecast match 1D 50-SMA regime?
    trend_matches = (
        (structure.trend_regime == "BULLISH" and predicted_direction == "BULLISH")
        or (structure.trend_regime == "BEARISH" and predicted_direction == "BEARISH")
    )
    trend_pts = 30 if trend_matches else 0

    # 2. Liquidity Boundary (30 pts): Is entry occurring within Buy/Sell zone aligned with regime/reversal?
    liquidity_pts = 0
    if structure.trend_regime == "BEARISH" and structure.in_sell_zone:
        liquidity_pts = 30
    elif structure.trend_regime == "BULLISH" and structure.in_buy_zone:
        liquidity_pts = 30
    elif structure.in_sell_zone or structure.in_buy_zone:
        liquidity_pts = 15  # Testing liquidity boundary, but counter-trend

    # 3. ATR Range Feasibility Gate (20 pts)
    # Note: If ATR is already heavily consumed (>60%) during a counter-trend morning rally into the Sell Zone,
    # a mean-reversion reversal back inside the intraday range restores equilibrium, whereas further trend
    # expansion beyond the remaining ATR budget is mathematically infeasible.
    is_target_feasible = bool(predicted_delta <= max(structure.remaining_atr, 1e-6))
    range_pts = 20 if is_target_feasible else 0

    # 4. Price Action Compression (20 pts)
    is_compressed, comp_ratio = detect_candle_compression(intraday_5m_df)
    compression_pts = 20 if is_compressed else (10 if comp_ratio <= 1.05 else 0)

    total_score = int(trend_pts + liquidity_pts + range_pts + compression_pts)
    score_breakdown = {
        "trend_alignment": trend_pts,
        "liquidity_boundary": liquidity_pts,
        "range_feasibility": range_pts,
        "price_compression": compression_pts,
    }

    warnings: List[str] = []
    rationale: List[str] = []

    # Check Anti-Pattern 1: The Chased Breakout Trap
    # Price breaks morning high / tests upper liquidity (RH/SH) while Price < 50 SMA (Bearish regime)
    # and trader/model projects bullish continuation or ATR budget is depleted.
    near_morning_high = current_price >= (structure.high_of_day - 0.15 * max(structure.atr_14, 0.01))
    chased_breakout_trap = bool(
        structure.trend_regime == "BEARISH"
        and (structure.in_sell_zone or near_morning_high)
        and (predicted_direction == "BULLISH" or structure.atr_consumed_pct >= 75.0 and predicted_direction == "BULLISH")
    )
    if chased_breakout_trap:
        warnings.append("⚠️ CHASED BREAKOUT TRAP DETECTED - DO NOT GO LONG (FALSE BREAKOUT WARNING - CONTRARIAN TRAP)")
        rationale.append(
            "Price is below the Daily 50-SMA (Bearish regime) and colliding into overhead liquidity (Range/Swing High). "
            "Buying breakouts here requires a Low-of-Day stop with unrealistic ATR reward or gets stopped out on pullbacks."
        )

    # Check Anti-Pattern 2: Exhaustion Overextension
    atr_exhaustion_warning = bool(structure.is_overextended or structure.is_exhausted_multi_atr)
    if atr_exhaustion_warning:
        warnings.append("⚠️ ATR EXHAUSTION - REVERSAL WATCH (Daily ATR Consumed >= 85%)")
        rationale.append(
            f"Asset has consumed {structure.atr_consumed_pct:.1f}% of its Daily ATR (${structure.atr_14:.2f}). "
            "Additional trend continuation in the extended direction is mathematically improbable."
        )

    if not is_target_feasible:
        feasibility_status = "MATHEMATICALLY INVALID / UNREALISTIC REWARD"
        warnings.append(
            f"⚠️ UNREALISTIC REWARD: Forecast move (${predicted_delta:.2f}) exceeds remaining Daily ATR budget (${structure.remaining_atr:.2f})."
        )
    else:
        feasibility_status = "FEASIBLE WITHIN ATR BUDGET"

    # Determine Structural Entry, Stop-Loss, and Take-Profit levels
    structural_entry = round(current_price, 4)
    tick_pad = max(0.02 * structure.atr_14, current_price * 0.0005, 0.01)

    setup_archetype = "NO SETUP / WAIT FOR BOUNDARY"
    setup_side = "NEUTRAL"
    is_valid_trade = False

    # Archetype 1: Topside Compression Reversal (Short Setup)
    # Confluence: Price < 50 SMA + Price in Sell Zone (RH to SH) + ATR Consumed >= 60% + Kronos projects downward mean-reversion
    if (
        structure.trend_regime == "BEARISH"
        and structure.in_sell_zone
        and predicted_direction == "BEARISH"
    ):
        # Stop-Loss placed strictly above Swing High or compression pivot high
        recent_high = float(intraday_5m_df["high"].tail(6).max()) if not intraday_5m_df.empty else current_price
        pivot_cap = max(structure.swing_high, recent_high, current_price + tick_pad)
        structural_stop = round(pivot_cap + tick_pad, 4)
        # Target: Early morning base (low_of_day) or Range Low
        structural_target = round(min(structure.range_low, structure.low_of_day, predicted_target), 4)
        if structural_target >= structural_entry:
            structural_target = round(structural_entry - max(0.6 * structure.atr_14, 3.0 * (structural_stop - structural_entry)), 4)

        if structure.atr_consumed_pct >= 60.0 and is_target_feasible:
            setup_archetype = "TOPSIDE COMPRESSION REVERSAL (SHORT)"
            setup_side = "SHORT"
            is_valid_trade = True
            rationale.append(
                "High-Probability Short Confluence: Bearish 1D 50-SMA bias + testing Upper Liquidity Zone (RH/SH) "
                f"+ {structure.atr_consumed_pct:.1f}% ATR consumed + Kronos projects downward mean-reversion."
            )
        else:
            setup_archetype = "DEVELOPING SHORT REVERSAL (WATCH COMPRESSION)"
            setup_side = "SHORT"
            is_valid_trade = bool(is_target_feasible and total_score >= 70)
            rationale.append(
                "Bearish regime at upper liquidity zone; monitor ATR exhaustion (>=60%) and 5M candle rejection before full execution."
            )

    # Archetype 2: Bullish Dip Reversal / Range Low Bounce (Long Setup)
    # Confluence: Price > 50 SMA + Price in Buy Zone (RL to SL) + Kronos projects upward bounce
    elif (
        structure.trend_regime == "BULLISH"
        and structure.in_buy_zone
        and predicted_direction == "BULLISH"
    ):
        recent_low = float(intraday_5m_df["low"].tail(6).min()) if not intraday_5m_df.empty else current_price
        pivot_floor = min(structure.swing_low, recent_low, current_price - tick_pad)
        structural_stop = round(max(0.01, pivot_floor - tick_pad), 4)
        structural_target = round(max(structure.range_high, structure.swing_high, predicted_target), 4)
        if structural_target <= structural_entry:
            structural_target = round(structural_entry + max(0.6 * structure.atr_14, 3.0 * (structural_entry - structural_stop)), 4)

        if is_target_feasible and not structure.is_exhausted_multi_atr:
            setup_archetype = "BULLISH DIP REVERSAL / RANGE LOW BOUNCE (LONG)"
            setup_side = "LONG"
            is_valid_trade = True
            rationale.append(
                "High-Probability Long Confluence: Bullish 1D 50-SMA bias + testing Lower Liquidity Zone (RL/SL) "
                "+ normal ATR pullback + Kronos projects upward bounce."
            )
        else:
            setup_archetype = "LONG SETUP INVALIDATED (EXCEEDS ATR CAPACITY)"
            setup_side = "NEUTRAL"
            is_valid_trade = False

    # Contrarian or Mid-Range cases
    else:
        if chased_breakout_trap:
            setup_archetype = "INVALID: CHASED BREAKOUT TRAP (DO NOT LONG)"
            setup_side = "NEUTRAL"
            is_valid_trade = False
        elif not trend_matches:
            setup_archetype = f"CONTRARIAN FORECAST VS {structure.trend_regime} 50-SMA (SCALP ONLY / WAIT)"
            setup_side = "NEUTRAL"
            is_valid_trade = False
            rationale.append(
                f"Kronos projects a {predicted_direction} move, which contradicts the Daily 50-SMA ({structure.trend_regime} regime). "
                "3R Rule enforces 80%–90% execution on the trend side."
            )
        elif not is_target_feasible:
            setup_archetype = "INVALID: TARGET EXCEEDS REMAINING DAILY ATR"
            setup_side = "NEUTRAL"
            is_valid_trade = False
        else:
            setup_archetype = "MID-RANGE / AWAITING LIQUIDITY BOUNDARY TEST"
            setup_side = "LONG" if structure.trend_regime == "BULLISH" else "SHORT"
            is_valid_trade = False
            rationale.append(
                "Price is currently between liquidity boundaries. Wait for price to test Range Low/Swing Low (for Longs) "
                "or Range High/Swing High (for Shorts) to keep structural stop tight."
            )

        if structure.trend_regime == "BEARISH":
            structural_stop = round(max(structure.swing_high, current_price + tick_pad) + tick_pad, 4)
            structural_target = round(min(structure.range_low, current_price - 3.0 * (structural_stop - current_price)), 4)
        else:
            structural_stop = round(max(0.01, min(structure.swing_low, current_price - tick_pad) - tick_pad), 4)
            structural_target = round(max(structure.range_high, current_price + 3.0 * (current_price - structural_stop)), 4)

    stop_dist = abs(structural_entry - structural_stop)
    reward_dist = abs(structural_target - structural_entry)
    estimated_rr = round(reward_dist / stop_dist, 2) if stop_dist > 1e-8 else 0.0

    # If R:R is below 3.0 on an otherwise active setup, note the 3R threshold
    if is_valid_trade and estimated_rr < 3.0:
        rationale.append(
            f"Note: Current mid-zone entry offers {estimated_rr:.2f}:1 R:R. Waiting for price closer to Swing pivot improves R:R to >=3.0:1."
        )

    return ConfluenceEvaluation(
        setup_archetype=setup_archetype,
        setup_side=setup_side,
        confluence_score=total_score,
        score_breakdown=score_breakdown,
        predicted_target=round(predicted_target, 4),
        predicted_delta=round(predicted_delta, 4),
        predicted_direction=predicted_direction,
        predicted_return_pct=round(predicted_return_pct, 3),
        is_target_feasible=is_target_feasible,
        feasibility_status=feasibility_status,
        structural_entry=structural_entry,
        structural_stop=structural_stop,
        structural_target=structural_target,
        estimated_rr=estimated_rr,
        is_valid_trade=is_valid_trade,
        chased_breakout_trap=chased_breakout_trap,
        atr_exhaustion_warning=atr_exhaustion_warning,
        warnings=warnings,
        rationale=rationale,
    )


def generate_and_evaluate_forecast(
    predictor: Any,
    intraday_5m_df: pd.DataFrame,
    structure: MarketStructure,
    pred_len: int = 24,
    lookback: int = 256,
    temperature: float = 0.25,
    top_p: float = 0.9,
    sample_count: int = 5,
    normalization_mode: str = "detrend",
    selection_mode: str = "medoid",
) -> Tuple[pd.DataFrame, int, ConfluenceEvaluation]:
    """
    1. Generates autoregressive K-line forecast via `predictor` (`KronosPredictor` or `EnhancedKronosPredictor`).
    2. Validates forecast against 3R structural rules.
    3. Computes confluence score (0-100%) and returns `(pred_df, confluence_score, setup_evaluation)`.
    """
    if intraday_5m_df is None or intraday_5m_df.empty:
        raise ValueError("intraday_5m_df cannot be empty.")

    hist_df = intraday_5m_df.tail(max(16, min(lookback, len(intraday_5m_df)))).reset_index(drop=True)
    if "timestamps" in hist_df.columns:
        x_ts = pd.to_datetime(hist_df["timestamps"])
    else:
        x_ts = pd.Series(pd.date_range("2025-01-01", periods=len(hist_df), freq="5min"))

    if len(x_ts) >= 2:
        step = x_ts.iloc[-1] - x_ts.iloc[-2]
        if step <= pd.Timedelta(0):
            step = pd.Timedelta(minutes=5)
    else:
        step = pd.Timedelta(minutes=5)
    y_ts = pd.Series(pd.date_range(x_ts.iloc[-1] + step, periods=pred_len, freq=step), name="timestamps")

    req_cols = [c for c in ("open", "high", "low", "close", "volume", "amount") if c in hist_df.columns]

    if predictor is not None:
        # Support both EnhancedKronosPredictor and standard KronosPredictor signatures
        try:
            pred_df = predictor.predict(
                df=hist_df[req_cols],
                x_timestamp=x_ts,
                y_timestamp=y_ts,
                pred_len=pred_len,
                T=temperature,
                top_p=top_p,
                sample_count=sample_count,
                normalization_mode=normalization_mode,
                selection_mode=selection_mode,
            )
        except TypeError:
            pred_df = predictor.predict(
                df=hist_df[req_cols],
                x_timestamp=x_ts,
                y_timestamp=y_ts,
                pred_len=pred_len,
                T=temperature,
                top_p=top_p,
                sample_count=sample_count,
            )
    else:
        raise ValueError("A valid Kronos predictor instance is required for inference.")

    evaluation = evaluate_forecast_confluence(
        pred_df=pred_df,
        intraday_5m_df=hist_df,
        structure=structure,
    )
    return pred_df, evaluation.confluence_score, evaluation
