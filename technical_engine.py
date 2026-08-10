import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


logger = logging.getLogger("BG_STAR_PRO_TechnicalEngine")


class TechnicalEngine:
    """
    BG STAR PRO - Robust Technical Signal Engine

    Main goals:
    - Never crash when market data is dict/list/DataFrame.
    - Always return a dictionary from analyze_market().
    - Produce stable technical scores.
    - Avoid false signals from incomplete candles/data.
    - Keep output compatible with app.py:
          for coin, data in tech_results.items():
              ...
    """

    def __init__(self):
        self.minimum_bars = 30
        self.minimum_score = 70

    # ==========================================================
    # PUBLIC ENTRY POINT
    # ==========================================================

    def analyze_market(self, market_data: Any) -> Dict[str, Dict[str, Any]]:
        """
        Analyze all available assets.

        IMPORTANT:
        This always returns a DICT.
        """

        results: Dict[str, Dict[str, Any]] = {}

        if market_data is None:
            return results

        # ------------------------------------------------------
        # Case 1: pandas DataFrame = single market dataset
        # ------------------------------------------------------
        if isinstance(market_data, pd.DataFrame):
            result = self._analyze_dataframe(market_data, "MARKET")

            if result is not None:
                results["MARKET"] = result

            return results

        # ------------------------------------------------------
        # Case 2: dictionary
        #
        # Usually:
        # {
        #     "BTC": dataframe/dict/list,
        #     "ETH": dataframe/dict/list,
        #     ...
        # }
        # ------------------------------------------------------
        if isinstance(market_data, dict):

            for coin, raw_data in market_data.items():

                try:
                    # Ignore metadata/scalar values.
                    if not self._looks_like_market_data(raw_data):
                        continue

                    result = self._analyze_any(raw_data, str(coin))

                    if result is not None:
                        results[str(coin)] = result

                except Exception as exc:
                    logger.exception(
                        "Technical analysis failed for %s: %s",
                        coin,
                        exc
                    )

                    # Never stop the complete cycle because of one coin.
                    results[str(coin)] = self._empty_result(
                        str(coin),
                        reason="analysis_error"
                    )

            return results

        # ------------------------------------------------------
        # Case 3: list
        #
        # This can happen if the fetcher returns:
        # [
        #     {"symbol":"BTC", ...},
        #     {"symbol":"ETH", ...}
        # ]
        # ------------------------------------------------------
        if isinstance(market_data, list):

            for index, item in enumerate(market_data):

                try:
                    if not isinstance(item, dict):
                        continue

                    coin = (
                        item.get("symbol")
                        or item.get("coin")
                        or item.get("asset")
                        or f"ASSET_{index}"
                    )

                    result = self._analyze_any(item, str(coin))

                    if result is not None:
                        results[str(coin)] = result

                except Exception as exc:
                    logger.exception(
                        "Technical list item failed: %s",
                        exc
                    )

            return results

        logger.warning(
            "Unsupported market_data type: %s",
            type(market_data).__name__
        )

        return results

    # ==========================================================
    # UNIVERSAL DATA HANDLER
    # ==========================================================

    def _analyze_any(
        self,
        raw_data: Any,
        coin: str
    ) -> Optional[Dict[str, Any]]:

        # DataFrame
        if isinstance(raw_data, pd.DataFrame):
            return self._analyze_dataframe(raw_data, coin)

        # Dictionary
        if isinstance(raw_data, dict):

            # Sometimes a single candle dict is supplied.
            if self._looks_like_candle(raw_data):
                df = self._dict_to_dataframe(raw_data)

            # Sometimes data is nested.
            elif "data" in raw_data:
                df = self._to_dataframe(raw_data["data"])

            elif "candles" in raw_data:
                df = self._to_dataframe(raw_data["candles"])

            elif "ohlcv" in raw_data:
                df = self._to_dataframe(raw_data["ohlcv"])

            else:
                df = self._dict_to_dataframe(raw_data)

            if df is None or df.empty:
                return self._empty_result(
                    coin,
                    reason="empty_market_data"
                )

            return self._analyze_dataframe(df, coin)

        # List
        if isinstance(raw_data, list):
            df = self._to_dataframe(raw_data)

            if df is None or df.empty:
                return self._empty_result(
                    coin,
                    reason="empty_market_data"
                )

            return self._analyze_dataframe(df, coin)

        return None

    # ==========================================================
    # DATAFRAME CONVERSION
    # ==========================================================

    def _to_dataframe(self, data: Any) -> Optional[pd.DataFrame]:

        if data is None:
            return None

        if isinstance(data, pd.DataFrame):
            return data.copy()

        if isinstance(data, list):

            if not data:
                return None

            try:
                return pd.DataFrame(data)
            except Exception as exc:
                logger.error(
                    "Could not convert list to DataFrame: %s",
                    exc
                )
                return None

        if isinstance(data, dict):

            # OHLCV column dictionary
            try:

                values = list(data.values())

                # If values contain lists, this is probably
                # column-oriented market data.
                if values and any(
                    isinstance(v, (list, tuple, np.ndarray, pd.Series))
                    for v in values
                ):
                    return pd.DataFrame(data)

                # Single candle/scalar dictionary.
                return pd.DataFrame([data])

            except Exception as exc:
                logger.error(
                    "Could not convert dict to DataFrame: %s",
                    exc
                )
                return None

        return None

    def _dict_to_dataframe(
        self,
        data: Dict[str, Any]
    ) -> Optional[pd.DataFrame]:

        if not data:
            return None

        try:
            return pd.DataFrame([data])
        except Exception:
            return None

    # ==========================================================
    # MARKET DATA VALIDATION
    # ==========================================================

    def _looks_like_market_data(self, data: Any) -> bool:

        if isinstance(data, pd.DataFrame):
            return not data.empty

        if isinstance(data, list):
            return len(data) > 0

        if isinstance(data, dict):

            market_keys = {
                "open",
                "high",
                "low",
                "close",
                "volume",
                "data",
                "candles",
                "ohlcv"
            }

            return bool(
                market_keys.intersection(
                    {str(k).lower() for k in data.keys()}
                )
            )

        return False

    def _looks_like_candle(self, data: Dict[str, Any]) -> bool:

        keys = {
            str(k).lower()
            for k in data.keys()
        }

        required = {"open", "high", "low", "close"}

        return required.issubset(keys)

    # ==========================================================
    # MAIN TECHNICAL ANALYSIS
    # ==========================================================

    def _analyze_dataframe(
        self,
        df: pd.DataFrame,
        coin: str
    ) -> Dict[str, Any]:

        try:

            df = self._prepare_dataframe(df)

            if df is None or df.empty:
                return self._empty_result(
                    coin,
                    reason="empty_market_data"
                )

            if len(df) < self.minimum_bars:
                return self._empty_result(
                    coin,
                    reason=f"insufficient_bars_{len(df)}"
                )

            # --------------------------------------------------
            # Indicators
            # --------------------------------------------------

            df["ema9"] = df["close"].ewm(
                span=9,
                adjust=False
            ).mean()

            df["ema21"] = df["close"].ewm(
                span=21,
                adjust=False
            ).mean()

            df["ema50"] = df["close"].ewm(
                span=50,
                adjust=False
            ).mean()

            # RSI
            delta = df["close"].diff()

            gain = delta.clip(lower=0)
            loss = -delta.clip(upper=0)

            avg_gain = gain.rolling(14).mean()
            avg_loss = loss.rolling(14).mean()

            rs = avg_gain / avg_loss.replace(0, np.nan)

            df["rsi"] = 100 - (
                100 / (1 + rs)
            )

            df["rsi"] = df["rsi"].fillna(50)

            # ATR
            previous_close = df["close"].shift(1)

            tr1 = df["high"] - df["low"]
            tr2 = (df["high"] - previous_close).abs()
            tr3 = (df["low"] - previous_close).abs()

            df["tr"] = pd.concat(
                [tr1, tr2, tr3],
                axis=1
            ).max(axis=1)

            df["atr"] = df["tr"].rolling(14).mean()

            # Volume average
            df["volume_ma"] = df["volume"].rolling(20).mean()

            # --------------------------------------------------
            # Current values
            # --------------------------------------------------

            last = df.iloc[-1]
            prev = df.iloc[-2]

            close = self._safe_float(last["close"])
            prev_close = self._safe_float(prev["close"])

            ema9 = self._safe_float(last["ema9"])
            ema21 = self._safe_float(last["ema21"])
            ema50 = self._safe_float(last["ema50"])

            rsi = self._safe_float(last["rsi"], 50)

            atr = self._safe_float(last["atr"], 0)

            volume = self._safe_float(last["volume"], 0)
            volume_ma = self._safe_float(
                last["volume_ma"],
                0
            )

            # --------------------------------------------------
            # Trend
            # --------------------------------------------------

            bullish_trend = (
                close > ema21
                and ema9 > ema21
            )

            bearish_trend = (
                close < ema21
                and ema9 < ema21
            )

            strong_bullish_trend = (
                bullish_trend
                and close > ema50
                and ema21 > ema50
            )

            strong_bearish_trend = (
                bearish_trend
                and close < ema50
                and ema21 < ema50
            )

            # --------------------------------------------------
            # Momentum
            # --------------------------------------------------

            bullish_momentum = rsi >= 55 and rsi <= 72
            bearish_momentum = rsi <= 45 and rsi >= 28

            # --------------------------------------------------
            # Volume confirmation
            # --------------------------------------------------

            volume_ratio = (
                volume / volume_ma
                if volume_ma > 0
                else 1.0
            )

            volume_confirmed = volume_ratio >= 1.15

            # --------------------------------------------------
            # Price displacement
            # --------------------------------------------------

            price_move_pct = 0.0

            if prev_close > 0:
                price_move_pct = (
                    (close - prev_close)
                    / prev_close
                ) * 100

            # --------------------------------------------------
            # Structure
            # --------------------------------------------------

            recent_high = df["high"].iloc[-11:-1].max()
            recent_low = df["low"].iloc[-11:-1].min()

            bullish_breakout = (
                close > recent_high
            )

            bearish_breakdown = (
                close < recent_low
            )

            # --------------------------------------------------
            # Candle pressure
            # --------------------------------------------------

            candle_range = max(
                self._safe_float(last["high"])
                - self._safe_float(last["low"]),
                0.0
            )

            candle_body = abs(
                close
                - self._safe_float(last["open"])
            )

            body_ratio = (
                candle_body / candle_range
                if candle_range > 0
                else 0
            )

            bullish_candle = (
                close > self._safe_float(last["open"])
                and body_ratio >= 0.45
            )

            bearish_candle = (
                close < self._safe_float(last["open"])
                and body_ratio >= 0.45
            )

            # --------------------------------------------------
            # Score
            # --------------------------------------------------

            buy_score = 0
            sell_score = 0

            buy_triggers = []
            sell_triggers = []

            # Trend
            if bullish_trend:
                buy_score += 18
                buy_triggers.append("EMA Bullish")

            if strong_bullish_trend:
                buy_score += 10
                buy_triggers.append("HTF Trend Alignment")

            if bearish_trend:
                sell_score += 18
                sell_triggers.append("EMA Bearish")

            if strong_bearish_trend:
                sell_score += 10
                sell_triggers.append("HTF Trend Alignment")

            # Momentum
            if bullish_momentum:
                buy_score += 16
                buy_triggers.append("RSI Momentum")

            if bearish_momentum:
                sell_score += 16
                sell_triggers.append("RSI Momentum")

            # Breakout
            if bullish_breakout:
                buy_score += 20
                buy_triggers.append("Bullish Breakout")

            if bearish_breakdown:
                sell_score += 20
                sell_triggers.append("Bearish Breakdown")

            # Volume
            if volume_confirmed:

                if price_move_pct > 0:
                    buy_score += 14
                    buy_triggers.append("Volume Confirmation")

                elif price_move_pct < 0:
                    sell_score += 14
                    sell_triggers.append("Volume Confirmation")

            # Candle confirmation
            if bullish_candle:
                buy_score += 10
                buy_triggers.append("Bullish Candle")

            if bearish_candle:
                sell_score += 10
                sell_triggers.append("Bearish Candle")

            # Small price displacement
            if price_move_pct >= 0.20:
                buy_score += 5
                buy_triggers.append("Positive Price Expansion")

            if price_move_pct <= -0.20:
                sell_score += 5
                sell_triggers.append("Negative Price Expansion")

            # --------------------------------------------------
            # Clamp scores
            # --------------------------------------------------

            buy_score = int(
                max(0, min(100, buy_score))
            )

            sell_score = int(
                max(0, min(100, sell_score))
            )

            # --------------------------------------------------
            # Final direction
            # --------------------------------------------------

            if buy_score > sell_score:
                action = "BUY"
                score = buy_score
                triggers = buy_triggers

            elif sell_score > buy_score:
                action = "SELL"
                score = sell_score
                triggers = sell_triggers

            else:
                action = "WAIT"
                score = max(
                    buy_score,
                    sell_score
                )
                triggers = []

            # --------------------------------------------------
            # Confirmation
            # --------------------------------------------------

            structure_confirmed = (
                bullish_breakout
                or bearish_breakdown
                or strong_bullish_trend
                or strong_bearish_trend
            )

            momentum_confirmed = (
                bullish_momentum
                or bearish_momentum
            )

            # --------------------------------------------------
            # Anti-whipsaw
            #
            # Do NOT force BUY/SELL when the evidence is weak.
            # --------------------------------------------------

            if score < self.minimum_score:

                return {
                    "coin": coin,
                    "action": "WAIT",
                    "score": score,
                    "buy_score": buy_score,
                    "sell_score": sell_score,
                    "triggers": triggers,
                    "signal": False,
                    "structure_confirmed": structure_confirmed,
                    "momentum_confirmed": momentum_confirmed,
                    "volume_confirmed": volume_confirmed,
                    "weak_adx": False,
                    "pressure": "NEUTRAL",
                    "rsi": round(rsi, 2),
                    "volume_ratio": round(
                        volume_ratio,
                        2
                    ),
                    "price_move_pct": round(
                        price_move_pct,
                        3
                    ),
                    "atr": round(
                        atr,
                        8
                    ),
                    "reason": "score_below_minimum"
                }

            # --------------------------------------------------
            # Strong signal requirement
            # --------------------------------------------------

            confirmation_count = sum(
                [
                    structure_confirmed,
                    momentum_confirmed,
                    volume_confirmed,
                ]
            )

            if confirmation_count < 2:

                return {
                    "coin": coin,
                    "action": "WAIT",
                    "score": score,
                    "buy_score": buy_score,
                    "sell_score": sell_score,
                    "triggers": triggers,
                    "signal": False,
                    "structure_confirmed": structure_confirmed,
                    "momentum_confirmed": momentum_confirmed,
                    "volume_confirmed": volume_confirmed,
                    "weak_adx": False,
                    "pressure": "NEUTRAL",
                    "rsi": round(rsi, 2),
                    "volume_ratio": round(
                        volume_ratio,
                        2
                    ),
                    "price_move_pct": round(
                        price_move_pct,
                        3
                    ),
                    "atr": round(
                        atr,
                        8
                    ),
                    "reason": "confirmation_failed"
                }

            # --------------------------------------------------
            # Final strong signal
            # --------------------------------------------------

            pressure = (
                "BULLISH"
                if action == "BUY"
                else "BEARISH"
            )

            return {
                "coin": coin,
                "action": action,
                "score": score,
                "buy_score": buy_score,
                "sell_score": sell_score,
                "triggers": triggers,
                "signal": True,
                "structure_confirmed": structure_confirmed,
                "momentum_confirmed": momentum_confirmed,
                "volume_confirmed": volume_confirmed,
                "weak_adx": False,
                "pressure": pressure,
                "rsi": round(rsi, 2),
                "volume_ratio": round(
                    volume_ratio,
                    2
                ),
                "price_move_pct": round(
                    price_move_pct,
                    3
                ),
                "atr": round(
                    atr,
                    8
                ),
                "reason": "technical_confirmation_passed"
            }

        except Exception as exc:

            logger.exception(
                "Technical engine error for %s: %s",
                coin,
                exc
            )

            return self._empty_result(
                coin,
                reason="technical_engine_error"
            )

    # ==========================================================
    # DATA PREPARATION
    # ==========================================================

    def _prepare_dataframe(
        self,
        df: pd.DataFrame
    ) -> Optional[pd.DataFrame]:

        if df is None or df.empty:
            return None

        df = df.copy()

        # Normalize column names
        df.columns = [
            str(c).strip().lower()
            for c in df.columns
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

        for old, new in aliases.items():

            if old in df.columns and new not in df.columns:
                df[new] = df[old]

        required = [
            "open",
            "high",
            "low",
            "close"
        ]

        for column in required:

            if column not in df.columns:
                logger.warning(
                    "Missing OHLC column: %s",
                    column
                )
                return None

        if "volume" not in df.columns:
            df["volume"] = 0.0

        # Numeric conversion
        for column in [
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]:

            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

        # Remove invalid rows
        df = df.dropna(
            subset=[
                "open",
                "high",
                "low",
                "close"
            ]
        )

        # Remove impossible prices
        df = df[
            (df["close"] > 0)
            & (df["high"] > 0)
            & (df["low"] > 0)
        ]

        if df.empty:
            return None

        # Sort by index/time if possible
        if "timestamp" in df.columns:

            try:
                df = df.sort_values(
                    "timestamp"
                )
            except Exception:
                pass

        return df.reset_index(
            drop=True
        )

    # ==========================================================
    # EMPTY / SAFE HELPERS
    # ==========================================================

    def _empty_result(
        self,
        coin: str,
        reason: str
    ) -> Dict[str, Any]:

        return {
            "coin": coin,
            "action": "WAIT",
            "score": 0,
            "buy_score": 0,
            "sell_score": 0,
            "triggers": [],
            "signal": False,
            "structure_confirmed": False,
            "momentum_confirmed": False,
            "volume_confirmed": False,
            "weak_adx": False,
            "pressure": "NEUTRAL",
            "rsi": 50.0,
            "volume_ratio": 0.0,
            "price_move_pct": 0.0,
            "atr": 0.0,
            "reason": reason
        }

    @staticmethod
    def _safe_float(
        value: Any,
        default: float = 0.0
    ) -> float:

        try:

            if value is None:
                return default

            value = float(value)

            if not np.isfinite(value):
                return default

            return value

        except Exception:
            return default


# ==========================================================
# COMPATIBILITY ALIAS
# ==========================================================

TechnicalEngineV2 = TechnicalEngine
