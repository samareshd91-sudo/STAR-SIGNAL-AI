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
            
            # Trigger check (Score >= 70 is our base threshold)
            is_triggered = tech_score >= 70

            scan_results[coin] = {
                "coin": coin,
                "features": features,
                "is_triggered": is_triggered,
                "technical_score": tech_score,
                "direction": features["trend_direction"],
                "trigger_reasons": [k for k, v in features.items() if v is True and k != "trend_direction"]
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
            "cvd_confirmation": False,
            "trend_direction": "NEUTRAL"
        }

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        bullish_points = 0
        bearish_points = 0

        # 1. EMA Trend (Bi-directional)
        ema20 = df['close'].ewm(span=20, adjust=False).mean().iloc[-1]
        if latest['close'] > ema20: 
            features["ema_trend"] = True
            bullish_points += 1
        elif latest['close'] < ema20:
            features["ema_trend"] = True
            bearish_points += 1

        # 2. HTF Alignment Proxy (Bi-directional)
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        if latest['close'] > sma50: 
            features["htf_alignment"] = True
            bullish_points += 1
        elif latest['close'] < sma50:
            features["htf_alignment"] = True
            bearish_points += 1

        # 3. BOS / CHOCH (Bi-directional)
        recent_high = df['high'].iloc[-11:-2].max()
        recent_low = df['low'].iloc[-11:-2].min()
        if latest['close'] > recent_high: 
            features["bos_choch"] = True
            features["trend_direction"] = "BULLISH"
        elif latest['close'] < recent_low:
            features["bos_choch"] = True
            features["trend_direction"] = "BEARISH"

        # 4. Liquidity Sweep (Bi-directional)
        if latest['low'] < recent_low and latest['close'] > recent_low:
            features["liquidity_sweep"] = True
            bullish_points += 1
        elif latest['high'] > recent_high and latest['close'] < recent_high:
            features["liquidity_sweep"] = True
            bearish_points += 1

        # 5. OB + FVG (Bi-directional)
        range_high = df['high'].iloc[-15:-1].max()
        range_low = df['low'].iloc[-15:-1].min()
        discount_zone = range_low + ((range_high - range_low) * 0.3)
        premium_zone = range_high - ((range_high - range_low) * 0.3)
        
        if latest['low'] <= discount_zone and latest['close'] > discount_zone:
            features["ob_fvg"] = True # Bouncing up from support
            bullish_points += 1
        elif latest['high'] >= premium_zone and latest['close'] < premium_zone:
            features["ob_fvg"] = True # Rejecting down from resistance
            bearish_points += 1

        # 6. ADX Rising Proxy (Bi-directional Momentum)
        ema10 = df['close'].ewm(span=10, adjust=False).mean().iloc[-1]
        if latest['close'] > ema10 and latest['close'] > prev['close']:
            features["adx_rising"] = True # Upward momentum
        elif latest['close'] < ema10 and latest['close'] < prev['close']:
            features["adx_rising"] = True # Downward momentum

        # 7. Volume Spike (Direction Neutral)
        vol_sma20 = df['volume'].rolling(20).mean().iloc[-2]
        if latest['volume'] > (vol_sma20 * 2):
            features["volume_spike"] = True

        # 8. CVD Confirmation Proxy (Bi-directional Pressure)
        buying_pressure = latest['close'] - latest['low']
        selling_pressure = latest['high'] - latest['close']
        if buying_pressure > selling_pressure and latest['close'] > latest['open']:
            features["cvd_confirmation"] = True
            bullish_points += 1
        elif selling_pressure > buying_pressure and latest['close'] < latest['open']:
            features["cvd_confirmation"] = True
            bearish_points += 1

        # Finalize Trend Direction if BOS/CHOCH didn't explicitly trigger it
        if features["trend_direction"] == "NEUTRAL":
            if bullish_points > bearish_points:
                features["trend_direction"] = "BULLISH"
            elif bearish_points > bullish_points:
                features["trend_direction"] = "BEARISH"

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
