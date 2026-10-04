# Kronos project instructions

- This is Aaron's fork of shiyu-coder/Kronos; preserve its forecasting architecture and upstream examples.
- Follow the workstation instructions and standing GitHub authorization in the shared AI_Memory policy when available.
- Use the project-local `.venv`; keep models, caches, input data, and generated forecasts out of Git, except the four validated browser ONNX graphs explicitly requested under `browser/perchance/src/kronos-local/models/`.
- Launch the trial UI with `Start-Kronos.cmd`; bind only to localhost and keep debug mode disabled.
- Validate setup changes with `scripts/verify_setup.py` and relevant tests; predictions must use real model weights.
- Sample data is historical research data. Do not describe sample forecasts as live trading signals or profitability evidence.
