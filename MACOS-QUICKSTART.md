# Kronos on an Apple Silicon Mac mini

This checkout has a macOS installer and launcher. On 2026-10-04, the pinned environment passed 47 backend tests on an Apple Silicon Mac, and Kronos-base generated 120 historical candles using MPS in 20.33 seconds. Validate each new machine with the checks below; CPU is an explicit fallback if MPS fails. Do not copy the Windows `.venv`.

## Install (Terminal, bash/zsh)

Use a native arm64 Python 3.12 installation already available on the Mac. The installer accepts Python 3.10–3.12 and refuses Rosetta/x86 Python. It installs only into this project's `.venv` and never installs Homebrew, Python, drivers, services, or system packages.

```bash
mkdir -p "$HOME/projects"
cd "$HOME/projects"
git clone https://github.com/JawlessEel/Kronos.git kronos
cd kronos
python3.12 scripts/setup_mac.py --download-models
bash Start-Kronos.sh --production
```

Open http://127.0.0.1:7070 in Safari. Select a model, select MPS if available (or CPU), then Load Model. Stop the server with Ctrl+C. The launcher uses only downloaded local weights and never binds to the LAN. Downloads are resumable; rerunning setup preserves existing model files and private configuration.

If `kronos` already exists, inspect its `git status` before pulling; do not clone over it. If setup reports a Windows environment, use a fresh clone instead of deleting an environment. `requirements-macos.txt` pins PyTorch 2.7.1 without a CUDA suffix; this is a reproducible baseline, not a claim that it is the newest release. See [official MPS guidance](https://docs.pytorch.org/docs/stable/notes/mps.html).

## Data and private configuration

Use Finder to copy your historical CSV files into `data/` (create that directory if absent). Git excludes data, models, `.venv`, caches, and generated outputs. They are not shipped by a Git push. You can copy the five `models/Kronos-*` folders from Windows instead of downloading them again. `verify_setup.py` requires the historical sample `data/HK_ali_09988_kline_5min_all.csv` that is present on the Windows installation.

Create `.env` in the checkout using a text editor. Put your Polygon key in `POLYGON_API_KEY`; use `.env.example` for names, never commit the populated file. The browser/phone never receives that key. Subscription freshness limits still apply.

Checks, from the project root:

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python scripts/verify_setup.py
```

`verify_setup.py` selects MPS when available, otherwise CPU, and writes the actual device and timings into ignored `outputs/`. If MPS errors, select CPU in the UI and report the exact error rather than assuming GPU success. Optional Qlib fine-tuning tests are outside the supported `tests/` suite.

## iPhone web app and private HTTPS access

The first mobile version is the responsive web UI: bottom navigation, 44px touch targets, safe-area padding, readable inputs, scrollable prediction table with pinned timestamps, compact chart preset, and the same CSV/PDF downloads. Designed for iPhone 15 and newer, including iPhone 16 Pro. Actual Safari/device validation remains required.

Phone access needs a private HTTPS reverse proxy. The app includes optional login and secure 12-hour session cookies; it remains localhost-only. Do not expose the unauthenticated Flask server or forward router ports.

One option is [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve), restricted to your private tailnet. If Tailscale is already installed and authorized on both the Mac and phone, add a separate random `KRONOS_ACCESS_TOKEN` of at least 32 characters to the Mac's private `.env` using your password manager. This is a dashboard token, not the Polygon key.

```bash
# Mac Terminal 1: authenticated production server, foreground until Ctrl+C
bash Start-Kronos.sh --production --require-auth
# Mac Terminal 2: private HTTPS proxy, foreground until Ctrl+C
tailscale serve http://127.0.0.1:7070
```

Use the HTTPS URL printed by Serve in iPhone Safari with Tailscale connected; sign in with the dashboard token. Use Safari's Share menu to add it to the Home Screen if desired. Authenticated mode deliberately requires HTTPS; localhost HTTP cookies will not work in that mode. Proxy must preserve the HTTPS hostname. Never use public Funnel. This task does not install Tailscale, alter network permissions, enable HTTPS on your tailnet, or start a permanent service; those steps depend on your Mac's existing access setup. Export presets on Windows and import them in Safari; browser storage is per device and origin, not automatic cloud sync.

## Presets

Choose one of three built-ins or name your current configuration and select **Save new**. **Apply** restores model choice, compatible device, ticker, interval, history/lookback/horizon, sampling controls, and chart/indicator settings. It does not run inference or restart refresh. Load the selected model before forecasting. Unsupported devices and out-of-range controls remain unchanged and are reported.

**Update selected** saves edits to an existing named preset; duplicate names are rejected. **Export preset / Import preset** transfers one validated JSON preset between machines. Predicted data, keys, historical filesystem paths, refresh state, and temporary drawings are excluded. Built-ins cannot be deleted. Up to 100 browser-local presets are supported; keep exported backups before clearing Safari storage.

## Native iOS and Apple Watch next

See `docs/APPLE-ROADMAP.md`. Native apps are the next stage, not included as a compiled/tested app in this release.
