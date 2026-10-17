# Claude's upgrades branch (`Claudes_upgrades`)

Branched from `master` at `9ce8f3a` on 2026-10-17. Each change is small and reversible; upstream Kronos model code and examples are untouched.

## What was measured first

| Area | Finding |
| --- | --- |
| Main page layout | The forecast workspace (controls + charts) started ~2,000 px down, below the 1,760 px Testing Lab. Page height 5,181 px at 1025 px wide. |
| Control column | 3,145 px tall next to a 579 px chart column, so most of the page was empty space beside the controls. |
| Tests | `pytest` from the repo root collected `finetune/qlib_test.py` (needs qlib) and stopped. `test_presets.cjs` crashed (`window` undefined after the resize handler moved to `window`). The Postgres test failed on any machine without the `kronos_research` DB. |
| Web server | `webui/app.py` and `webui/run.py` started with `debug=True, host='0.0.0.0'`, against the project's localhost-only / no-debug rule. |
| Data API | `/api/load-data` and `/api/predict` read any `.csv`/`.feather` path the client sent, including files outside `data/`. That matters once `--require-auth` exposes the UI to a phone. |

## What changed

1. **Forecast-first layout** (`webui/templates/index.html`, new `webui/static/workspace_layout.css`)
   - The forecast workspace is first. The Testing Lab moved below it and is one click away.
   - A sticky section nav (Forecast · Controls · Live chart · Results · Testing Lab · 3R System · ↑) uses the Darkwave tokens. Phones keep the existing bottom nav, now ordered Controls first.
   - On desktop the control panel is a sticky sidebar that scrolls on its own, so the charts stay in view while you change settings. The page is now 2,442 px tall, down from 5,181 px.
   - PDF export still prints the whole control panel; the clone overrides the sticky and scroll rules.
2. **Test harness** (`pytest.ini`, `tests/`)
   - `testpaths = tests`, `pythonpath = .`. Plain `pytest` now works.
   - The Postgres test skips with the reason when the DB or psycopg is missing.
   - The `test_presets.cjs` context gets a `window` stub.
   - New `tests/test_data_paths.py` covers the data-directory guard.
3. **One-command checks** (`scripts/run_checks.py`): runs pytest plus every Node test (`tests/*.cjs`, `browser/chrome-bridge/tests/*.test.cjs`) and prints a pass/fail summary. The idea comes from `trading_bot`'s `smoke_imports.py` / `preflight_check.py`.
4. **CI** (`.github/workflows/checks.yml`): CPU-only torch on Ubuntu, Python 3.12 + Node 22, caches the pinned Kronos-small regression weights, and runs `scripts/run_checks.py`. It uses no secrets. Modelled on `trading_bot/.github/workflows/ci.yml`.
5. **Server hardening** (`webui/app.py`, `webui/run.py`)
   - `resolve_data_path()` keeps request paths inside `data/`. It uses `abspath`, not `realpath`, so datasets linked into `data/` by junction still work.
   - Both legacy entry points now bind `127.0.0.1` with debug off.

Verification:
- `python scripts/run_checks.py`: 70 passed, 1 skipped (Postgres), all 4 Node suites pass.
- `scripts/verify_setup.py`: 120/120 forecast rows on the RTX 3050 in 5.6 s.
- In the browser, a Kronos-mini forecast ran end to end through the new layout, including the time-window slider inside the scrolling sidebar.
- Checked at 375 px mobile width with no horizontal scroll.

## Ideas taken from other repos in `D:\projects`

| Source | Idea | Status |
| --- | --- | --- |
| `trading_bot` | GitHub Actions CI, import smoke test, non-destructive preflight | CI and `run_checks.py` added |
| `trading_bot` | `.editorconfig` | Not added; `end_of_line = lf` would churn the `.cmd`/`.ps1` files |
| `Wendys_Ace` | `.github/instructions/*.instructions.md` per file type for Copilot | Candidate: split the Python, JS and Swift rules out of `AGENTS.md` |
| `lab` | `_orch/task.md` with Goal / Do / Done-when, one writer at a time | Candidate for multi-AI work on this repo (Antigravity, Codex and Claude all commit here) |
| `kronos-webgpu` | A worktree on `feat/perchance-webgpu`, already merged to master via PR #7 | Can be removed with `git worktree remove` once you confirm nothing local is left |

## Recommended next steps (not done here)

1. **Testing Lab noise.** On a machine without fine-tuned checkpoints, every page load fires one `run-backtest` (404, "Dataset not found for SPY (1hour)") and seven `run-analysis` calls (400, "Unknown model key"). Gate the auto-runs on `/api/testing/overview` reporting the model and dataset.
2. **Pin front-end libraries.** `plotly-latest.min.js` is frozen at v1.58.5 (2021) and `axios` is unpinned from jsDelivr. Pin both or vendor them like `html2canvas` and `pdf-lib` so the offline launch (`HF_HUB_OFFLINE=1`) works without a network.
3. **Split `index.html`.** About 430 lines of inline CSS and about 600 lines of inline JS. Moving them to `static/` makes the forecast logic testable like `presets.js`.
4. **"Latest data" mislabel.** `/api/predict` without a start date uses `df.iloc[:lookback]`, which is the *earliest* rows, while calling it "latest data". This is upstream behaviour; rename the label or switch to the tail.
5. **Postgres on Windows.** `psycopg` is only in `requirements-macos.txt`, so the research vault is always "Disconnected" on the ASUS. Add it to the Windows tested requirements or an optional research requirements file.
6. **`scripts/` sprawl.** 18 flat scripts. Group them into `scripts/data/`, `scripts/benchmarks/` and `scripts/setup/`, with thin compatibility shims for documented commands.
7. **3R module name.** `webui/pages/3r_trading_system.py` starts with a digit, so it needs an `importlib` loader. Rename it to `three_r_trading_system.py` and keep a shim.
