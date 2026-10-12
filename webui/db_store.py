"""
PostgreSQL Research & Analytics Store for Kronos WebUI Testing Dashboard.
Stores tuned model registry, underlying snapshots + technicals + news,
options chain snapshots + contract quotes/greeks, forecast runs, and walk-forward backtest runs.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from dotenv import dotenv_values

try:
    import psycopg
    from psycopg.rows import dict_row
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_URL = "postgresql:///kronos_research"


def _json_clean(obj: Any) -> Any:
    """Recursively sanitize numpy/pandas floats, booleans, and NaNs for JSONB and Postgres storage."""
    if isinstance(obj, dict):
        return {str(k): _json_clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_clean(v) for v in obj]
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        val = float(obj)
        return None if (np.isnan(val) or np.isinf(val)) else val
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def get_db_url() -> str:
    private = dotenv_values(ROOT / ".env")
    return (
        os.environ.get("KRONOS_DATABASE_URL")
        or private.get("KRONOS_DATABASE_URL")
        or DEFAULT_DB_URL
    )


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS tuned_models_registry (
    model_key TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    tickers JSONB NOT NULL DEFAULT '[]'::jsonb,
    timeframes JSONB NOT NULL DEFAULT '[]'::jsonb,
    context_length INTEGER NOT NULL DEFAULT 512,
    params TEXT NOT NULL DEFAULT '102.3M',
    normalization_mode TEXT NOT NULL DEFAULT 'detrend',
    model_dir TEXT NOT NULL,
    tokenizer_dir TEXT NOT NULL,
    total_training_bars BIGINT DEFAULT 0,
    training_status TEXT DEFAULT 'COMPLETED',
    benchmark_accuracy_pct DOUBLE PRECISION,
    benchmark_mae DOUBLE PRECISION,
    benchmark_mape_pct DOUBLE PRECISION,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS underlying_snapshots (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    price DOUBLE PRECISION,
    today_change DOUBLE PRECISION,
    today_change_pct DOUBLE PRECISION,
    day_open DOUBLE PRECISION,
    day_high DOUBLE PRECISION,
    day_low DOUBLE PRECISION,
    day_close DOUBLE PRECISION,
    day_volume DOUBLE PRECISION,
    day_vwap DOUBLE PRECISION,
    prev_close DOUBLE PRECISION,
    prev_volume DOUBLE PRECISION,
    bid DOUBLE PRECISION,
    ask DOUBLE PRECISION,
    spread DOUBLE PRECISION,
    market_cap DOUBLE PRECISION,
    company_name TEXT,
    primary_exchange TEXT,
    sic_description TEXT,
    rsi_14 DOUBLE PRECISION,
    sma_20 DOUBLE PRECISION,
    ema_20 DOUBLE PRECISION,
    macd_val DOUBLE PRECISION,
    macd_signal DOUBLE PRECISION,
    macd_hist DOUBLE PRECISION,
    news_json JSONB DEFAULT '[]'::jsonb,
    raw_json JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_underlying_snapshots_ticker_time ON underlying_snapshots (ticker, captured_at DESC);

CREATE TABLE IF NOT EXISTS options_chain_snapshots (
    id BIGSERIAL PRIMARY KEY,
    ticker TEXT NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    underlying_price DOUBLE PRECISION,
    expiration_filter TEXT,
    contracts_count INTEGER NOT NULL DEFAULT 0,
    total_call_oi BIGINT NOT NULL DEFAULT 0,
    total_put_oi BIGINT NOT NULL DEFAULT 0,
    put_call_oi_ratio DOUBLE PRECISION,
    total_call_vol BIGINT NOT NULL DEFAULT 0,
    total_put_vol BIGINT NOT NULL DEFAULT 0,
    put_call_vol_ratio DOUBLE PRECISION,
    atm_iv DOUBLE PRECISION,
    avg_call_iv DOUBLE PRECISION,
    avg_put_iv DOUBLE PRECISION,
    iv_skew_25d DOUBLE PRECISION,
    max_pain_strike DOUBLE PRECISION,
    call_wall_strike DOUBLE PRECISION,
    put_wall_strike DOUBLE PRECISION,
    net_delta_exposure DOUBLE PRECISION,
    net_gamma_exposure DOUBLE PRECISION,
    expirations_json JSONB DEFAULT '[]'::jsonb,
    summary_json JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_options_chain_ticker_time ON options_chain_snapshots (ticker, captured_at DESC);

CREATE TABLE IF NOT EXISTS options_contracts_quotes (
    id BIGSERIAL PRIMARY KEY,
    snapshot_id BIGINT NOT NULL REFERENCES options_chain_snapshots(id) ON DELETE CASCADE,
    ticker TEXT NOT NULL,
    contract_ticker TEXT NOT NULL,
    contract_type TEXT NOT NULL,
    expiration_date DATE,
    strike_price DOUBLE PRECISION NOT NULL,
    implied_volatility DOUBLE PRECISION,
    open_interest BIGINT DEFAULT 0,
    volume BIGINT DEFAULT 0,
    bid DOUBLE PRECISION,
    ask DOUBLE PRECISION,
    midpoint DOUBLE PRECISION,
    last_price DOUBLE PRECISION,
    break_even_price DOUBLE PRECISION,
    delta DOUBLE PRECISION,
    gamma DOUBLE PRECISION,
    theta DOUBLE PRECISION,
    vega DOUBLE PRECISION,
    vwap DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS idx_options_quotes_snapshot ON options_contracts_quotes (snapshot_id);
CREATE INDEX IF NOT EXISTS idx_options_quotes_ticker_strike ON options_contracts_quotes (ticker, expiration_date, strike_price);

CREATE TABLE IF NOT EXISTS model_forecast_runs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    run_source TEXT NOT NULL DEFAULT 'live',
    ticker TEXT NOT NULL,
    model_key TEXT NOT NULL,
    predictor_mode TEXT NOT NULL DEFAULT 'enhanced',
    normalization_mode TEXT NOT NULL DEFAULT 'detrend',
    selection_mode TEXT NOT NULL DEFAULT 'medoid',
    interval_minutes INTEGER NOT NULL DEFAULT 60,
    lookback INTEGER NOT NULL DEFAULT 256,
    pred_len INTEGER NOT NULL DEFAULT 24,
    temperature DOUBLE PRECISION NOT NULL DEFAULT 0.3,
    top_p DOUBLE PRECISION NOT NULL DEFAULT 0.9,
    sample_count INTEGER NOT NULL DEFAULT 5,
    anchor_timestamp TIMESTAMPTZ,
    last_close DOUBLE PRECISION,
    predicted_close DOUBLE PRECISION,
    predicted_return_pct DOUBLE PRECISION,
    predicted_high DOUBLE PRECISION,
    predicted_low DOUBLE PRECISION,
    env_high_max DOUBLE PRECISION,
    env_low_min DOUBLE PRECISION,
    confluence_signal TEXT,
    confluence_confirmed BOOLEAN,
    conviction_score DOUBLE PRECISION,
    companion_ticker TEXT,
    companion_pred_return_pct DOUBLE PRECISION,
    mae DOUBLE PRECISION,
    rmse DOUBLE PRECISION,
    mape_pct DOUBLE PRECISION,
    direction_hit BOOLEAN,
    predictions_json JSONB DEFAULT '[]'::jsonb,
    actuals_json JSONB DEFAULT '[]'::jsonb,
    metadata_json JSONB DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_forecast_runs_ticker_time ON model_forecast_runs (ticker, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_forecast_runs_model ON model_forecast_runs (model_key, created_at DESC);

CREATE TABLE IF NOT EXISTS model_backtest_runs (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ticker TEXT NOT NULL,
    model_key TEXT NOT NULL,
    companion_model_key TEXT,
    timeframe TEXT NOT NULL,
    lookback INTEGER NOT NULL,
    horizon INTEGER NOT NULL,
    num_windows INTEGER NOT NULL,
    normalization_mode TEXT NOT NULL,
    selection_mode TEXT NOT NULL,
    total_valid_windows INTEGER NOT NULL,
    direction_hits INTEGER NOT NULL,
    direction_accuracy_pct DOUBLE PRECISION NOT NULL,
    avg_mae DOUBLE PRECISION,
    avg_rmse DOUBLE PRECISION,
    avg_mape_pct DOUBLE PRECISION,
    p_value DOUBLE PRECISION,
    confirmed_trades INTEGER,
    confirmed_hits INTEGER,
    confirmed_accuracy_pct DOUBLE PRECISION,
    windows_json JSONB DEFAULT '[]'::jsonb,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_backtest_runs_ticker_time ON model_backtest_runs (ticker, created_at DESC);
"""


class KronosResearchDB:
    """Manages PostgreSQL storage and longitudinal queries for Kronos testing & options data."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or get_db_url()
        self.ready = False
        self.last_error: Optional[str] = None

    def connect(self):
        if not PSYCOPG_AVAILABLE:
            raise RuntimeError("psycopg is not installed in the active environment.")
        return psycopg.connect(self.db_url, autocommit=True, row_factory=dict_row)

    def ensure_schema(self) -> bool:
        if not PSYCOPG_AVAILABLE:
            self.last_error = "psycopg not installed"
            return False
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(SCHEMA_SQL)
            self.ready = True
            self.last_error = None
            return True
        except Exception as e:
            self.ready = False
            self.last_error = str(e)
            return False

    def upsert_tuned_model(self, model_spec: Dict[str, Any]) -> None:
        if not self.ready and not self.ensure_schema():
            return
        sql = """
        INSERT INTO tuned_models_registry (
            model_key, name, category, tickers, timeframes, context_length, params,
            normalization_mode, model_dir, tokenizer_dir, total_training_bars,
            training_status, benchmark_accuracy_pct, benchmark_mae, benchmark_mape_pct,
            description, updated_at
        ) VALUES (
            %(model_key)s, %(name)s, %(category)s, %(tickers)s::jsonb, %(timeframes)s::jsonb,
            %(context_length)s, %(params)s, %(normalization_mode)s, %(model_dir)s, %(tokenizer_dir)s,
            %(total_training_bars)s, %(training_status)s, %(benchmark_accuracy_pct)s,
            %(benchmark_mae)s, %(benchmark_mape_pct)s, %(description)s, NOW()
        )
        ON CONFLICT (model_key) DO UPDATE SET
            name = EXCLUDED.name,
            category = EXCLUDED.category,
            tickers = EXCLUDED.tickers,
            timeframes = EXCLUDED.timeframes,
            context_length = EXCLUDED.context_length,
            params = EXCLUDED.params,
            normalization_mode = EXCLUDED.normalization_mode,
            model_dir = EXCLUDED.model_dir,
            tokenizer_dir = EXCLUDED.tokenizer_dir,
            total_training_bars = EXCLUDED.total_training_bars,
            training_status = EXCLUDED.training_status,
            benchmark_accuracy_pct = COALESCE(EXCLUDED.benchmark_accuracy_pct, tuned_models_registry.benchmark_accuracy_pct),
            benchmark_mae = COALESCE(EXCLUDED.benchmark_mae, tuned_models_registry.benchmark_mae),
            benchmark_mape_pct = COALESCE(EXCLUDED.benchmark_mape_pct, tuned_models_registry.benchmark_mape_pct),
            description = EXCLUDED.description,
            updated_at = NOW();
        """
        params = {
            "model_key": model_spec["model_key"],
            "name": model_spec["name"],
            "category": model_spec.get("category", "specialized_multi_tf"),
            "tickers": json.dumps(_json_clean(model_spec.get("tickers", []))),
            "timeframes": json.dumps(_json_clean(model_spec.get("timeframes", ["5min", "15min", "1hour", "1day"]))),
            "context_length": int(model_spec.get("context_length", 512)),
            "params": model_spec.get("params", "102.3M"),
            "normalization_mode": model_spec.get("normalization_mode", "detrend"),
            "model_dir": str(model_spec.get("model_id", "")),
            "tokenizer_dir": str(model_spec.get("tokenizer_id", "")),
            "total_training_bars": int(model_spec.get("total_training_bars", 0)),
            "training_status": model_spec.get("training_status", "COMPLETED"),
            "benchmark_accuracy_pct": _json_clean(model_spec.get("benchmark_accuracy_pct")),
            "benchmark_mae": _json_clean(model_spec.get("benchmark_mae")),
            "benchmark_mape_pct": _json_clean(model_spec.get("benchmark_mape_pct")),
            "description": model_spec.get("description", ""),
        }
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)

    def save_underlying_snapshot(self, snap: Dict[str, Any]) -> Optional[int]:
        if not self.ready and not self.ensure_schema():
            return None
        sql = """
        INSERT INTO underlying_snapshots (
            ticker, price, today_change, today_change_pct,
            day_open, day_high, day_low, day_close, day_volume, day_vwap,
            prev_close, prev_volume, bid, ask, spread, market_cap,
            company_name, primary_exchange, sic_description,
            rsi_14, sma_20, ema_20, macd_val, macd_signal, macd_hist,
            news_json, raw_json
        ) VALUES (
            %(ticker)s, %(price)s, %(today_change)s, %(today_change_pct)s,
            %(day_open)s, %(day_high)s, %(day_low)s, %(day_close)s, %(day_volume)s, %(day_vwap)s,
            %(prev_close)s, %(prev_volume)s, %(bid)s, %(ask)s, %(spread)s, %(market_cap)s,
            %(company_name)s, %(primary_exchange)s, %(sic_description)s,
            %(rsi_14)s, %(sma_20)s, %(ema_20)s, %(macd_val)s, %(macd_signal)s, %(macd_hist)s,
            %(news_json)s::jsonb, %(raw_json)s::jsonb
        ) RETURNING id;
        """
        clean = _json_clean(snap)
        params = {
            "ticker": clean.get("ticker", "SPY"),
            "price": clean.get("price"),
            "today_change": clean.get("today_change"),
            "today_change_pct": clean.get("today_change_pct"),
            "day_open": clean.get("day_open"),
            "day_high": clean.get("day_high"),
            "day_low": clean.get("day_low"),
            "day_close": clean.get("day_close"),
            "day_volume": clean.get("day_volume"),
            "day_vwap": clean.get("day_vwap"),
            "prev_close": clean.get("prev_close"),
            "prev_volume": clean.get("prev_volume"),
            "bid": clean.get("bid"),
            "ask": clean.get("ask"),
            "spread": clean.get("spread"),
            "market_cap": clean.get("market_cap"),
            "company_name": clean.get("company_name"),
            "primary_exchange": clean.get("primary_exchange"),
            "sic_description": clean.get("sic_description"),
            "rsi_14": clean.get("rsi_14"),
            "sma_20": clean.get("sma_20"),
            "ema_20": clean.get("ema_20"),
            "macd_val": clean.get("macd_val"),
            "macd_signal": clean.get("macd_signal"),
            "macd_hist": clean.get("macd_hist"),
            "news_json": json.dumps(clean.get("news", [])),
            "raw_json": json.dumps(clean.get("raw", {})),
        }
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return int(row["id"]) if row else None

    def save_options_snapshot(self, summary: Dict[str, Any], contracts: List[Dict[str, Any]]) -> Optional[int]:
        if not self.ready and not self.ensure_schema():
            return None
        clean_sum = _json_clean(summary)
        snap_sql = """
        INSERT INTO options_chain_snapshots (
            ticker, underlying_price, expiration_filter, contracts_count,
            total_call_oi, total_put_oi, put_call_oi_ratio,
            total_call_vol, total_put_vol, put_call_vol_ratio,
            atm_iv, avg_call_iv, avg_put_iv, iv_skew_25d,
            max_pain_strike, call_wall_strike, put_wall_strike,
            net_delta_exposure, net_gamma_exposure,
            expirations_json, summary_json
        ) VALUES (
            %(ticker)s, %(underlying_price)s, %(expiration_filter)s, %(contracts_count)s,
            %(total_call_oi)s, %(total_put_oi)s, %(put_call_oi_ratio)s,
            %(total_call_vol)s, %(total_put_vol)s, %(put_call_vol_ratio)s,
            %(atm_iv)s, %(avg_call_iv)s, %(avg_put_iv)s, %(iv_skew_25d)s,
            %(max_pain_strike)s, %(call_wall_strike)s, %(put_wall_strike)s,
            %(net_delta_exposure)s, %(net_gamma_exposure)s,
            %(expirations_json)s::jsonb, %(summary_json)s::jsonb
        ) RETURNING id;
        """
        params = {
            "ticker": clean_sum.get("ticker", "SPY"),
            "underlying_price": clean_sum.get("underlying_price"),
            "expiration_filter": clean_sum.get("expiration_filter", "all_near_term"),
            "contracts_count": int(clean_sum.get("contracts_count", len(contracts))),
            "total_call_oi": int(clean_sum.get("total_call_oi") or 0),
            "total_put_oi": int(clean_sum.get("total_put_oi") or 0),
            "put_call_oi_ratio": clean_sum.get("put_call_oi_ratio"),
            "total_call_vol": int(clean_sum.get("total_call_vol") or 0),
            "total_put_vol": int(clean_sum.get("total_put_vol") or 0),
            "put_call_vol_ratio": clean_sum.get("put_call_vol_ratio"),
            "atm_iv": clean_sum.get("atm_iv"),
            "avg_call_iv": clean_sum.get("avg_call_iv"),
            "avg_put_iv": clean_sum.get("avg_put_iv"),
            "iv_skew_25d": clean_sum.get("iv_skew_25d"),
            "max_pain_strike": clean_sum.get("max_pain_strike"),
            "call_wall_strike": clean_sum.get("call_wall_strike"),
            "put_wall_strike": clean_sum.get("put_wall_strike"),
            "net_delta_exposure": clean_sum.get("net_delta_exposure"),
            "net_gamma_exposure": clean_sum.get("net_gamma_exposure"),
            "expirations_json": json.dumps(clean_sum.get("expirations", [])),
            "summary_json": json.dumps(clean_sum),
        }
        quote_sql = """
        INSERT INTO options_contracts_quotes (
            snapshot_id, ticker, contract_ticker, contract_type, expiration_date,
            strike_price, implied_volatility, open_interest, volume,
            bid, ask, midpoint, last_price, break_even_price,
            delta, gamma, theta, vega, vwap
        ) VALUES (
            %(snapshot_id)s, %(ticker)s, %(contract_ticker)s, %(contract_type)s, %(expiration_date)s,
            %(strike_price)s, %(implied_volatility)s, %(open_interest)s, %(volume)s,
            %(bid)s, %(ask)s, %(midpoint)s, %(last_price)s, %(break_even_price)s,
            %(delta)s, %(gamma)s, %(theta)s, %(vega)s, %(vwap)s
        );
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(snap_sql, params)
                row = cur.fetchone()
                if not row:
                    return None
                snap_id = int(row["id"])
                if contracts:
                    batch = []
                    for c in contracts:
                        cc = _json_clean(c)
                        exp_str = cc.get("expiration_date")
                        batch.append({
                            "snapshot_id": snap_id,
                            "ticker": clean_sum.get("ticker", "SPY"),
                            "contract_ticker": cc.get("contract_ticker", ""),
                            "contract_type": cc.get("contract_type", "call"),
                            "expiration_date": exp_str if exp_str else None,
                            "strike_price": float(cc.get("strike_price") or 0.0),
                            "implied_volatility": cc.get("implied_volatility"),
                            "open_interest": int(cc.get("open_interest") or 0),
                            "volume": int(cc.get("volume") or 0),
                            "bid": cc.get("bid"),
                            "ask": cc.get("ask"),
                            "midpoint": cc.get("midpoint"),
                            "last_price": cc.get("last_price"),
                            "break_even_price": cc.get("break_even_price"),
                            "delta": cc.get("delta"),
                            "gamma": cc.get("gamma"),
                            "theta": cc.get("theta"),
                            "vega": cc.get("vega"),
                            "vwap": cc.get("vwap"),
                        })
                    cur.executemany(quote_sql, batch)
                return snap_id

    def save_forecast_run(self, run_data: Dict[str, Any]) -> Optional[int]:
        if not self.ready and not self.ensure_schema():
            return None
        clean = _json_clean(run_data)
        sql = """
        INSERT INTO model_forecast_runs (
            run_source, ticker, model_key, predictor_mode, normalization_mode, selection_mode,
            interval_minutes, lookback, pred_len, temperature, top_p, sample_count,
            anchor_timestamp, last_close, predicted_close, predicted_return_pct,
            predicted_high, predicted_low, env_high_max, env_low_min,
            confluence_signal, confluence_confirmed, conviction_score,
            companion_ticker, companion_pred_return_pct,
            mae, rmse, mape_pct, direction_hit,
            predictions_json, actuals_json, metadata_json
        ) VALUES (
            %(run_source)s, %(ticker)s, %(model_key)s, %(predictor_mode)s, %(normalization_mode)s, %(selection_mode)s,
            %(interval_minutes)s, %(lookback)s, %(pred_len)s, %(temperature)s, %(top_p)s, %(sample_count)s,
            %(anchor_timestamp)s, %(last_close)s, %(predicted_close)s, %(predicted_return_pct)s,
            %(predicted_high)s, %(predicted_low)s, %(env_high_max)s, %(env_low_min)s,
            %(confluence_signal)s, %(confluence_confirmed)s, %(conviction_score)s,
            %(companion_ticker)s, %(companion_pred_return_pct)s,
            %(mae)s, %(rmse)s, %(mape_pct)s, %(direction_hit)s,
            %(predictions_json)s::jsonb, %(actuals_json)s::jsonb, %(metadata_json)s::jsonb
        ) RETURNING id;
        """
        params = {
            "run_source": clean.get("run_source", "live"),
            "ticker": clean.get("ticker", "SPY"),
            "model_key": clean.get("model_key", "kronos-base"),
            "predictor_mode": clean.get("predictor_mode", "enhanced"),
            "normalization_mode": clean.get("normalization_mode", "detrend"),
            "selection_mode": clean.get("selection_mode", "medoid"),
            "interval_minutes": int(clean.get("interval_minutes") or 60),
            "lookback": int(clean.get("lookback") or 256),
            "pred_len": int(clean.get("pred_len") or 24),
            "temperature": float(clean.get("temperature") or 0.3),
            "top_p": float(clean.get("top_p") or 0.9),
            "sample_count": int(clean.get("sample_count") or 5),
            "anchor_timestamp": clean.get("anchor_timestamp"),
            "last_close": clean.get("last_close"),
            "predicted_close": clean.get("predicted_close"),
            "predicted_return_pct": clean.get("predicted_return_pct"),
            "predicted_high": clean.get("predicted_high"),
            "predicted_low": clean.get("predicted_low"),
            "env_high_max": clean.get("env_high_max"),
            "env_low_min": clean.get("env_low_min"),
            "confluence_signal": clean.get("confluence_signal"),
            "confluence_confirmed": clean.get("confluence_confirmed"),
            "conviction_score": clean.get("conviction_score"),
            "companion_ticker": clean.get("companion_ticker"),
            "companion_pred_return_pct": clean.get("companion_pred_return_pct"),
            "mae": clean.get("mae"),
            "rmse": clean.get("rmse"),
            "mape_pct": clean.get("mape_pct"),
            "direction_hit": clean.get("direction_hit"),
            "predictions_json": json.dumps(clean.get("predictions", [])),
            "actuals_json": json.dumps(clean.get("actuals", [])),
            "metadata_json": json.dumps(clean.get("metadata", {})),
        }
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return int(row["id"]) if row else None

    def save_backtest_run(self, bt_data: Dict[str, Any]) -> Optional[int]:
        if not self.ready and not self.ensure_schema():
            return None
        clean = _json_clean(bt_data)
        sql = """
        INSERT INTO model_backtest_runs (
            ticker, model_key, companion_model_key, timeframe,
            lookback, horizon, num_windows, normalization_mode, selection_mode,
            total_valid_windows, direction_hits, direction_accuracy_pct,
            avg_mae, avg_rmse, avg_mape_pct, p_value,
            confirmed_trades, confirmed_hits, confirmed_accuracy_pct,
            windows_json, notes
        ) VALUES (
            %(ticker)s, %(model_key)s, %(companion_model_key)s, %(timeframe)s,
            %(lookback)s, %(horizon)s, %(num_windows)s, %(normalization_mode)s, %(selection_mode)s,
            %(total_valid_windows)s, %(direction_hits)s, %(direction_accuracy_pct)s,
            %(avg_mae)s, %(avg_rmse)s, %(avg_mape_pct)s, %(p_value)s,
            %(confirmed_trades)s, %(confirmed_hits)s, %(confirmed_accuracy_pct)s,
            %(windows_json)s::jsonb, %(notes)s
        ) RETURNING id;
        """
        params = {
            "ticker": clean.get("ticker", "SPY"),
            "model_key": clean.get("model_key", "SPY_23yr_multi_tf"),
            "companion_model_key": clean.get("companion_model_key"),
            "timeframe": clean.get("timeframe", "1hour"),
            "lookback": int(clean.get("lookback") or 256),
            "horizon": int(clean.get("horizon") or 24),
            "num_windows": int(clean.get("num_windows") or 10),
            "normalization_mode": clean.get("normalization_mode", "detrend"),
            "selection_mode": clean.get("selection_mode", "medoid"),
            "total_valid_windows": int(clean.get("total_valid_windows") or 0),
            "direction_hits": int(clean.get("direction_hits") or 0),
            "direction_accuracy_pct": float(clean.get("direction_accuracy_pct") or 0.0),
            "avg_mae": clean.get("avg_mae"),
            "avg_rmse": clean.get("avg_rmse"),
            "avg_mape_pct": clean.get("avg_mape_pct"),
            "p_value": clean.get("p_value"),
            "confirmed_trades": clean.get("confirmed_trades"),
            "confirmed_hits": clean.get("confirmed_hits"),
            "confirmed_accuracy_pct": clean.get("confirmed_accuracy_pct"),
            "windows_json": json.dumps(clean.get("windows", [])),
            "notes": clean.get("notes", ""),
        }
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return int(row["id"]) if row else None

    def get_database_summary(self, ticker: Optional[str] = None, limit: int = 25) -> Dict[str, Any]:
        if not self.ready and not self.ensure_schema():
            return {
                "connected": False,
                "error": self.last_error,
                "database": self.db_url,
                "counts": {},
                "tuned_models": [],
                "recent_forecasts": [],
                "recent_backtests": [],
                "recent_options": [],
                "recent_underlyings": [],
            }
        try:
            with self.connect() as conn:
                with conn.cursor() as cur:
                    counts = {}
                    for tbl in (
                        "tuned_models_registry",
                        "underlying_snapshots",
                        "options_chain_snapshots",
                        "options_contracts_quotes",
                        "model_forecast_runs",
                        "model_backtest_runs",
                    ):
                        cur.execute(f"SELECT COUNT(*) AS cnt FROM {tbl};")
                        counts[tbl] = int(cur.fetchone()["cnt"])

                    cur.execute("SELECT * FROM tuned_models_registry ORDER BY category, model_key;")
                    tuned_models = _json_clean(cur.fetchall())

                    where_clause = "WHERE ticker = %(ticker)s" if ticker else ""
                    q_params = {"ticker": ticker.upper(), "limit": int(limit)} if ticker else {"limit": int(limit)}

                    cur.execute(
                        f"""
                        SELECT id, created_at, run_source, ticker, model_key, predictor_mode,
                               normalization_mode, selection_mode, interval_minutes, lookback, pred_len,
                               last_close, predicted_close, predicted_return_pct,
                               confluence_signal, confluence_confirmed, conviction_score,
                               mae, rmse, mape_pct, direction_hit
                        FROM model_forecast_runs
                        {where_clause}
                        ORDER BY created_at DESC LIMIT %(limit)s;
                        """,
                        q_params,
                    )
                    recent_forecasts = _json_clean(cur.fetchall())

                    cur.execute(
                        f"""
                        SELECT id, created_at, ticker, model_key, companion_model_key, timeframe,
                               lookback, horizon, num_windows, normalization_mode, selection_mode,
                               total_valid_windows, direction_hits, direction_accuracy_pct,
                               avg_mae, avg_rmse, avg_mape_pct, p_value,
                               confirmed_trades, confirmed_hits, confirmed_accuracy_pct, notes
                        FROM model_backtest_runs
                        {where_clause}
                        ORDER BY created_at DESC LIMIT %(limit)s;
                        """,
                        q_params,
                    )
                    recent_backtests = _json_clean(cur.fetchall())

                    cur.execute(
                        f"""
                        SELECT id, ticker, captured_at, underlying_price, expiration_filter,
                               contracts_count, total_call_oi, total_put_oi, put_call_oi_ratio,
                               total_call_vol, total_put_vol, put_call_vol_ratio,
                               atm_iv, avg_call_iv, avg_put_iv, iv_skew_25d,
                               max_pain_strike, call_wall_strike, put_wall_strike,
                               net_delta_exposure, net_gamma_exposure
                        FROM options_chain_snapshots
                        {where_clause}
                        ORDER BY captured_at DESC LIMIT %(limit)s;
                        """,
                        q_params,
                    )
                    recent_options = _json_clean(cur.fetchall())

                    cur.execute(
                        f"""
                        SELECT id, ticker, captured_at, price, today_change, today_change_pct,
                               day_open, day_high, day_low, day_close, day_volume, day_vwap,
                               bid, ask, spread, market_cap, company_name, rsi_14, sma_20, ema_20,
                               macd_val, macd_signal, macd_hist
                        FROM underlying_snapshots
                        {where_clause}
                        ORDER BY captured_at DESC LIMIT %(limit)s;
                        """,
                        q_params,
                    )
                    recent_underlyings = _json_clean(cur.fetchall())

            return {
                "connected": True,
                "database": "kronos_research",
                "counts": counts,
                "tuned_models": tuned_models,
                "recent_forecasts": recent_forecasts,
                "recent_backtests": recent_backtests,
                "recent_options": recent_options,
                "recent_underlyings": recent_underlyings,
            }
        except Exception as e:
            self.last_error = str(e)
            return {
                "connected": False,
                "error": str(e),
                "database": self.db_url,
                "counts": {},
            }
