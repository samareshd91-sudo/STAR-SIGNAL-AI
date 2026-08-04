import pandas as pd
import logging

logger = logging.getLogger("BG_STAR_PRO_TechEngine")

class TechnicalEngine:
    def __init__(self):
        self.target_coins = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]

    def analyze_market(self, market_data: dict) -> dict:
        scan_results = {}
        for coin in self.target_coins:
            if coin not in market_data or market_data[coin].empty or len(market_data[coin]) < 50:
                continue

            df = market_data[coin]
            features = self._calculate_smc_features(df)
            tech_score = self._calculate_dynamic_score(features)
            
            # Trigger check (Score >= 70 is our new base threshold)
            is_triggered = tech_score >= 70

            scan_results[coin] = {
                "coin": coin,
                "features": features,
                "is_triggered": is_triggered,
                "technical_score": tech_score,
                "direction": features["trend_direction"],
                "trigger_reasons": [k for k, v in features.items() if v is True]
            }
        return scan_results

    def _calculate_smc_features(self, df: pd.DataFrame) -> dict:
        features = {
            "bos_choch": False,
            "liquidity_sweep": False,
            "ob_fvg": False,
            "htf_alignment": False,
            "ema_trend": False,
            "adx_rising": False,
            "volume_spike": False,
            "cvd_confirmation": False
        }

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        trend_direction = "NEUTRAL"

        # 1. EMA Trend
        ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        if latest['close'] > ema20: features["ema_trend"] = True

        # 2. HTF Alignment Proxy
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        if latest['close'] > sma50: features["htf_alignment"] = True

        # 3. BOS / CHOCH
        recent_high = df['high'].iloc[-11:-2].max()
        recent_low = df['low'].iloc[-11:-2].min()
        if latest['close'] > recent_high: 
            features["bos_choch"] = True
            trend_direction = "BULLISH"
        elif latest['close'] < recent_low:
            features["bos_choch"] = True
            trend_direction = "BEARISH"

        # 4. Liquidity Sweep
        if latest['low'] < recent_low and latest['close'] > recent_low:
            features["liquidity_sweep"] = True

        # 5. OB + FVG
        range_high = df['high'].iloc[-15:-1].max()
        range_low = df['low'].iloc[-15:-1].min()
        discount_zone = range_low + ((range_high - range_low) * 0.3)
        if latest['low'] <= discount_zone and latest['close'] > discount_zone:
            features["ob_fvg"] = True

        # 6. ADX Rising Proxy
        ema10 = df['close'].ewm(span=10, adjust=False).mean().iloc[-1]
        if latest['close'] > ema10 and latest['close'] > prev['close']:
            features["adx_rising"] = True

        # 7. Volume Spike
        vol_sma20 = df['volume'].rolling(20).mean().iloc[-2]
        if latest['volume'] > (vol_sma20 * 2):
            features["volume_spike"] = True

        # 8. CVD Confirmation Proxy (Buying Pressure)
        buying_pressure = latest['close'] - latest['low']
        selling_pressure = latest['high'] - latest['close']
        if buying_pressure > selling_pressure and latest['close'] > latest['open']:
            features["cvd_confirmation"] = True

        if trend_direction == "NEUTRAL" and (features["ema_trend"] or features["htf_alignment"]):
            trend_direction = "BULLISH"

        features["trend_direction"] = trend_direction
        return features

    def _calculate_dynamic_score(self, features: dict) -> int:
        score = 45 # Base Score
        if features["ema_trend"]: score += 10
        if features["htf_alignment"]: score += 15
        if features["bos_choch"]: score += 15
        if features["liquidity_sweep"]: score += 10
        if features["ob_fvg"]: score += 10
        if features["adx_rising"]: score += 10
        if features["volume_spike"]: score += 10
        if features["cvd_confirmation"]: score += 5
        
        # Normalize to 100
        normalized = int((score / 120) * 100)
        return min(100, normalized)
