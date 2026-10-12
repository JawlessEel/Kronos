#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo 'Missing macOS environment. See MACOS-QUICKSTART.md.' >&2
  exit 1
fi
export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export HF_HUB_CACHE="$ROOT/.cache/huggingface" HF_XET_CACHE="$ROOT/.cache/xet"
export HF_HUB_OFFLINE=1
exec "$ROOT/.venv/bin/python" "$ROOT/scripts/run_webui.py" "$@"
