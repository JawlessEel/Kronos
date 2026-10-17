"""
Kronos 3R Rule Trading System Page Package.
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

_PAGE_FILE = Path(__file__).resolve().parent / "3r_trading_system.py"
_spec = spec_from_file_location("webui.pages.three_r_trading_system", _PAGE_FILE)
three_r_module = module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(three_r_module)

register_3r_trading_system = three_r_module.register_3r_trading_system
build_3r_chart_bundle = three_r_module.build_3r_chart_bundle
run_3r_system_evaluation = three_r_module.run_3r_system_evaluation

__all__ = [
    "register_3r_trading_system",
    "build_3r_chart_bundle",
    "run_3r_system_evaluation",
]
