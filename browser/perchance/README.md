# Perchance WebGPU prediction workbench

This directory contains the browser application, Perchance panels, real Kronos-mini runtime, and reproducible ONNX exporters. It is independent of the Python WebUI and native Apple companion work.

## Run the validated release

Download [the complete WebGPU package](https://github.com/JawlessEel/Kronos/releases/tag/webgpu-mini-2026-10-04), extract it into a new directory, and follow its `README-WEBGPU.md`. The ZIP includes all four real model graphs and validation evidence.

ZIP SHA-256: `4e7a8fb92ddc73ed6adfb190c0e69cc1f888604cea97608ef6c1cd364310ef37`.

## Run this source checkout

The four converted FP32 ONNX models are included directly in this checkout under `src/kronos-local/models` (33,595,885 bytes total). No separate model download or conversion is needed to run the workbench. The runtime verifies each graph's size and SHA-256 against the tracked manifest. Market inputs, generated forecasts, caches, and other model weights remain excluded from Git. For the optional browser validation harness, copy only `src/kronos-local/parity` from the release ZIP into the corresponding ignored directory here.

From this directory, run:

```powershell
python -m http.server 7080 --bind 127.0.0.1
```

Open `http://127.0.0.1:7080/`, choose OKX spot, fetch completed candles, load Kronos-mini, then forecast. Stop with Ctrl+C. Inference runs in the browser; the server serves static assets only. The commands also work in a macOS terminal.

See [the implementation and validation report](README-WEBGPU.md) and [the complete Perchance apply prompt](Perchance-Apply-WebGPU-Prompt.md). The four ONNX graphs are tracked in Git; parity fixtures, forecast outputs, and graph-check reports remain release assets. Export scripts can also rebuild the assets from upstream-compatible local weights.

Desktop WebGPU parity and local workbench behavior were verified. This repository sync does not publish the live Perchance generator or provide a tested HTTPS/CORS model host. Physical iPhone GPU testing remains outstanding. Forecasts are experimental model output, not demonstrated trading performance.

Only application and model-runtime source is included here. Unrelated workspace/agent bridge modules from the supplied archive remain preserved in the complete download.
