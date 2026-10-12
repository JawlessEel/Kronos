"""
Dual-Model SPY + VIX Confluence Predictor.
Pairs the 20-Year Multi-Timeframe SPY Model with the VIX Companion Model
to generate volatility-confirmed directional signals and filter out market chop.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np
import pandas as pd
import torch

from model import Kronos, KronosTokenizer
from model.enhanced_predictor import EnhancedKronosPredictor


@dataclass
class ConfluenceResult:
    spy_pred_df: pd.DataFrame
    vix_pred_df: pd.DataFrame
    spy_last_close: float
    spy_pred_close: float
    spy_return_pct: float
    vix_last_close: float
    vix_pred_close: float
    vix_return_pct: float
    signal: str                  # "HIGH_CONVICTION_BULL", "HIGH_CONVICTION_BEAR", or "CONFLICT_STAND_ASIDE"
    is_confirmed: bool           # True when SPY and VIX move inversely as expected
    conviction_score: float      # 0.0 to 1.0


class SPYVIXConfluencePredictor:
    """
    Runs synchronized inference across the 20-Year SPY Model and VIX Companion Model.
    """

    def __init__(
        self,
        spy_model_dir: str | Path,
        vix_model_dir: str | Path,
        device: Optional[str] = None,
        max_context: int = 512,
    ):
        if device is None:
            if torch.cuda.is_available():
                device = "cuda:0"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.device = device

        spy_dir = Path(spy_model_dir)
        vix_dir = Path(vix_model_dir)

        print(f"[ConfluencePredictor] Loading 20-Yr SPY Model from {spy_dir} on {device}...")
        spy_tok = KronosTokenizer.from_pretrained(str(spy_dir / "tokenizer" / "best_model"))
        spy_mdl = Kronos.from_pretrained(str(spy_dir / "basemodel" / "best_model"))
        self.spy_predictor = EnhancedKronosPredictor(spy_mdl, spy_tok, device=device, max_context=max_context)

        print(f"[ConfluencePredictor] Loading VIX Companion Model from {vix_dir} on {device}...")
        vix_tok = KronosTokenizer.from_pretrained(str(vix_dir / "tokenizer" / "best_model"))
        vix_mdl = Kronos.from_pretrained(str(vix_dir / "basemodel" / "best_model"))
        self.vix_predictor = EnhancedKronosPredictor(vix_mdl, vix_tok, device=device, max_context=max_context)

    def predict(
        self,
        spy_df: pd.DataFrame,
        vix_df: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        pred_len: int,
        T: float = 0.2,
        top_p: float = 0.9,
        sample_count: int = 5,
        min_spy_move_pct: float = 0.05,
        min_vix_move_pct: float = 0.10,
    ) -> ConfluenceResult:
        """
        Generate synchronized SPY and VIX forecasts and evaluate inverse volatility confluence.
        """
        spy_cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in spy_df.columns]
        vix_cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in vix_df.columns]

        spy_pred = self.spy_predictor.predict(
            df=spy_df[spy_cols],
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=T,
            top_p=top_p,
            sample_count=sample_count,
            normalization_mode="detrend",
            selection_mode="medoid",
            verbose=False,
        )

        # VIX is mean-reverting around its rolling regime equilibrium; standard z-score matches training distribution
        vix_pred = self.vix_predictor.predict(
            df=vix_df[vix_cols],
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=T,
            top_p=top_p,
            sample_count=sample_count,
            normalization_mode="standard",
            selection_mode="medoid",
            verbose=False,
        )

        spy_last = float(spy_df["close"].iloc[-1])
        spy_fut = float(spy_pred["close"].iloc[-1])
        spy_ret = (spy_fut / spy_last - 1.0) * 100.0

        vix_last = float(vix_df["close"].iloc[-1])
        vix_fut = float(vix_pred["close"].iloc[-1])
        vix_ret = (vix_fut / vix_last - 1.0) * 100.0

        # Evaluate inverse volatility confirmation above noise threshold
        if spy_ret > min_spy_move_pct and vix_ret < -min_vix_move_pct:
            signal = "HIGH_CONVICTION_BULL"
            is_confirmed = True
        elif spy_ret < -min_spy_move_pct and vix_ret > min_vix_move_pct:
            signal = "HIGH_CONVICTION_BEAR"
            is_confirmed = True
        else:
            signal = "CONFLICT_STAND_ASIDE"
            is_confirmed = False

        # Conviction score scales with agreement and normalized return magnitudes
        if is_confirmed:
            raw_score = min(1.0, (abs(spy_ret) / 0.25) * 0.5 + (abs(vix_ret) / 1.5) * 0.5)
            conviction = round(float(np.clip(raw_score, 0.1, 1.0)), 3)
        else:
            conviction = 0.0

        return ConfluenceResult(
            spy_pred_df=spy_pred,
            vix_pred_df=vix_pred,
            spy_last_close=spy_last,
            spy_pred_close=spy_fut,
            spy_return_pct=spy_ret,
            vix_last_close=vix_last,
            vix_pred_close=vix_fut,
            vix_return_pct=vix_ret,
            signal=signal,
            is_confirmed=is_confirmed,
            conviction_score=conviction,
        )
