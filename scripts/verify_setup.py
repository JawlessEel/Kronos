"""Exercise the real UI endpoints and save a reproducible setup-check report."""
import json
from pathlib import Path
import time

import numpy as np
import torch
from run_webui import ROOT, configure_local_models, ui


def checked(response):
    payload = response.get_json()
    if response.status_code != 200 or not payload.get("success"):
        raise RuntimeError(f"HTTP {response.status_code}: {payload}")
    return payload


def main():
    configure_local_models()
    torch.manual_seed(123)
    np.random.seed(123)
    device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
    client = ui.app.test_client()
    sample = ROOT / "data" / "HK_ali_09988_kline_5min_all.csv"
    assert client.get("/").status_code == 200
    assert any(item["path"] == str(sample) for item in client.get("/api/data-files").get_json())
    checked(client.post("/api/load-data", json={"file_path": str(sample)}))
    for model_key in ("kronos-mini", "kronos-small"):
        checked(client.post("/api/load-model", json={"model_key": model_key, "device": "cpu"}))
    checked(client.post("/api/load-model", json={"model_key": "kronos-base", "device": device}))
    start = time.perf_counter()
    payload = checked(client.post("/api/predict", json={
        "file_path": str(sample), "lookback": 400, "pred_len": 120,
        "temperature": 1.0, "top_p": 0.9, "sample_count": 1,
        "start_date": "2019-11-26T09:35",
    }))
    assert len(payload["prediction_results"]) == 120
    assert len(payload["actual_data"]) == 120
    for pred, actual in zip(payload["prediction_results"], payload["actual_data"]):
        assert pred["timestamp"] == actual["timestamp"], (pred["timestamp"], actual["timestamp"])
        assert all(np.isfinite(pred[key]) for key in ("open", "high", "low", "close"))
    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)
    (output / "setup-check-forecast.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    report = {"device": device, "gpu": torch.cuda.get_device_name(0) if device == "cuda" else None,
              "torch": torch.__version__, "rows_predicted": 120, "actual_rows": 120,
              "seconds": round(time.perf_counter() - start, 2),
              "peak_gpu_memory_mb": round(torch.cuda.max_memory_allocated() / 1024**2, 1) if device == "cuda" else None}
    (output / "setup-check.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
