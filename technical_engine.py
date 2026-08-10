import logging
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


logger = logging.getLogger("BG_STAR_PRO_TechnicalEngine")


class TechnicalEngine:
    """
    BG STAR PRO - Technical Signal Engine

    Main responsibilities:
    - Accept market data as dict or DataFrame
    - Normalize OHLCV data safely
    - Calculate trend / momentum / volume / structure
    - Generate BUY / SELL candidates
    - Reject weak setups
    - Return clean candidate dictionaries for app.py
    """

    def __init__(
        self,
        minimum_score: int = 70,
        strong_score: int = 85,
    ):
        self.minimum_score = minimum_score
        self.strong_score = strong_score

        self.assets = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]

    # ============================================================
    # PUBLIC METHOD
    # ============================================================

    def analyze_market(self, live_data: Any) -> List[Dict[str, Any]]:
        """
        Main entry point used by app.py.

        Supports:
            DataFrame
            {
                "BTC": DataFrame,
                "ETH": DataFrame,
                ...
            }

        Also supports:
            {
                "BTC": {...},
                "ETH": {...}
            }
        """

        datasets = self._normalize_market_data(live_data)

        if not datasets:
            logger.warning("Technical Engine: no usable market data received.")
            return []

        candidates: List[Dict[str, Any]] = []

        for asset, raw_df in datasets.items():

            try:
                df = self._prepare_dataframe(raw_df)

                if df is None or df.empty:
                    logger.info(f"REJECT {asset}: empty_market_data")
                    continue

                if len(df) < 30:
                    logger.info(
                        f"REJECT {asset}: insufficient_data "
                        f"(rows={len(df)}, required=30)"
                    )
                    continue

                result = self._analyze_single_asset(asset, df)

                if result is None:
                    continue

                score = int(result.get("score", 0))
                reasons = result.get("rejection_reasons", [])

                if score < self.minimum_score:
                    if not reasons:
                        reasons = ["score_below_minimum"]

                    logger.info(
                        f"REJECT {asset}: score={score} < "
                        f"{self.minimum_score} | {reasons}"
                    )
                    continue

                candidates.append(result)

                logger.info(
                    f"CANDIDATE {asset}: "
                    f"{result['action']} | score={score} | "
                    f"triggers={result.get('triggers', [])}"
                )

            except Exception as exc:
                logger.exception(
                    f"Technical Engine error for {asset}: {exc}"
                )

        # Highest-quality candidates first
        candidates.sort(
            key=lambda x: x.get("score", 0),
            reverse=True
        )

        return candidates

    # ============================================================
    # DATA NORMALIZATION
    # ============================================================

    def _normalize_market_data(
        self,
        live_data: Any
    ) -> Dict[str, Any]:

        if live_data is None:
            return {}

        # Direct DataFrame
        if isinstance(live_data, pd.DataFrame):
            return {"BTC": live_data}

        # Dictionary
        if isinstance(live_data, dict):

            # Case:
            # {"BTC": DataFrame, "ETH": DataFrame}
            if any(
                isinstance(v, pd.DataFrame)
                for v in live_data.values()
            ):
                return {
                    str(k).upper(): v
                    for k, v in live_data.items()
                    if v is not None
                }

            # Case:
            # {"BTC": {"open": [...], ...}}
            result = {}

            for key, value in live_data.items():

                if isinstance(value, pd.DataFrame):
                    result[str(key).upper()] = value

                elif isinstance(value, dict):

                    try:
                        df = pd.DataFrame(value)

                        if not df.empty:
                            result[str(key).upper()] = df

                    except Exception:
                        continue

            # Case:
            # {"open": [...], "high": [...], ...}
            if not result and self._looks_like_ohlcv_dict(live_data):

                try:
                    return {
                        "BTC": pd.DataFrame(live_data)
                    }
                except Exception:
                    return {}

            return result

        logger.error(
            f"Unsupported live_data type: {type(live_data)}"
        )

        return {}

    def _looks_like_ohlcv_dict(self, data: Dict[str, Any]) -> bool:

        required_groups = [
            {"open", "high", "low", "close"},
            {"Open", "High", "Low", "Close"},
        ]

        keys = set(data.keys())

        for group in required_groups:
            if group.issubset(keys):
                return True

        return False

    # ============================================================
    # DATAFRAME PREPARATION
    # ============================================================

    def _prepare_dataframe(
        self,
        raw_df: Any
    ) -> Optional[pd.DataFrame]:

        if raw_df is None:
            return None

        if isinstance(raw_df, dict):

            try:
                raw_df = pd.DataFrame(raw_df)
            except Exception as exc:
                logger.error(
                    f"Could not convert dict to DataFrame: {exc}"
                )
                return None

        if not isinstance(raw_df, pd.DataFrame):
            return None

        if raw_df.empty:
            return None

        df = raw_df.copy()

        # Normalize column names
        df.columns = [
            str(col).strip().lower()
            for col in df.columns
        ]

        # Common aliases
        aliases = {
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
            "vol": "volume",
        }

        df.rename(columns=aliases, inplace=True)

        required = ["open", "high", "low", "close"]

        if not all(col in df.columns for col in required):
            logger.warning(
                f"Missing OHLC columns. Found: {list(df.columns)}"
            )
            return None

        if "volume" not in df.columns:
            df["volume"] = 0.0

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df.replace(
            [np.inf, -np.inf],
            np.nan,
            inplace=True
        )

        df.dropna(
            subset=["open", "high", "low", "close"],
            inplace=True
        )

        if df.empty:
            return None

        # Keep chronological order when possible
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.sort_index()

        return df.reset_index(drop=True)

    # ============================================================
    # SINGLE ASSET ANALYSIS
    # ============================================================

    def _analyze_single_asset(
        self,
        asset: str,
        df: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:

        df = df.copy()

        self._add_indicators(df)

        last = df.iloc[-1]
        prev = df.iloc[-2]

        close = float(last["close"])

        if close <= 0:
            return None

        # --------------------------------------------------------
        # TREND
        # --------------------------------------------------------

        ema_fast = float(last["ema_fast"])
        ema_slow = float(last["ema_slow"])

        trend_bullish = ema_fast > ema_slow
        trend_bearish = ema_fast < ema_slow

        # --------------------------------------------------------
        # MOMENTUM
        # --------------------------------------------------------

        rsi = float(last["rsi"])

        momentum_bullish = 52 <= rsi <= 72
        momentum_bearish = 28 <= rsi <= 48

        # --------------------------------------------------------
        # MACD
        # --------------------------------------------------------

        macd = float(last["macd"])
        macd_signal = float(last["macd_signal"])

        macd_bullish = macd > macd_signal
        macd_bearish = macd < macd_signal

        # --------------------------------------------------------
        # VOLUME
        # --------------------------------------------------------

        volume_ratio = float(last["volume_ratio"])

        volume_confirmed = volume_ratio >= 1.10

        # --------------------------------------------------------
        # PRICE STRUCTURE
        # --------------------------------------------------------

        recent_high = float(
            df["high"].iloc[-6:-1].max()
        )

        recent_low = float(
            df["low"].iloc[-6:-1].min()
        )

        bullish_breakout = close > recent_high
        bearish_breakdown = close < recent_low

        # --------------------------------------------------------
        # CANDLE
        # --------------------------------------------------------

        candle_range = max(
            float(last["high"] - last["low"]),
            0.00000001
        )

        body = abs(
            float(last["close"] - last["open"])
        )

        body_ratio = body / candle_range

        bullish_candle = (
            last["close"] > last["open"]
            and body_ratio >= 0.45
        )

        bearish_candle = (
            last["close"] < last["open"]
            and body_ratio >= 0.45
        )

        # --------------------------------------------------------
        # PRICE CHANGE
        # --------------------------------------------------------

        prev_close = float(prev["close"])

        price_change_pct = (
            (close - prev_close)
            / prev_close
            * 100
            if prev_close != 0
            else 0
        )

        # --------------------------------------------------------
        # ATR
        # --------------------------------------------------------

        atr = float(last["atr"])

        if atr > 0:
            atr_percent = (atr / close) * 100
        else:
            atr_percent = 0

        # --------------------------------------------------------
        # BUY SCORE
        # --------------------------------------------------------

        buy_score = 0
        buy_triggers = []

        if trend_bullish:
            buy_score += 22
            buy_triggers.append("EMA Trend Bullish")

        if macd_bullish:
            buy_score += 16
            buy_triggers.append("MACD Bullish")

        if momentum_bullish:
            buy_score += 14
            buy_triggers.append("RSI Momentum")

        if volume_confirmed and trend_bullish:
            buy_score += 14
            buy_triggers.append("Volume Confirmation")

        if bullish_breakout:
            buy_score += 16
            buy_triggers.append("Structure Breakout")

        if bullish_candle:
            buy_score += 8
            buy_triggers.append("Bullish Candle")

        if price_change_pct > 0:
            buy_score += 5

        # --------------------------------------------------------
        # SELL SCORE
        # --------------------------------------------------------

        sell_score = 0
        sell_triggers = []

        if trend_bearish:
            sell_score += 22
            sell_triggers.append("EMA Trend Bearish")

        if macd_bearish:
            sell_score += 16
            sell_triggers.append("MACD Bearish")

        if momentum_bearish:
            sell_score += 14
            sell_triggers.append("RSI Momentum")

        if volume_confirmed and trend_bearish:
            sell_score += 14
            sell_triggers.append("Volume Confirmation")

        if bearish_breakdown:
            sell_score += 16
            sell_triggers.append("Structure Breakdown")

        if bearish_candle:
            sell_score += 8
            sell_triggers.append("Bearish Candle")

        if price_change_pct < 0:
            sell_score += 5

        # --------------------------------------------------------
        # SELECT DIRECTION
        # --------------------------------------------------------

        if buy_score == 0 and sell_score == 0:
            return {
                "asset": asset,
                "coin": asset,
                "action": "WAIT",
                "score": 0,
                "triggers": [],
                "rejection_reasons": [
                    "no_directional_setup"
                ],
            }

        if buy_score >= sell_score:
            action = "BUY"
            score = min(buy_score, 100)
            triggers = buy_triggers
            opposite_score = sell_score
        else:
            action = "SELL"
            score = min(sell_score, 100)
            triggers = sell_triggers
            opposite_score = buy_score

        # --------------------------------------------------------
        # CONFIRMATION / REJECTION LOGIC
        # --------------------------------------------------------

        rejection_reasons = []

        if score < self.minimum_score:
            rejection_reasons.append("score_below_minimum")

        # Prevent weak direction when opposite side is almost equal
        if score > 0:
            direction_gap = score - opposite_score

            if direction_gap < 10:
                rejection_reasons.append(
                    "direction_not_clear"
                )

        # Avoid overbought BUY
        if action == "BUY" and rsi >= 78:
            rejection_reasons.append(
                "rsi_overbought"
            )

        # Avoid oversold SELL
        if action == "SELL" and rsi <= 22:
            rejection_reasons.append(
                "rsi_oversold"
            )

        # Need at least 2 technical confirmations
        if len(triggers) < 2:
            rejection_reasons.append(
                "insufficient_confirmation"
            )

        # --------------------------------------------------------
        # FINAL RESULT
        # --------------------------------------------------------

        result = {
            "asset": asset,
            "coin": asset,
            "action": action,
            "score": int(score),

            "signal_type": (
                "🟢 Strong Signal"
                if score >= self.strong_score
                else "🟡 Technical Signal"
            ),

            "triggers": triggers,

            "price": round(close, 8),

            "price_change_pct": round(
                price_change_pct,
                4
            ),

            "rsi": round(rsi, 2),

            "macd": round(
                macd,
                8
            ),

            "macd_signal": round(
                macd_signal,
                8
            ),

            "volume_ratio": round(
                volume_ratio,
                2
            ),

            "atr": round(
                atr,
                8
            ),

            "atr_percent": round(
                atr_percent,
                4
            ),

            "ema_fast": round(
                ema_fast,
                8
            ),

            "ema_slow": round(
                ema_slow,
                8
            ),

            "rejection_reasons": rejection_reasons,

            "reason": self._build_reason(
                action,
                score,
                triggers,
                rsi,
                volume_ratio
            ),
        }

        # If technically weak, don't return it as a candidate
        if rejection_reasons:
            logger.info(
                f"REJECT {asset}: score={score} < "
                f"{self.minimum_score} or confirmation failed "
                f"| {rejection_reasons}"
            )
            return None

        return result

    # ============================================================
    # INDICATORS
    # ============================================================

    def _add_indicators(
        self,
        df: pd.DataFrame
    ) -> None:

        # EMA
        df["ema_fast"] = (
            df["close"]
            .ewm(span=9, adjust=False)
            .mean()
        )

        df["ema_slow"] = (
            df["close"]
            .ewm(span=21, adjust=False)
            .mean()
        )

        # RSI
        delta = df["close"].diff()

        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()

        rs = avg_gain / avg_loss.replace(
            0,
            np.nan
        )

        df["rsi"] = (
            100
            - (100 / (1 + rs))
        )

        df["rsi"] = df["rsi"].fillna(50)

        # MACD
        ema12 = (
            df["close"]
            .ewm(span=12, adjust=False)
            .mean()
        )

        ema26 = (
            df["close"]
            .ewm(span=26, adjust=False)
            .mean()
        )

        df["macd"] = ema12 - ema26

        df["macd_signal"] = (
            df["macd"]
            .ewm(span=9, adjust=False)
            .mean()
        )

        # ATR
        previous_close = df["close"].shift(1)

        tr1 = (
            df["high"]
            - df["low"]
        )

        tr2 = (
            df["high"]
            - previous_close
        ).abs()

        tr3 = (
            df["low"]
            - previous_close
        ).abs()

        true_range = pd.concat(
            [tr1, tr2, tr3],
            axis=1
        ).max(axis=1)

        df["atr"] = (
            true_range
            .rolling(14)
            .mean()
        )

        # Volume ratio
        volume_mean = (
            df["volume"]
            .rolling(14)
            .mean()
        )

        df["volume_ratio"] = (
            df["volume"]
            / volume_mean.replace(
                0,
                np.nan
            )
        )

        df["volume_ratio"] = (
            df["volume_ratio"]
            .replace(
                [np.inf, -np.inf],
                np.nan
            )
            .fillna(1.0)
        )

        # Final cleanup
        numeric_columns = [
            "ema_fast",
            "ema_slow",
            "rsi",
            "macd",
            "macd_signal",
            "atr",
            "volume_ratio",
        ]

        for col in numeric_columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df[numeric_columns] = (
            df[numeric_columns]
            .replace(
                [np.inf, -np.inf],
                np.nan
            )
            .ffill()
            .bfill()
        )

    # ============================================================
    # REASONING
    # ============================================================

    def _build_reason(
        self,
        action: str,
        score: int,
        triggers: List[str],
        rsi: float,
        volume_ratio: float,
    ) -> str:

        direction = (
            "bullish"
            if action == "BUY"
            else "bearish"
        )

        trigger_text = ", ".join(
            triggers[:5]
        )

        return (
            f"{direction.capitalize()} technical structure "
            f"with score {score}/100. "
            f"Confirmations: {trigger_text}. "
            f"RSI={rsi:.1f}, "
            f"VolumeRatio={volume_ratio:.2f}."
        )


# ================================================================
# SAFE FACTORY
# ================================================================

def create_technical_engine() -> TechnicalEngine:
    return TechnicalEngine(
        minimum_score=70,
        strong_score=85
    )
