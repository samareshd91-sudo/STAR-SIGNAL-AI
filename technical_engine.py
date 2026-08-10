import logging
from typing import Dict, Any

import numpy as np
import pandas as pd


logger = logging.getLogger("BG_STAR_PRO_TechEngine")


class TechnicalEngine:
    """
    Production-style technical signal engine.

    Design goals:
    - Avoid noisy signals.
    - Avoid rejecting good setups because of one missing secondary confirmation.
    - Use closed-candle data only.
    - Keep HTF/structure as core confirmation.
    - Use momentum/volume/displacement as supporting confirmation.
    - Return detailed rejection reasons for diagnostics.
    """

    TARGET_COINS = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]

    MIN_SIGNAL_SCORE = 82
    STRONG_SIGNAL_SCORE = 90

    def __init__(self):
        self.target_coins = self.TARGET_COINS.copy()

    # ==========================================================
    # PUBLIC MARKET ANALYSIS
    # ==========================================================

    def analyze_market(self, market_data: dict) -> dict:
        scan_results = {}

        for coin in self.target_coins:

            if coin not in market_data:
                continue

            df = market_data[coin]

            if df is None or df.empty:
                continue

            if len(df) < 80:
                logger.warning(
                    "%s: insufficient candles (%s)",
                    coin,
                    len(df),
                )
                continue

            try:
                # --------------------------------------------------
                # Work only with closed candles.
                # If exchange returns the currently forming candle,
                # ignore it.
                # --------------------------------------------------
                df = self._prepare_dataframe(df)

                if len(df) < 70:
                    continue

                features = self._calculate_features(df)

                direction = features["trend_direction"]

                score = self._calculate_dynamic_score(features)

                mandatory_ok, rejection_reasons = (
                    self._qualification_gate(
                        features,
                        direction,
                        score,
                    )
                )

                is_triggered = (
                    mandatory_ok
                    and score >= self.MIN_SIGNAL_SCORE
                )

                if score < self.MIN_SIGNAL_SCORE:
                    rejection_reasons.append(
                        f"score_below_{self.MIN_SIGNAL_SCORE}"
                    )

                # Remove duplicate reasons.
                rejection_reasons = list(
                    dict.fromkeys(rejection_reasons)
                )

                trigger_reasons = self._build_trigger_reasons(
                    features,
                    direction,
                )

                scan_results[coin] = {
                    "coin": coin,
                    "features": features,
                    "is_triggered": is_triggered,
                    "technical_score": score,
                    "direction": direction,
                    "trigger_reasons": trigger_reasons,
                    "rejection_reasons": (
                        []
                        if is_triggered
                        else rejection_reasons
                    ),
                    "signal_tier": self._get_signal_tier(
                        score,
                        features,
                        is_triggered,
                    ),
                }

                if is_triggered:
                    logger.info(
                        "✅ QUALIFIED %s | %s | score=%s | "
                        "tier=%s | triggers=%s",
                        coin,
                        direction,
                        score,
                        scan_results[coin]["signal_tier"],
                        ", ".join(trigger_reasons),
                    )
                else:
                    logger.info(
                        "REJECT %s: score=%s | reasons=%s",
                        coin,
                        score,
                        ", ".join(rejection_reasons),
                    )

            except Exception as exc:
                logger.exception(
                    "Technical analysis failed for %s: %s",
                    coin,
                    exc,
                )

        return scan_results

    # ==========================================================
    # DATA PREPARATION
    # ==========================================================

    @staticmethod
    def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:

        data = df.copy()

        required = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        for column in required:
            if column not in data.columns:
                raise ValueError(
                    f"Missing required column: {column}"
                )

            data[column] = pd.to_numeric(
                data[column],
                errors="coerce",
            )

        data = data.dropna(
            subset=required
        ).copy()

        data = data.drop_duplicates(
            subset=["timestamp"]
            if "timestamp" in data.columns
            else None
        )

        data = data.reset_index(drop=True)

        return data

    # ==========================================================
    # FEATURE ENGINE
    # ==========================================================

    def _calculate_features(
        self,
        df: pd.DataFrame,
    ) -> Dict[str, Any]:

        features = {
            "trend_direction": "NEUTRAL",

            "ema_trend": False,
            "ema_direction": "NEUTRAL",

            "htf_alignment": False,
            "htf_direction": "NEUTRAL",

            "structure_confirmation": False,
            "structure_direction": "NEUTRAL",

            "bos_choch": False,
            "bos_direction": "NEUTRAL",

            "liquidity_sweep": False,
            "liquidity_direction": "NEUTRAL",

            "ob_fvg": False,
            "ob_fvg_direction": "NEUTRAL",

            "adx_strength": False,
            "adx_direction": "NEUTRAL",

            "pressure_confirmation": False,
            "pressure_direction": "NEUTRAL",

            "displacement": False,
            "displacement_direction": "NEUTRAL",

            "candle_confirmation": False,
            "candle_direction": "NEUTRAL",

            "volume_spike": False,
            "volume_direction": "NEUTRAL",

            "bullish_points": 0,
            "bearish_points": 0,

            "atr": 0.0,
            "adx": 0.0,
            "volume_ratio": 1.0,
            "body_ratio": 0.0,
        }

        # ------------------------------------------------------
        # Indicators
        # ------------------------------------------------------

        close = df["close"]
        high = df["high"]
        low = df["low"]
        open_price = df["open"]
        volume = df["volume"]

        ema20 = close.ewm(
            span=20,
            adjust=False,
        ).mean()

        ema50 = close.ewm(
            span=50,
            adjust=False,
        ).mean()

        ema100 = close.ewm(
            span=100,
            adjust=False,
        ).mean()

        # ------------------------------------------------------
        # ATR
        # ------------------------------------------------------

        prev_close = close.shift(1)

        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr14 = tr.rolling(14).mean()

        # ------------------------------------------------------
        # ADX
        # ------------------------------------------------------

        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm = plus_dm.where(
            (plus_dm > minus_dm)
            & (plus_dm > 0),
            0.0,
        )

        minus_dm = minus_dm.where(
            (minus_dm > plus_dm)
            & (minus_dm > 0),
            0.0,
        )

        atr_safe = atr14.replace(0, np.nan)

        plus_di = (
            100
            * plus_dm.rolling(14).mean()
            / atr_safe
        )

        minus_di = (
            100
            * minus_dm.rolling(14).mean()
            / atr_safe
        )

        dx = (
            100
            * (plus_di - minus_di).abs()
            / (plus_di + minus_di).replace(
                0,
                np.nan,
            )
        )

        adx = dx.rolling(14).mean()

        # ------------------------------------------------------
        # Latest closed candle
        # ------------------------------------------------------

        latest = df.iloc[-1]
        previous = df.iloc[-2]

        latest_close = float(latest["close"])
        latest_open = float(latest["open"])
        latest_high = float(latest["high"])
        latest_low = float(latest["low"])

        current_atr = float(
            atr14.iloc[-1]
            if pd.notna(atr14.iloc[-1])
            else 0
        )

        current_adx = float(
            adx.iloc[-1]
            if pd.notna(adx.iloc[-1])
            else 0
        )

        features["atr"] = round(
            current_atr,
            8,
        )

        features["adx"] = round(
            current_adx,
            2,
        )

        # ======================================================
        # 1. EMA TREND
        # ======================================================

        ema20_now = float(ema20.iloc[-1])
        ema50_now = float(ema50.iloc[-1])

        if (
            latest_close > ema20_now
            and ema20_now > ema50_now
        ):
            features["ema_trend"] = True
            features["ema_direction"] = "BULLISH"

        elif (
            latest_close < ema20_now
            and ema20_now < ema50_now
        ):
            features["ema_trend"] = True
            features["ema_direction"] = "BEARISH"

        # ======================================================
        # 2. HTF PROXY
        # ======================================================

        ema100_now = float(ema100.iloc[-1])

        if (
            latest_close > ema50_now
            and ema50_now > ema100_now
        ):
            features["htf_alignment"] = True
            features["htf_direction"] = "BULLISH"

        elif (
            latest_close < ema50_now
            and ema50_now < ema100_now
        ):
            features["htf_alignment"] = True
            features["htf_direction"] = "BEARISH"

        # ======================================================
        # 3. MARKET STRUCTURE / BOS
        # ======================================================

        swing_high = (
            high.iloc[-11:-1].max()
        )

        swing_low = (
            low.iloc[-11:-1].min()
        )

        if latest_close > swing_high:

            features["bos_choch"] = True
            features["bos_direction"] = "BULLISH"

            features["structure_confirmation"] = True
            features["structure_direction"] = "BULLISH"

        elif latest_close < swing_low:

            features["bos_choch"] = True
            features["bos_direction"] = "BEARISH"

            features["structure_confirmation"] = True
            features["structure_direction"] = "BEARISH"

        else:

            # Structure can also be confirmed by consecutive
            # higher-high/higher-low or lower-high/lower-low
            # behavior. This prevents good trends from being
            # rejected simply because the latest candle did not
            # print a fresh BOS.

            recent = df.iloc[-6:]

            higher_highs = (
                recent["high"].iloc[-1]
                > recent["high"].iloc[-3]
            )

            higher_lows = (
                recent["low"].iloc[-1]
                > recent["low"].iloc[-3]
            )

            lower_highs = (
                recent["high"].iloc[-1]
                < recent["high"].iloc[-3]
            )

            lower_lows = (
                recent["low"].iloc[-1]
                < recent["low"].iloc[-3]
            )

            if higher_highs and higher_lows:
                features[
                    "structure_confirmation"
                ] = True
                features[
                    "structure_direction"
                ] = "BULLISH"

            elif lower_highs and lower_lows:
                features[
                    "structure_confirmation"
                ] = True
                features[
                    "structure_direction"
                ] = "BEARISH"

        # ======================================================
        # 4. LIQUIDITY SWEEP
        # ======================================================

        previous_range_high = (
            high.iloc[-12:-2].max()
        )

        previous_range_low = (
            low.iloc[-12:-2].min()
        )

        bullish_sweep = (
            latest_low < previous_range_low
            and latest_close > previous_range_low
        )

        bearish_sweep = (
            latest_high > previous_range_high
            and latest_close < previous_range_high
        )

        if bullish_sweep:
            features["liquidity_sweep"] = True
            features["liquidity_direction"] = "BULLISH"

        elif bearish_sweep:
            features["liquidity_sweep"] = True
            features["liquidity_direction"] = "BEARISH"

        # ======================================================
        # 5. OB / FVG STYLE LOCATION
        # ======================================================

        range_high = float(
            high.iloc[-20:-1].max()
        )

        range_low = float(
            low.iloc[-20:-1].min()
        )

        range_size = range_high - range_low

        if range_size > 0:

            discount = (
                range_low
                + range_size * 0.35
            )

            premium = (
                range_high
                - range_size * 0.35
            )

            if (
                latest_low <= discount
                and latest_close > discount
            ):
                features["ob_fvg"] = True
                features[
                    "ob_fvg_direction"
                ] = "BULLISH"

            elif (
                latest_high >= premium
                and latest_close < premium
            ):
                features["ob_fvg"] = True
                features[
                    "ob_fvg_direction"
                ] = "BEARISH"

        # ======================================================
        # 6. ADX / MOMENTUM
        # ======================================================

        previous_adx = float(
            adx.iloc[-2]
            if pd.notna(adx.iloc[-2])
            else 0
        )

        adx_rising = (
            current_adx >= 18
            and current_adx >= previous_adx
        )

        if adx_rising:

            if (
                plus_di.iloc[-1]
                > minus_di.iloc[-1]
            ):
                features["adx_strength"] = True
                features[
                    "adx_direction"
                ] = "BULLISH"

            elif (
                minus_di.iloc[-1]
                > plus_di.iloc[-1]
            ):
                features["adx_strength"] = True
                features[
                    "adx_direction"
                ] = "BEARISH"

        # ======================================================
        # 7. PRESSURE
        # ======================================================

        candle_range = max(
            latest_high - latest_low,
            1e-12,
        )

        buying_pressure = (
            latest_close - latest_low
        ) / candle_range

        selling_pressure = (
            latest_high - latest_close
        ) / candle_range

        if (
            latest_close > latest_open
            and buying_pressure >= 0.60
        ):
            features[
                "pressure_confirmation"
            ] = True

            features[
                "pressure_direction"
            ] = "BULLISH"

        elif (
            latest_close < latest_open
            and selling_pressure >= 0.60
        ):
            features[
                "pressure_confirmation"
            ] = True

            features[
                "pressure_direction"
            ] = "BEARISH"

        # ======================================================
        # 8. DISPLACEMENT
        # ======================================================

        body = abs(
            latest_close - latest_open
        )

        body_ratio = body / candle_range

        features["body_ratio"] = round(
            body_ratio,
            3,
        )

        average_atr = (
            atr14.iloc[-6:-1].mean()
        )

        if (
            pd.notna(average_atr)
            and average_atr > 0
            and body >= average_atr * 0.65
            and body_ratio >= 0.55
        ):

            if latest_close > latest_open:
                features[
                    "displacement"
                ] = True

                features[
                    "displacement_direction"
                ] = "BULLISH"

            else:
                features[
                    "displacement"
                ] = True

                features[
                    "displacement_direction"
                ] = "BEARISH"

        # ======================================================
        # 9. TWO CANDLE CONFIRMATION
        # ======================================================

        previous_body = abs(
            float(previous["close"])
            - float(previous["open"])
        )

        previous_bullish = (
            previous["close"]
            > previous["open"]
        )

        previous_bearish = (
            previous["close"]
            < previous["open"]
        )

        current_bullish = (
            latest_close > latest_open
        )

        current_bearish = (
            latest_close < latest_open
        )

        if (
            previous_bullish
            and current_bullish
            and body >= previous_body * 0.75
        ):

            features[
                "candle_confirmation"
            ] = True

            features[
                "candle_direction"
            ] = "BULLISH"

        elif (
            previous_bearish
            and current_bearish
            and body >= previous_body * 0.75
        ):

            features[
                "candle_confirmation"
            ] = True

            features[
                "candle_direction"
            ] = "BEARISH"

        # ======================================================
        # 10. VOLUME
        # ======================================================

        volume_average = (
            volume.iloc[-21:-1].mean()
        )

        if (
            pd.notna(volume_average)
            and volume_average > 0
        ):

            volume_ratio = (
                float(latest["volume"])
                / float(volume_average)
            )

            features["volume_ratio"] = round(
                volume_ratio,
                2,
            )

            if volume_ratio >= 1.35:

                features[
                    "volume_spike"
                ] = True

                if current_bullish:
                    features[
                        "volume_direction"
                    ] = "BULLISH"

                elif current_bearish:
                    features[
                        "volume_direction"
                    ] = "BEARISH"

        # ======================================================
        # FINAL DIRECTION
        # ======================================================

        bullish_votes = 0
        bearish_votes = 0

        directional_features = [
            (
                features["ema_direction"],
                2,
            ),
            (
                features["htf_direction"],
                3,
            ),
            (
                features["structure_direction"],
                3,
            ),
            (
                features["bos_direction"],
                2,
            ),
            (
                features["liquidity_direction"],
                1,
            ),
            (
                features["ob_fvg_direction"],
                1,
            ),
            (
                features["adx_direction"],
                1,
            ),
            (
                features["pressure_direction"],
                2,
            ),
            (
                features["displacement_direction"],
                2,
            ),
            (
                features["candle_direction"],
                1,
            ),
            (
                features["volume_direction"],
                1,
            ),
        ]

        for direction_value, weight in directional_features:

            if direction_value == "BULLISH":
                bullish_votes += weight

            elif direction_value == "BEARISH":
                bearish_votes += weight

        features["bullish_points"] = bullish_votes
        features["bearish_points"] = bearish_votes

        if bullish_votes >= bearish_votes + 2:
            features[
                "trend_direction"
            ] = "BULLISH"

        elif bearish_votes >= bullish_votes + 2:
            features[
                "trend_direction"
            ] = "BEARISH"

        else:
            features[
                "trend_direction"
            ] = "NEUTRAL"

        return features

    # ==========================================================
    # SCORING
    # ==========================================================

    def _calculate_dynamic_score(
        self,
        features: Dict[str, Any],
    ) -> int:

        direction = features[
            "trend_direction"
        ]

        if direction not in (
            "BULLISH",
            "BEARISH",
        ):
            return 0

        score = 0

        # ------------------------------------------------------
        # CORE
        # ------------------------------------------------------

        if (
            features["htf_alignment"]
            and features["htf_direction"]
            == direction
        ):
            score += 20

        if (
            features[
                "structure_confirmation"
            ]
            and features[
                "structure_direction"
            ]
            == direction
        ):
            score += 20

        if (
            features["ema_trend"]
            and features["ema_direction"]
            == direction
        ):
            score += 10

        # ------------------------------------------------------
        # MOMENTUM
        # ------------------------------------------------------

        if (
            features["adx_strength"]
            and features["adx_direction"]
            == direction
        ):
            score += 10

        if (
            features[
                "pressure_confirmation"
            ]
            and features[
                "pressure_direction"
            ]
            == direction
        ):
            score += 10

        if (
            features["displacement"]
            and features[
                "displacement_direction"
            ]
            == direction
        ):
            score += 10

        if (
            features[
                "candle_confirmation"
            ]
            and features[
                "candle_direction"
            ]
            == direction
        ):
            score += 6

        # ------------------------------------------------------
        # LOCATION / LIQUIDITY
        # ------------------------------------------------------

        if (
            features["ob_fvg"]
            and features[
                "ob_fvg_direction"
            ]
            == direction
        ):
            score += 5

        if (
            features["liquidity_sweep"]
            and features[
                "liquidity_direction"
            ]
            == direction
        ):
            score += 5

        # ------------------------------------------------------
        # VOLUME
        # ------------------------------------------------------

        if (
            features["volume_spike"]
            and features[
                "volume_direction"
            ] == direction
        ):
            score += 4

        # ------------------------------------------------------
        # Confluence bonus
        # ------------------------------------------------------

        confirmations = 0

        for key, direction_key in [
            (
                "adx_strength",
                "adx_direction",
            ),
            (
                "pressure_confirmation",
                "pressure_direction",
            ),
            (
                "displacement",
                "displacement_direction",
            ),
            (
                "candle_confirmation",
                "candle_direction",
            ),
        ]:

            if (
                features[key]
                and features[direction_key]
                == direction
            ):
                confirmations += 1

        if confirmations >= 3:
            score += 5

        elif confirmations >= 2:
            score += 2

        return min(
            100,
            int(score),
        )

    # ==========================================================
    # QUALIFICATION GATE
    # ==========================================================

    def _qualification_gate(
        self,
        features: Dict[str, Any],
        direction: str,
        score: int,
    ):

        reasons = []

        if direction not in (
            "BULLISH",
            "BEARISH",
        ):
            return False, [
                "direction_neutral"
            ]

        # ------------------------------------------------------
        # CORE GATES
        # ------------------------------------------------------

        htf_ok = (
            features["htf_alignment"]
            and features["htf_direction"]
            == direction
        )

        structure_ok = (
            features[
                "structure_confirmation"
            ]
            and features[
                "structure_direction"
            ] == direction
        )

        ema_ok = (
            features["ema_trend"]
            and features[
                "ema_direction"
            ] == direction
        )

        if not htf_ok:
            reasons.append(
                "htf_not_aligned"
            )

        if not structure_ok:
            reasons.append(
                "structure_not_confirmed"
            )

        if not ema_ok:
            reasons.append(
                "ema_trend_not_confirmed"
            )

        # Core structure remains mandatory.
        if not (
            htf_ok
            and structure_ok
            and ema_ok
        ):
            return False, reasons

        # ------------------------------------------------------
        # SUPPORTING CONFIRMATIONS
        # ------------------------------------------------------

        support = []

        if (
            features["adx_strength"]
            and features[
                "adx_direction"
            ] == direction
        ):
            support.append("ADX")

        if (
            features[
                "pressure_confirmation"
            ]
            and features[
                "pressure_direction"
            ] == direction
        ):
            support.append("PRESSURE")

        if (
            features["displacement"]
            and features[
                "displacement_direction"
            ] == direction
        ):
            support.append(
                "DISPLACEMENT"
            )

        if (
            features[
                "candle_confirmation"
            ]
            and features[
                "candle_direction"
            ] == direction
        ):
            support.append(
                "TWO_CANDLE"
            )

        # Need at least 2 supporting confirmations.
        if len(support) < 2:

            reasons.append(
                "insufficient_momentum_confirmation"
            )

            if not features["adx_strength"]:
                reasons.append(
                    "weak_adx"
                )

            if not features[
                "pressure_confirmation"
            ]:
                reasons.append(
                    "pressure_not_confirmed"
                )

            if not features[
                "displacement"
            ]:
                reasons.append(
                    "weak_displacement"
                )

            if not features[
                "candle_confirmation"
            ]:
                reasons.append(
                    "two_candle_confirmation_failed"
                )

            return False, reasons

        return True, []

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
                "HTF Alignment",
                "htf_direction",
            ),
            (
                "structure_confirmation",
                "Market Structure",
                "structure_direction",
            ),
            (
                "bos_choch",
                "BOS/CHOCH",
                "bos_direction",
            ),
            (
                "ema_trend",
                "EMA Trend",
                "ema_direction",
            ),
            (
                "adx_strength",
                "ADX Momentum",
                "adx_direction",
            ),
            (
                "pressure_confirmation",
                "Price Pressure",
                "pressure_direction",
            ),
            (
                "displacement",
                "Displacement",
                "displacement_direction",
            ),
            (
                "candle_confirmation",
                "2-Candle Confirmation",
                "candle_direction",
            ),
            (
                "liquidity_sweep",
                "Liquidity Sweep",
                "liquidity_direction",
            ),
            (
                "ob_fvg",
                "OB/FVG",
                "ob_fvg_direction",
            ),
            (
                "volume_spike",
                "Volume Confirmation",
                "volume_direction",
            ),
        ]

        for feature_key, label, direction_key in mapping:

            if (
                features.get(feature_key)
                and features.get(
                    direction_key
                ) == direction
            ):
                reasons.append(label)

        return reasons

    # ==========================================================
    # SIGNAL TIER
    # ==========================================================

    @staticmethod
    def _get_signal_tier(
        score: int,
        features: Dict[str, Any],
        is_triggered: bool,
    ):

        if not is_triggered:
            return "REJECTED"

        if score >= 90:
            return "A+ STRONG"

        if score >= 86:
            return "A STRONG"

        return "QUALIFIED"

    # ==========================================================
    # HELPER FOR EXTERNAL USE
    # ==========================================================

    @classmethod
    def is_strong_signal(
        cls,
        score: int,
    ) -> bool:

        return score >= cls.STRONG_SIGNAL_SCORE
