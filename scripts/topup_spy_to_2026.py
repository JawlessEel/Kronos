"""
Top-Up SPY 20-Year Dataset (2004-2024) through 2026-10-09 (23 Years Total)
and configure the fast 1-epoch Experience Replay Incremental Fine-Tuning pass
starting from the already-trained SPY_20yr_multi_timeframe weights.
"""
import shutil
from pathlib import Path
import pandas as pd
import yaml

from scripts.run_model_factory_queue import fetch_polygon_range, TIMEFRAMES, ROOT, CONFIGS_DIR

SPY_DATA_DIR = ROOT / "data" / "spy_multi_timeframe"
END_DATE = "2026-10-09"


def main():
    print("=" * 80)
    print(f"TOPPING UP SPY MULTI-TIMEFRAME DATASET TO {END_DATE}")
    print("=" * 80)

    total_bars = 0
    for tf in TIMEFRAMES:
        tf_name = tf["name"]
        old_file = SPY_DATA_DIR / f"SPY_{tf_name}_2004_2024.csv"
        new_file = SPY_DATA_DIR / f"SPY_{tf_name}_2004_2026.csv"

        if new_file.exists():
            df = pd.read_csv(new_file)
            print(f"  [Cache Hit] {new_file.name}: {len(df):,} bars ({df['timestamps'].iloc[0]} -> {df['timestamps'].iloc[-1]})")
            total_bars += len(df)
            continue

        if not old_file.exists():
            raise FileNotFoundError(f"Expected {old_file} not found.")

        print(f"  [Topping Up] {old_file.name} -> {new_file.name} (2024-11-29 to {END_DATE})...")
        df_old = pd.read_csv(old_file)
        df_delta = fetch_polygon_range("SPY", tf["mult"], tf["span"], "2024-11-29", END_DATE)

        if not df_delta.empty:
            df_merged = pd.concat([df_old, df_delta], ignore_index=True)
            df_merged = df_merged.sort_values("timestamps").drop_duplicates("timestamps").reset_index(drop=True)
        else:
            df_merged = df_old

        df_merged.to_csv(new_file, index=False)
        old_file.unlink()
        total_bars += len(df_merged)
        print(f"  [Saved] {new_file.name}: {len(df_merged):,} bars ({df_merged['timestamps'].iloc[0]} -> {df_merged['timestamps'].iloc[-1]})")

    print(f"\nTotal SPY 2004-2026 Multi-Timeframe Bars: {total_bars:,}")

    # Copy already-trained SPY 20yr tokenizer into SPY_23yr_multi_tf/tokenizer/best_model
    src_tok = ROOT / "finetune_csv" / "finetuned" / "SPY_20yr_multi_timeframe" / "tokenizer" / "best_model"
    src_base = ROOT / "finetune_csv" / "finetuned" / "SPY_20yr_multi_timeframe" / "basemodel" / "best_model"

    dst_exp_dir = ROOT / "finetune_csv" / "finetuned" / "SPY_23yr_multi_tf"
    dst_tok = dst_exp_dir / "tokenizer" / "best_model"
    dst_tok.parent.mkdir(parents=True, exist_ok=True)
    if dst_tok.exists():
        shutil.rmtree(dst_tok)
    shutil.copytree(src_tok, dst_tok)
    print(f"Copied pre-adapted SPY Tokenizer -> {dst_tok}")

    # Create incremental experience-replay config
    cfg_path = CONFIGS_DIR / "config_spy_23yr_topup.yaml"
    config_data = {
        "data": {
            "data_path": str(SPY_DATA_DIR),
            "lookback_window": 256,
            "predict_window": 48,
            "max_context": 512,
            "clip": 5.0,
            "train_ratio": 0.92,
            "val_ratio": 0.08,
            "test_ratio": 0.0,
        },
        "training": {
            "tokenizer_epochs": 1,
            "basemodel_epochs": 1,
            "batch_size": 32,
            "log_interval": 50,
            "num_workers": 0,
            "seed": 42,
            "tokenizer_learning_rate": 0.00005,
            "predictor_learning_rate": 0.0000005,
            "adam_beta1": 0.9,
            "adam_beta2": 0.95,
            "adam_weight_decay": 0.01,
            "accumulation_steps": 2,
        },
        "model_paths": {
            "pretrained_tokenizer": str(src_tok),
            "pretrained_predictor": str(src_base),
            "exp_name": "SPY_23yr_multi_tf",
            "base_path": str(ROOT / "finetune_csv" / "finetuned"),
            "base_save_path": "",
            "finetuned_tokenizer": str(dst_tok),
            "tokenizer_save_name": "tokenizer",
            "basemodel_save_name": "basemodel",
        },
        "experiment": {
            "name": "kronos_spy_23yr_topup",
            "description": "Incremental experience-replay top-up of SPY 20yr model through 2026-10-09",
            "use_comet": False,
            "train_tokenizer": False,
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
    print(f"Wrote incremental SPY top-up config -> {cfg_path}")


if __name__ == "__main__":
    main()
