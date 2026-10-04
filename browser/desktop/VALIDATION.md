# Desktop packaging validation — 2026-10-04

- Windows installer compiled using the installed .NET Framework compiler. Embedded payload extraction and real COM shortcut creation passed in a new test directory; no desktop shortcut or existing installation was changed during the test.
- The final Windows native server passed all 14 `test-http.py` checks. Chrome loaded the four real bundled graphs, verified their hashes/smoke tests, and produced 24 forecast rows using 32 lookback in 1.1 seconds. Python was used only as the independent test client; the native server and browser inference did not use Python.
- On the Mac mini, Apple's installed Command Line Tools compiled a universal arm64/x86_64 app. The arm64 native server executed and passed the same 14 checks, including downloading and hashing all four models.
- `lipo` confirmed both architecture slices; `codesign --verify --deep --strict` passed for the ad-hoc-signed app; `hdiutil verify` passed for the final DMG. These do not establish Apple notarization or Gatekeeper acceptance of a downloaded copy.
- The original installed ASUS TradingView bridge test remains valid; the desktop server serves the same reviewed bridge-enabled workbench and separate extension package.

Not verified: clicking through Windows installer UI in a clean user account, macOS Finder drag-install/launcher UI, native Intel execution, Mac Chrome inference, physical iPhone inference, actual Perchance iframe behavior, or download-origin SmartScreen/Gatekeeper first-launch flow. These prototypes are unsigned/not notarized for public-trust purposes. No code bypasses those protections.
