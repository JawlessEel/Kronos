"""
Engine C: Sizing & Capital Scaling Engine ("The Wall Street Raise") for the 3R Rule Trading System.

Eliminates arbitrary monetary stops by deriving exact share/contract sizing from
structural invalidation distance while enforcing a strict dollar risk budget ($20–$50 base).
"""
from typing import Any, Dict, List


def calculate_trade_sizing(
    account_balance: float,
    max_risk_dollars: float,  # e.g., $20 - $50
    entry_price: float,
    structural_stop_price: float,
    target_price: float,
    point_multiplier: float = 1.0,
) -> Dict[str, Any]:
    """
    Calculates structural position sizing so total dollar loss at the structural stop
    never exceeds `max_risk_dollars`.

    Formula:
        Shares / Contracts = floor(max_risk_dollars / (abs(entry_price - structural_stop_price) * point_multiplier))
    """
    account_balance = float(account_balance)
    max_risk_dollars = float(max_risk_dollars)
    entry_price = float(entry_price)
    structural_stop_price = float(structural_stop_price)
    target_price = float(target_price)
    point_multiplier = max(float(point_multiplier), 1e-6)

    if max_risk_dollars <= 0:
        return {"error": "Maximum allowed risk ($) must be greater than zero."}
    if account_balance <= 0:
        return {"error": "Account balance must be greater than zero."}

    stop_distance = abs(entry_price - structural_stop_price)
    reward_distance = abs(target_price - entry_price)

    if stop_distance <= 1e-9:
        return {"error": "Invalid stop price equal to entry"}

    risk_per_unit = stop_distance * point_multiplier
    reward_per_unit = reward_distance * point_multiplier

    position_size = int(max_risk_dollars // risk_per_unit)
    if position_size < 0:
        position_size = 0

    realized_rr = reward_distance / stop_distance
    total_risk_exposure = round(position_size * risk_per_unit, 2)
    projected_profit = round(position_size * reward_per_unit, 2)
    notional_exposure = round(position_size * entry_price * point_multiplier, 2)
    account_risk_pct = round((total_risk_exposure / account_balance) * 100.0, 3) if account_balance > 0 else 0.0

    meets_3r_minimum = bool(realized_rr >= 3.0)

    return {
        "position_size": position_size,
        "stop_distance": round(stop_distance, 4),
        "reward_distance": round(reward_distance, 4),
        "risk_per_unit": round(risk_per_unit, 4),
        "risk_reward_ratio": round(realized_rr, 2),
        "meets_3r_minimum": meets_3r_minimum,
        "max_risk_budget": round(max_risk_dollars, 2),
        "total_risk_exposure": total_risk_exposure,
        "unused_risk_budget": round(max(0.0, max_risk_dollars - total_risk_exposure), 2),
        "projected_profit": projected_profit,
        "notional_exposure": notional_exposure,
        "account_risk_pct": account_risk_pct,
        "trade_direction": "SHORT" if structural_stop_price > entry_price else "LONG",
    }


def evaluate_scaling_eligibility(
    base_balance: float,
    current_balance: float,
    profitable_days_this_week: int,
    consecutive_consistent_weeks: int = 1,
    base_shares: int = 50,
    base_risk_dollars: float = 50.0,
) -> Dict[str, Any]:
    """
    Evaluates trader progress along Doug's 'Wall Street Raise' 10% Scaling Matrix:
    - Consistency prerequisite: At least 3 out of 5 profitable trading days per week.
    - Scaling rule: For every 10% net increase in account balance, scale position size by 10%
      (compounded step ladder: $5,000 -> $5,500 -> $6,050 -> $6,655 -> $7,320.50).
    """
    base_balance = max(float(base_balance), 100.0)
    current_balance = max(float(current_balance), 0.0)
    profitable_days = max(0, min(5, int(profitable_days_this_week)))
    consecutive_weeks = max(0, int(consecutive_consistent_weeks))
    base_shares = max(1, int(base_shares))
    base_risk_dollars = max(5.0, float(base_risk_dollars))

    growth_pct = ((current_balance - base_balance) / base_balance) * 100.0
    consistency_met = bool(profitable_days >= 3 and consecutive_weeks >= 1)

    # Compute how many full 10% compound steps have been achieved
    if current_balance <= base_balance:
        steps_unlocked = 0
    else:
        import math
        steps_unlocked = max(0, int(math.floor(math.log(current_balance / base_balance) / math.log(1.10) + 1e-9)))

    effective_steps = steps_unlocked if consistency_met else 0
    scale_multiplier = (1.10 ** effective_steps)

    recommended_shares = int(round(base_shares * scale_multiplier))
    recommended_risk_min = round(20.0 * scale_multiplier, 2)
    recommended_risk_max = round(base_risk_dollars * scale_multiplier, 2)
    next_milestone_balance = round(base_balance * (1.10 ** (steps_unlocked + 1)), 2)
    dollars_to_next_raise = round(max(0.0, next_milestone_balance - current_balance), 2)

    is_large_account = bool(current_balance >= 300_000.0)
    if is_large_account:
        scaling_note = (
            "Large Account Regime ($300k+): Use fractional account percentage risk (0.25%–0.50% per trade) "
            "rather than full 10% step increments."
        )
    elif not consistency_met:
        scaling_note = (
            f"Consistency Prerequisite Pending ({profitable_days}/5 green days, {consecutive_weeks} wk). "
            "Maintain baseline sizing until achieving >=3/5 profitable days per week."
        )
    elif steps_unlocked >= 4:
        scaling_note = (
            f"Post-30% Acceleration Threshold Unlocked (+{growth_pct:.1f}% growth, Step {steps_unlocked}). "
            "Dynamic scaling active."
        )
    else:
        scaling_note = (
            f"Wall Street Raise Level {effective_steps} Active (+{growth_pct:.1f}% growth). "
            f"Next +10% raise unlocks at ${next_milestone_balance:,.2f}."
        )

    ladder = calculate_wall_street_raise_ladder(
        base_balance=base_balance,
        base_shares=base_shares,
        base_risk_max=base_risk_dollars,
        current_balance=current_balance,
        consistency_met=consistency_met,
    )

    return {
        "base_balance": round(base_balance, 2),
        "current_balance": round(current_balance, 2),
        "growth_pct": round(growth_pct, 2),
        "profitable_days_this_week": profitable_days,
        "consecutive_consistent_weeks": consecutive_weeks,
        "consistency_met": consistency_met,
        "steps_unlocked": steps_unlocked,
        "effective_steps": effective_steps,
        "scale_multiplier": round(scale_multiplier, 4),
        "recommended_shares": recommended_shares,
        "recommended_risk_range": f"${recommended_risk_min:.0f} – ${recommended_risk_max:.0f}",
        "recommended_risk_max": recommended_risk_max,
        "next_milestone_balance": next_milestone_balance,
        "dollars_to_next_raise": dollars_to_next_raise,
        "is_large_account": is_large_account,
        "scaling_note": scaling_note,
        "ladder": ladder,
    }


def calculate_wall_street_raise_ladder(
    base_balance: float = 5000.0,
    base_shares: int = 50,
    base_risk_max: float = 50.0,
    current_balance: float = 5000.0,
    consistency_met: bool = True,
    num_levels: int = 6,
) -> List[Dict[str, Any]]:
    """
    Generates the benchmark 10% scaling matrix table ($5,000 -> $5,500 -> $6,050 -> $6,655 -> $7,320+).
    """
    rows: List[Dict[str, Any]] = []
    base_risk_min = 20.0 * (base_risk_max / 50.0)

    for step in range(num_levels):
        mult = 1.10 ** step
        bal = round(base_balance * mult, 2)
        growth = round((mult - 1.0) * 100.0, 1)
        shares = int(round(base_shares * mult))
        r_min = int(round(base_risk_min * mult))
        r_max = int(round(base_risk_max * mult))

        unlocked = bool(current_balance + 1e-6 >= bal and (step == 0 or consistency_met))
        rows.append({
            "step": step,
            "label": "Base" if step == 0 else (f"Tier {step}" if step < 4 else f"Tier {step} (Accelerate)"),
            "account_balance": bal,
            "growth_from_base_pct": growth,
            "position_sizing_shares": f"{shares} shares",
            "shares_numeric": shares,
            "risk_per_trade": f"${r_min} – ${r_max}",
            "risk_max_numeric": r_max,
            "unlocked": unlocked,
        })
    return rows
