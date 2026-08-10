# technical_engine.py

import logging
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


logger = logging.getLogger("BG_STAR_PRO_TechnicalEngine")


class TechnicalEngine:
    """
    BG STAR PRO - Technical Signal Engine

    Designed to work with the current app.py.

    Main changes:
    - Does NOT over-filter good setups.
    - Produces BUY/SELL candidates when directional evidence is strong.
    - Uses score as the main technical quality measure.
    - Structure / momentum / volume are confirmations, not all mandatory.
    - Keeps compatibility with MasterSignalBot.
    - Handles DataFrame / dict / list input safely.
    - Uses the latest CLOSED candle when possible.
    """

    def __init__(self):

        self.minimum_bars = 50

        # Technical engine can create a candidate from 65+.
        # app.py will still apply its own final MIN_SIGNAL_SCORE.
        self.minimum_score = 65

        # Minimum directional edge between BUY and SELL.
        self.minimum_direction_edge = 8

    # ==========================================================
    # PUBLIC ENTRY
    # ==========================================================

    def analyze_market(
        self,
        market_data: Any
    ) -> Dict[str, Dict[str, Any]]:

        results: Dict[str, Dict[str, Any]] = {}

        if market_data is None:
            return results

        # ------------------------------------------------------
        # Single DataFrame
        # ------------------------------------------------------

        if isinstance(market_data, pd.DataFrame):

            result = self._analyze_dataframe(
                market_data,
                "MARKET"
            )

            if result is not None:
                results["MARKET"] = result

            return results

        # ------------------------------------------------------
        # Dictionary
        # ------------------------------------------------------

        if isinstance(market_data, dict):

            for coin, raw_data in market_data.items():

                try:

                    if not self._looks_like_market_data(
                        raw_data
                    ):
                        continue

                    result = self._analyze_any(
                        raw_data,
                        str(coin)
                    )

                    if result is not None:
                        results[str(coin)] = result

                except Exception as exc:

                    logger.exception(
                        "Technical analysis failed for %s: %s",
                        coin,
                        exc
                    )

                    results[str(coin)] = self._empty_result(
                        str(coin),
                        "analysis_error"
                    )

            return results

        # ------------------------------------------------------
        # List
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

                    result = self._analyze_any(
                        item,
                        str(coin)
                    )

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

        if isinstance(raw_data, pd.DataFrame):

            return self._analyze_dataframe(
                raw_data,
                coin
            )

        if isinstance(raw_data, dict):

            if "data" in raw_data:
                df = self._to_dataframe(
                    raw_data["data"]
                )

            elif "candles" in raw_data:
                df = self._to_dataframe(
                    raw_data["candles"]
                )

            elif "ohlcv" in raw_data:
                df = self._to_dataframe(
                    raw_data["ohlcv"]
                )

            elif self._looks_like_candle(raw_data):
                df = self._dict_to_dataframe(
                    raw_data
                )

            else:
                df = self._dict_to_dataframe(
                    raw_data
                )

            if df is None or df.empty:

                return self._empty_result(
                    coin,
                    "empty_market_data"
                )

            return self._analyze_dataframe(
                df,
                coin
            )

        if isinstance(raw_data, list):

            df = self._to_dataframe(
                raw_data
            )

            if df is None or df.empty:

                return self._empty_result(
                    coin,
                    "empty_market_data"
                )

            return self._analyze_dataframe(
                df,
                coin
            )

        return None

    # ==========================================================
    # DATAFRAME CONVERSION
    # ==========================================================

    def _to_dataframe(
        self,
        data: Any
    ) -> Optional[pd.DataFrame]:

        if data is None:
            return None

        if isinstance(data, pd.DataFrame):

            return data.copy()

        if isinstance(data, list):

            if not data:
                return None

            try:

                # CCXT OHLCV:
                # [timestamp, open, high, low, close, volume]
                if (
                    isinstance(data[0], (list, tuple))
                    and len(data[0]) >= 6
                ):

                    return pd.DataFrame(
                        data,
                        columns=[
                            "timestamp",
                            "open",
                            "high",
                            "low",
                            "close",
                            "volume"
                        ]
                    )

                return pd.DataFrame(data)

            except Exception as exc:

                logger.error(
                    "List -> DataFrame failed: %s",
                    exc
                )

                return None

        if isinstance(data, dict):

            try:

                values = list(data.values())

                if values and any(
                    isinstance(
                        v,
                        (
                            list,
                            tuple,
                            np.ndarray,
                            pd.Series
                        )
                    )
                    for v in values
                ):

                    return pd.DataFrame(data)

                return pd.DataFrame([data])

            except Exception as exc:

                logger.error(
                    "Dict -> DataFrame failed: %s",
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
    # DATA VALIDATION
    # ==========================================================

    def _looks_like_market_data(
        self,
        data: Any
    ) -> bool:

        if isinstance(data, pd.DataFrame):
            return not data.empty

        if isinstance(data, list):
            return len(data) > 0

        if isinstance(data, dict):

            keys = {
                str(k).lower()
                for k in data.keys()
            }

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
                keys.intersection(market_keys)
            )

        return False

    def _looks_like_candle(
        self,
        data: Dict[str, Any]
    ) -> bool:

        keys = {
            str(k).lower()
            for k in data.keys()
        }

        return {
            "open",
            "high",
            "low",
            "close"
        }.issubset(keys)

    # ==========================================================
    # MAIN ANALYSIS
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
                    "empty_market_data"
                )

            if len(df) < self.minimum_bars:

                return self._empty_result(
                    coin,
                    f"insufficient_bars_{len(df)}"
                )

            # --------------------------------------------------
            # IMPORTANT:
            # Ignore currently forming candle when possible.
            # KuCoin fetcher supplies timestamp data.
            # Master app also has ClosedCandle=True from volatility.
            # --------------------------------------------------

            analysis_df = df.copy()

            if len(analysis_df) >= 3:

                try:

                    last_ts = pd.to_datetime(
                        analysis_df.iloc[-1]["timestamp"]
                    )

                    now = pd.Timestamp.utcnow()

                    if last_ts.tzinfo is None:
                        last_ts = last_ts.tz_localize("UTC")

                    if last_ts > now:
                        analysis_df = analysis_df.iloc[:-1]

                except Exception:
                    pass

            if len(analysis_df) < self.minimum_bars:
                return self._empty_result(
                    coin,
                    "insufficient_closed_bars"
                )

            df = analysis_df

            # --------------------------------------------------
            # INDICATORS
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

            gain = delta.clip(
                lower=0
            )

            loss = -delta.clip(
                upper=0
            )

            avg_gain = gain.rolling(
                14,
                min_periods=14
            ).mean()

            avg_loss = loss.rolling(
                14,
                min_periods=14
            ).mean()

            rs = (
                avg_gain
                /
                avg_loss.replace(
                    0,
                    np.nan
                )
            )

            df["rsi"] = (
                100
                -
                (
                    100
                    /
                    (1 + rs)
                )
            )

            df["rsi"] = df["rsi"].fillna(50)

            # ATR
            previous_close = df["close"].shift(1)

            tr1 = (
                df["high"]
                -
                df["low"]
            )

            tr2 = (
                df["high"]
                -
                previous_close
            ).abs()

            tr3 = (
                df["low"]
                -
                previous_close
            ).abs()

            df["tr"] = pd.concat(
                [
                    tr1,
                    tr2,
                    tr3
                ],
                axis=1
            ).max(axis=1)

            df["atr"] = df["tr"].rolling(
                14,
                min_periods=14
            ).mean()

            # Volume
            df["volume_ma"] = df["volume"].rolling(
                20,
                min_periods=5
            ).mean()

            # --------------------------------------------------
            # CURRENT VALUES
            # --------------------------------------------------

            last = df.iloc[-1]
            prev = df.iloc[-2]

            close = self._safe_float(
                last["close"]
            )

            prev_close = self._safe_float(
                prev["close"]
            )

            open_price = self._safe_float(
                last["open"]
            )

            high = self._safe_float(
                last["high"]
            )

            low = self._safe_float(
                last["low"]
            )

            ema9 = self._safe_float(
                last["ema9"]
            )

            ema21 = self._safe_float(
                last["ema21"]
            )

            ema50 = self._safe_float(
                last["ema50"]
            )

            rsi = self._safe_float(
                last["rsi"],
                50
            )

            atr = self._safe_float(
                last["atr"],
                0
            )

            volume = self._safe_float(
                last["volume"],
                0
            )

            volume_ma = self._safe_float(
                last["volume_ma"],
                0
            )

            # --------------------------------------------------
            # PRICE MOVE
            # --------------------------------------------------

            price_move_pct = 0.0

            if prev_close > 0:

                price_move_pct = (
                    (
                        close
                        -
                        prev_close
                    )
                    /
                    prev_close
                ) * 100

            # --------------------------------------------------
            # TREND
            # --------------------------------------------------

            bullish_trend = (
                close > ema21
                and ema9 >= ema21
            )

            bearish_trend = (
                close < ema21
                and ema9 <= ema21
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
            # RSI MOMENTUM
            # --------------------------------------------------

            bullish_momentum = (
                52 <= rsi <= 72
            )

            bearish_momentum = (
                28 <= rsi <= 48
            )

            # --------------------------------------------------
            # VOLUME
            # --------------------------------------------------

            volume_ratio = (
                volume / volume_ma
                if volume_ma > 0
                else 1.0
            )

            volume_confirmed = (
                volume_ratio >= 1.10
            )

            # --------------------------------------------------
            # STRUCTURE
            # --------------------------------------------------

            lookback = min(
                12,
                len(df) - 2
            )

            recent_high = (
                df["high"]
                .iloc[-lookback:-1]
                .max()
            )

            recent_low = (
                df["low"]
                .iloc[-lookback:-1]
                .min()
            )

            bullish_breakout = (
                close > recent_high
            )

            bearish_breakdown = (
                close < recent_low
            )

            # --------------------------------------------------
            # RECENT SWING STRUCTURE
            # --------------------------------------------------

            previous_high = (
                df["high"]
                .iloc[-6:-2]
                .max()
            )

            previous_low = (
                df["low"]
                .iloc[-6:-2]
                .min()
            )

            bullish_structure = (
                close > previous_high
            )

            bearish_structure = (
                close < previous_low
            )

            # --------------------------------------------------
            # CANDLE PRESSURE
            # --------------------------------------------------

            candle_range = max(
                high - low,
                0.0
            )

            candle_body = abs(
                close - open_price
            )

            body_ratio = (
                candle_body / candle_range
                if candle_range > 0
                else 0
            )

            bullish_candle = (
                close > open_price
                and body_ratio >= 0.40
            )

            bearish_candle = (
                close < open_price
                and body_ratio >= 0.40
            )

            # --------------------------------------------------
            # SCORE
            #
            # More balanced than the previous engine.
            # --------------------------------------------------

            buy_score = 0
            sell_score = 0

            buy_triggers = []
            sell_triggers = []

            # Trend
            if bullish_trend:

                buy_score += 18
                buy_triggers.append(
                    "EMA Bullish"
                )

            if strong_bullish_trend:

                buy_score += 8
                buy_triggers.append(
                    "HTF Trend Alignment"
                )

            if bearish_trend:

                sell_score += 18
                sell_triggers.append(
                    "EMA Bearish"
                )

            if strong_bearish_trend:

                sell_score += 8
                sell_triggers.append(
                    "HTF Trend Alignment"
                )

            # RSI
            if bullish_momentum:

                buy_score += 15
                buy_triggers.append(
                    "RSI Momentum"
                )

            if bearish_momentum:

                sell_score += 15
                sell_triggers.append(
                    "RSI Momentum"
                )

            # Structure / breakout
            if bullish_breakout:

                buy_score += 20
                buy_triggers.append(
                    "Bullish Breakout"
                )

            elif bullish_structure:

                buy_score += 12
                buy_triggers.append(
                    "Bullish Structure"
                )

            if bearish_breakdown:

                sell_score += 20
                sell_triggers.append(
                    "Bearish Breakdown"
                )

            elif bearish_structure:

                sell_score += 12
                sell_triggers.append(
                    "Bearish Structure"
                )

            # Volume
            if volume_confirmed:

                if price_move_pct > 0:

                    buy_score += 12
                    buy_triggers.append(
                        "Volume Confirmation"
                    )

                elif price_move_pct < 0:

                    sell_score += 12
                    sell_triggers.append(
                        "Volume Confirmation"
                    )

                else:

                    # Volume is high but direction is unclear.
                    # Give small support to dominant trend.
                    if bullish_trend:

                        buy_score += 5
                        buy_triggers.append(
                            "Volume Support"
                        )

                    elif bearish_trend:

                        sell_score += 5
                        sell_triggers.append(
                            "Volume Support"
                        )

            # Candle
            if bullish_candle:

                buy_score += 8
                buy_triggers.append(
                    "Bullish Candle"
                )

            if bearish_candle:

                sell_score += 8
                sell_triggers.append(
                    "Bearish Candle"
                )

            # Price expansion
            if price_move_pct >= 0.15:

                buy_score += 5
                buy_triggers.append(
                    "Positive Price Expansion"
                )

            elif price_move_pct <= -0.15:

                sell_score += 5
                sell_triggers.append(
                    "Negative Price Expansion"
                )

            # --------------------------------------------------
            # Clamp
            # --------------------------------------------------

            buy_score = int(
                max(
                    0,
                    min(
                        100,
                        buy_score
                    )
                )
            )

            sell_score = int(
                max(
                    0,
                    min(
                        100,
                        sell_score
                    )
                )
            )

            # --------------------------------------------------
            # DIRECTION
            # --------------------------------------------------

            score_difference = abs(
                buy_score - sell_score
            )

            if (
                buy_score >= self.minimum_score
                and buy_score > sell_score
                and score_difference >= self.minimum_direction_edge
            ):

                action = "BUY"
                score = buy_score
                triggers = buy_triggers

            elif (
                sell_score >= self.minimum_score
                and sell_score > buy_score
                and score_difference >= self.minimum_direction_edge
            ):

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
            # CONFIRMATIONS
            #
            # These are now descriptive.
            # They do NOT kill the signal here.
            # --------------------------------------------------

            if action == "BUY":

                structure_confirmed = (
                    bullish_breakout
                    or bullish_structure
                    or strong_bullish_trend
                )

                momentum_confirmed = (
                    bullish_momentum
                    or bullish_candle
                )

            elif action == "SELL":

                structure_confirmed = (
                    bearish_breakdown
                    or bearish_structure
                    or strong_bearish_trend
                )

                momentum_confirmed = (
                    bearish_momentum
                    or bearish_candle
                )

            else:

                structure_confirmed = (
                    bullish_breakout
                    or bearish_breakdown
                    or bullish_structure
                    or bearish_structure
                )

                momentum_confirmed = (
                    bullish_momentum
                    or bearish_momentum
                )

            # --------------------------------------------------
            # SIGNAL QUALITY
            # --------------------------------------------------

            confirmation_count = sum(
                [
                    bool(structure_confirmed),
                    bool(momentum_confirmed),
                    bool(volume_confirmed)
                ]
            )

            # --------------------------------------------------
            # WEAK TREND WARNING
            # --------------------------------------------------

            weak_trend = (
                not bullish_trend
                and not bearish_trend
            )

            # --------------------------------------------------
            # PRESSURE
            # --------------------------------------------------

            if action == "BUY":
                pressure = "BULLISH"

            elif action == "SELL":
                pressure = "BEARISH"

            else:

                if buy_score > sell_score:
                    pressure = "LEAN_BULLISH"

                elif sell_score > buy_score:
                    pressure = "LEAN_BEARISH"

                else:
                    pressure = "NEUTRAL"

            # --------------------------------------------------
            # SIGNAL DECISION
            #
            # IMPORTANT:
            # No second hard confirmation gate here.
            # MasterSignalBot handles final filtering.
            # --------------------------------------------------

            signal = (
                action in ("BUY", "SELL")
                and score >= self.minimum_score
                and confirmation_count >= 1
            )

            if not signal:

                reason = (
                    "direction_not_strong_enough"
                    if action == "WAIT"
                    else
                    "minimum_confirmation_missing"
                )

            else:

                reason = (
                    "technical_setup_confirmed"
                )

            # --------------------------------------------------
            # RETURN
            # --------------------------------------------------

            return {
                "coin": coin,

                "action": action,

                "score": int(score),

                "buy_score": int(
                    buy_score
                ),

                "sell_score": int(
                    sell_score
                ),

                "triggers": triggers,

                "signal": bool(signal),

                "structure_confirmed": bool(
                    structure_confirmed
                ),

                "momentum_confirmed": bool(
                    momentum_confirmed
                ),

                "volume_confirmed": bool(
                    volume_confirmed
                ),

                "confirmation_count": int(
                    confirmation_count
                ),

                "weak_adx": bool(
                    weak_trend
                ),

                "pressure": pressure,

                "rsi": round(
                    rsi,
                    2
                ),

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

                "ema9": round(
                    ema9,
                    8
                ),

                "ema21": round(
                    ema21,
                    8
                ),

                "ema50": round(
                    ema50,
                    8
                ),

                "bullish_breakout": bool(
                    bullish_breakout
                ),

                "bearish_breakdown": bool(
                    bearish_breakdown
                ),

                "bullish_structure": bool(
                    bullish_structure
                ),

                "bearish_structure": bool(
                    bearish_structure
                ),

                "bullish_candle": bool(
                    bullish_candle
                ),

                "bearish_candle": bool(
                    bearish_candle
                ),

                "body_ratio": round(
                    body_ratio,
                    3
                ),

                "reason": reason
            }

        except Exception as exc:

            logger.exception(
                "Technical engine error for %s: %s",
                coin,
                exc
            )

            return self._empty_result(
                coin,
                "technical_engine_error"
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

        # Normalize columns
        df.columns = [
            str(c).strip().lower()
            for c in df.columns
        ]

        aliases = {
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
            "vol": "volume"
        }

        for old, new in aliases.items():

            if (
                old in df.columns
                and new not in df.columns
            ):

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

        df = df.dropna(
            subset=[
                "open",
                "high",
                "low",
                "close"
            ]
        )

        df = df[
            (df["open"] > 0)
            &
            (df["high"] > 0)
            &
            (df["low"] > 0)
            &
            (df["close"] > 0)
        ]

        if df.empty:
            return None

        # Timestamp normalization
        if "timestamp" in df.columns:

            try:

                # Numeric milliseconds
                if pd.api.types.is_numeric_dtype(
                    df["timestamp"]
                ):

                    df["timestamp"] = pd.to_datetime(
                        df["timestamp"],
                        unit="ms",
                        errors="coerce",
                        utc=True
                    )

                else:

                    df["timestamp"] = pd.to_datetime(
                        df["timestamp"],
                        errors="coerce",
                        utc=True
                    )

                df = df.sort_values(
                    "timestamp"
                )

            except Exception:

                pass

        return df.reset_index(
            drop=True
        )

    # ==========================================================
    # EMPTY RESULT
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

            "confirmation_count": 0,

            "weak_adx": True,

            "pressure": "NEUTRAL",

            "rsi": 50.0,

            "volume_ratio": 0.0,

            "price_move_pct": 0.0,

            "atr": 0.0,

            "ema9": 0.0,

            "ema21": 0.0,

            "ema50": 0.0,

            "bullish_breakout": False,

            "bearish_breakdown": False,

            "bullish_structure": False,

            "bearish_structure": False,

            "bullish_candle": False,

            "bearish_candle": False,

            "body_ratio": 0.0,

            "reason": reason
        }

    # ==========================================================
    # SAFE FLOAT
    # ==========================================================

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
