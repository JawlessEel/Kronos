# Discord forecast sessions and accountability payload

`scripts/run_discord_forecast.py` produces the real-model dark PNGs and JSON used by TITAN's scheduled Kronos cog. The bot owns scheduling, Discord delivery, and its PostgreSQL alert/outcome ledger; this runner does not post messages or place orders.

## Equity input sessions

`--equity-session all` is the Discord runner default. It retains actual completed provider stock candles from all available trading sessions, without filling gaps or manufacturing overnight prices. Five- and fifteen-minute data keep provider timestamps. Hourly all-session data use native provider clock-hour aggregates; regular-session hourly bars remain the existing 09:30-anchored construction from 30-minute aggregates. The browser UI retains its existing regular-session default. Feed caches and calibration histories distinguish the session modes.

The [provider documents US-stock coverage from 04:00 to 20:00 Eastern](https://massive.com/knowledge-base/article/market-data-outside-of-normal-hours), including premarket and after-hours; this does not establish full 24-hour SPY access. The JSON carries actual observed local hours and a session description. Only returned eligible aggregate bars are input; missing traded intervals are not synthesized. Actual provider candles outside those documented hours, if returned on an exchange trading date, are retained and identified by observed hours.

Equity forecast timestamps use NYSE trading dates and 04:00–20:00 ET extended-session hours, with 17:00 late-session closes on exchange early-close dates according to the [NYSE calendar](https://www.nyse.com/trade/hours-calendars). They skip holidays/weekends and handle Eastern daylight saving. They are scheduled projection targets, not a claim that every future interval will have an eligible aggregate. Crypto remains continuous UTC 24/7. Daily stock timestamps identify the provider's ET calendar date and become available at the following ET midnight; a daily forecast is not scored at the regular-session close.

`--equity-session regular` preserves the prior intraday regular-session input/calendar. All-session intraday histories use a new calibration-key suffix, so the old regular-session residuals cannot qualify the changed series for empirical calibration. Crypto and provider daily histories preserve their existing calibration keys. Until enough compatible forecasts mature, all-session intraday output uses the explicitly uncalibrated sample spread and existing raw-model fallback rather than claiming prior residual coverage applies.

The all-session setting changes SPY's intraday input. Its daily panel remains the provider-native daily aggregate under the [provider's daily aggregation rules](https://massive.com/knowledge-base/categories/stocks), which differ from intraday pre/post-market aggregates. It is not rebuilt from all-session intraday bars and does not claim to include every extended-hours price; its existing daily calibration remains compatible.

## JSON and immutable artifacts

Existing summary fields remain available. Top-level `provider`, `equity_session`, `model_fingerprint`, and `configuration_fingerprint` identify source and effective configuration. Every timeframe includes:

- `reference_at`, `reference_available_at`, and `decision_at` for the completed input anchor and generation decision;
- `forecast_end_at`, `forecast_available_at`, and `forecast_bars` for the exact endpoint candle and when its completed close can be compared;
- `forecast_path` with each candle's `timestamp`, `available_at`, OHLC, and pointwise `band_lower`/`band_upper`;
- source/session, observed-hours, timezone, history-start, model, and configuration provenance.

Targets identify candle starts; `available_at` identifies candle completion. Actual outcomes must match the provider timestamp and aggregation exactly. Unavailable target bars remain unscored. Do not substitute a nearby close, a different session aggregation, or a future outcome. Sample spreads and empirical residual bands retain their existing distinct meanings and no coverage guarantee.

Every generated chart has a unique filename so a later run cannot overwrite the chart referenced by an earlier prepared delivery. Keep files referenced by the delivery ledger; automated retention is not introduced here. Source freshness that leaves the entire forecast endpoint already in the past is rejected.

## Validation

Session, calendar, payload, calibration-isolation, and artifact-immutability regressions live in `tests/test_polygon_feed.py`, `tests/test_discord_forecast.py`, and `tests/test_calibration_store.py`. In the Mac mini's current setup, the Kronos `.venv/bin/python` launcher points to a removed Homebrew framework; the live bot already uses the configured Homebrew Python 3.12 interpreter with the existing Kronos site-packages. No environment recreation is part of this change.
