"""
Kronos 3R Rule Trading System Services Package.
Integrates Doug's 3R Structural Trading System with Kronos autoregressive forecasting.
"""
from webui.services.structural_analysis import MarketStructure, StructuralAnalyzer
from webui.services.confluence_engine import (
    ConfluenceEvaluation,
    evaluate_forecast_confluence,
    generate_and_evaluate_forecast,
)
from webui.services.sizing_calculator import (
    calculate_trade_sizing,
    calculate_wall_street_raise_ladder,
    evaluate_scaling_eligibility,
)

__all__ = [
    "MarketStructure",
    "StructuralAnalyzer",
    "ConfluenceEvaluation",
    "evaluate_forecast_confluence",
    "generate_and_evaluate_forecast",
    "calculate_trade_sizing",
    "calculate_wall_street_raise_ladder",
    "evaluate_scaling_eligibility",
]
