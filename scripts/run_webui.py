"""Run the existing UI using local weights and a localhost-only server."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HF_HUB_CACHE", str(ROOT / ".cache" / "huggingface"))
os.environ.setdefault("HF_XET_CACHE", str(ROOT / ".cache" / "xet"))

import torch
from webui import app as ui


def configure_local_models():
    torch.set_num_threads(1)
    if not ui.MODEL_AVAILABLE:
        raise RuntimeError("Kronos imports failed. Check the project environment.")
    for config in ui.AVAILABLE_MODELS.values():
        for key in ("model_id", "tokenizer_id"):
            local = ROOT / "models" / config[key].split("/")[-1]
            if not (local / "config.json").is_file() or not (local / "model.safetensors").is_file():
                raise FileNotFoundError(f"Missing local weights or configuration: {local}")
            config[key] = str(local)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7070)
    args = parser.parse_args()
    configure_local_models()
    from webui.polygon_feed import register_live_feed
    register_live_feed(ui.app, ui)
    print(f"Open http://127.0.0.1:{args.port}; Ctrl+C stops the server.", flush=True)
    ui.app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
