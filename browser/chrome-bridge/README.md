# Kronos → TradingView Chrome bridge

Chrome-only Manifest V3 extension and Pine v6 overlay, shared by Windows and macOS. The model runs in the Kronos workbench; the extension transfers predictions into the dedicated indicator's text setting. No TradingView private API, account cookies, credentials, brokerage access, or inference server is used.

## Install once on each computer

1. Download and extract the Chrome bridge ZIP from the repository's release downloads, or use this directory from a clone.
2. In Chrome, open `chrome://extensions`, enable Developer mode, choose **Load unpacked**, and select the `extension` directory (the one containing `manifest.json`). Pin **Kronos TradingView Bridge** to the toolbar. A ZIP itself cannot be selected as an unpacked extension.
3. Open your TradingView chart. In the Pine Editor, create a **new Indicator**; preserve your existing scripts. Paste `extension/Kronos-Forecast-Bridge.pine`, save it privately as **Kronos Forecast Bridge**, and choose **Add to chart**. The popup's **Copy Pine indicator source** button provides the same code. Do not use a strategy or place trades.
4. Reload both the Kronos workbench and TradingView after loading or reloading the extension. For a local source checkout, start the workbench from `browser/perchance` with `python -m http.server 7082 --bind 127.0.0.1`, then open `http://127.0.0.1:7082/`. Stop the server with Ctrl+C. Port 7082 is optional.

Chrome stores unpacked extension registration per profile on each computer. Keep the extracted folder in a stable location. Installing on ASUS does not install it on the Mac; no remote Mac extension installation is claimed.

## Transfer a real forecast

1. Fetch completed candles, load Kronos-mini, and generate a forecast.
2. In **TradingView · Chrome bridge**, confirm the exact exchange-qualified chart symbol, such as `OKX:BTCUSDT`. Known crypto spot venues are suggested; stocks require entering the exact qualified chart symbol yourself. USD, USDT, spot, perpetuals, and different exchanges are not interchangeable.
3. Click **Send to Chrome bridge**. Open the extension popup, select your TradingView chart tab, then click **Open indicator settings and apply**.
4. The overlay checks the chart symbol, timeframe, regular-session requirement, generation age, and horizon expiry before drawing. Its table states any mismatch instead of silently plotting wrong data. Forecast high/low timestamps refer to candle starts, not exact intrabar turning points.

To remove repeated transfer clicks, enable **Send each newly generated forecast** in the workbench and **Automatically apply received forecasts to this tab** in the popup. Both default off. This forwards forecasts you generate; it does not schedule model runs or place orders. Keep the pages open, do not edit indicator settings during automatic updates, and reselect the destination after closing/reopening a chart tab. Multiple Kronos indicators on one chart are deliberately rejected as ambiguous.

## Data and failure handling

- Forecasts are stored in `chrome.storage.local` on the current Chrome profile. They are not sent through Chrome Sync. **Forget stored forecast** removes only this extension's stored forecast.
- The extension has local storage permission plus content access to TradingView charts, localhost, and Perchance origins. It does not access cookies, passwords, your complete browsing history, or arbitrary websites. Applying the payload uses TradingView's indicator settings; TradingView may retain indicator inputs with its chart layout.
- Only real Kronos forecasts are accepted, capped at 120 rows. Statistical fallback results, stale selections, expired horizons, invalid timestamps, and nonfinite/missing prices are rejected. OHLC inconsistency flags are preserved: flagged candle bodies/wicks are omitted, close paths retained, and the table warns. High/low summaries use unflagged candles only.
- The bridge does not authenticate or certify the source website's forecast. Run your trusted local checkout or reviewed generator. Exchange symbol matching cannot verify provider corporate-action adjustments or identical daily session boundaries. Stock 4h/daily candles can align differently between vendors; compare source session and candle timestamps before relying on an overlay.
- TradingView settings automation is an interface adapter, not an official inbound prediction API. Changes to their UI can break it. If the extension cannot safely identify one dedicated indicator/dialog/textarea/OK button, it stops with a useful message. Open the indicator's **Inputs** settings manually and retry; **Copy TradingView data** is a fallback.
- The runtime and popup do not load remotely hosted extension code. Public Perchance delivery needs the new `tradingview-contract.js` and `tradingview-bridge.js` scripts hosted alongside the existing workbench assets; this change does not publish the generator.

## Development and checks

Verified on ASUS Chrome on 2026-10-04: the Pine script compiled and was saved privately; a real 32-lookback/24-horizon WebGPU forecast from completed OKX candles exported successfully; the settings adapter opened the dedicated indicator, filled its payload, and submitted it on the actual TradingView site. The overlay displayed future candles, a close path, high/low labels, and an explicit mismatch on a Coinbase BTCUSD chart. The adapter was exercised through Chrome's developer testing interface, not an installed extension: complete extension installation/message routing still needs a user-approved unpacked install. Chrome/macOS installation and inference have not been tested. The original 256-context model parity remains documented separately.

Nineteen Node contract/worker tests and five Chrome DOM adapter tests passed. The synthetic browser harness is `tests/adapter-harness.html`; it is a safety fixture, not model output or a live integration result.

`browser/perchance/src/tradingview-contract.js` is the canonical contract. Copy it to `extension/protocol.js` after changes; the test suite checks byte identity. Run from the repository root:

```powershell
node --test browser/chrome-bridge/tests/contract.test.cjs
```

The extension and Pine source use the repository's MIT license. Existing model attribution remains in the Perchance package. Rollback: disable/remove this extension in Chrome, remove only the Kronos Forecast Bridge indicator from the chart, and leave your other scripts and indicators intact.
