# Try Kronos on Windows

Double-click `Start-Kronos.cmd`, then open http://127.0.0.1:7070 in your browser.
Leave the console running. Press Ctrl+C there to stop, or double-click `Stop-Kronos.cmd`.
No administrator permissions or environment activation are needed.

1. Select **Kronos-base** and **CUDA (NVIDIA GPU)**, then click **Load Model**.
2. Select **HK_ali_09988_kline_5min_all.csv**, then click **Load Data**.
3. Leave temperature at **1.0**, top-p at **0.9**, and sample count at **1** for the first trial.
4. Click **Start Prediction**. The defaults use 400 historical candles to predict the following 120; both lengths are editable.
5. Compare the forecast with the held-out actual candles, and move the time-window slider to try another period.

The included CSV is upstream historical Alibaba Hong Kong (09988) five-minute data,
not a live feed. The CSV controls perform historical forecast comparisons. For
current provider data, use the Polygon panel below. The application does not place
trades. Historical results are saved in `webui/prediction_results/`.
The setup-check report and forecast are in `outputs/`.

## Use your own data

Copy a CSV into `data/`, reload the page, select it, and click Load Data.
Use at least lookback + prediction-length chronological rows (520 for the defaults), preferably more so the slider has room.
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
4. Set **Chart history candles** (16–10,000, default 1,000). The live chart displays that many completed regular-session candles when your subscription has sufficient history.
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

The adapter queries up to 365 calendar days using split-adjusted descending
aggregates with a 50,000 base-bar page limit and at most 12 additional same-provider pages, then sorts and validates OHLCV, estimates
turnover as VWAP times share volume, and filters exchange sessions. Missing
trade intervals are not filled with invented prices. Responses are cached for
60 seconds per symbol/interval/history-length combination. Network requests have bounded timeouts and do not
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

## Customizable charts and forecast lengths

Each live and historical chart has its own **Expand chart**, **Fullscreen**,
**Reset zoom**, export controls, and **Chart settings and indicators** editor.
Expand hides the control column and uses the full page width; Restore controls
brings it back. Fullscreen opens a viewport overlay that also works inside the
Codex browser. Click Fullscreen again or press Escape to close it.

- Set height (300–1,800 px), font size, dark/light theme, candles/OHLC/close line,
  grid, legend, crosshair, log price scale, mouse-wheel zoom, and range slider.
- Toggle history, model forecast, or held-out actuals separately.
- Set separate rising/falling colors for observed and forecast candles.
- Add up to 30 moving averages. Each supports SMA/EMA/WMA/RMA, period 1–5,000,
  open/high/low/close/HL2/HLC3/OHLC4 source, color, width, offset, and line style.
- Optional Bollinger bands (period/deviations), observed session VWAP, RSI
  (period), MACD (fast/slow/signal), and a volume pane.
- Pan/zoom using the chart toolbar. Draw lines, freehand paths or rectangles,
  and erase shapes with Plotly's modebar. Drawings are temporary and are not
  included in exported settings; exports of the chart include visible drawings.
- Calendar gaps are hidden by default using an ordered candle axis, with real
  timestamps preserved. Enable Show calendar gaps for elapsed calendar time.
- Export PNG (1,600 px wide, 2x scale), candles CSV, or settings JSON. Import
  settings JSON to restore/share the chart editor configuration. Settings are
  shared between both charts and saved in this browser. Forecast control values
  are also saved locally, separately from chart settings JSON.

Base/small model lookback supports **16–512**, and forecast length **1–512**.
Mini supports lookback **16–2,048**, and forecast length **1–2,048**.
The UI limits follow the selected model; server validation follows the actually
loaded model. Load the selected model after switching. These are the published
context capacities, and the installed decoder returns only its final context;
the UI does not pretend longer horizons work. More candles and samples take more
time and memory. Sampling controls support temperature 0.1–2, top-p (0,1], and
1–20 samples. Samples are averaged, not a confidence interval.

Chart history can exceed model context. Kronos receives only the most recent
selected lookback; indicators use all displayed history. Moving averages and
bands continue through generated candles with dashed forecast-derived segments.
Indicator warm-up values remain empty until a full period is available.
VWAP is observed only and resets at the New York date boundary; the first visible
session can be partial if history starts mid-session. RSI/MACD include generated
prices after the anchor; they do not represent future observations. Historical
CSV VWAP uses that same New York reset convention. Indicators are chart overlays
and do not change the pretrained model's inputs.

The historical time window selects exact candle rows, rather than interpolating
elapsed time across session closures. API callers can use `start_index` or retain
the original `start_date` interface. Both chart legends use actual selected lengths.

Validation commands in PowerShell from this folder:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
node tests/test_chart_math.cjs
.\.venv\Scripts\python.exe scripts/verify_live_feed.py
```

`pytest tests` covers the supported regression suite. A repository-wide `pytest`
also collects the optional `finetune/qlib_test.py`, which requires the separately
uninstalled Qlib fine-tuning stack. No Qlib dependencies were added for chart work.

This chart editor has built-in indicators; it does not execute Pine Script or
import arbitrary TradingView indicators. Model capacities:
https://github.com/shiyu-coder/Kronos#-model-zoo

## Download the whole Web UI as PDF

Click **Download whole UI as PDF** in the top header. The export includes current
control values, model selection, market-data status, both generated charts,
indicator settings, and the visible historical comparison results. It includes
the control panel even when Expand chart hides it, opens chart-setting panels in
the snapshot, and captures the full displayed comparison table. Charts retain
their current zoom and indicators. No new market request or forecast is triggered.

The PDF is an image-based dashboard snapshot, paginated on landscape A4 with
capture timestamps and page numbers. The dashboard pages are raster snapshots; the appended predicted-candle tables are searchable vector text.
No chart is invented when a section has not been generated. Exports are generated
locally using pinned, integrity-verified html2canvas 1.4.1 and pdf-lib 1.17.1 assets
included under webui/static/vendor (licenses and provenance included); no snapshot
is uploaded. The original browser page is not rearranged during capture.

Example filename: `Kronos-WebUI-2026-10-04T08-00-00-123Z-a1b2c3d4.pdf`.
Each name includes a UTC timestamp to milliseconds plus a random suffix, so
successive exports do not overwrite previous downloads. Your browser chooses
its normal Downloads folder or asks for a destination. Existing PDFs are retained.
Export is disabled while one is running and gives a visible success/error status.
Very large dashboards have a bounded capture-size/page budget and produce an
explicit error rather than exhausting browser memory.

## Predicted candle data

After a live or historical forecast, the chart is followed by **predicted candles**.
Every model output row is available in a scrollable table, with candle-start date
and time, open/high/low/close, close change, close-change percent, movement/body,
volume and turnover. Live timestamps use New York ET (EDT/EST); historical CSV
rows retain source timestamps. Movement compares close with the preceding close;
body compares close with this candle's open. The first row uses the observed
anchor close. The summary shows first/last time and final change from the anchor.
Prices show four decimals, percentages two; CSV exports retain raw model values.
Volume and turnover are model estimates, not future observations. None of these
movements is a completed trade or guarantee of future prices.

**Download predicted candles CSV** saves all rows with exact ISO timestamps and
unrounded numeric fields. **Download whole UI as PDF** appends all prediction rows
as clean, searchable, paginated tables with repeated headers, even when the UI
shows only the top part of its scrollable table. Native inputs in the dashboard
snapshot are rendered as static aligned boxes/sliders to avoid Adobe clipping.

Additional check: `node tests/test_prediction_candles.cjs`.

The Quality column flags impossible OHLC ranges and negative volume/turnover.
Kronos predicts channels independently and can produce inconsistent candle bounds;
raw outputs are retained in the UI, CSV and PDF rather than silently repaired.
