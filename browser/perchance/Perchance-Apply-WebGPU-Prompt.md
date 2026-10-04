Use the attached complete Kronos-WebGPU package to finish `utterly-prediction` with real browser-local Kronos inference. Preserve the existing generator and unrelated source files. Work on a reviewable draft; do not publish the generator automatically.

The package already contains working FP32 ONNX artifacts, the four-stage exporter, a real WebGPU worker, the full HTML/lists panels, and desktop Chrome numerical parity evidence. Do not regenerate a placeholder runtime or replace inference with a statistical forecast. Do not merely change a manifest status to claim completion.

Apply these complete updated sources from the package:

- `index.html` → HTML panel, retaining all existing plugin and interface integration.
- `top-panel.txt` → lists panel, preserving the Perchance imports and metadata.
- `src/pulse-workbench.js` → workbench module.
- `src/kronos-local/` → engine, preprocessing, worker, manifest, four model graphs, exporter, parity evidence, and documentation.

Review the actual current generator against this package first so newer edits are not lost. The full source ZIP also preserves the original unrelated modules/icons. Do not overwrite them with older versions when only the named runtime/workbench files need changing.

The model files are `tokenizer-encode.onnx`, `tokenizer-decode.onnx`, `predictor-s1.onnx`, and `predictor-s2.onnx`. Use exact sizes and SHA-256 values from the manifest. Public downloads must use actual HTTPS/CORS URLs without authentication, a Polygon key, a user account, a Mac server, or a remote inference endpoint. Source-file import is not proof that model binaries are publicly hosted. If they are not hosted yet, report that dependency explicitly and prepare the upload rather than inventing URLs.

Once public hosting is available, configure the real hosted `kronos-local/` directory through `window.KronosLocalConfig.assetBase` before loading the engine, and resolve the panel script URLs to their real published/source-file locations. Keep model URLs relative to the hosted manifest or use its actual immutable absolute URLs. Preserve the pinned ONNX Runtime WebGPU entry point and matching WASM directory. Blob workers must receive absolute preprocessing and manifest URLs.

The tested pipeline uses six channels, upstream float32 statistics and normalization, coarse/fine token generation, conditional fine-token logits, full-window decoding and inverse normalization. Native int32 token/calendar inputs are required by this export. Preserve timestamps, source metadata, completed-candle filtering, raw model OHLC/quality flags, cancellation, stale-result rejection, and the optional model cache. Do not upload candles to perform inference. Narrative AI remains a separate optional Perchance feature.

Preserve free Binance/OKX/Bybit crypto feeds, stocks/ETF feeds and CSV import, 1h/4h/daily timeframes, chart expansion and overlays, presets, forecast tables and timestamped CSV/PDF downloads. Retain the corrected OKX `after` pagination and Eastern-time hour parsing. Do not copy or alter any private Polygon configuration from the separate Kronos desktop project.

Keep the tested initial browser limits at 256 lookback, 24 forecast candles and one sample. Display history remains independent. Expand those limits only after actual memory/latency and parity measurements. Keep smaller/base models disabled until separately exported and validated.

Verify from the actual Perchance preview iframe: supported secure WebGPU adapter/device; successful CORS/module/WASM/model downloads; all four SHA-256/size checks and graph smoke tests; a real completed-candle forecast; 24 correctly timestamped rows; chart overlay; CSV/PDF matching the rows; Cancel and reload recovery; stale results rejected after selection changes; cache opt-in, reuse and scoped removal. Check an actual iPhone 16 Pro if available. A narrow responsive viewport is not proof of Safari GPU inference.

Return the full updated panels/source files, actual hosting URLs, observed test results and remaining limits. Keep the published generator unchanged until Aaron explicitly asks to publish it.
