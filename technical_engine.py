import logging
from typing import Dict, Any

import numpy as np
import pandas as pd


logger = logging.getLogger("BG_STAR_PRO_TechEngine")


class TechnicalEngine:
    """
    Strong Signal Technical Engine

    Philosophy:
        QUALITY > QUANTITY

    Final signal requires:
        - Closed 15m candle
        - 1H + 4H alignment
        - Market structure
        - EMA trend
        - ADX strength
        - directional pressure
        - displacement
        - 2-candle confirmation
        - score >= MIN_SIGNAL_SCORE

    NOTE:
        OHLCV does not contain true bid/ask delta.
        Therefore pressure_confirmation is an OHLCV volume-pressure proxy,
        NOT true exchange CVD.
    """

    MIN_SIGNAL_SCORE = 85
    STRONG_SIGNAL_SCORE = 90

    MIN_ADX = 22.0
    MIN_DISPLACEMENT_ATR = 0.80

    def __init__(self):
        self.target_coins = [
            "BTC",
            "ETH",
            "BNB",
            "SOL",
            "XRP",
            "DOGE",
        ]

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def analyze_market(self, market_data: dict) -> dict:
        results = {}

        for coin in self.target_coins:
            try:
                if coin not in market_data:
                    continue

                bundle = market_data[coin]

                if not isinstance(bundle, dict):
                    # Backward compatibility:
                    # old architecture may pass only 15m dataframe.
                    logger.warning(
                        "%s: HTF data missing; strong signal disabled.",
                        coin,
                    )
                    continue

                df15 = bundle.get("15m")
                df1h = bundle.get("1h")
                df4h = bundle.get("4h")

                if not self._valid_dataframe(df15, 60):
                    continue

                if not self._valid_dataframe(df1h, 60):
                    continue

                if not self._valid_dataframe(df4h, 60):
                    continue

                features = self._calculate_smc_features(
                    df15=df15,
                    df1h=df1h,
                    df4h=df4h,
                )

                score = self._calculate_dynamic_score(features)

                direction = features.get("trend_direction", "NEUTRAL")

                mandatory_ok, mandatory_reasons = (
                    self._mandatory_gate(features, direction)
                )

                approved = (
                    direction in ("BULLISH", "BEARISH")
                    and score >= self.MIN_SIGNAL_SCORE
                    and mandatory_ok
                )

                rejection_reasons = []

                if score < self.MIN_SIGNAL_SCORE:
                    rejection_reasons.append("score_below_85")

                rejection_reasons.extend(mandatory_reasons)

                if not approved and not rejection_reasons:
                    rejection_reasons.append("technical_gate_failed")

                triggers = self._build_trigger_reasons(
                    features,
                    direction,
                )

                results[coin] = {
                    "coin": coin,
                    "features": features,
                    "is_triggered": approved,
                    "technical_score": score,
                    "direction": direction,
                    "trigger_reasons": triggers,
                    "rejection_reasons": list(dict.fromkeys(rejection_reasons)),
                    "confidence_tier": self._confidence_tier(score),
                }

            except Exception as exc:
                logger.exception(
                    "Technical analysis failed for %s: %s",
                    coin,
                    exc,
                )

        return results

    # ==========================================================
    # VALIDATION
    # ==========================================================

    @staticmethod
    def _valid_dataframe(df: pd.DataFrame, minimum_rows: int) -> bool:
        if df is None or df.empty:
            return False

        if len(df) < minimum_rows:
            return False

        required = {
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }

        if not required.issubset(df.columns):
            return False

        return True

    # ==========================================================
    # MAIN FEATURE ENGINE
    # ==========================================================

    def _calculate_smc_features(
        self,
        df15: pd.DataFrame,
        df1h: pd.DataFrame,
        df4h: pd.DataFrame,
    ) -> Dict[str, Any]:

        df = df15.copy()

        # ------------------------------------------------------
        # Make absolutely sure the latest candle is treated as
        # the latest CLOSED candle supplied by data_fetcher.
        # ------------------------------------------------------
        df = df.tail(160).reset_index(drop=True)

        latest = df.iloc[-1]
        previous = df.iloc[-2]

        features = {
            "trend_direction": "NEUTRAL",
            "structure_direction": "NEUTRAL",
            "htf_direction": "NEUTRAL",

            "ema_trend": False,
            "htf_alignment": False,
            "structure_confirmation": False,
            "liquidity_sweep": False,
            "ob_fvg": False,
            "adx_strength": False,
            "volume_confirmation": False,
            "pressure_confirmation": False,
            "displacement": False,
            "candle_confirmation": False,

            "adx_value": 0.0,
            "atr_value": 0.0,
            "displacement_ratio": 0.0,

            "ema_direction": "NEUTRAL",
            "pressure_direction": "NEUTRAL",
            "liquidity_direction": "NEUTRAL",
            "ob_fvg_direction": "NEUTRAL",

            "one_hour_direction": "NEUTRAL",
            "four_hour_direction": "NEUTRAL",

            "close": float(latest["close"]),
            "candle_timestamp": str(latest["timestamp"]),
        }

        # ======================================================
        # 1. ATR
        # ======================================================

        atr = self._atr(df, 14)

        if pd.isna(atr.iloc[-1]) or atr.iloc[-1] <= 0:
            return features

        atr_value = float(atr.iloc[-1])
        features["atr_value"] = round(atr_value, 8)

        # ======================================================
        # 2. EMA TREND
        # ======================================================

        ema20 = df["close"].ewm(
            span=20,
            adjust=False,
        ).mean()

        ema50 = df["close"].ewm(
            span=50,
            adjust=False,
        ).mean()

        if (
            latest["close"] > ema20.iloc[-1]
            and ema20.iloc[-1] > ema50.iloc[-1]
        ):
            features["ema_direction"] = "BULLISH"
            features["ema_trend"] = True

        elif (
            latest["close"] < ema20.iloc[-1]
            and ema20.iloc[-1] < ema50.iloc[-1]
        ):
            features["ema_direction"] = "BEARISH"
            features["ema_trend"] = True

        # ======================================================
        # 3. REAL HTF ALIGNMENT
        # ======================================================

        one_hour_direction = self._htf_direction(df1h)
        four_hour_direction = self._htf_direction(df4h)

        features["one_hour_direction"] = one_hour_direction
        features["four_hour_direction"] = four_hour_direction

        if (
            one_hour_direction == "BULLISH"
            and four_hour_direction == "BULLISH"
        ):
            features["htf_direction"] = "BULLISH"
            features["htf_alignment"] = True

        elif (
            one_hour_direction == "BEARISH"
            and four_hour_direction == "BEARISH"
        ):
            features["htf_direction"] = "BEARISH"
            features["htf_alignment"] = True

        # ======================================================
        # 4. MARKET STRUCTURE / BOS
        # ======================================================

        lookback = 10

        prior_high = df["high"].iloc[-(lookback + 1):-1].max()
        prior_low = df["low"].iloc[-(lookback + 1):-1].min()

        structure_direction = "NEUTRAL"

        if latest["close"] > prior_high:
            structure_direction = "BULLISH"
            features["structure_confirmation"] = True

        elif latest["close"] < prior_low:
            structure_direction = "BEARISH"
            features["structure_confirmation"] = True

        features["structure_direction"] = structure_direction

        # ======================================================
        # 5. LIQUIDITY SWEEP
        # ======================================================

        previous_low = df["low"].iloc[-(lookback + 1):-1].min()
        previous_high = df["high"].iloc[-(lookback + 1):-1].max()

        if (
            latest["low"] < previous_low
            and latest["close"] > previous_low
        ):
            features["liquidity_sweep"] = True
            features["liquidity_direction"] = "BULLISH"

        elif (
            latest["high"] > previous_high
            and latest["close"] < previous_high
        ):
            features["liquidity_sweep"] = True
            features["liquidity_direction"] = "BEARISH"

        # ======================================================
        # 6. FVG / OB PROXY
        # ======================================================

        if len(df) >= 5:
            c1 = df.iloc[-3]
            c3 = df.iloc[-1]

            # Bullish FVG:
            # current low > candle[-3] high
            if (
                c3["low"] > c1["high"]
                and c3["close"] > c1["high"]
            ):
                features["ob_fvg"] = True
                features["ob_fvg_direction"] = "BULLISH"

            # Bearish FVG:
            # current high < candle[-3] low
            elif (
                c3["high"] < c1["low"]
                and c3["close"] < c1["low"]
            ):
                features["ob_fvg"] = True
                features["ob_fvg_direction"] = "BEARISH"

        # ======================================================
        # 7. REAL ADX
        # ======================================================

        adx_series = self._adx(df, 14)
        adx_value = float(adx_series.iloc[-1])

        if not np.isfinite(adx_value):
            adx_value = 0.0

        features["adx_value"] = round(adx_value, 2)

        if adx_value >= self.MIN_ADX:
            features["adx_strength"] = True

        # ======================================================
        # 8. VOLUME CONFIRMATION
        # ======================================================

        volume_baseline = (
            df["volume"]
            .iloc[-21:-1]
            .median()
        )

        if (
            np.isfinite(volume_baseline)
            and volume_baseline > 0
            and latest["volume"] >= volume_baseline * 1.20
        ):
            features["volume_confirmation"] = True

        # ======================================================
        # 9. OHLCV VOLUME-PRESSURE PROXY
        # ======================================================

        pressure = self._pressure_score(df.tail(6))

        if pressure > 0.12:
            features["pressure_direction"] = "BULLISH"
            features["pressure_confirmation"] = True

        elif pressure < -0.12:
            features["pressure_direction"] = "BEARISH"
            features["pressure_confirmation"] = True

        # ======================================================
        # 10. DISPLACEMENT
        # ======================================================

        candle_body = abs(
            float(latest["close"]) - float(latest["open"])
        )

        displacement_ratio = candle_body / atr_value
        features["displacement_ratio"] = round(
            displacement_ratio,
            2,
        )

        if displacement_ratio >= self.MIN_DISPLACEMENT_ATR:
            features["displacement"] = True

        # ======================================================
        # 11. TWO-CANDLE CONFIRMATION
        # ======================================================

        candle_confirmation = self._two_candle_confirmation(
            df,
            ema20,
        )

        features["candle_confirmation"] = candle_confirmation

        # ======================================================
        # 12. FINAL DIRECTION
        # ======================================================

        direction = self._resolve_direction(features)

        features["trend_direction"] = direction

        return features

    # ==========================================================
    # HTF
    # ==========================================================

    @staticmethod
    def _htf_direction(df: pd.DataFrame) -> str:
        if df is None or len(df) < 60:
            return "NEUTRAL"

        close = df["close"]

        ema50 = close.ewm(
            span=50,
            adjust=False,
        ).mean()

        ema200 = close.ewm(
            span=200,
            adjust=False,
        ).mean()

        last_close = float(close.iloc[-1])
        e50 = float(ema50.iloc[-1])
        e200 = float(ema200.iloc[-1])

        if last_close > e50 and e50 > e200:
            return "BULLISH"

        if last_close < e50 and e50 < e200:
            return "BEARISH"

        return "NEUTRAL"

    # ==========================================================
    # ATR
    # ==========================================================

    @staticmethod
    def _atr(
        df: pd.DataFrame,
        period: int = 14,
    ) -> pd.Series:

        previous_close = df["close"].shift(1)

        tr = pd.concat(
            [
                df["high"] - df["low"],
                (df["high"] - previous_close).abs(),
                (df["low"] - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        return tr.ewm(
            alpha=1 / period,
            adjust=False,
        ).mean()

    # ==========================================================
    # ADX
    # ==========================================================

    @classmethod
    def _adx(
        cls,
        df: pd.DataFrame,
        period: int = 14,
    ) -> pd.Series:

        high = df["high"]
        low = df["low"]
        close = df["close"]

        up_move = high.diff()
        down_move = -low.diff()

        plus_dm = pd.Series(
            np.where(
                (up_move > down_move) & (up_move > 0),
                up_move,
                0.0,
            ),
            index=df.index,
        )

        minus_dm = pd.Series(
            np.where(
                (down_move > up_move) & (down_move > 0),
                down_move,
                0.0,
            ),
            index=df.index,
        )

        prev_close = close.shift(1)

        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr = tr.ewm(
            alpha=1 / period,
            adjust=False,
        ).mean()

        plus_smoothed = plus_dm.ewm(
            alpha=1 / period,
            adjust=False,
        ).mean()

        minus_smoothed = minus_dm.ewm(
            alpha=1 / period,
            adjust=False,
        ).mean()

        plus_di = 100 * (
            plus_smoothed / atr.replace(0, np.nan)
        )

        minus_di = 100 * (
            minus_smoothed / atr.replace(0, np.nan)
        )

        denominator = (
            plus_di + minus_di
        ).replace(0, np.nan)

        dx = (
            100
            * (plus_di - minus_di).abs()
            / denominator
        )

        return dx.ewm(
            alpha=1 / period,
            adjust=False,
        ).mean().fillna(0.0)

    # ==========================================================
    # PRESSURE PROXY
    # ==========================================================

    @staticmethod
    def _pressure_score(df: pd.DataFrame) -> float:
        if df.empty:
            return 0.0

        high_low = (
            df["high"] - df["low"]
        ).replace(0, np.nan)

        candle_location = (
            (
                (df["close"] - df["low"])
                - (df["high"] - df["close"])
            )
            / high_low
        ).fillna(0.0)

        volume = df["volume"]

        weighted = candle_location * volume

        denominator = volume.sum()

        if denominator <= 0:
            return 0.0

        return float(weighted.sum() / denominator)

    # ==========================================================
    # 2-CANDLE CONFIRMATION
    # ==========================================================

    @staticmethod
    def _two_candle_confirmation(
        df: pd.DataFrame,
        ema20: pd.Series,
    ) -> bool:

        if len(df) < 3:
            return False

        c1 = df.iloc[-2]
        c2 = df.iloc[-1]

        ema1 = ema20.iloc[-2]
        ema2 = ema20.iloc[-1]

        bullish = (
            c1["close"] > c1["open"]
            and c2["close"] > c2["open"]
            and c1["close"] > ema1
            and c2["close"] > ema2
            and c2["close"] >= c1["close"]
        )

        bearish = (
            c1["close"] < c1["open"]
            and c2["close"] < c2["open"]
            and c1["close"] < ema1
            and c2["close"] < ema2
            and c2["close"] <= c1["close"]
        )

        return bool(bullish or bearish)

    # ==========================================================
    # DIRECTION
    # ==========================================================

    @staticmethod
    def _resolve_direction(features: Dict[str, Any]) -> str:

        bullish = 0
        bearish = 0

        def add(direction, points):
            nonlocal bullish, bearish

            if direction == "BULLISH":
                bullish += points

            elif direction == "BEARISH":
                bearish += points

        add(features["htf_direction"], 5)
        add(features["ema_direction"], 3)
        add(features["structure_direction"], 5)
        add(features["pressure_direction"], 3)
        add(features["liquidity_direction"], 2)
        add(features["ob_fvg_direction"], 2)

        if bullish >= bearish + 3:
            return "BULLISH"

        if bearish >= bullish + 3:
            return "BEARISH"

        return "NEUTRAL"

    # ==========================================================
    # SCORE
    # ==========================================================

    @staticmethod
    def _calculate_dynamic_score(
        features: Dict[str, Any],
    ) -> int:

        score = 0
        direction = features["trend_direction"]

        if direction == "NEUTRAL":
            return 0

        if (
            features["htf_alignment"]
            and features["htf_direction"] == direction
        ):
            score += 20

        if (
            features["structure_confirmation"]
            and features["structure_direction"] == direction
        ):
            score += 18

        if (
            features["ema_trend"]
            and features["ema_direction"] == direction
        ):
            score += 10

        if features["adx_strength"]:
            score += 10

        if (
            features["pressure_confirmation"]
            and features["pressure_direction"] == direction
        ):
            score += 10

        if features["displacement"]:
            score += 10

        if (
            features["candle_confirmation"]
        ):
            score += 8

        if (
            features["ob_fvg"]
            and features["ob_fvg_direction"] == direction
        ):
            score += 6

        if (
            features["liquidity_sweep"]
            and features["liquidity_direction"] == direction
        ):
            score += 4

        if features["volume_confirmation"]:
            score += 4

        return min(100, int(score))

    # ==========================================================
    # HARD FILTER
    # ==========================================================

    @staticmethod
    def _mandatory_gate(
        features: Dict[str, Any],
        direction: str,
    ):
        reasons = []

        if direction == "NEUTRAL":
            reasons.append("direction_neutral")
            return False, reasons

        if not features["htf_alignment"]:
            reasons.append("htf_not_aligned")

        elif features["htf_direction"] != direction:
            reasons.append("htf_direction_conflict")

        if not features["structure_confirmation"]:
            reasons.append("structure_not_confirmed")

        elif features["structure_direction"] != direction:
            reasons.append("structure_direction_conflict")

        if not features["ema_trend"]:
            reasons.append("ema_trend_not_confirmed")

        elif features["ema_direction"] != direction:
            reasons.append("ema_direction_conflict")

        if not features["adx_strength"]:
            reasons.append("weak_adx")

        if not features["pressure_confirmation"]:
            reasons.append("pressure_not_confirmed")

        elif features["pressure_direction"] != direction:
            reasons.append("pressure_direction_conflict")

        if not features["displacement"]:
            reasons.append("weak_displacement")

        if not features["candle_confirmation"]:
            reasons.append("two_candle_confirmation_failed")

        return len(reasons) == 0, reasons

    # ==========================================================
    # TRIGGER REASONS
    # ==========================================================

    @staticmethod
    def _build_trigger_reasons(
        features: Dict[str, Any],
        direction: str,
    ):

        reasons = []

        mapping = [
            (
                "htf_alignment",
                features["htf_alignment"],
            ),
            (
                "structure_confirmation",
                features["structure_confirmation"],
            ),
            (
                "ema_trend",
                features["ema_trend"],
            ),
            (
                "adx_strength",
                features["adx_strength"],
            ),
            (
                "pressure_confirmation",
                features["pressure_confirmation"],
            ),
            (
                "displacement",
                features["displacement"],
            ),
            (
                "candle_confirmation",
                features["candle_confirmation"],
            ),
            (
                "ob_fvg",
                features["ob_fvg"],
            ),
            (
                "liquidity_sweep",
                features["liquidity_sweep"],
            ),
            (
                "volume_confirmation",
                features["volume_confirmation"],
            ),
        ]

        for name, enabled in mapping:
            if enabled:
                reasons.append(name)

        return reasons

    # ==========================================================
    # TIER
    # ==========================================================

    @staticmethod
    def _confidence_tier(score: int) -> str:
        if score >= 95:
            return "ELITE"

        if score >= 90:
            return "STRONG"

        if score >= 85:
            return "VALID"

        if score >= 75:
            return "WATCH"

        return "REJECT"
