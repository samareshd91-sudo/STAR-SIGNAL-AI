import time
import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("BG_STAR_PRO_SmartAPI")

class VolatilityEngine:
    def __init__(self):
        self.pause_duration = 25 * 60  # 25 minutes pause limit
        self.pause_end_time = 0
        self.current_level = "NORMAL"

    def update(self, btc_df: pd.DataFrame) -> bool:
        if btc_df is None or btc_df.empty or len(btc_df) < 15:
            return False

        df = btc_df.copy()
        
        # True Range Calculation
        df['prev_close'] = df['close'].shift(1)
        tr1 = df['high'] - df['low']
        tr2 = abs(df['high'] - df['prev_close'])
        tr3 = abs(df['low'] - df['prev_close'])
        df['tr'] = tr1.combine(tr2, max).combine(tr3, max)
        
        # ATR Calculation
        df['atr'] = df['tr'].rolling(window=14).mean()

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. Price Spike: Previous Close -> Current Close
        prev_close = prev['close'] if pd.notna(prev['close']) else last['open']
        price_change_pct = (abs(last['close'] - prev_close) / prev_close) * 100

        # 2. ATR Ratio: Current ATR vs Previous 14-Period Mean ATR (Excluding current candle)
        current_atr = last['atr']
        mean_14_atr = df['atr'].dropna().iloc[-15:-1].mean()
        atr_ratio = current_atr / mean_14_atr if mean_14_atr > 0 else 1.0

        # 3. Volume Ratio: Current Volume vs Previous 14-Period Mean Vol (Excluding current candle)
        current_vol = last['volume']
        mean_14_vol = df['volume'].dropna().iloc[-15:-1].mean()
        volume_ratio = current_vol / mean_14_vol if mean_14_vol > 0 else 1.0

        # Spike Checks (Thresholds)
        price_spike = price_change_pct > 1.2
        atr_spike = atr_ratio > 2.0
        volume_spike = volume_ratio > 3.0

        newly_triggered_high = False

        # Determine Preliminary State
        if price_spike and (atr_spike or volume_spike):
            new_state = "HIGH"
        elif price_spike or atr_spike or volume_spike:
            new_state = "MEDIUM"
        else:
            new_state = "NORMAL"

        is_currently_paused = self.is_paused()

        # Apply Pause Logic & State
        if new_state == "HIGH":
            # Always extend the pause if HIGH volatility is detected
            self.pause_end_time = time.time() + self.pause_duration
            self.current_level = "HIGH"
            
            # But ONLY alert if it wasn't already paused (Prevents Telegram spam)
            if not is_currently_paused:
                newly_triggered_high = True
                logger.warning("🚨 HIGH Market Volatility Detected. Initiating/Extending Pause.")
                logger.info(
                    f"\nHIGH triggered by:\n"
                    f"{'✓' if price_spike else '✗'} Price Spike ({price_change_pct:.2f}%)\n"
                    f"{'✓' if atr_spike else '✗'} ATR Spike (Ratio: {atr_ratio:.2f})\n"
                    f"{'✓' if volume_spike else '✗'} Volume Spike (Ratio: {volume_ratio:.2f})"
                )
        else:
            if is_currently_paused:
                self.current_level = "HIGH"
            else:
                self.current_level = new_state

        # Detailed Logging for Live Diagnostics
        remaining_pause_sec = max(0, int(self.pause_end_time - time.time()))
        pause_remaining_min = f"{remaining_pause_sec // 60}m" if remaining_pause_sec > 0 else "0m"

        logger.info(
            f"[Volatility] Level={self.current_level} | "
            f"PriceSpike={price_change_pct:.2f}% | "
            f"ATR_Ratio={atr_ratio:.2f} | "
            f"Volume_Ratio={volume_ratio:.2f} | "
            f"Paused={is_currently_paused} | "
            f"PauseRemaining={pause_remaining_min}"
        )

        return newly_triggered_high

    def is_paused(self) -> bool:
        return time.time() < self.pause_end_time
      
