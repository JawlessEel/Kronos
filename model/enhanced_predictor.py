"""
Enhanced Kronos Predictor with Trend-Preserving Normalization,
Medoid Path Selection, and Probabilistic Volatility Envelopes.
"""
import numpy as np
import pandas as pd
import torch
from model.kronos import calc_time_stamps, sample_from_logits

class EnhancedKronosPredictor:
    """
    Enhanced predictor wrapping Kronos with:
    1. Level-anchored or detrended normalization (eliminates false mean-reversion drift).
    2. Medoid trajectory selection (preserves realistic candlestick geometry and wicks).
    3. Quantile support/resistance volatility envelope generation.
    """

    def __init__(self, model, tokenizer, device=None, max_context=512, clip=5):
        self.device = device if device else ('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = model.to(self.device)
        self.tokenizer = tokenizer.to(self.device)
        self.max_context = max_context
        self.clip = clip
        self.price_cols = ['open', 'high', 'low', 'close']
        self.vol_col = 'volume'
        self.amt_vol = 'amount'

    def predict(
        self,
        df: pd.DataFrame,
        x_timestamp: pd.Series,
        y_timestamp: pd.Series,
        pred_len: int,
        T: float = 0.3,
        top_k: int = 0,
        top_p: float = 0.9,
        sample_count: int = 5,
        normalization_mode: str = "last_price_anchor",  # 'standard', 'last_price_anchor', 'detrend'
        selection_mode: str = "medoid",  # 'mean', 'medoid'
        verbose: bool = False
    ) -> pd.DataFrame:
        """
        Run enhanced prediction.
        Returns a DataFrame containing predicted OHLCV + upper/lower volatility envelope bounds.
        """
        if not isinstance(df, pd.DataFrame):
            raise ValueError("Input must be a pandas DataFrame.")
        if not all(col in df.columns for col in self.price_cols):
            raise ValueError(f"Price columns {self.price_cols} not found.")

        df = df.copy()
        if self.vol_col not in df.columns:
            df[self.vol_col] = 0.0
            df[self.amt_vol] = 0.0
        if self.amt_vol not in df.columns and self.vol_col in df.columns:
            df[self.amt_vol] = df[self.vol_col] * df[self.price_cols].mean(axis=1)

        x_time_df = calc_time_stamps(x_timestamp)
        y_time_df = calc_time_stamps(y_timestamp)

        x = df[self.price_cols + [self.vol_col, self.amt_vol]].values.astype(np.float32)
        x_stamp = x_time_df.values.astype(np.float32)
        y_stamp = y_time_df.values.astype(np.float32)

        L = len(x)
        t_steps = np.arange(L, dtype=np.float32)
        future_steps = np.arange(L, L + pred_len, dtype=np.float32)

        # 1. Normalization Strategy
        if normalization_mode == "detrend":
            # Fit linear trend to price columns: y = slope * t + intercept
            slopes = np.zeros(4, dtype=np.float32)
            intercepts = np.zeros(4, dtype=np.float32)
            for c_idx in range(4):
                slopes[c_idx], intercepts[c_idx] = np.polyfit(t_steps, x[:, c_idx], 1)
            
            trend_history = slopes * t_steps[:, np.newaxis] + intercepts
            trend_future = slopes * future_steps[:, np.newaxis] + intercepts
            
            x_price_res = x[:, :4] - trend_history
            vol_mean, vol_std = np.mean(x[:, 4:], axis=0), np.std(x[:, 4:], axis=0) + 1e-5
            price_std = np.std(x_price_res, axis=0) + 1e-5
            
            x_norm = np.zeros_like(x)
            x_norm[:, :4] = x_price_res / price_std
            x_norm[:, 4:] = (x[:, 4:] - vol_mean) / vol_std
            
        elif normalization_mode == "last_price_anchor":
            # Anchor prices to the latest close price to eliminate backward level shift
            last_close = x[-1, 3]
            price_std = np.std(x[:, :4], axis=0) + 1e-5
            vol_mean, vol_std = np.mean(x[:, 4:], axis=0), np.std(x[:, 4:], axis=0) + 1e-5
            
            x_norm = np.zeros_like(x)
            x_norm[:, :4] = (x[:, :4] - last_close) / price_std
            x_norm[:, 4:] = (x[:, 4:] - vol_mean) / vol_std
            
        else:  # 'standard' (original upstream behavior)
            x_mean = np.mean(x, axis=0)
            x_std = np.std(x, axis=0) + 1e-5
            x_norm = (x - x_mean) / x_std

        x_norm = np.clip(x_norm, -self.clip, self.clip)
        x_norm_tensor = torch.from_numpy(x_norm[np.newaxis, :]).to(self.device)
        x_stamp_tensor = torch.from_numpy(x_stamp[np.newaxis, :]).to(self.device)
        y_stamp_tensor = torch.from_numpy(y_stamp[np.newaxis, :]).to(self.device)

        # 2. Autoregressive Rollout returning individual paths
        with torch.no_grad():
            preds_all_samples = self._generate_paths(
                x_norm_tensor, x_stamp_tensor, y_stamp_tensor,
                pred_len=pred_len, T=T, top_k=top_k, top_p=top_p,
                sample_count=sample_count
            )

        # preds_all_samples shape: (sample_count, pred_len, channels)
        
        # 3. Denormalize each sample trajectory
        denorm_samples = np.zeros_like(preds_all_samples)
        for s in range(sample_count):
            sample = preds_all_samples[s]
            if normalization_mode == "detrend":
                denorm_samples[s, :, :4] = sample[:, :4] * price_std + trend_future
                denorm_samples[s, :, 4:] = sample[:, 4:] * vol_std + vol_mean
            elif normalization_mode == "last_price_anchor":
                denorm_samples[s, :, :4] = sample[:, :4] * price_std + last_close
                denorm_samples[s, :, 4:] = sample[:, 4:] * vol_std + vol_mean
            else:
                denorm_samples[s] = sample * x_std + x_mean

        # 4. Trajectory Aggregation: Medoid vs Mean
        if selection_mode == "medoid" and sample_count > 1:
            close_trajectories = denorm_samples[:, :, 3]  # shape (sample_count, pred_len)
            diffs = close_trajectories[:, np.newaxis, :] - close_trajectories[np.newaxis, :, :]
            dist_matrix = np.sum(np.abs(diffs), axis=2)  # pairwise L1 distance
            total_distances = np.sum(dist_matrix, axis=1)
            medoid_idx = int(np.argmin(total_distances))
            chosen_pred = denorm_samples[medoid_idx]
        else:
            chosen_pred = np.mean(denorm_samples, axis=0)

        # Calculate volatility envelopes across all generated sample paths
        env_low = np.min(denorm_samples[:, :, 2], axis=0)   # lowest low across paths
        env_high = np.max(denorm_samples[:, :, 1], axis=0)  # highest high across paths

        result_cols = self.price_cols + [self.vol_col, self.amt_vol]
        pred_df = pd.DataFrame(chosen_pred, columns=result_cols, index=y_timestamp)
        pred_df['env_low'] = env_low
        pred_df['env_high'] = env_high
        
        return pred_df

    def _generate_paths(self, x, x_stamp, y_stamp, pred_len, T, top_k, top_p, sample_count):
        """Autoregressive path generator preserving all individual sample trajectories."""
        device = self.device
        x = x.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x.size(1), x.size(2)).to(device)
        x_stamp = x_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, x_stamp.size(1), x_stamp.size(2)).to(device)
        y_stamp = y_stamp.unsqueeze(1).repeat(1, sample_count, 1, 1).reshape(-1, y_stamp.size(1), y_stamp.size(2)).to(device)

        x_token = self.tokenizer.encode(x, half=True)
        initial_seq_len = x.size(1)
        batch_size = x_token[0].size(0)
        total_seq_len = initial_seq_len + pred_len
        full_stamp = torch.cat([x_stamp, y_stamp], dim=1)

        generated_pre = x_token[0].new_empty(batch_size, pred_len)
        generated_post = x_token[1].new_empty(batch_size, pred_len)

        pre_buffer = x_token[0].new_zeros(batch_size, self.max_context)
        post_buffer = x_token[1].new_zeros(batch_size, self.max_context)
        buffer_len = min(initial_seq_len, self.max_context)
        if buffer_len > 0:
            start_idx = max(0, initial_seq_len - self.max_context)
            pre_buffer[:, :buffer_len] = x_token[0][:, start_idx:start_idx + buffer_len]
            post_buffer[:, :buffer_len] = x_token[1][:, start_idx:start_idx + buffer_len]

        for i in range(pred_len):
            current_seq_len = initial_seq_len + i
            window_len = min(current_seq_len, self.max_context)

            if current_seq_len <= self.max_context:
                input_tokens = [pre_buffer[:, :window_len], post_buffer[:, :window_len]]
            else:
                input_tokens = [pre_buffer, post_buffer]

            context_end = current_seq_len
            context_start = max(0, context_end - self.max_context)
            current_stamp = full_stamp[:, context_start:context_end, :].contiguous()

            s1_logits, context = self.model.decode_s1(input_tokens[0], input_tokens[1], current_stamp)
            s1_logits = s1_logits[:, -1, :]
            sample_pre = sample_from_logits(s1_logits, temperature=T, top_k=top_k, top_p=top_p, sample_logits=True)

            s2_logits = self.model.decode_s2(context, sample_pre)
            s2_logits = s2_logits[:, -1, :]
            sample_post = sample_from_logits(s2_logits, temperature=T, top_k=top_k, top_p=top_p, sample_logits=True)

            generated_pre[:, i] = sample_pre.squeeze(-1)
            generated_post[:, i] = sample_post.squeeze(-1)

            if current_seq_len < self.max_context:
                pre_buffer[:, current_seq_len] = sample_pre.squeeze(-1)
                post_buffer[:, current_seq_len] = sample_post.squeeze(-1)
            else:
                pre_buffer.copy_(torch.roll(pre_buffer, shifts=-1, dims=1))
                post_buffer.copy_(torch.roll(post_buffer, shifts=-1, dims=1))
                pre_buffer[:, -1] = sample_pre.squeeze(-1)
                post_buffer[:, -1] = sample_post.squeeze(-1)

        full_pre = torch.cat([x_token[0], generated_pre], dim=1)
        full_post = torch.cat([x_token[1], generated_post], dim=1)

        context_start = max(0, total_seq_len - self.max_context)
        input_tokens = [
            full_pre[:, context_start:total_seq_len].contiguous(),
            full_post[:, context_start:total_seq_len].contiguous()
        ]
        z = self.tokenizer.decode(input_tokens, half=True)
        # z shape: (sample_count, total_seq_len, channels)
        preds = z[:, -pred_len:, :].cpu().numpy()
        return preds
