# Try Kronos on Windows

Double-click `Start-Kronos.cmd`, then open http://127.0.0.1:7070 in your browser.
Leave the console running. Press Ctrl+C there to stop, or double-click `Stop-Kronos.cmd`.
No administrator permissions or environment activation are needed.

1. Select **Kronos-base** and **CUDA (NVIDIA GPU)**, then click **Load Model**.
2. Select **HK_ali_09988_kline_5min_all.csv**, then click **Load Data**.
3. Leave temperature at **1.0**, top-p at **0.9**, and sample count at **1** for the first trial.
4. Click **Start Prediction**. The UI uses 400 historical candles to predict the following 120.
5. Compare the forecast with the held-out actual candles, and move the time-window slider to try another period.

The included CSV is upstream historical Alibaba Hong Kong (09988) five-minute data,
not a live feed. This UI performs historical forecast comparisons; it does not place
trades or fetch current quotes. Results are saved in `webui/prediction_results/`.
The setup-check report and forecast are in `outputs/`.

## Use your own data

Copy a CSV into `data/`, reload the page, select it, and click Load Data.
Use at least 520 chronological rows, preferably more so the slider has room.
Required columns: `open,high,low,close` and a real `timestamps`, `timestamp`, or `date` column.
Optional columns: `volume,amount`. Use consistent units, finite numeric values,
unique ascending timestamps, and one asset and interval per file.
Feather files are also supported. Without timestamps, upstream code invents hourly
dates, so always provide the actual timestamps for meaningful results.

The models are research forecasters. Assess performance on unseen periods and
against simple baselines before using forecasts in any trading strategy.

## What was installed

- Your GitHub fork on its existing default branch, `master`.
- A separate `.venv` built with the existing Python 3.12 runtime.
- PyTorch 2.7.1 with CUDA 12.8; no driver or system CUDA changes.
- Repository requirements, Web UI requirements, PyArrow for Feather support, and pytest.
- Local predictor weights for Kronos-base, small, and mini, and both matching tokenizers.
- Your Hugging Face bucket downloaded into `models/Kronos-Tokenizer-base/`.
  Despite its name, that bucket contains tokenizer weights. The base predictor came
  from `NeoQuasar/Kronos-base`; the bucket tokenizer was checksum-verified against
  `NeoQuasar/Kronos-Tokenizer-base`.

`scripts/run_webui.py` requires the local files and configures the existing UI to
load them. `Start-Kronos.cmd` enables offline model loading. The page still loads
Plotly and Axios from upstream CDN URLs, so its frontend currently requires internet.
The server binds to 127.0.0.1, with Flask debug mode and auto-reload disabled.

## Verification and rebuilding

Run in PowerShell from the repository:

```powershell
Set-Location 'D:\projects\kronos'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:HF_HUB_OFFLINE = '1'
.\.venv\Scripts\python.exe scripts\verify_setup.py
uv pip check --python .venv\Scripts\python.exe
```

The setup check loads the real local base model, exercises the Web UI endpoints,
generates 120 candles on CUDA when available, checks finite prices and matching
comparison timestamps, and saves its results. CPU is supported when CUDA is unavailable.

`requirements-windows-tested.txt` records the exact installed package versions.
To rebuild into a **new** environment without altering the installed one:

```powershell
Set-Location 'D:\projects\kronos'
$env:UV_CACHE_DIR = 'D:\projects\kronos\.cache\uv'
uv venv --python C:\Python312\python.exe .venv-rebuild
uv pip install --python .venv-rebuild\Scripts\python.exe torch==2.7.1 --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv-rebuild\Scripts\python.exe -r requirements-windows-tested.txt
```

Stop the launcher to release the port and GPU memory. Installation is contained in
this folder; preserve models, data, and forecasts before any future cleanup.

Sources: https://github.com/JawlessEel/Kronos and
https://huggingface.co/buckets/Jawless/Kronos-base-bucket.
