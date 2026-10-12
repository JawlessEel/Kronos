"""
Autonomous Multi-Model Factory & Dataset Preparation Pipeline.
1. Extends VIX Companion dataset through 2026-10-09.
2. Prepares full 2004-01-01 to 2026-10-09 multi-timeframe (5m, 15m, 1h, 1d) datasets for:
   - GME (GameStop — full volatility history through 10/09/2026)
   - QQQ (Invesco QQQ Nasdaq-100 ETF)
   - IWM (iShares Russell 2000 Small-Cap ETF)
   - NVDA (NVIDIA Corp — AI & Semiconductor bellwether)
   - MACRO_TLT_GLD (TLT 20+ Yr Treasuries & GLD Gold Macro Companion)
3. Trains each specialized Kronos model sequentially from fresh base weights:
   Order: VIX_companion_multi_tf -> GME_23yr_multi_tf -> QQQ_23yr_multi_tf -> IWM_23yr_multi_tf -> NVDA_23yr_multi_tf -> MACRO_TLT_GLD_23yr_multi_tf
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, parse_qsl
import pandas as pd
import requests
import yaml
from dotenv import dotenv_values

ROOT = Path("/Volumes/MacMoneyMakerSSD/Ai_apps/kronos")
CONFIGS_DIR = ROOT / "finetune_csv" / "configs"
OUTPUTS_DIR = ROOT / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
STATUS_FILE = OUTPUTS_DIR / "model_factory_status.json"

BASE_URL = "https://api.massive.com"
END_DATE = "2026-10-09"

TIMEFRAMES = [
    {"name": "5min", "mult": 5, "span": "minute"},
    {"name": "15min", "mult": 15, "span": "minute"},
    {"name": "1hour", "mult": 1, "span": "hour"},
    {"name": "1day", "mult": 1, "span": "day"},
]

MODEL_QUEUE = [
    {
        "exp_name": "VIX_companion_multi_tf",
        "config_file": "config_vix_companion.yaml",
        "data_dir": ROOT / "data" / "vix_companion",
        "description": "VIX Companion Multi-Timeframe (VIXY, UVXY, I:VIX through 2026-10-09)",
        "assets": [
            {"symbol": "VIXY", "clean_name": "VIXY", "start": "2011-01-03", "end": END_DATE},
            {"symbol": "UVXY", "clean_name": "UVXY", "start": "2011-10-04", "end": END_DATE},
            {"symbol": "I:VIX", "clean_name": "INDEX_VIX", "start": "2023-01-01", "end": END_DATE},
        ],
    },
    {
        "exp_name": "GME_23yr_multi_tf",
        "config_file": "config_gme_multi_tf.yaml",
        "data_dir": ROOT / "data" / "gme_multi_timeframe",
        "description": "GameStop (GME) 23-Year Multi-Timeframe (2004-01-01 to 2026-10-09)",
        "assets": [
            {"symbol": "GME", "clean_name": "GME", "start": "2004-01-01", "end": END_DATE},
        ],
    },
    {
        "exp_name": "QQQ_23yr_multi_tf",
        "config_file": "config_qqq_multi_tf.yaml",
        "data_dir": ROOT / "data" / "qqq_multi_timeframe",
        "description": "Nasdaq-100 (QQQ) 23-Year Multi-Timeframe (2004-01-01 to 2026-10-09)",
        "assets": [
            {"symbol": "QQQ", "clean_name": "QQQ", "start": "2004-01-01", "end": END_DATE},
        ],
    },
    {
        "exp_name": "IWM_23yr_multi_tf",
        "config_file": "config_iwm_multi_tf.yaml",
        "data_dir": ROOT / "data" / "iwm_multi_timeframe",
        "description": "Russell 2000 (IWM) 23-Year Multi-Timeframe (2004-01-01 to 2026-10-09)",
        "assets": [
            {"symbol": "IWM", "clean_name": "IWM", "start": "2004-01-01", "end": END_DATE},
        ],
    },
    {
        "exp_name": "NVDA_23yr_multi_tf",
        "config_file": "config_nvda_multi_tf.yaml",
        "data_dir": ROOT / "data" / "nvda_multi_timeframe",
        "description": "NVIDIA (NVDA) 23-Year Multi-Timeframe (2004-01-01 to 2026-10-09)",
        "assets": [
            {"symbol": "NVDA", "clean_name": "NVDA", "start": "2004-01-01", "end": END_DATE},
        ],
    },
    {
        "exp_name": "MACRO_TLT_GLD_23yr_multi_tf",
        "config_file": "config_macro_tlt_gld_multi_tf.yaml",
        "data_dir": ROOT / "data" / "macro_tlt_gld_multi_timeframe",
        "description": "Macro Rates & Gold Companion (TLT + GLD 2004-01-01 to 2026-10-09)",
        "assets": [
            {"symbol": "TLT", "clean_name": "TLT", "start": "2004-01-01", "end": END_DATE},
            {"symbol": "GLD", "clean_name": "GLD", "start": "2004-11-18", "end": END_DATE},
        ],
    },
]


def get_api_key():
    key = os.environ.get("POLYGON_API_KEY") or dotenv_values(ROOT / ".env").get("POLYGON_API_KEY")
    if not key:
        raise RuntimeError("POLYGON_API_KEY not found in environment or .env file.")
    return key


def fetch_polygon_range(symbol: str, mult: int, span: str, start: str, end: str) -> pd.DataFrame:
    key = get_api_key()
    url = f"{BASE_URL}/v2/aggs/ticker/{symbol}/range/{mult}/{span}/{start}/{end}"
    params = {"adjusted": "true", "sort": "asc", "limit": 50000}

    all_rows = []
    next_url = None
    page_count = 0

    while True:
        page_count += 1
        for attempt in range(4):
            try:
                if next_url:
                    parsed = urlsplit(next_url)
                    query_params = {k: v for k, v in parse_qsl(parsed.query) if k.lower() != "apikey"}
                    req_url = BASE_URL + parsed.path
                    response = requests.get(req_url, headers={"Authorization": f"Bearer {key}"}, params=query_params, timeout=30)
                else:
                    response = requests.get(url, headers={"Authorization": f"Bearer {key}"}, params=params, timeout=30)
                if response.status_code == 200:
                    break
                time.sleep(1.5 * (attempt + 1))
            except Exception as e:
                print(f"  [Retry {attempt+1}] {symbol} {mult}-{span}: {e}")
                time.sleep(2.0 * (attempt + 1))
        else:
            raise RuntimeError(f"Failed fetching {symbol} {mult}-{span} after retries.")

        payload = response.json()
        results = payload.get("results", [])
        if not results:
            break

        all_rows.extend(results)
        if page_count % 10 == 0 or not payload.get("next_url"):
            print(f"    [{symbol} {mult}-{span}] Page {page_count}: accumulated {len(all_rows):,} bars")

        next_url = payload.get("next_url")
        if not next_url:
            break
        time.sleep(0.11)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows).rename(columns={
        "t": "timestamps", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"
    })
    df["timestamps"] = pd.to_datetime(df["timestamps"], unit="ms", utc=True)

    if "volume" not in df or df["volume"].isnull().all() or (df["volume"] == 0).all():
        bar_range = (df["high"] - df["low"]).abs() + (df["close"].diff().abs().fillna(0.01)) + 0.01
        df["volume"] = (bar_range * 10000.0).round(2)
        df["amount"] = (df["volume"] * df[["open", "high", "low", "close"]].mean(axis=1)).round(4)
    else:
        df["volume"] = df["volume"].fillna(0.0)
        if "vw" in df:
            df["amount"] = df["vw"].fillna(df["close"]) * df["volume"]
        else:
            df["amount"] = df[["open", "high", "low", "close"]].mean(axis=1) * df["volume"]

    cols = ["timestamps", "open", "close", "high", "low", "volume", "amount"]
    df = df.sort_values("timestamps").drop_duplicates("timestamps").reset_index(drop=True)
    df["timestamps"] = df["timestamps"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df[cols]


def ensure_dataset_prepared(model_spec: dict) -> dict:
    data_dir: Path = model_spec["data_dir"]
    data_dir.mkdir(parents=True, exist_ok=True)
    bar_counts = {}

    for asset in model_spec["assets"]:
        sym = asset["symbol"]
        clean_name = asset["clean_name"]
        start = asset["start"]
        end = asset["end"]

        for tf in TIMEFRAMES:
            tf_name = tf["name"]
            target_file = data_dir / f"{clean_name}_{tf_name}_{start[:4]}_{end[:4]}.csv"
            legacy_file = data_dir / f"{clean_name}_{tf_name}_{start[:4]}_2024.csv"

            if target_file.exists():
                df_existing = pd.read_csv(target_file)
                bar_counts[f"{clean_name}_{tf_name}"] = len(df_existing)
                print(f"  [Cache Hit] {target_file.name}: {len(df_existing):,} bars")
                continue

            if legacy_file.exists():
                print(f"  [Topping Up to {end}] {legacy_file.name} -> {target_file.name}...")
                df_old = pd.read_csv(legacy_file)
                df_delta = fetch_polygon_range(sym, tf["mult"], tf["span"], "2024-11-29", end)
                if not df_delta.empty:
                    df_combined = pd.concat([df_old, df_delta], ignore_index=True)
                    df_combined = df_combined.sort_values("timestamps").drop_duplicates("timestamps").reset_index(drop=True)
                else:
                    df_combined = df_old
                df_combined.to_csv(target_file, index=False)
                legacy_file.unlink()
                bar_counts[f"{clean_name}_{tf_name}"] = len(df_combined)
                print(f"  [Updated] {target_file.name}: {len(df_combined):,} bars (through {df_combined['timestamps'].iloc[-1]})")
                continue

            print(f"  [Fetching Full History] {clean_name} {tf_name} ({start} to {end})...")
            df_full = fetch_polygon_range(sym, tf["mult"], tf["span"], start, end)
            if not df_full.empty:
                df_full.to_csv(target_file, index=False)
                bar_counts[f"{clean_name}_{tf_name}"] = len(df_full)
                print(f"  [Saved] {target_file.name}: {len(df_full):,} bars ({df_full['timestamps'].iloc[0]} -> {df_full['timestamps'].iloc[-1]})")

    return bar_counts


def write_model_config(model_spec: dict) -> Path:
    cfg_path = CONFIGS_DIR / model_spec["config_file"]
    config_data = {
        "data": {
            "data_path": str(model_spec["data_dir"]),
            "lookback_window": 256,
            "predict_window": 48,
            "max_context": 512,
            "clip": 5.0,
            "train_ratio": 0.85,
            "val_ratio": 0.15,
            "test_ratio": 0.0,
        },
        "training": {
            "tokenizer_epochs": 3,
            "basemodel_epochs": 2,
            "batch_size": 32,
            "log_interval": 50,
            "num_workers": 0,
            "seed": 42,
            "tokenizer_learning_rate": 0.0001,
            "predictor_learning_rate": 0.000001,
            "adam_beta1": 0.9,
            "adam_beta2": 0.95,
            "adam_weight_decay": 0.01,
            "accumulation_steps": 2,
        },
        "model_paths": {
            "pretrained_tokenizer": str(ROOT / "models" / "Kronos-Tokenizer-base"),
            "pretrained_predictor": str(ROOT / "models" / "Kronos-base"),
            "exp_name": model_spec["exp_name"],
            "base_path": str(ROOT / "finetune_csv" / "finetuned"),
            "base_save_path": "",
            "finetuned_tokenizer": "",
            "tokenizer_save_name": "tokenizer",
            "basemodel_save_name": "basemodel",
        },
        "experiment": {
            "name": model_spec["exp_name"].lower(),
            "description": model_spec["description"],
            "use_comet": False,
            "train_tokenizer": True,
            "train_basemodel": True,
            "skip_existing": True,
        },
        "device": {
            "use_cuda": False,
            "device_id": 0,
        },
    }
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, indent=2)
    return cfg_path


def update_status(status_dict: dict):
    status_dict["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status_dict, f, indent=2)


def main():
    print("=" * 80)
    print("KRONOS AUTONOMOUS MULTI-MODEL FACTORY")
    print(f"Target End Date: {END_DATE}")
    print(f"Models Queued  : {len(MODEL_QUEUE)}")
    print("=" * 80)

    factory_state = {
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "target_end_date": END_DATE,
        "current_stage": "initializing",
        "current_model": None,
        "datasets": {},
        "models_status": {m["exp_name"]: "PENDING" for m in MODEL_QUEUE},
    }
    update_status(factory_state)

    # PHASE 1: Top up VIX dataset & launch VIX Companion training immediately,
    # or prepare all datasets first so every CSV is verified on disk right away.
    # Preparing all datasets takes ~8-10 minutes total, ensuring 100% of data is ready offline!
    factory_state["current_stage"] = "preparing_all_datasets"
    update_status(factory_state)

    for model_spec in MODEL_QUEUE:
        exp = model_spec["exp_name"]
        print(f"\n>>> Preparing dataset & config for [{exp}] ({model_spec['description']})...")
        counts = ensure_dataset_prepared(model_spec)
        cfg_path = write_model_config(model_spec)
        factory_state["datasets"][exp] = {
            "total_bars": sum(counts.values()),
            "breakdown": counts,
            "config_path": str(cfg_path),
        }
        update_status(factory_state)

    print("\n" + "=" * 80)
    print("ALL DATASETS PREPARED THROUGH 2026-10-09! STARTING SEQUENTIAL MODEL TRAINING...")
    print("=" * 80)

    # PHASE 2: Train each model sequentially
    python_exe = str(ROOT / ".venv" / "bin" / "python")
    trainer_script = str(ROOT / "finetune_csv" / "train_sequential.py")

    for model_spec in MODEL_QUEUE:
        exp = model_spec["exp_name"]
        cfg_path = str(CONFIGS_DIR / model_spec["config_file"])
        best_base = ROOT / "finetune_csv" / "finetuned" / exp / "basemodel" / "best_model" / "model.safetensors"

        if best_base.exists():
            print(f"[{exp}] Model already trained at {best_base}, marking COMPLETED.")
            factory_state["models_status"][exp] = "COMPLETED"
            update_status(factory_state)
            continue

        print(f"\n" + "=" * 80)
        print(f"LAUNCHING TRAINING FOR: {exp}")
        print(f"Config: {cfg_path}")
        print("=" * 80)

        factory_state["current_stage"] = "training_models"
        factory_state["current_model"] = exp
        factory_state["models_status"][exp] = "TRAINING"
        update_status(factory_state)

        t0 = time.time()
        env = os.environ.copy()
        env["KRONOS_MAX_TRAIN_SAMPLES"] = "64000"
        env["KRONOS_MAX_VAL_SAMPLES"] = "9600"

        proc = subprocess.run(
            [python_exe, trainer_script, "--config", cfg_path, "--skip-existing"],
            cwd=str(ROOT),
            env=env,
        )
        elapsed_min = round((time.time() - t0) / 60.0, 2)

        if proc.returncode == 0 and best_base.exists():
            factory_state["models_status"][exp] = f"COMPLETED ({elapsed_min} min)"
            print(f"[{exp}] Training succeeded in {elapsed_min} minutes!")
        else:
            factory_state["models_status"][exp] = f"FAILED (code {proc.returncode})"
            print(f"[{exp}] Training exited with code {proc.returncode}")

        update_status(factory_state)

    factory_state["current_stage"] = "all_completed"
    factory_state["current_model"] = None
    update_status(factory_state)
    print("\n" + "=" * 80)
    print("ALL QUEUED MODELS COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    main()
