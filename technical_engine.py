import pandas as pd
import logging

logger = logging.getLogger("BG_STAR_PRO_TechEngine")

class TechnicalEngine:
    def __init__(self):
        # Stage 1: Strictly limited to these 6 coins
        self.target_coins = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]
        
        # Trigger thresholds
        self.min_confluence_events = 2  # Minimum SMC events required to trigger API

    def analyze_market(self, market_data: dict) -> dict:
        """
        Stage 1 & Stage 2 Execution.
        Iterates through the 6 coins, calculates SMC features, and evaluates the Smart Trigger.
        """
        scan_results = {}

        for coin in self.target_coins:
            # We need at least 50 candles to calculate SMA and trends properly
            if coin not in market_data or market_data[coin].empty or len(market_data[coin]) < 50:
                logger.warning(f"Not enough data for {coin}, skipping.")
                continue

            df = market_data[coin]
            
            # 1. Calculate Technical & SMC Features using Real OHLCV Data
            features = self._calculate_smc_features(df)
            
            # 2. Evaluate Stage 2 Smart Trigger
            trigger_status = self._evaluate_smart_trigger(features)
            
            # 3. Base Technical Score (For logging and backup fallback)
            tech_score = self._calculate_base_score(features)

            scan_results[coin] = {
                "coin": coin,
                "features": features,
                "is_triggered": trigger_status["is_triggered"],
                "trigger_reasons": trigger_status["reasons"],
                "technical_score": tech_score,
                "direction": features["trend_direction"]
            }

        return scan_results

    def _calculate_smc_features(self, df: pd.DataFrame) -> dict:
        """
        Detects Price Action and SMC events in the current candle using real OHLCV Math.
        """
        features = {
            "bos_choch_detected": False,
            "liquidity_sweep": False,
            "ob_fvg_retest": False,
            "htf_alignment": False,
            "adx_rising": False,
            "volume_spike": False,
            "trend_direction": "NEUTRAL"
        }

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. BOS / CHOCH (Break of Structure): Close above/below the 10-candle highest high / lowest low
        recent_high = df['high'].iloc[-11:-2].max()
        recent_low = df['low'].iloc[-11:-2].min()
        
        if latest['close'] > recent_high: 
            features["bos_choch_detected"] = True
            features["trend_direction"] = "BULLISH"
        elif latest['close'] < recent_low:
            features["bos_choch_detected"] = True
            features["trend_direction"] = "BEARISH"

        # 2. Liquidity Sweep: Price dips below recent low but closes above it (Long lower wick)
        if latest['low'] < recent_low and latest['close'] > recent_low:
            features["liquidity_sweep"] = True
            features["trend_direction"] = "BULLISH"

        # 3. OB + FVG Retest Proxy: Price pulls back to the bottom 30% of the recent 15-candle range and bounces
        range_high = df['high'].iloc[-15:-1].max()
        range_low = df['low'].iloc[-15:-1].min()
        discount_zone = range_low + ((range_high - range_low) * 0.3)
        
        if latest['low'] <= discount_zone and latest['close'] > discount_zone:
            features["ob_fvg_retest"] = True

        # 4. Volume Spike: Current volume is 200% higher than the 20-candle average
        vol_sma20 = df['volume'].rolling(20).mean().iloc[-2]
        if latest['volume'] > (vol_sma20 * 2):
            features["volume_spike"] = True

        # 5. Momentum Rising (ADX Proxy): Close is higher than 10 EMA and trending up
        ema10 = df['close'].ewm(span=10, adjust=False).mean().iloc[-1]
        if latest['close'] > ema10 and latest['close'] > prev['close']:
            features["adx_rising"] = True

        # 6. HTF Alignment Proxy: Price is above the 50 SMA (Macro Bullish)
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        if latest['close'] > sma50:
            features["htf_alignment"] = True

        # Fallback direction if trigger happens without BOS
        if features["trend_direction"] == "NEUTRAL" and (features["adx_rising"] or features["htf_alignment"]):
            features["trend_direction"] = "BULLISH"

        return features

    def _evaluate_smart_trigger(self, features: dict) -> dict:
        """
        Stage 2: Smart Trigger Engine
        Checks if at least 2 strong events happened simultaneously.
        """
        active_events = []
        
        if features["bos_choch_detected"]: active_events.append("BOS/CHOCH")
        if features["liquidity_sweep"]: active_events.append("Liquidity Sweep")
        if features["ob_fvg_retest"]: active_events.append("OB + FVG Retest")
        if features["htf_alignment"]: active_events.append("HTF Alignment")
        if features["adx_rising"]: active_events.append("Momentum Rising")
        if features["volume_spike"]: active_events.append("Volume Spike")

        is_triggered = len(active_events) >= self.min_confluence_events

        if is_triggered:
            logger.info(f"🔥 SMART TRIGGER ACTIVATED! Confluence: {', '.join(active_events)}")

        return {
            "is_triggered": is_triggered,
            "reasons": active_events
        }

    def _calculate_base_score(self, features: dict) -> int:
        """
        Calculates a baseline score based on technical features.
        """
        score = 50 
        if features["htf_alignment"]: score += 15
        if features["bos_choch_detected"]: score += 15
        if features["ob_fvg_retest"]: score += 10
        if features["adx_rising"]: score += 5
        if features["volume_spike"]: score += 5
        return min(100, score)
