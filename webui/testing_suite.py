"""
Tuned Models Registry, Multi-Model Evaluation Suite, Confluence Analyzer,
Options Hub, and PostgreSQL Persistence Blueprint for the Kronos Testing Dashboard.
"""
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import math
import threading
import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.utils import PlotlyJSONEncoder
from flask import Blueprint, jsonify, request
import torch

from webui.db_store import KronosResearchDB, _json_clean
from webui.options_service import (
    fetch_options_chain_analytics,
    fetch_underlying_intelligence,
    validate_equity_ticker,
)
from webui.polygon_feed import FeedError

ROOT = Path(__file__).resolve().parents[1]
FINETUNED_DIR = ROOT / "finetune_csv" / "finetuned"
DATA_DIR = ROOT / "data"
OUTPUTS_DIR = ROOT / "outputs"

# Metadata for our specialized fine-tuned models
TUNED_MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    "SPY_23yr_multi_tf": {
        "name": "SPY 23-Yr Multi-Timeframe (2004–2026)",
        "category": "specialized_23yr",
        "tickers": ["SPY"],
        "timeframes": ["5min", "15min", "1hour", "1day"],
        "normalization_mode": "detrend",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "S&P 500 ETF 23-year multi-timeframe model (5m, 15m, 1h, 1d through Oct 2026)",
        "default_csv": str(DATA_DIR / "spy_multi_timeframe" / "SPY_1hour_2004_2026.csv"),
    },
    "VIX_companion_multi_tf": {
        "name": "VIX Companion Multi-Timeframe (VIX, VIXY, UVXY)",
        "category": "specialized_23yr",
        "tickers": ["I:VIX", "VIXY", "UVXY"],
        "timeframes": ["5min", "15min", "1hour", "1day"],
        "normalization_mode": "standard",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "Volatility Regime Companion model trained on Spot VIX, VIXY, and UVXY (1.79M bars)",
        "default_csv": str(DATA_DIR / "vix_companion" / "INDEX_VIX_1hour_2023_2026.csv"),
    },
    "QQQ_23yr_multi_tf": {
        "name": "QQQ 23-Yr Multi-Timeframe (2004–2026)",
        "category": "specialized_23yr",
        "tickers": ["QQQ"],
        "timeframes": ["5min", "15min", "1hour", "1day"],
        "normalization_mode": "detrend",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "Nasdaq-100 ETF 23-year multi-timeframe model (1.01M bars across 5m/15m/1h/1d)",
        "default_csv": str(DATA_DIR / "qqq_multi_timeframe" / "QQQ_1hour_2004_2026.csv"),
    },
    "IWM_23yr_multi_tf": {
        "name": "IWM 23-Yr Multi-Timeframe (2004–2026)",
        "category": "specialized_23yr",
        "tickers": ["IWM"],
        "timeframes": ["5min", "15min", "1hour", "1day"],
        "normalization_mode": "detrend",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "Russell 2000 Small-Cap ETF 23-year multi-timeframe model (1.19M bars)",
        "default_csv": str(DATA_DIR / "iwm_multi_timeframe" / "IWM_1hour_2004_2026.csv"),
    },
    "NVDA_23yr_multi_tf": {
        "name": "NVDA 23-Yr Multi-Timeframe (2004–2026)",
        "category": "specialized_23yr",
        "tickers": ["NVDA"],
        "timeframes": ["5min", "15min", "1hour", "1day"],
        "normalization_mode": "standard",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "NVIDIA Corp 23-year multi-timeframe semiconductor & AI bellwether model (1.09M bars)",
        "default_csv": str(DATA_DIR / "nvda_multi_timeframe" / "NVDA_1hour_2004_2026.csv"),
    },
    "GME_23yr_multi_tf": {
        "name": "GME 23-Yr Multi-Timeframe (2004–2026)",
        "category": "specialized_23yr",
        "tickers": ["GME"],
        "timeframes": ["5min", "15min", "1hour", "1day"],
        "normalization_mode": "last_price_anchor",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "GameStop 23-year multi-timeframe squeeze & high-volatility equity model (851K bars)",
        "default_csv": str(DATA_DIR / "gme_multi_timeframe" / "GME_1hour_2004_2026.csv"),
    },
    "MACRO_TLT_GLD_23yr_multi_tf": {
        "name": "Macro Rates & Gold (TLT + GLD 23-Yr Multi-TF)",
        "category": "specialized_23yr",
        "tickers": ["TLT", "GLD"],
        "timeframes": ["5min", "15min", "1hour", "1day"],
        "normalization_mode": "last_price_anchor",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "20+ Year Treasury Bond (TLT) & Gold (GLD) 23-year macro companion model (2.06M bars)",
        "default_csv": str(DATA_DIR / "macro_tlt_gld_multi_timeframe" / "TLT_1hour_2004_2026.csv"),
    },
    "SPY_20yr_multi_timeframe": {
        "name": "SPY 20-Yr Multi-Timeframe (2004–2024)",
        "category": "specialized_legacy",
        "tickers": ["SPY"],
        "timeframes": ["5min", "15min", "1hour", "1day"],
        "normalization_mode": "detrend",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "Pre-2025 held-out SPY 20-year multi-timeframe model",
        "default_csv": str(DATA_DIR / "spy_multi_timeframe" / "SPY_1hour_2004_2026.csv"),
    },
    "SPY_5min_intraday": {
        "name": "SPY 5-Min Intraday Specialist",
        "category": "specialized_legacy",
        "tickers": ["SPY"],
        "timeframes": ["5min"],
        "normalization_mode": "last_price_anchor",
        "context_length": 512,
        "params": "102.3M (Tuned)",
        "description": "Dedicated 5-minute intraday microstructure specialist for SPY",
        "default_csv": str(DATA_DIR / "spy_multi_timeframe" / "SPY_5min_2004_2026.csv"),
    },
}

TICKER_TO_MODEL_MAP: Dict[str, Dict[str, Any]] = {
    "SPY": {
        "model_key": "SPY_23yr_multi_tf",
        "normalization_mode": "detrend",
        "data_subdir": "spy_multi_timeframe",
        "file_prefix": "SPY",
        "span_years": "2004_2026",
    },
    "QQQ": {
        "model_key": "QQQ_23yr_multi_tf",
        "normalization_mode": "detrend",
        "data_subdir": "qqq_multi_timeframe",
        "file_prefix": "QQQ",
        "span_years": "2004_2026",
    },
    "IWM": {
        "model_key": "IWM_23yr_multi_tf",
        "normalization_mode": "detrend",
        "data_subdir": "iwm_multi_timeframe",
        "file_prefix": "IWM",
        "span_years": "2004_2026",
    },
    "NVDA": {
        "model_key": "NVDA_23yr_multi_tf",
        "normalization_mode": "standard",
        "data_subdir": "nvda_multi_timeframe",
        "file_prefix": "NVDA",
        "span_years": "2004_2026",
    },
    "GME": {
        "model_key": "GME_23yr_multi_tf",
        "normalization_mode": "last_price_anchor",
        "data_subdir": "gme_multi_timeframe",
        "file_prefix": "GME",
        "span_years": "2004_2026",
    },
    "TLT": {
        "model_key": "MACRO_TLT_GLD_23yr_multi_tf",
        "normalization_mode": "standard",
        "data_subdir": "macro_tlt_gld_multi_timeframe",
        "file_prefix": "TLT",
        "span_years": "2004_2026",
    },
    "GLD": {
        "model_key": "MACRO_TLT_GLD_23yr_multi_tf",
        "normalization_mode": "last_price_anchor",
        "data_subdir": "macro_tlt_gld_multi_timeframe",
        "file_prefix": "GLD",
        "span_years": "2004_2026",
    },
    "VIXY": {
        "model_key": "VIX_companion_multi_tf",
        "normalization_mode": "standard",
        "data_subdir": "vix_companion",
        "file_prefix": "VIXY",
        "span_years": "2011_2026",
    },
    "UVXY": {
        "model_key": "VIX_companion_multi_tf",
        "normalization_mode": "standard",
        "data_subdir": "vix_companion",
        "file_prefix": "UVXY",
        "span_years": "2011_2026",
    },
    "I:VIX": {
        "model_key": "VIX_companion_multi_tf",
        "normalization_mode": "standard",
        "data_subdir": "vix_companion",
        "file_prefix": "INDEX_VIX",
        "span_years": "2023_2026",
    },
}


def resolve_local_dataset_csv(ticker: str, timeframe: str = "1hour") -> Optional[Path]:
    t = ticker.strip().upper()
    tf = timeframe.strip().lower()
    if tf not in ("5min", "15min", "1hour", "1day"):
        tf = "1hour"
    spec = TICKER_TO_MODEL_MAP.get(t)
    if spec:
        candidate = DATA_DIR / spec["data_subdir"] / f"{spec['file_prefix']}_{tf}_{spec['span_years']}.csv"
        if candidate.is_file():
            return candidate
    # Fallback search in data subfolders
    clean_t = t.replace("I:", "INDEX_")
    for p in DATA_DIR.rglob(f"{clean_t}_{tf}*.csv"):
        return p
    return None


def discover_and_register_models(ui_module, db: KronosResearchDB) -> List[Dict[str, Any]]:
    """
    Discovers all fine-tuned checkpoints under `finetune_csv/finetuned/`,
    adds them to `ui.AVAILABLE_MODELS`, and seeds the PostgreSQL registry with factory & benchmark stats.
    """
    factory_status_path = OUTPUTS_DIR / "model_factory_status.json"
    factory_data = {}
    if factory_status_path.is_file():
        try:
            factory_data = json.loads(factory_status_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    bench_path = OUTPUTS_DIR / "spy_vix_confluence_benchmark" / "confluence_benchmark_summary.json"
    bench_map: Dict[str, Dict[str, Any]] = {}
    if bench_path.is_file():
        try:
            b_json = json.loads(bench_path.read_text(encoding="utf-8"))
            for row in b_json.get("single_model_suite", []):
                m_key = row.get("model")
                if m_key and m_key not in bench_map:
                    bench_map[m_key] = row
        except Exception:
            pass

    discovered: List[Dict[str, Any]] = []
    if FINETUNED_DIR.is_dir():
        for model_folder in sorted(FINETUNED_DIR.iterdir()):
            if not model_folder.is_dir():
                continue
            model_key = model_folder.name
            base_best = model_folder / "basemodel" / "best_model"
            tok_best = model_folder / "tokenizer" / "best_model"
            if not (base_best / "model.safetensors").is_file() or not (tok_best / "model.safetensors").is_file():
                continue

            meta = TUNED_MODEL_CATALOG.get(model_key, {
                "name": model_key,
                "category": "specialized_custom",
                "tickers": [model_key.split("_")[0]],
                "timeframes": ["5min", "15min", "1hour", "1day"],
                "normalization_mode": "detrend",
                "context_length": 512,
                "params": "102.3M (Tuned)",
                "description": f"Fine-tuned Kronos model ({model_key})",
            })

            ds_info = (factory_data.get("datasets") or {}).get(model_key) or {}
            total_bars = int(ds_info.get("total_bars") or 0)
            if total_bars == 0 and model_key == "SPY_23yr_multi_tf":
                total_bars = 1236150
            train_status = (factory_data.get("models_status") or {}).get(model_key, "COMPLETED")
            b_stats = bench_map.get(model_key, {})

            entry = {
                "model_key": model_key,
                "name": meta["name"],
                "category": meta["category"],
                "tickers": meta["tickers"],
                "timeframes": meta["timeframes"],
                "normalization_mode": meta["normalization_mode"],
                "context_length": meta["context_length"],
                "params": meta["params"],
                "description": meta["description"],
                "model_id": str(base_best),
                "tokenizer_id": str(tok_best),
                "total_training_bars": total_bars,
                "training_status": train_status,
                "benchmark_accuracy_pct": b_stats.get("accuracy_pct"),
                "benchmark_mae": b_stats.get("avg_mae"),
                "benchmark_mape_pct": b_stats.get("avg_mape_pct"),
                "default_csv": meta.get("default_csv", ""),
            }
            discovered.append(entry)

            # Register into ui.AVAILABLE_MODELS so standard /api/load-model works seamlessly!
            ui_module.AVAILABLE_MODELS[model_key] = {
                "name": meta["name"],
                "model_id": str(base_best),
                "tokenizer_id": str(tok_best),
                "context_length": meta["context_length"],
                "params": meta["params"],
                "description": meta["description"],
                "category": meta["category"],
                "tickers": meta["tickers"],
                "normalization_mode": meta["normalization_mode"],
            }

            try:
                db.upsert_tuned_model(entry)
            except Exception as e:
                print(f"[TestingSuite] Warning: Could not upsert model {model_key} to Postgres: {e}")

    return discovered


def seed_initial_benchmarks_to_db(db: KronosResearchDB) -> None:
    """Seeds existing out-of-sample benchmark runs into Postgres if `model_backtest_runs` is empty."""
    if not db.ready and not db.ensure_schema():
        return
    try:
        summary = db.get_database_summary(limit=1)
        if (summary.get("counts") or {}).get("model_backtest_runs", 0) > 0:
            return
        bench_path = OUTPUTS_DIR / "spy_vix_confluence_benchmark" / "confluence_benchmark_summary.json"
        if not bench_path.is_file():
            return
        b_data = json.loads(bench_path.read_text(encoding="utf-8"))

        # Seed SPY + Spot VIX Confluence run
        spot_vix = b_data.get("confluence_spot_vix")
        if spot_vix:
            db.save_backtest_run({
                "ticker": "SPY",
                "model_key": "SPY_23yr_multi_tf",
                "companion_model_key": "VIX_companion_multi_tf (I:VIX)",
                "timeframe": "1hour",
                "lookback": 256,
                "horizon": 24,
                "num_windows": spot_vix.get("total_windows", 29),
                "normalization_mode": "detrend",
                "selection_mode": "medoid",
                "total_valid_windows": spot_vix.get("total_windows", 29),
                "direction_hits": spot_vix.get("unfiltered_hits", 19),
                "direction_accuracy_pct": round(float(spot_vix.get("unfiltered_accuracy", 65.5)), 2),
                "avg_mae": round(float(spot_vix.get("unfiltered_avg_mae", 4.35)), 4),
                "p_value": round(float(spot_vix.get("confirmed_p_value", 0.0176)), 4),
                "confirmed_trades": spot_vix.get("confirmed_trades", 15),
                "confirmed_hits": spot_vix.get("confirmed_hits", 12),
                "confirmed_accuracy_pct": round(float(spot_vix.get("confirmed_accuracy", 80.0)), 2),
                "windows": spot_vix.get("records", []),
                "notes": "Out-of-Sample 2026 Benchmark: Dual-Model SPY (23-Yr) + Spot VIX (I:VIX) 1-Hour Swing",
            })

        # Seed SPY + VIXY Confluence run
        vixy_res = b_data.get("confluence_vixy")
        if vixy_res:
            db.save_backtest_run({
                "ticker": "SPY",
                "model_key": "SPY_23yr_multi_tf",
                "companion_model_key": "VIX_companion_multi_tf (VIXY)",
                "timeframe": "1hour",
                "lookback": 256,
                "horizon": 24,
                "num_windows": vixy_res.get("total_windows", 30),
                "normalization_mode": "detrend",
                "selection_mode": "medoid",
                "total_valid_windows": vixy_res.get("total_windows", 30),
                "direction_hits": vixy_res.get("unfiltered_hits", 17),
                "direction_accuracy_pct": round(float(vixy_res.get("unfiltered_accuracy", 56.7)), 2),
                "avg_mae": round(float(vixy_res.get("unfiltered_avg_mae", 4.18)), 4),
                "p_value": round(float(vixy_res.get("confirmed_p_value", 0.0717)), 4),
                "confirmed_trades": vixy_res.get("confirmed_trades", 17),
                "confirmed_hits": vixy_res.get("confirmed_hits", 12),
                "confirmed_accuracy_pct": round(float(vixy_res.get("confirmed_accuracy", 70.6)), 2),
                "windows": vixy_res.get("records", []),
                "notes": "Out-of-Sample 2026 Benchmark: Dual-Model SPY (23-Yr) + VIXY ETF 1-Hour Swing",
            })

        # Seed single model suite runs
        for item in b_data.get("single_model_suite", []):
            lbl = item.get("label", item.get("model", ""))
            tkr = "GLD" if "(GLD)" in lbl else "TLT" if "(TLT)" in lbl else lbl.split("_")[0]
            norm = TICKER_TO_MODEL_MAP.get(tkr, {}).get("normalization_mode", "detrend")
            db.save_backtest_run({
                "ticker": tkr,
                "model_key": item.get("model", ""),
                "companion_model_key": None,
                "timeframe": "1hour",
                "lookback": 256,
                "horizon": 24,
                "num_windows": item.get("total", 25),
                "normalization_mode": norm,
                "selection_mode": "medoid",
                "total_valid_windows": item.get("total", 25),
                "direction_hits": item.get("hits", 0),
                "direction_accuracy_pct": item.get("accuracy_pct", 0.0),
                "avg_mae": item.get("avg_mae"),
                "avg_mape_pct": item.get("avg_mape_pct"),
                "notes": f"Held-out 2026 1-Hour Evaluation Suite ({lbl})",
            })
    except Exception as e:
        print(f"[TestingSuite] Warning seeding initial benchmarks: {e}")


def calc_binomial_pval(k: int, n: int, p: float = 0.5) -> float:
    if n <= 0 or k <= 0:
        return 1.0
    return float(sum(math.comb(n, i) * (p ** i) * ((1.0 - p) ** (n - i)) for i in range(k, n + 1)))


def calc_wilson_95_ci(k: int, n: int) -> tuple[float, float]:
    """Computes 95% Wilson score confidence interval (in %) for directional hit rate k/n."""
    if n <= 0:
        return (0.0, 0.0)
    z = 1.95996
    phat = max(0.0, min(1.0, k / n))
    denom = 1.0 + (z * z) / n
    center = (phat + (z * z) / (2.0 * n)) / denom
    half = (z * math.sqrt((phat * (1.0 - phat) + (z * z) / (4.0 * n)) / n)) / denom
    return (round(max(0.0, (center - half) * 100.0), 1), round(min(100.0, (center + half) * 100.0), 1))


def register_testing_suite(app, ui_module, live_feed=None) -> KronosResearchDB:
    """Registers all `/api/testing/*` routes on the Flask app and initializes PostgreSQL storage."""
    db = KronosResearchDB()
    db.ensure_schema()
    discovered_models = discover_and_register_models(ui_module, db)
    seed_initial_benchmarks_to_db(db)

    suite_bp = Blueprint("testing_suite", __name__)
    model_cache: Dict[str, Any] = {}
    suite_lock = threading.Lock()

    def _get_device() -> str:
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def _load_enhanced_predictor(model_key: str):
        from model import Kronos, KronosTokenizer
        from model.enhanced_predictor import EnhancedKronosPredictor

        if model_key in model_cache:
            return model_cache[model_key]
        if model_key not in ui_module.AVAILABLE_MODELS:
            raise FeedError(f"Unknown model key: {model_key}", 400)
        cfg = ui_module.AVAILABLE_MODELS[model_key]
        device = _get_device()
        tok = KronosTokenizer.from_pretrained(cfg["tokenizer_id"])
        mdl = Kronos.from_pretrained(cfg["model_id"])
        tok.eval()
        mdl.eval()
        pred = EnhancedKronosPredictor(mdl, tok, device=device, max_context=cfg.get("context_length", 512))
        if len(model_cache) >= 3:
            model_cache.clear()
        model_cache[model_key] = pred
        return pred

    def _normalize_ts_series(series: pd.Series) -> pd.Series:
        ts = pd.to_datetime(series)
        if getattr(ts.dt, "tz", None) is not None:
            ts = ts.dt.tz_convert("UTC").dt.tz_localize(None)
        return ts

    @suite_bp.errorhandler(FeedError)
    def handle_feed_error(err: FeedError):
        return jsonify(error=str(err)), err.status

    @suite_bp.errorhandler(Exception)
    def handle_unexpected_error(err: Exception):
        if isinstance(err, FeedError):
            return jsonify(error=str(err)), err.status
        return jsonify(error=f"{type(err).__name__}: {err}"), 500

    @suite_bp.get("/api/testing/overview")
    def overview():
        """Returns complete overview of tuned models, benchmark scoreboard, dataset inventory, and Postgres counts."""
        factory_status_path = OUTPUTS_DIR / "model_factory_status.json"
        factory_status = {}
        if factory_status_path.is_file():
            try:
                factory_status = json.loads(factory_status_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        bench_path = OUTPUTS_DIR / "spy_vix_confluence_benchmark" / "confluence_benchmark_summary.json"
        benchmarks = {}
        if bench_path.is_file():
            try:
                benchmarks = json.loads(bench_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        db_summary = db.get_database_summary(limit=15)
        return jsonify({
            "success": True,
            "tuned_models": discovered_models,
            "ticker_map": TICKER_TO_MODEL_MAP,
            "factory_status": factory_status,
            "benchmarks": benchmarks,
            "database": db_summary,
            "accelerator": _get_device(),
        })

    @suite_bp.post("/api/testing/underlying")
    def analyze_underlying():
        """Fetches underlying snapshot, fundamentals, daily technicals (RSI/SMA/EMA/MACD), and news from Polygon and saves to Postgres."""
        body = request.get_json(silent=True) or {}
        ticker = validate_equity_ticker(body.get("ticker", "SPY"))
        save_to_db = bool(body.get("save_to_db", True))

        intel = fetch_underlying_intelligence(ticker)
        row_id = None
        if save_to_db:
            try:
                row_id = db.save_underlying_snapshot(intel)
            except Exception as e:
                intel["db_warning"] = str(e)
        intel["saved_snapshot_id"] = row_id
        return jsonify({"success": True, "underlying": _json_clean(intel)})

    @suite_bp.post("/api/testing/options-chain")
    def analyze_options_chain():
        """Fetches live options chain from Polygon, computes P/C ratios, Max Pain, GEX, IV Smile, and saves to Postgres."""
        body = request.get_json(silent=True) or {}
        ticker = validate_equity_ticker(body.get("ticker", "SPY"))
        expiration_date = body.get("expiration_date") or None
        strike_window_pct = float(body.get("strike_window_pct", 0.12))
        max_days_out = int(body.get("max_days_out", 45))
        save_to_db = bool(body.get("save_to_db", True))

        strike_window_pct = max(0.03, min(0.35, strike_window_pct))
        max_days_out = max(1, min(180, max_days_out))

        summary, contracts, charts = fetch_options_chain_analytics(
            ticker=ticker,
            expiration_date=expiration_date,
            strike_window_pct=strike_window_pct,
            max_days_out=max_days_out,
        )
        snap_id = None
        if save_to_db and contracts:
            try:
                snap_id = db.save_options_snapshot(summary, contracts)
            except Exception as e:
                summary["db_warning"] = str(e)
        summary["saved_snapshot_id"] = snap_id
        return jsonify({
            "success": True,
            "summary": _json_clean(summary),
            "charts": charts,
            "contracts_stored": len(contracts) if snap_id else 0,
        })

    @suite_bp.post("/api/testing/run-analysis")
    def run_ticker_analysis():
        """
        Runs EnhancedKronosPredictor on a tuned ticker (using either local multi-timeframe dataset or live Polygon candles),
         optionally runs VIX Companion confluence confirmation, generates interactive trajectory + volatility envelope chart,
        and persists the run to PostgreSQL.
        """
        body = request.get_json(silent=True) or {}
        ticker = str(body.get("ticker", "SPY")).strip().upper()
        timeframe = str(body.get("timeframe", "1hour")).strip().lower()
        data_source = str(body.get("data_source", "local")).strip().lower()  # 'local' or 'live'
        lookback = max(32, min(512, int(body.get("lookback", 256))))
        pred_len = max(4, min(120, int(body.get("pred_len", 24))))
        temperature = max(0.05, min(1.5, float(body.get("temperature", 0.25))))
        top_p = max(0.1, min(1.0, float(body.get("top_p", 0.9))))
        sample_count = max(1, min(15, int(body.get("sample_count", 5))))
        eval_mode = str(body.get("eval_mode", "held_out")).strip().lower()  # 'held_out' (compare vs actuals) or 'future'
        window_offset = max(0, int(body.get("window_offset", 1)))
        include_confluence = bool(body.get("include_confluence", True))
        companion_symbol = str(body.get("companion_symbol", "I:VIX")).strip().upper()

        spec = TICKER_TO_MODEL_MAP.get(ticker, TICKER_TO_MODEL_MAP["SPY"])
        model_key = body.get("model_key") or spec["model_key"]
        norm_mode = body.get("normalization_mode") or spec["normalization_mode"]
        selection_mode = body.get("selection_mode") or "medoid"

        tf_to_minutes = {"5min": 5, "15min": 15, "1hour": 60, "1day": 1440}
        interval_minutes = tf_to_minutes.get(timeframe, 60)

        t_start = time.perf_counter()
        with suite_lock:
            predictor = _load_enhanced_predictor(model_key)

            actual_df = None
            source_provenance = "LOCAL_23YR_RESEARCH_CSV"
            if data_source == "live" and live_feed is not None:
                df_live, _ = live_feed.candles(ticker, interval_minutes, max(400, lookback + pred_len))
                df_all = df_live.copy()
                df_all["timestamps"] = _normalize_ts_series(df_all["timestamps"])
                source_provenance = "POLYGON_LIVE_FEED"
            else:
                csv_path = resolve_local_dataset_csv(ticker, timeframe)
                if not csv_path or not csv_path.is_file():
                    raise FeedError(f"Local dataset not found for {ticker} ({timeframe}).", 404)
                df_all = pd.read_csv(csv_path, parse_dates=["timestamps"]).tail(5000).reset_index(drop=True)
                df_all["timestamps"] = _normalize_ts_series(df_all["timestamps"])

            if eval_mode == "held_out" and len(df_all) >= lookback + pred_len * max(1, window_offset):
                end_idx = len(df_all) - (pred_len * max(1, window_offset))
                hist_df = df_all.iloc[end_idx - lookback : end_idx].reset_index(drop=True)
                actual_df = df_all.iloc[end_idx : end_idx + pred_len].reset_index(drop=True)
                x_ts = hist_df["timestamps"]
                y_ts = actual_df["timestamps"]
            else:
                hist_df = df_all.tail(lookback).reset_index(drop=True)
                x_ts = hist_df["timestamps"]
                from webui.polygon_feed import future_timestamps
                try:
                    last_ts = pd.Timestamp(x_ts.iloc[-1])
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.tz_localize("UTC")
                    y_ts = future_timestamps(last_ts, interval_minutes, pred_len, ticker).dt.tz_localize(None)
                except Exception:
                    step = pd.Timedelta(minutes=interval_minutes)
                    y_ts = pd.Series(pd.date_range(x_ts.iloc[-1] + step, periods=pred_len, freq=step), name="timestamps")

            req_cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in hist_df.columns]
            pred_df = predictor.predict(
                df=hist_df[req_cols],
                x_timestamp=x_ts,
                y_timestamp=y_ts,
                pred_len=pred_len,
                T=temperature,
                top_p=top_p,
                sample_count=sample_count,
                normalization_mode=norm_mode,
                selection_mode=selection_mode,
            )

            last_close = float(hist_df["close"].iloc[-1])
            pred_close = float(pred_df["close"].iloc[-1])
            pred_ret_pct = (pred_close / last_close - 1.0) * 100.0
            pred_high = float(pred_df["high"].max())
            pred_low = float(pred_df["low"].min())
            env_high_max = float(pred_df["env_high"].max()) if "env_high" in pred_df.columns else pred_high
            env_low_min = float(pred_df["env_low"].min()) if "env_low" in pred_df.columns else pred_low

            # Optional Companion Confluence (VIX Companion for equity/index models, or TLT/GLD for macro)
            confluence_info = None
            vix_pred_df = None
            vix_hist_df = None
            vix_actual_df = None
            if include_confluence and companion_symbol != "NONE" and "VIX_companion_multi_tf" in ui_module.AVAILABLE_MODELS:
                vix_raw = None
                if data_source == "live" and live_feed is not None:
                    for try_sym in ([companion_symbol, "VIXY"] if companion_symbol == "I:VIX" else [companion_symbol]):
                        try:
                            v_live, _ = live_feed.candles(try_sym, interval_minutes, max(400, lookback + pred_len))
                            if v_live is not None and len(v_live) >= 64:
                                vix_raw = v_live.copy()
                                vix_raw["timestamps"] = _normalize_ts_series(vix_raw["timestamps"])
                                break
                        except Exception:
                            continue
                if vix_raw is None:
                    vix_csv = resolve_local_dataset_csv(companion_symbol, timeframe)
                    if vix_csv and vix_csv.is_file():
                        vix_raw = pd.read_csv(vix_csv, parse_dates=["timestamps"]).tail(6000)
                        vix_raw["timestamps"] = _normalize_ts_series(vix_raw["timestamps"])

                if vix_raw is not None and not vix_raw.empty:
                    # Align timestamps with hist_df
                    merged_hist = pd.merge(
                        hist_df[["timestamps"]], vix_raw, on="timestamps", how="inner"
                    ).sort_values("timestamps").reset_index(drop=True)
                    if len(merged_hist) < 64 and len(vix_raw) >= len(hist_df):
                        merged_hist = vix_raw.tail(len(hist_df)).reset_index(drop=True).copy()
                        merged_hist["timestamps"] = hist_df["timestamps"].values
                    if len(merged_hist) >= 64:
                        vix_predictor = _load_enhanced_predictor("VIX_companion_multi_tf")
                        vix_cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in merged_hist.columns]
                        vix_pred_df = vix_predictor.predict(
                            df=merged_hist[vix_cols],
                            x_timestamp=merged_hist["timestamps"],
                            y_timestamp=y_ts.reset_index(drop=True),
                            pred_len=pred_len,
                            T=temperature,
                            top_p=top_p,
                            sample_count=sample_count,
                            normalization_mode="standard",
                            selection_mode="medoid",
                        )
                        vix_hist_df = merged_hist
                        vix_last = float(merged_hist["close"].iloc[-1])
                        vix_fut = float(vix_pred_df["close"].iloc[-1])
                        vix_ret_pct = (vix_fut / vix_last - 1.0) * 100.0

                        if pred_ret_pct > 0.05 and vix_ret_pct < -0.10:
                            sig = "HIGH_CONVICTION_BULL"
                            confirmed = True
                        elif pred_ret_pct < -0.05 and vix_ret_pct > 0.10:
                            sig = "HIGH_CONVICTION_BEAR"
                            confirmed = True
                        else:
                            sig = "CONFLICT_STAND_ASIDE"
                            confirmed = False

                        if confirmed:
                            raw_sc = min(1.0, (abs(pred_ret_pct) / 0.25) * 0.5 + (abs(vix_ret_pct) / 1.5) * 0.5)
                            conv_score = round(float(np.clip(raw_sc, 0.1, 1.0)), 3)
                        else:
                            conv_score = 0.0

                        confluence_info = {
                            "companion_symbol": companion_symbol,
                            "vix_last_close": round(vix_last, 3),
                            "vix_pred_close": round(vix_fut, 3),
                            "vix_return_pct": round(vix_ret_pct, 2),
                            "signal": sig,
                            "is_confirmed": confirmed,
                            "conviction_score": conv_score,
                        }

        inference_ms = round((time.perf_counter() - t_start) * 1000.0, 1)

        # Error metrics & Naive Random-Walk baseline comparison if held-out actual_df exists
        mae = rmse = mape_pct = actual_ret_pct = naive_mae = mae_skill_pct = None
        direction_hit = None
        if actual_df is not None and len(actual_df) == len(pred_df):
            act_closes = actual_df["close"].to_numpy()
            errs = np.abs(pred_df["close"].to_numpy() - act_closes)
            naive_errs = np.abs(act_closes - last_close)
            mae = round(float(np.mean(errs)), 4)
            naive_mae = round(float(np.mean(naive_errs)), 4)
            mae_skill_pct = round(float((1.0 - mae / max(1e-6, naive_mae)) * 100.0), 1)
            rmse = round(float(np.sqrt(np.mean(errs ** 2))), 4)
            mape_pct = round(float(np.mean(errs / act_closes) * 100.0), 3)
            actual_ret_pct = round((float(actual_df["close"].iloc[-1]) / last_close - 1.0) * 100.0, 2)
            direction_hit = bool(np.sign(pred_ret_pct) == np.sign(actual_ret_pct))

        # Build rich TradingView-style gapless Plotly chart (with Volatility Envelope + Optional VIX Companion subplot)
        has_vix_subplot = vix_pred_df is not None and vix_hist_df is not None
        sig_label = str(confluence_info["signal"]).replace("_", " ") if confluence_info else ""
        if has_vix_subplot:
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.13,
                row_heights=[0.65, 0.35],
                subplot_titles=(
                    f"{ticker} ({timeframe})  •  Model: {model_key}  |  Norm: {norm_mode} ({selection_mode})",
                    f"Companion Volatility Forecast ({companion_symbol})  •  Confluence: {sig_label}"
                )
            )
        else:
            fig = make_subplots(
                rows=1, cols=1,
                subplot_titles=(f"{ticker} ({timeframe})  •  Model: {model_key}  |  Norm: {norm_mode} ({selection_mode})",)
            )

        def _fmt_ts(series_or_list) -> List[str]:
            out = []
            for val in series_or_list:
                ts = pd.Timestamp(val)
                if timeframe == "1day":
                    out.append(ts.strftime("%Y-%m-%d"))
                else:
                    out.append(ts.strftime("%b %d %H:%M"))
            return out

        disp_hist = hist_df.tail(min(220, len(hist_df))).reset_index(drop=True)
        hist_x = _fmt_ts(disp_hist["timestamps"])
        fut_x = _fmt_ts(y_ts)
        # Ensure unique ordered category labels
        all_x = list(dict.fromkeys(hist_x + fut_x))

        fig.add_trace(
            go.Candlestick(
                x=hist_x,
                open=disp_hist["open"], high=disp_hist["high"],
                low=disp_hist["low"], close=disp_hist["close"],
                name=f"{ticker} History",
                increasing_line_color="#00f5d4", decreasing_line_color="#ff2a85",
                increasing_fillcolor="rgba(0, 245, 212, 0.78)", decreasing_fillcolor="rgba(255, 42, 133, 0.78)",
            ),
            row=1, col=1
        )

        # Volatility envelope band
        if "env_high" in pred_df.columns and "env_low" in pred_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=fut_x + fut_x[::-1],
                    y=list(pred_df["env_high"]) + list(pred_df["env_low"])[::-1],
                    fill="toself",
                    fillcolor="rgba(0, 245, 212, 0.13)",
                    line=dict(color="rgba(0, 245, 212, 0.45)", width=1),
                    name=f"Probabilistic Envelope ({sample_count} paths)",
                    hoverinfo="skip",
                ),
                row=1, col=1
            )

        fig.add_trace(
            go.Candlestick(
                x=fut_x,
                open=pred_df["open"], high=pred_df["high"],
                low=pred_df["low"], close=pred_df["close"],
                name=f"Kronos Medoid Forecast ({pred_len} bars)",
                increasing_line_color="#00bbf9", decreasing_line_color="#d946ef",
                increasing_fillcolor="rgba(0, 187, 249, 0.82)", decreasing_fillcolor="rgba(217, 70, 239, 0.82)",
            ),
            row=1, col=1
        )

        if actual_df is not None and not actual_df.empty:
            act_x = _fmt_ts(actual_df["timestamps"])
            fig.add_trace(
                go.Scatter(
                    x=act_x,
                    y=actual_df["close"],
                    mode="lines+markers",
                    name="Realized Actual Close",
                    line=dict(color="#fcee09", width=2.4, dash="dot"),
                    marker=dict(size=5, color="#fcee09"),
                ),
                row=1, col=1
            )

        if has_vix_subplot:
            left_ts = pd.DataFrame({"timestamps": pd.to_datetime(disp_hist["timestamps"]).dt.tz_localize(None)})
            right_vix = vix_hist_df[["timestamps", "close"]].copy()
            right_vix["timestamps"] = pd.to_datetime(right_vix["timestamps"]).dt.tz_localize(None)
            right_vix = right_vix.sort_values("timestamps").reset_index(drop=True)
            aligned_vix = pd.merge_asof(
                left_ts.sort_values("timestamps"),
                right_vix,
                on="timestamps",
                direction="backward",
            )
            aligned_vix["close"] = aligned_vix["close"].bfill().ffill()
            vix_hist_x = hist_x
            vix_hist_y = [float(v) for v in aligned_vix["close"]]
            # Connect last history point to first forecast point smoothly
            conn_x = ([vix_hist_x[-1]] if vix_hist_x else []) + fut_x
            conn_y = ([vix_hist_y[-1]] if vix_hist_y else []) + [float(v) for v in vix_pred_df["close"]]
            fig.add_trace(
                go.Scatter(
                    x=vix_hist_x, y=vix_hist_y,
                    mode="lines", name=f"{companion_symbol} History",
                    line=dict(color="#94a3b8", width=1.9),
                ),
                row=2, col=1
            )
            fig.add_trace(
                go.Scatter(
                    x=conn_x, y=conn_y,
                    mode="lines+markers", name=f"{companion_symbol} Forecast ({confluence_info['vix_return_pct']:+.2f}%)",
                    line=dict(color="#ff2a85" if confluence_info["vix_return_pct"] > 0 else "#00f5d4", width=2.5),
                    marker=dict(size=5),
                ),
                row=2, col=1
            )

        # Evenly spaced readable X-axis ticks across all_x
        total_bars = len(all_x)
        tick_step = max(1, total_bars // 9)
        tick_vals = [all_x[i] for i in range(0, total_bars, tick_step)]
        focus_start = max(0, len(hist_x) - 75)
        focus_end = total_bars - 1 + 1.5

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0c0e1a",
            plot_bgcolor="#080a12",
            font=dict(color="#e2e8f0", family="Inter, system-ui, sans-serif"),
            height=680 if has_vix_subplot else 540,
            dragmode="pan",
            hovermode="x unified",
            xaxis_rangeslider_visible=False,
            xaxis2_rangeslider_visible=False if has_vix_subplot else None,
            margin=dict(l=82, r=36, t=64, b=118),
            legend=dict(
                orientation="h",
                y=-0.16 if has_vix_subplot else -0.22,
                yanchor="top",
                x=0.0,
                xanchor="left",
                font=dict(size=11.5),
            ),
        )
        fig.update_annotations(font=dict(size=12.5, color="#00f5d4"))
        fig.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=all_x,
            tickmode="array",
            tickvals=tick_vals,
            ticktext=tick_vals,
            tickangle=0,
            range=[focus_start, focus_end],
            automargin=True,
            showspikes=True,
            spikemode="across",
            spikesnap="cursor",
            spikecolor="rgba(0, 245, 212, 0.45)",
            spikethickness=1,
            gridcolor="rgba(0, 245, 212, 0.08)",
            zerolinecolor="rgba(0, 245, 212, 0.15)",
        )
        fig.update_yaxes(
            fixedrange=False,
            automargin=True,
            title_standoff=10,
            showspikes=True,
            spikemode="across",
            spikecolor="rgba(255, 42, 133, 0.4)",
            spikethickness=1,
            gridcolor="rgba(0, 245, 212, 0.08)",
            zerolinecolor="rgba(0, 245, 212, 0.15)",
        )
        fig.update_yaxes(title_text=f"{ticker} Price ($)", row=1, col=1)
        if has_vix_subplot:
            fig.update_xaxes(showticklabels=False, title_text="", row=1, col=1)
            fig.update_yaxes(title_text=f"{companion_symbol}", row=2, col=1)
            fig.update_xaxes(showticklabels=True, title_text="Trading Session Time", title_standoff=10, row=2, col=1)
        else:
            fig.update_xaxes(showticklabels=True, title_text="Trading Session Time", title_standoff=10, row=1, col=1)

        preds_records = []
        for idx_i, (_, r) in enumerate(pred_df.iterrows()):
            ts_val = y_ts.iloc[idx_i]
            preds_records.append({
                "timestamp": ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val),
                "open": round(float(r["open"]), 4),
                "high": round(float(r["high"]), 4),
                "low": round(float(r["low"]), 4),
                "close": round(float(r["close"]), 4),
                "env_high": round(float(r.get("env_high", r["high"])), 4),
                "env_low": round(float(r.get("env_low", r["low"])), 4),
            })

        actuals_records = []
        if actual_df is not None:
            for _, r in actual_df.iterrows():
                ts_val = r["timestamps"]
                actuals_records.append({
                    "timestamp": ts_val.isoformat() if hasattr(ts_val, "isoformat") else str(ts_val),
                    "open": round(float(r["open"]), 4),
                    "high": round(float(r["high"]), 4),
                    "low": round(float(r["low"]), 4),
                    "close": round(float(r["close"]), 4),
                })

        anchor_ts = hist_df["timestamps"].iloc[-1]
        mode_badge = "LIVE FORWARD FORECAST" if (eval_mode == "future" or actual_df is None) else "HISTORICAL HOLDOUT BACKTEST"
        run_record = {
            "run_source": f"dashboard_{eval_mode}_{data_source}",
            "source_provenance": source_provenance,
            "mode_badge": mode_badge,
            "inference_ms": inference_ms,
            "ticker": ticker,
            "model_key": model_key,
            "predictor_mode": "enhanced",
            "normalization_mode": norm_mode,
            "selection_mode": selection_mode,
            "interval_minutes": interval_minutes,
            "lookback": lookback,
            "pred_len": pred_len,
            "temperature": temperature,
            "top_p": top_p,
            "sample_count": sample_count,
            "anchor_timestamp": anchor_ts.isoformat() if hasattr(anchor_ts, "isoformat") else str(anchor_ts),
            "last_close": round(last_close, 4),
            "predicted_close": round(pred_close, 4),
            "predicted_return_pct": round(pred_ret_pct, 3),
            "predicted_high": round(pred_high, 4),
            "predicted_low": round(pred_low, 4),
            "env_high_max": round(env_high_max, 4),
            "env_low_min": round(env_low_min, 4),
            "confluence_signal": confluence_info["signal"] if confluence_info else None,
            "confluence_confirmed": confluence_info["is_confirmed"] if confluence_info else None,
            "conviction_score": confluence_info["conviction_score"] if confluence_info else None,
            "companion_ticker": confluence_info["companion_symbol"] if confluence_info else None,
            "companion_pred_return_pct": confluence_info["vix_return_pct"] if confluence_info else None,
            "mae": mae,
            "naive_mae": naive_mae,
            "mae_skill_pct": mae_skill_pct,
            "rmse": rmse,
            "mape_pct": mape_pct,
            "direction_hit": direction_hit,
            "predictions": preds_records,
            "actuals": actuals_records,
            "metadata": {
                "timeframe": timeframe,
                "eval_mode": eval_mode,
                "window_offset": window_offset,
                "source_provenance": source_provenance,
                "inference_ms": inference_ms,
                "naive_mae": naive_mae,
                "mae_skill_pct": mae_skill_pct,
            },
        }
        saved_run_id = None
        try:
            saved_run_id = db.save_forecast_run(run_record)
        except Exception as e:
            run_record["db_warning"] = str(e)

        return jsonify({
            "success": True,
            "saved_run_id": saved_run_id,
            "summary": _json_clean({k: v for k, v in run_record.items() if k not in ("predictions", "actuals")}),
            "actual_return_pct": actual_ret_pct,
            "confluence": _json_clean(confluence_info),
            "chart": json.dumps(fig, cls=PlotlyJSONEncoder),
            "predictions": preds_records,
            "actuals": actuals_records,
        })

    @suite_bp.post("/api/testing/run-backtest")
    def run_rolling_backtest():
        """
        Runs a multi-window rolling out-of-sample walk-forward evaluation on a tuned model & timeframe,
        computes 95% Wilson CI, Naive Random-Walk Skill Score, Always-Long Baseline, optional VIX Companion Confluence,
        saves the results to PostgreSQL `model_backtest_runs`, and returns a 2-row chart (Window Returns + Cumulative Curve).
        """
        body = request.get_json(silent=True) or {}
        ticker = str(body.get("ticker", "SPY")).strip().upper()
        timeframe = str(body.get("timeframe", "1hour")).strip().lower()
        lookback = max(32, min(512, int(body.get("lookback", 256))))
        horizon = max(4, min(64, int(body.get("horizon", 24))))
        num_windows = max(3, min(30, int(body.get("num_windows", 10))))
        sample_count = max(1, min(10, int(body.get("sample_count", 3))))
        temperature = max(0.05, min(1.2, float(body.get("temperature", 0.2))))
        companion_symbol = str(body.get("companion_symbol", "NONE")).strip().upper()

        spec = TICKER_TO_MODEL_MAP.get(ticker, TICKER_TO_MODEL_MAP["SPY"])
        model_key = body.get("model_key") or spec["model_key"]
        norm_mode = body.get("normalization_mode") or spec["normalization_mode"]
        selection_mode = body.get("selection_mode") or "medoid"

        csv_path = resolve_local_dataset_csv(ticker, timeframe)
        if not csv_path or not csv_path.is_file():
            raise FeedError(f"Dataset not found for {ticker} ({timeframe}).", 404)

        df = pd.read_csv(csv_path, parse_dates=["timestamps"]).tail(5000).reset_index(drop=True)
        df["timestamps"] = _normalize_ts_series(df["timestamps"])
        req_cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in df.columns]

        vix_df = None
        use_companion = (
            companion_symbol not in ("", "NONE", "FALSE")
            and "VIX_companion_multi_tf" in ui_module.AVAILABLE_MODELS
        )
        if use_companion:
            vix_csv = resolve_local_dataset_csv(companion_symbol, timeframe)
            if vix_csv and vix_csv.is_file():
                vix_df = pd.read_csv(vix_csv, parse_dates=["timestamps"]).tail(6000).reset_index(drop=True)
                vix_df["timestamps"] = _normalize_ts_series(vix_df["timestamps"])

        t_bt_start = time.perf_counter()
        with suite_lock:
            predictor = _load_enhanced_predictor(model_key)
            vix_predictor = _load_enhanced_predictor("VIX_companion_multi_tf") if (use_companion and vix_df is not None) else None
            windows = []
            hits = 0
            valid = 0
            long_baseline_hits = 0
            confirmed_trades = 0
            confirmed_hits = 0
            maes = []
            naive_maes = []
            rmses = []
            mapes = []
            cum_strat = 0.0
            cum_bh = 0.0

            for w in range(num_windows, 0, -1):
                end_idx = len(df) - w * horizon
                if end_idx - lookback < 0:
                    continue
                hist = df.iloc[end_idx - lookback : end_idx].reset_index(drop=True)
                act = df.iloc[end_idx : end_idx + horizon].reset_index(drop=True)
                last_c = float(hist["close"].iloc[-1])
                act_c = float(act["close"].iloc[-1])
                act_ret = (act_c / last_c - 1.0) * 100.0
                if abs(act_ret) < 0.03:
                    continue

                p_df = predictor.predict(
                    df=hist[req_cols],
                    x_timestamp=hist["timestamps"],
                    y_timestamp=act["timestamps"],
                    pred_len=horizon,
                    T=temperature,
                    top_p=0.9,
                    sample_count=sample_count,
                    normalization_mode=norm_mode,
                    selection_mode=selection_mode,
                )
                pred_c = float(p_df["close"].iloc[-1])
                pred_ret = (pred_c / last_c - 1.0) * 100.0
                act_closes = act["close"].to_numpy()
                errs = np.abs(p_df["close"].to_numpy() - act_closes)
                n_errs = np.abs(act_closes - last_c)
                w_mae = float(np.mean(errs))
                w_naive_mae = float(np.mean(n_errs))
                w_rmse = float(np.sqrt(np.mean(errs ** 2)))
                w_mape = float(np.mean(errs / act_closes) * 100.0)
                hit = bool(np.sign(pred_ret) == np.sign(act_ret))

                is_conf = None
                vix_ret_w = None
                if vix_predictor is not None and vix_df is not None:
                    m_vix = pd.merge(hist[["timestamps"]], vix_df, on="timestamps", how="inner").sort_values("timestamps").reset_index(drop=True)
                    if len(m_vix) >= 64:
                        v_cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in m_vix.columns]
                        vp_df = vix_predictor.predict(
                            df=m_vix[v_cols],
                            x_timestamp=m_vix["timestamps"],
                            y_timestamp=act["timestamps"].reset_index(drop=True),
                            pred_len=horizon,
                            T=temperature,
                            top_p=0.9,
                            sample_count=max(1, min(3, sample_count)),
                            normalization_mode="standard",
                            selection_mode="medoid",
                        )
                        v_last = float(m_vix["close"].iloc[-1])
                        v_fut = float(vp_df["close"].iloc[-1])
                        vix_ret_w = round((v_fut / v_last - 1.0) * 100.0, 2)
                        is_conf = bool((pred_ret > 0.05 and vix_ret_w < -0.10) or (pred_ret < -0.05 and vix_ret_w > 0.10))
                        if is_conf:
                            confirmed_trades += 1
                            if hit:
                                confirmed_hits += 1

                valid += 1
                if hit:
                    hits += 1
                if act_ret > 0:
                    long_baseline_hits += 1
                maes.append(w_mae)
                naive_maes.append(w_naive_mae)
                rmses.append(w_rmse)
                mapes.append(w_mape)

                strat_step = act_ret if pred_ret >= 0 else -act_ret
                cum_strat += strat_step
                cum_bh += act_ret

                windows.append({
                    "window": w,
                    "timestamp": str(act["timestamps"].iloc[0]),
                    "last_close": round(last_c, 3),
                    "actual_close": round(act_c, 3),
                    "predicted_close": round(pred_c, 3),
                    "actual_return_pct": round(act_ret, 2),
                    "predicted_return_pct": round(pred_ret, 2),
                    "mae": round(w_mae, 3),
                    "naive_mae": round(w_naive_mae, 3),
                    "mape_pct": round(w_mape, 2),
                    "hit": hit,
                    "confirmed": is_conf,
                    "vix_return_pct": vix_ret_w,
                    "cum_strategy_return_pct": round(cum_strat, 2),
                    "cum_buy_hold_return_pct": round(cum_bh, 2),
                })

        bt_elapsed_ms = round((time.perf_counter() - t_bt_start) * 1000.0, 1)
        acc_pct = round((hits / max(1, valid)) * 100.0, 2)
        ci_low, ci_high = calc_wilson_95_ci(hits, valid)
        long_base_acc = round((long_baseline_hits / max(1, valid)) * 100.0, 2)
        avg_mae = round(float(np.mean(maes)), 4) if maes else 0.0
        avg_naive_mae = round(float(np.mean(naive_maes)), 4) if naive_maes else 0.0
        skill_vs_naive_pct = round(float((1.0 - avg_mae / max(1e-6, avg_naive_mae)) * 100.0), 1) if avg_naive_mae > 0 else 0.0
        avg_rmse = round(float(np.mean(rmses)), 4) if rmses else 0.0
        avg_mape = round(float(np.mean(mapes)), 3) if mapes else 0.0
        pval = round(calc_binomial_pval(hits, valid), 4)

        conf_acc_pct = round((confirmed_hits / confirmed_trades) * 100.0, 2) if confirmed_trades > 0 else None
        conf_pval = round(calc_binomial_pval(confirmed_hits, confirmed_trades), 4) if confirmed_trades > 0 else None

        bt_record = {
            "ticker": ticker,
            "model_key": model_key,
            "companion_model_key": f"VIX_companion_multi_tf ({companion_symbol})" if (vix_predictor is not None) else None,
            "timeframe": timeframe,
            "lookback": lookback,
            "horizon": horizon,
            "num_windows": num_windows,
            "normalization_mode": norm_mode,
            "selection_mode": selection_mode,
            "total_valid_windows": valid,
            "direction_hits": hits,
            "direction_accuracy_pct": acc_pct,
            "ci_95_low_pct": ci_low,
            "ci_95_high_pct": ci_high,
            "always_long_accuracy_pct": long_base_acc,
            "avg_mae": avg_mae,
            "avg_naive_mae": avg_naive_mae,
            "skill_vs_naive_pct": skill_vs_naive_pct,
            "avg_rmse": avg_rmse,
            "avg_mape_pct": avg_mape,
            "p_value": pval,
            "confirmed_trades": confirmed_trades if vix_predictor is not None else None,
            "confirmed_hits": confirmed_hits if vix_predictor is not None else None,
            "confirmed_accuracy_pct": conf_acc_pct,
            "confirmed_p_value": conf_pval,
            "cum_strategy_return_pct": round(cum_strat, 2),
            "cum_buy_hold_return_pct": round(cum_bh, 2),
            "inference_ms": bt_elapsed_ms,
            "windows": windows,
            "notes": (
                f"Walk-Forward ({valid} windows, {timeframe}, {norm_mode}"
                + (f", {companion_symbol} Conf: {confirmed_hits}/{confirmed_trades}" if confirmed_trades else "")
                + ")"
            ),
        }
        saved_bt_id = None
        try:
            saved_bt_id = db.save_backtest_run(bt_record)
        except Exception as e:
            bt_record["db_warning"] = str(e)

        # Build 2-row Plotly chart: Row 1 = Window Returns Bar Chart, Row 2 = Cumulative Walk-Forward Return vs Buy & Hold
        x_labels = [w["timestamp"][:16] for w in windows] if windows else []
        bt_step = max(1, len(x_labels) // 7) if x_labels else 1
        bt_tick_vals = [x_labels[i] for i in range(0, len(x_labels), bt_step)] if x_labels else []

        fig = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.14,
            row_heights=[0.58, 0.42],
            subplot_titles=(
                f"{ticker} ({timeframe}) Walk-Forward Windows: {hits}/{valid} Hits ({acc_pct:.1f}%, 95% CI [{ci_low:.1f}%–{ci_high:.1f}%], p={pval:.4f})",
                f"Cumulative Walk-Forward Horizon Return vs Buy-&-Hold (Research Simulation Only)"
            ),
        )
        if windows:
            fig.add_trace(
                go.Bar(
                    x=x_labels,
                    y=[w["actual_return_pct"] for w in windows],
                    name="Actual Window Return (%)",
                    marker_color="#7b2cbf",
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Bar(
                    x=x_labels,
                    y=[w["predicted_return_pct"] for w in windows],
                    name="Kronos Predicted Return (%)",
                    marker_color=["#00f5d4" if w["hit"] else "#ff2a85" for w in windows],
                ),
                row=1, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=x_labels,
                    y=[w["cum_strategy_return_pct"] for w in windows],
                    mode="lines+markers",
                    name="Kronos Directional Cumulative (%)",
                    line=dict(color="#00f5d4", width=2.6),
                    marker=dict(size=5, color="#00f5d4"),
                ),
                row=2, col=1,
            )
            fig.add_trace(
                go.Scatter(
                    x=x_labels,
                    y=[w["cum_buy_hold_return_pct"] for w in windows],
                    mode="lines+markers",
                    name=f"{ticker} Passive Buy-&-Hold (%)",
                    line=dict(color="#94a3b8", width=2.0, dash="dot"),
                    marker=dict(size=4, color="#94a3b8"),
                ),
                row=2, col=1,
            )

        fig.update_layout(
            barmode="group",
            template="plotly_dark",
            paper_bgcolor="#0c0e1a",
            plot_bgcolor="#080a12",
            font=dict(color="#e2e8f0", family="Inter, system-ui, sans-serif"),
            height=620,
            dragmode="pan",
            hovermode="x unified",
            margin=dict(l=82, r=36, t=64, b=120),
            legend=dict(
                orientation="h",
                y=-0.16,
                yanchor="top",
                x=0.0,
                xanchor="left",
                font=dict(size=11.5),
            ),
        )
        fig.update_annotations(font=dict(size=12.5, color="#00f5d4"))
        fig.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=x_labels,
            tickmode="array",
            tickvals=bt_tick_vals,
            ticktext=bt_tick_vals,
            range=[-0.5, max(1, len(x_labels)) - 0.5],
            tickangle=0,
            automargin=True,
            gridcolor="rgba(0, 245, 212, 0.08)",
            zerolinecolor="rgba(0, 245, 212, 0.15)",
        )
        fig.update_xaxes(showticklabels=False, title_text="", row=1, col=1)
        fig.update_xaxes(showticklabels=True, title_text="Evaluation Window Start", title_standoff=10, row=2, col=1)
        fig.update_yaxes(
            fixedrange=False,
            automargin=True,
            title_standoff=10,
            gridcolor="rgba(0, 245, 212, 0.08)",
            zerolinecolor="rgba(0, 245, 212, 0.15)",
        )
        fig.update_yaxes(title_text="Window Return (%)", row=1, col=1)
        fig.update_yaxes(title_text="Cumulative (%)", row=2, col=1)

        return jsonify({
            "success": True,
            "saved_backtest_id": saved_bt_id,
            "backtest": _json_clean(bt_record),
            "chart": json.dumps(fig, cls=PlotlyJSONEncoder),
        })

    @suite_bp.get("/api/testing/db-history")
    def db_history():
        """Returns longitudinal history from PostgreSQL `kronos_research` database."""
        ticker = request.args.get("ticker")
        limit = max(5, min(200, int(request.args.get("limit", 35))))
        return jsonify({
            "success": True,
            "database": db.get_database_summary(ticker=ticker, limit=limit),
        })

    @suite_bp.get("/api/testing/export-db")
    def export_db_table():
        """Exports any longitudinal research table from `kronos_research` as CSV or JSON."""
        from flask import Response
        import io
        import csv

        table = str(request.args.get("table", "model_forecast_runs")).strip().lower()
        fmt = str(request.args.get("format", "csv")).strip().lower()
        ticker = str(request.args.get("ticker", "")).strip().upper()
        limit = max(10, min(2000, int(request.args.get("limit", 500))))

        allowed_tables = {
            "model_forecast_runs": ("created_at", True),
            "options_chain_snapshots": ("captured_at", True),
            "model_backtest_runs": ("created_at", True),
            "underlying_snapshots": ("captured_at", True),
            "tuned_models_registry": ("updated_at", False),
        }
        if table not in allowed_tables:
            raise FeedError(f"Unsupported export table: {table}", 400)

        order_col, has_ticker = allowed_tables[table]
        summary = db.get_database_summary(ticker=ticker if (ticker and has_ticker) else None, limit=limit)
        table_key_map = {
            "model_forecast_runs": "recent_forecasts",
            "options_chain_snapshots": "recent_options",
            "model_backtest_runs": "recent_backtests",
            "underlying_snapshots": "recent_underlyings",
            "tuned_models_registry": "tuned_models",
        }
        rows = summary.get(table_key_map[table], [])

        if fmt == "json":
            return Response(
                json.dumps({"table": table, "count": len(rows), "rows": rows}, indent=2),
                mimetype="application/json",
                headers={"Content-Disposition": f'attachment; filename="kronos_{table}.json"'},
            )

        output = io.StringIO()
        if rows:
            fieldnames = list(rows[0].keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for r in rows:
                writer.writerow({k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in r.items()})
        else:
            output.write("id,note\n0,no_rows\n")

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f'attachment; filename="kronos_{table}.csv"'},
        )

    app.register_blueprint(suite_bp)
    return db
