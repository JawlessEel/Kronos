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
not a live feed. The CSV controls perform historical forecast comparisons. For
current provider data, use the Polygon panel below. The application does not place
trades. Historical results are saved in `webui/prediction_results/`.
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

## Polygon live market data

The server reads `POLYGON_API_KEY` from a private, Git-ignored `.env` file in the
project root, or from an existing process environment variable. `.env.example`
documents the setting names. The browser never receives the key. Keep the key out
of URLs, screenshots, logs and Git; no changes to your original provider setup
are required. Restart Kronos after installation to register the live endpoints.

1. Load **Kronos-base** on **CUDA** in the Control Panel.
2. In **Polygon market data**, enter **SPY**, AAPL, or another US stock/ETF.
3. Choose 1-, 5-, or 15-minute candles and click **Fetch latest candles**.
4. The live chart shows the newest **400 completed regular-session candles**.
   The status gives the last candle's timestamp/close, fetch time, market-open state,
   and a data-delay notice. Extended-hours and unfinished bars are excluded.
5. Click **Forecast latest candles** to predict the next 1–120 candles (30 by default).
   Future timestamps follow the NYSE calendar, including holidays, early closes and
   daylight-saving changes. Both stocks and ETFs use this US regular-session calendar.
6. Optionally click **Start 60-second refresh**, then **Stop refresh** to stop it.
   Refresh updates observed candles, not forecasts. It stops when the tab is hidden,
   after three consecutive failures, or after four hours; it requires no background service.

This uses the Polygon **REST aggregate-candle feed**, not a tick-by-tick WebSocket
stream. Subscription entitlements determine whether data is end-of-day, delayed,
or real-time. An `OK` response does not prove real-time entitlement. At weekends
and after hours, the last completed regular-session bar can legitimately be old.
Forecasts always start after the latest available bar; with delayed data, some
forecast timestamps may already be in the past relative to your wall clock.

The adapter queries the latest 30 calendar days using split-adjusted descending
aggregates with a 50,000 base-bar limit, then sorts and validates OHLCV, estimates
turnover as VWAP times share volume, and filters exchange sessions. Missing
trade intervals are not filled with invented prices. Responses are cached for
60 seconds per symbol/interval. Network requests have bounded timeouts and do not
automatically retry. Subscription denials and rate limits produce explicit errors.

Live forecasts are timestamped JSON files under `outputs/live/`. They contain
the forecast anchor and freshness metadata, with no fabricated future actuals or
historical error scores. The original CSV workflow remains available separately.

Verification in PowerShell, with the local server running:

```powershell
Set-Location 'D:\projects\kronos'
.\.venv\Scripts\python.exe scripts\verify_live_feed.py
.\.venv\Scripts\python.exe -m pytest tests\test_polygon_feed.py -q
```

Provider documentation: https://massive.com/docs/rest/stocks/aggregates/custom-bars
(Polygon now operates as Massive; the existing Polygon URL and keys remain supported).
