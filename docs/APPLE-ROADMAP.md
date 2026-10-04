# Apple client roadmap

Requested order: responsive web app first, native iOS next, Apple Watch companion after that. Primary test phone: iPhone 16 Pro; minimum hardware target: iPhone 15. Select an iOS/watchOS deployment version when creating the Xcode targets on the Mac, based on the user's installed OS and Watch model.

## Delivered web foundation

Mac mini hosts Python Kronos and Polygon adapters; iPhone displays results. API remains separate from presentation, raw OHLC and timestamps remain intact, and clients must preserve quality flags and freshness notices. No trade execution. Named preset JSON version 1 provides a portable interchange format; browser saves are local, not a synchronization server. Authenticated HTTPS sessions are optional for private proxy access.

## Native iOS stage (requires Mac/Xcode)

Create SwiftUI iOS target with typed URLSession adapters for the existing `/api/available-models`, `/api/model-status`, `/api/live/status`, `/api/live/candles`, and `/api/live/predict` endpoints. Authenticate via `/login` session cookie; native POST requests must send the configured HTTPS Origin to match the server's origin protection. Store dashboard access material in Keychain, never Polygon keys. Do not invent a bearer API that the server does not implement.

Build connection/setup, presets, candle chart, prediction timeline, quality and freshness badges, and CSV/PDF sharing. Use the existing server context validation; device selection refers to server hardware. Add cancellable forecast progress, explicit stale-state handling, and user-triggered refresh. Store imported preset JSON privately on device. Verify sign-in, expiry, reconnection, market closures/DST, offline state, and long forecasts on a real iPhone 16 Pro before distribution. Add authenticated read-only saved-forecast summaries before background/Watch features; the current endpoint generates a new forecast and must not be polled from a watch.

## Apple Watch companion stage

Use WatchConnectivity to transfer a small, timestamped summary from the iPhone: symbol, interval, observed anchor, selected forecast movement, next forecast candle time, generation time, and quality flag count. The Watch does not run Kronos or hold the Polygon credential. Show last synchronization and stale/offline state. Add a watch-sized timeline and optional complication after selecting the actual Watch/watchOS target. Notifications/alerts are a later explicit opt-in feature, with deduplication, rate limits, and OS background limitations; do not promise continuous background updates.

## Gates before distribution

Actual Apple Silicon model inference; Safari touch/export testing; native Xcode build and device signing; real paired Watch testing; authenticated connection/session checks. No App Store upload, Apple Developer purchase, push notification service, or remote network exposure is performed by this release.
