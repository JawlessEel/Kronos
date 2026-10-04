"""Shared UI limits reflect the decoder's supported context window."""
import math


def validate_forecast(predictor, lookback, count, temperature, top_p, samples):
    limit = getattr(predictor, "max_context", 512)
    if not 16 <= lookback <= limit:
        raise ValueError(f"Model lookback must be 16–{limit} candles for the loaded model.")
    # The tokenizer decodes only the final context, so longer horizons lose rows.
    if not 1 <= count <= limit:
        raise ValueError(f"Forecast length must be 1–{limit} candles for the loaded model.")
    if not (math.isfinite(temperature) and 0.1 <= temperature <= 2 and math.isfinite(top_p) and 0 < top_p <= 1 and 1 <= samples <= 20):
        raise ValueError("Use temperature 0.1–2, top-p above 0 up to 1, and 1–20 samples.")


def history_length(value):
    count = int(value)
    if not 16 <= count <= 10000:
        raise ValueError("Chart history must be 16–10,000 candles.")
    return count
