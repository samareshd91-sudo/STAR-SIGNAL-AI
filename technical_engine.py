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
        market_data format: {"BTC": pd.DataFrame, "ETH": pd.DataFrame, ...}
        """
        scan_results = {}

        for coin in self.target_coins:
            if coin not in market_data or market_data[coin].empty:
                logger.warning(f"No data for {coin}, skipping.")
                continue

            df = market_data[coin]
            
            # 1. Calculate Technical & SMC Features
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
        Detects Price Action and SMC events in the current candle.
        (Simplified logic for structural representation)
        """
        # Fetching latest candle data
        latest = df.iloc[-1]
        prev = df.iloc[-2]

        features = {
            "bos_choch_detected": False,
            "liquidity_sweep": False,
            "ob_fvg_retest": False,
            "htf_alignment": False,
            "adx_rising": False,
            "volume_spike": False,
            "trend_direction": "NEUTRAL"
        }

        # Mock Logic for BOS / CHOCH (Requires swing high/low mapping in real implementation)
        if latest['close'] > prev['high_swing']: 
            features["bos_choch_detected"] = True
            features["trend_direction"] = "BULLISH"

        # Mock Logic for Liquidity Sweep
        if latest['low'] < prev['liquidity_pool'] and latest['close'] > prev['liquidity_pool']:
            features["liquidity_sweep"] = True

        # Mock Logic for Order Block + FVG Retest
        if latest['low'] <= prev['order_block_top'] and latest['close'] > prev['order_block_top']:
            features["ob_fvg_retest"] = True

        # Mock Logic for Volume Spike (e.g., Volume > 200% of 20 SMA Volume)
        if latest['volume'] > (df['volume'].rolling(20).mean().iloc[-1] * 2):
            features["volume_spike"] = True

        # Mock Logic for ADX Rising (> 25 and rising)
        if latest['adx'] > 25 and latest['adx'] > prev['adx']:
            features["adx_rising"] = True

        # Mock Logic for HTF Alignment (e.g., H1 and H4 trends match)
        if latest['h1_trend'] == latest['h4_trend']:
            features["htf_alignment"] = True

        return features

    def _evaluate_smart_trigger(self, features: dict) -> dict:
        """
        Stage 2: Smart Trigger Engine
        Checks if at least 2 or 3 strong events happened simultaneously.
        """
        active_events = []
        
        # Checking conditions based on the blueprint
        if features["bos_choch_detected"]:
            active_events.append("BOS/CHOCH")
        if features["liquidity_sweep"]:
            active_events.append("Liquidity Sweep")
        if features["ob_fvg_retest"]:
            active_events.append("OB + FVG Retest")
        if features["htf_alignment"]:
            active_events.append("HTF Alignment")
        if features["adx_rising"]:
            active_events.append("ADX Rising")
        if features["volume_spike"]:
            active_events.append("Volume Spike")

        # The core logic: Is the market actually making a major move?
        is_triggered = len(active_events) >= self.min_confluence_events

        if is_triggered:
            logger.info(f"🔥 SMART TRIGGER ACTIVATED! Confluence: {', '.join(active_events)}")

        return {
            "is_triggered": is_triggered,
            "reasons": active_events
        }

    def _calculate_base_score(self, features: dict) -> int:
        """
        Calculates a baseline 0-100 score strictly as a filter/fallback metric,
        NOT as the primary API trigger.
        """
        score = 50 # Base score
        if features["htf_alignment"]: score += 15
        if features["bos_choch_detected"]: score += 15
        if features["ob_fvg_retest"]: score += 10
        if features["adx_rising"]: score += 5
        if features["volume_spike"]: score += 5
        return min(100, score)

# Usage Example:
# engine = TechnicalEngine()
# results = engine.analyze_market(live_dataframe_dict)
# for coin, data in results.items():
#     if data["is_triggered"]:
#         print(f"Move {coin} to Stage 3 (News API)!")
