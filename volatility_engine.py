import time
import logging
import pandas as pd

logger = logging.getLogger("BG_STAR_PRO_VolatilityEngine")


class VolatilityEngine:
    """
    BG STAR PRO - Production Volatility Gate

    Purpose:
        Detect abnormal BTC volatility before the Strong Signal Engine
        is allowed to generate a trading setup.

    Design principles:
        1. Use CLOSED 5m candles only.
        2. Volume spike alone must NOT create MEDIUM/HIGH.
        3. Price expansion is the primary volatility evidence.
        4. ATR expansion confirms volatility regime.
        5. Volume expansion confirms participation.
        6. HIGH volatility activates a temporary trading pause.
        7. Lightweight enough for Render 512 MB.
    """

    # ============================================================
    # CONFIGURATION
    # ============================================================

    TIMEFRAME_MINUTES = 5

    # HIGH pause duration
    PAUSE_DURATION_SEC = 25 * 60

    # Minimum candles required for reliable calculation
    MIN_CANDLES = 35

    # ATR configuration
    ATR_PERIOD = 14
    ATR_BASELINE_PERIOD = 14

    # ------------------------------------------------------------
    # PRICE EXPANSION
    # ------------------------------------------------------------

    # Normal -> Medium evidence
    MEDIUM_PRICE_PCT = 0.70

    # Strong price expansion
    HIGH_PRICE_PCT = 1.20

    # Extreme price expansion
    EXTREME_PRICE_PCT = 1.80

    # ------------------------------------------------------------
    # ATR EXPANSION
    # ------------------------------------------------------------

    MEDIUM_ATR_RATIO = 1.35
    STRONG_ATR_RATIO = 1.70
    HIGH_ATR_RATIO = 2.00
    EXTREME_ATR_RATIO = 2.50

    # ------------------------------------------------------------
    # VOLUME EXPANSION
    # ------------------------------------------------------------

    # Volume alone is NEVER enough.
    MEDIUM_VOLUME_RATIO = 2.50
    STRONG_VOLUME_RATIO = 4.00
    HIGH_VOLUME_RATIO = 5.00

    # ------------------------------------------------------------
    # RANGE EXPANSION
    # ------------------------------------------------------------

    MEDIUM_RANGE_ATR_RATIO = 1.35
    HIGH_RANGE_ATR_RATIO = 1.80

    # ============================================================
    # INIT
    # ============================================================

    def __init__(self):
        self.pause_duration = self.PAUSE_DURATION_SEC
        self.pause_end_time = 0.0

        self.current_level = "NORMAL"

        # Diagnostics
        self.last_metrics = {
            "price_change_pct": 0.0,
            "atr_ratio": 1.0,
            "volume_ratio": 1.0,
            "range_atr_ratio": 1.0,
            "closed_candle": False,
        }

    # ============================================================
    # MAIN UPDATE
    # ============================================================

    def update(self, btc_df: pd.DataFrame) -> bool:
        """
        Update volatility state.

        Returns:
            True  -> a NEW HIGH-volatility event was detected.
            False -> no new HIGH event.
        """

        # --------------------------------------------------------
        # Basic validation
        # --------------------------------------------------------

        if btc_df is None or btc_df.empty:
            logger.warning("[Volatility] BTC 5m data unavailable.")
            return False

        if len(btc_df) < self.MIN_CANDLES:
            logger.warning(
                f"[Volatility] Insufficient BTC 5m candles: "
                f"{len(btc_df)}/{self.MIN_CANDLES}"
            )
            return False

        required_columns = [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]

        missing = [
            col for col in required_columns
            if col not in btc_df.columns
        ]

        if missing:
            logger.error(
                f"[Volatility] Missing columns: {missing}"
            )
            return False

        # --------------------------------------------------------
        # Clean lightweight copy
        # --------------------------------------------------------

        df = btc_df[
            ["open", "high", "low", "close", "volume"]
        ].copy()

        for col in required_columns:
            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df = df.dropna()

        if len(df) < self.MIN_CANDLES:
            logger.warning(
                "[Volatility] Not enough valid candles after cleaning."
            )
            return False

        # --------------------------------------------------------
        # CLOSED CANDLE ONLY
        #
        # CCXT normally returns the latest currently forming candle
        # as the final row.
        #
        # Therefore:
        #   -1 = potentially OPEN candle
        #   -2 = CLOSED candle
        #   -3 = previous CLOSED candle
        # --------------------------------------------------------

        closed_pos = len(df) - 2
        previous_pos = len(df) - 3

        if previous_pos < 1:
            return False

        last = df.iloc[closed_pos]
        prev = df.iloc[previous_pos]

        # --------------------------------------------------------
        # TRUE RANGE
        # --------------------------------------------------------

        prev_close_series = df["close"].shift(1)

        tr1 = df["high"] - df["low"]
        tr2 = (df["high"] - prev_close_series).abs()
        tr3 = (df["low"] - prev_close_series).abs()

        true_range = pd.concat(
            [tr1, tr2, tr3],
            axis=1
        ).max(axis=1)

        # --------------------------------------------------------
        # ATR
        # --------------------------------------------------------

        atr_series = true_range.rolling(
            window=self.ATR_PERIOD,
            min_periods=self.ATR_PERIOD
        ).mean()

        current_atr = atr_series.iloc[closed_pos]

        # Previous ATR baseline excludes current closed candle.
        atr_start = max(
            0,
            closed_pos - self.ATR_BASELINE_PERIOD
        )

        atr_baseline = atr_series.iloc[
            atr_start:closed_pos
        ].dropna()

        if (
            pd.isna(current_atr)
            or atr_baseline.empty
        ):
            logger.warning(
                "[Volatility] ATR baseline unavailable."
            )
            return False

        mean_atr = atr_baseline.mean()

        if mean_atr <= 0:
            atr_ratio = 1.0
        else:
            atr_ratio = float(
                current_atr / mean_atr
            )

        # --------------------------------------------------------
        # PRICE CHANGE
        #
        # CLOSED candle close -> previous CLOSED candle close
        # --------------------------------------------------------

        previous_close = float(prev["close"])
        current_close = float(last["close"])

        if previous_close <= 0:
            price_change_pct = 0.0
        else:
            price_change_pct = (
                abs(current_close - previous_close)
                / previous_close
            ) * 100.0

        # --------------------------------------------------------
        # VOLUME RATIO
        #
        # Compare current CLOSED candle against previous
        # 14 CLOSED candles.
        # --------------------------------------------------------

        volume_start = max(
            0,
            closed_pos - self.ATR_BASELINE_PERIOD
        )

        volume_baseline = df["volume"].iloc[
            volume_start:closed_pos
        ].dropna()

        current_volume = float(last["volume"])

        if (
            volume_baseline.empty
            or volume_baseline.mean() <= 0
        ):
            volume_ratio = 1.0
        else:
            volume_ratio = float(
                current_volume
                / volume_baseline.mean()
            )

        # --------------------------------------------------------
        # CANDLE RANGE EXPANSION
        # --------------------------------------------------------

        current_range = float(
            last["high"] - last["low"]
        )

        if current_atr > 0:
            range_atr_ratio = float(
                current_range / current_atr
            )
        else:
            range_atr_ratio = 1.0

        # --------------------------------------------------------
        # BASIC SANITY LIMITS
        #
        # Prevent corrupted exchange data from creating
        # artificial HIGH volatility.
        # --------------------------------------------------------

        if not pd.notna(price_change_pct):
            price_change_pct = 0.0

        if not pd.notna(atr_ratio):
            atr_ratio = 1.0

        if not pd.notna(volume_ratio):
            volume_ratio = 1.0

        if not pd.notna(range_atr_ratio):
            range_atr_ratio = 1.0

        # --------------------------------------------------------
        # STORE DIAGNOSTICS
        # --------------------------------------------------------

        self.last_metrics = {
            "price_change_pct": price_change_pct,
            "atr_ratio": atr_ratio,
            "volume_ratio": volume_ratio,
            "range_atr_ratio": range_atr_ratio,
            "closed_candle": True,
        }

        # ========================================================
        # VOLATILITY EVIDENCE
        # ========================================================

        price_medium = (
            price_change_pct >= self.MEDIUM_PRICE_PCT
        )

        price_high = (
            price_change_pct >= self.HIGH_PRICE_PCT
        )

        price_extreme = (
            price_change_pct >= self.EXTREME_PRICE_PCT
        )

        atr_medium = (
            atr_ratio >= self.MEDIUM_ATR_RATIO
        )

        atr_strong = (
            atr_ratio >= self.STRONG_ATR_RATIO
        )

        atr_high = (
            atr_ratio >= self.HIGH_ATR_RATIO
        )

        atr_extreme = (
            atr_ratio >= self.EXTREME_ATR_RATIO
        )

        volume_medium = (
            volume_ratio >= self.MEDIUM_VOLUME_RATIO
        )

        volume_strong = (
            volume_ratio >= self.STRONG_VOLUME_RATIO
        )

        volume_high = (
            volume_ratio >= self.HIGH_VOLUME_RATIO
        )

        range_medium = (
            range_atr_ratio >= self.MEDIUM_RANGE_ATR_RATIO
        )

        range_high = (
            range_atr_ratio >= self.HIGH_RANGE_ATR_RATIO
        )

        # ========================================================
        # IMPORTANT:
        #
        # VOLUME ALONE NEVER CREATES MEDIUM/HIGH.
        #
        # Example:
        #
        # Price = 0.03%
        # ATR   = 0.87
        # Volume= 5.55x
        #
        # Result -> NORMAL
        #
        # This prevents the exact false MEDIUM state that
        # appeared in the previous deployment.
        # ========================================================

        # ========================================================
        # HIGH VOLATILITY LOGIC
        # ========================================================

        high_condition_1 = (
            price_high
            and (
                atr_high
                or volume_high
                or range_high
            )
        )

        high_condition_2 = (
            price_extreme
            and (
                atr_strong
                or volume_strong
                or range_medium
            )
        )

        high_condition_3 = (
            atr_extreme
            and (
                volume_strong
                or price_medium
                or range_medium
            )
        )

        high_condition_4 = (
            price_high
            and atr_strong
        )

        is_high = (
            high_condition_1
            or high_condition_2
            or high_condition_3
            or high_condition_4
        )

        # ========================================================
        # MEDIUM VOLATILITY LOGIC
        # ========================================================

        medium_condition_1 = (
            price_medium
            and (
                atr_medium
                or volume_medium
                or range_medium
            )
        )

        medium_condition_2 = (
            atr_strong
            and (
                price_medium
                or volume_medium
                or range_medium
            )
        )

        medium_condition_3 = (
            volume_high
            and (
                price_medium
                or atr_medium
                or range_medium
            )
        )

        medium_condition_4 = (
            range_high
            and (
                price_medium
                or atr_medium
            )
        )

        is_medium = (
            medium_condition_1
            or medium_condition_2
            or medium_condition_3
            or medium_condition_4
        )

        # HIGH always wins.
        if is_high:
            new_state = "HIGH"
        elif is_medium:
            new_state = "MEDIUM"
        else:
            new_state = "NORMAL"

        # ========================================================
        # PAUSE STATE
        # ========================================================

        was_paused = self.is_paused()

        newly_triggered_high = False

        if new_state == "HIGH":

            # HIGH volatility always refreshes the pause.
            self.pause_end_time = (
                time.time()
                + self.pause_duration
            )

            self.current_level = "HIGH"

            # Alert only on NEW HIGH event.
            if not was_paused:
                newly_triggered_high = True

                logger.warning(
                    "🚨 [Volatility] HIGH volatility detected. "
                    "Trading pause activated."
                )

                logger.warning(
                    "[Volatility] HIGH evidence | "
                    f"Price={price_change_pct:.2f}% | "
                    f"ATR={atr_ratio:.2f}x | "
                    f"Volume={volume_ratio:.2f}x | "
                    f"Range={range_atr_ratio:.2f}x"
                )

        else:

            # If an existing HIGH pause is still active,
            # remain HIGH until the pause expires.
            if was_paused:
                self.current_level = "HIGH"
            else:
                self.current_level = new_state

        # ========================================================
        # PAUSE DIAGNOSTICS
        # ========================================================

        remaining_pause_sec = max(
            0,
            int(
                self.pause_end_time
                - time.time()
            )
        )

        pause_remaining_min = (
            f"{remaining_pause_sec // 60}m"
            if remaining_pause_sec > 0
            else "0m"
        )

        # ========================================================
        # DETAILED PRODUCTION LOG
        # ========================================================

        logger.info(
            "[Volatility] "
            f"Level={self.current_level} | "
            f"PriceMove={price_change_pct:.2f}% | "
            f"ATR_Ratio={atr_ratio:.2f} | "
            f"Volume_Ratio={volume_ratio:.2f} | "
            f"Range_ATR={range_atr_ratio:.2f} | "
            f"ClosedCandle=True | "
            f"Paused={self.is_paused()} | "
            f"PauseRemaining={pause_remaining_min}"
        )

        return newly_triggered_high

    # ============================================================
    # PAUSE CHECK
    # ============================================================

    def is_paused(self) -> bool:
        """
        Returns True while HIGH-volatility pause is active.
        """

        return time.time() < self.pause_end_time

    # ============================================================
    # DIAGNOSTIC SNAPSHOT
    # ============================================================

    def get_status(self) -> dict:
        """
        Lightweight status object for dashboard/debugging.
        """

        remaining_sec = max(
            0,
            int(
                self.pause_end_time
                - time.time()
            )
        )

        return {
            "level": self.current_level,
            "paused": self.is_paused(),
            "pause_remaining_sec": remaining_sec,
            "metrics": dict(self.last_metrics),
        }
