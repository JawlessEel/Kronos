# Kronos iPhone and Apple Watch

Native SwiftUI source and an XcodeGen project specification. This stage has backend tests on Windows; an Xcode build and physical-device validation are still required. No Apple app has been installed by this checkout.

The phone connects to the Mac's authenticated private HTTPS dashboard, loads a server model, reads saved forecasts, and explicitly generates a forecast through today's regular-session close. Dashboard access is stored in Keychain; the Polygon credential stays on the server. A separate comma-separated Kronos watchlist lets you choose the same symbols you follow in Stocks.

The Watch companion receives the latest summary through WatchConnectivity. Its rectangular **Kronos Today** complication fits **Modular → Middle**, showing the symbol, one selected Pred H or Pred L number, and a solid observed / dashed predicted chart. This replaces the Stocks complication in that slot. There is no implemented Apple Stocks watchlist import or chart modification.

## Build on the Mac

Read the Mac's local instructions and inspect any existing Kronos checkout before pulling. Clone this repository into your existing project root if no checkout exists. Use the existing Mac Python setup in `MACOS-QUICKSTART.md`; do not copy the Windows virtual environment. Keep the Python server on loopback behind authenticated private HTTPS.

From the repository root, in macOS Terminal (zsh):

```zsh
xcodebuild -version
xcrun --sdk iphoneos --show-sdk-version
xcrun --sdk watchos --show-sdk-version
command -v xcodegen
cd apple
xcodegen generate --spec project.yml
xcodebuild -list -project KronosApple.xcodeproj
xcodebuild -project KronosApple.xcodeproj -scheme KronosPhone -destination 'generic/platform=iOS Simulator' CODE_SIGNING_ALLOWED=NO build
xcodebuild -project KronosApple.xcodeproj -scheme KronosWatch -destination 'generic/platform=watchOS Simulator' CODE_SIGNING_ALLOWED=NO build
open KronosApple.xcodeproj
```

If XcodeGen is missing, install it with the Mac's existing package manager (`brew install xcodegen` when Homebrew is already installed). If Xcode is missing or too old for the installed device OS, install a compatible Apple Xcode release. A simulator build does not validate device signing or paired Watch delivery.

In Xcode, select your signing team on all three targets. Choose unique bundle identifiers if the defaults are unavailable, updating the Watch's `WKCompanionAppBundleIdentifier` to match the phone. Register one App Group available to your team and replace `KRONOS_APP_GROUP` in the project spec; regenerate the project. Enable that same App Group for all three targets. The Watch and its complication share a local cache; the iPhone transfers data with WatchConnectivity, not cross-device UserDefaults.

Build/run KronosPhone on the iPhone, then KronosWatch on its paired Watch. On the phone, enter the private HTTPS base address and dashboard access token, connect, load the server model, choose the symbol and high/low, then generate during an open trading session. In the Watch app on iPhone, select **My Watch → Modular → Middle → Kronos Today**. You can keep Stocks in another compatible complication slot.

## Meaning and freshness

- High/low summarize the predicted OHLC range of full future candles between generation and today's actual NYSE close. This is a remaining-session forecast, not a known full-day extreme; an in-progress candle is excluded.
- Early closes, holidays and New York daylight saving time use the existing exchange calendar. Closed/premarket/weekend requests do not silently target tomorrow.
- A saved forecast must reach close without missing bars. Inconsistent raw predicted candle bounds withhold the high/low; they are not silently repaired.
- Summaries expire after at most 15 minutes, sooner at close or when source candles become stale. Predicted extrema times are candle start timestamps, not exact intrabar event times.
- The Watch performs no inference and holds no Polygon key. Refresh is user-triggered on the phone. OS-controlled delivery and widget refresh are not a continuous live feed; expired/offline data requires refreshing on iPhone.
- Deployment minimums are iOS 17 and watchOS 10. The user's Series 9/watchOS 26.6 and iPhone 16 Pro require compatible local Xcode/device support. App Store distribution is a later stage.

## API contract

`POST /api/live/predict` retains existing parameters and accepts `target_today: true`. It computes the horizon from the latest completed candle through today's actual close, rejects closed/stale sources with HTTP 422, and retains model context limits.

`GET /api/live/watch-summary?ticker=SPY&interval=5` reads saved output only. Version 1 includes `status`, `reason`, `session_date`, `market_close`, `generated_at`, `expires_at`, `predicted_high`, `predicted_low`, `high_time`, `low_time`, observed/predicted timestamp-close points, and `quality_count`. Only `ready` with a valid expiry is displayable as a forecast number. Both APIs retain the dashboard's existing session authentication and POST Origin checks.

Before declaring the Apple stage complete, verify both simulator builds, signed device builds, login failure/session expiry, offline/expired state, paired transfer, high/low selection, and Modular Middle layout. Verify real Mac inference separately.
