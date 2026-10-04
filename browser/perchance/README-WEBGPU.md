# Utterly Prediction — real browser-local Kronos mini

This package replaces the placeholder worker/exporter supplied in the source ZIP with four working ONNX graphs and a complete autoregressive WebGPU pipeline. Original downloads, the local Kronos checkout, its Polygon configuration, and the live Perchance folder mirror were preserved.

## Try the complete workbench locally

Extract the ZIP into a new folder. In PowerShell, change into that extracted folder and run:

```powershell
python -m http.server 7080 --bind 127.0.0.1
```

Open `http://127.0.0.1:7080/` in a browser with working WebGPU. Choose OKX spot, load market data, load the model, and generate a forecast. To stop the temporary web server, press Ctrl+C in its terminal. No inference service is needed: this server only serves static files. Localhost is a secure context for WebGPU. Public hosting must use HTTPS. Opening the HTML directly as a file is not the supported launch method.

`index.html` is the complete Perchance HTML panel; `top-panel.txt` is the complete lists panel. Perchance's narrative AI plugin remains separate and will require the Perchance environment when using the AI Analyst. The standalone page can fetch public data and run Kronos without that plugin.

## Verified behavior

- Four actual ONNX sessions using ONNX Runtime Web 1.22.0's WebGPU entry point.
- SHA-256 and exact size checks for each model file, including cached files; session execution before reporting ready.
- Full tokenizer encode, coarse-token predictor, conditional fine-token predictor, tokenizer decode, float32 preprocessing matching upstream, and inverse normalization.
- Dynamic context lengths: graph parity checked at 16, 32 and 256 candles.
- Complete 256-to-24 greedy forecast compared against upstream Python and ONNX CPU using completed public OKX BTC-USDT hourly candles.
- Desktop Chrome 154.0.8037.93 produced the full WebGPU parity forecast in 1.18 seconds. This fixture's OHLC values matched Python exactly at float32 output precision. Largest error across all six channels was 14 in quote turnover, within `atol=0.003, rtol=0.0002`. This is an engineering parity check, not a forecast-accuracy evaluation.
- The complete workbench generated a sampled 24-candle forecast from 316 completed live-feed candles in approximately 1.7 seconds; timestamps, quality flags, CSV and two-page PDF were checked. Invalid model OHLC is flagged, not silently repaired.
- OKX pagination now requests older pages with `after`, preventing repeated recent pages and insufficient lookback.
- Eastern-time features use a 24-hour clock and were checked across winter, summer, and the autumn DST fold.
- Forecast errors remain visible, stale selection/data results are rejected, and cancellation terminates the worker and requires model reload.
- Model persistence is opt-in; a second load produced four verified cache hits. Scoped removal was followed by a fresh zero-hit load. Cache quota failures are surfaced as warnings while allowing an in-memory load. No unrelated browser storage is removed.

GPU parity evidence is in `src/kronos-local/parity/browser-greedy.json`; Python vectors are in `python-reference.json`; graph checks are in `models/graph-parity.json`. The runtime preserves raw predictions and labels the statistical alternative separately.

The model files total 33,595,885 bytes (about 32.04 MiB); ONNX Runtime JS/WASM downloads are additional. This is FP32, not a quantized build. Conservative browser limits remain 256 lookback / 24 horizon / 1 sample. Display history is independent.

## Perchance integration and public hosting

The package is a tested local build. It has NOT been published into the live generator, and its model URLs currently resolve relative to the packaged static assets. Public HTTPS/CORS hosting remains necessary before anyone can load these artifacts from Perchance.

Host `src/kronos-local/` and `src/pulse-workbench.js` on a static HTTPS host that serves `.js` as JavaScript, `.json` as JSON, `.onnx` as binary data, and permits the actual Perchance preview/published origins through CORS. No account or token should be required to download them. Keep each validated release immutable. Do not expose the local machine or an inference port to provide downloads.

The loader supports `window.KronosLocalConfig.assetBase`, set before loading `kronos-engine.js`, to use the actual hosted `kronos-local/` directory rather than a Perchance iframe-relative path. Use the real hosting URL after publication, and replace the panel script URLs with their actual hosted URLs or supported Perchance source-file URLs, including `tradingview-contract.js` and `tradingview-bridge.js` for the Chrome bridge. Do not insert invented URLs or mark an untested host ready. All model URLs in the manifest are resolved against the manifest's URL, not a blob worker URL.

After uploading, test loading from the actual Perchance preview and published iframe: CORS, runtime modules/WASM, all four model hashes, smoke tests, and a real forecast. Do not assume that importing a source ZIP publishes binary assets. Retain the user's current plugin imports and unrelated source files. Apply source changes as a reviewable draft; publishing the generator is a separate action.

## Rebuild in an isolated export environment

These dependencies are build-time only. Do not install this requirements file over a working CUDA/PyTorch environment. With a cloned upstream-compatible Kronos tree and local model/tokenizer directories:

```powershell
python -m venv .venv-export
.\.venv-export\Scripts\python.exe -m pip install -r src\kronos-local\exporter\requirements.txt
.\.venv-export\Scripts\python.exe src\kronos-local\exporter\export_browser.py --kronos-root ..\Kronos --model ..\Kronos\models\Kronos-mini --tokenizer ..\Kronos\models\Kronos-Tokenizer-2k --out src\kronos-local\models
Copy-Item -LiteralPath src\kronos-local\models\manifest.json -Destination src\kronos-local\manifest.json
.\.venv-export\Scripts\python.exe src\kronos-local\exporter\verify_forecast.py --kronos-root ..\Kronos --model ..\Kronos\models\Kronos-mini --tokenizer ..\Kronos\models\Kronos-Tokenizer-2k --assets src\kronos-local
```

Adjust the relative model paths to the real checkout. Exporter provenance: upstream-compatible source revision `6a853d53c644787e983742117b201feeb5b564ef`, PyTorch 2.7.1+cu128 in the existing build environment, ONNX 1.18.0, ONNX Runtime CPU 1.22.0. Export dependencies for this run were isolated in a separate target directory; the project's installed packages were not replaced.

The exporter intentionally writes `graph-validated` status. Browser session smoke tests remain mandatory. A new export needs a new complete browser parity run before being described as browser-validated. Native int32 Gather inputs are essential: the tested float-to-int64 conversion path produced incorrect GPU embeddings even though ONNX CPU parity passed.

`kronos-preprocess.js` is the canonical preprocessing source. `preprocess-module.js` is its worker-importable copy, with the global declaration changed to a local declaration and `export {KronosPre}` appended. Keep the two in sync when changing preprocessing.

## Remaining validation limits

No physical iPhone 16 Pro or Safari GPU inference test was available. Peak GPU/JS memory, first-download time, cache-hit load time, offline startup, quota eviction, corrupt-cache recovery, and device-loss behavior have not been benchmarked end to end. Keep the page active during prediction: background tabs were observed to pause GPU readback. Unsupported devices show an error; they do not silently produce a statistical result labeled as Kronos.

Stock feed access depends on CORS, provider limits, session history, and the Perchance fetch plugin. CSV remains the explicit import route. Stocks do not receive Polygon data in this browser build. Exchange and stock adapters were retained; the current live end-to-end run used OKX, not every provider.

## Licenses and preservation

Kronos source/model attribution: ShiYu 2025, MIT; source `https://github.com/shiyu-coder/Kronos`, model IDs `NeoQuasar/Kronos-mini` and `NeoQuasar/Kronos-Tokenizer-2k`. See `LICENSE-KRONOS.txt`. ONNX Runtime is Microsoft's MIT-licensed runtime, loaded from the pinned package CDN. Existing application modules, icons, plugins, watchlists, presets and exports were preserved except the scoped corrections described above. No private keys, passwords, API tokens, or Polygon credentials are included.
