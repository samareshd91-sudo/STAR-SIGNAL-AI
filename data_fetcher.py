import logging
import time
from typing import Dict

import ccxt
import pandas as pd


logger = logging.getLogger("BG_STAR_PRO_DataFetcher")


class KuCoinFetcher:
    """
    Lightweight KuCoin OHLCV fetcher.

    Designed for low-memory / low-CPU Render instances.

    Important:
        The final row returned by CCXT is normally the currently forming
        candle. We remove it and return CLOSED candles only.
    """

    TIMEFRAME_TTL = {
        "15m": 45,
        "1h": 600,
        "4h": 1800,
        "5m": 45,
    }

    def __init__(self):
        self.exchange = ccxt.kucoin(
            {
                "enableRateLimit": True,
                "timeout": 10000,
            }
        )

        self.cache = {}

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def fetch_live_data(
        self,
        coins: list,
    ) -> Dict[str, dict]:

        market_data = {}

        for coin in coins:
            try:
                df15 = self._get_ohlcv(
                    symbol=f"{coin}/USDT",
                    timeframe="15m",
                    limit=160,
                )

                df1h = self._get_ohlcv(
                    symbol=f"{coin}/USDT",
                    timeframe="1h",
                    limit=100,
                )

                df4h = self._get_ohlcv(
                    symbol=f"{coin}/USDT",
                    timeframe="4h",
                    limit=80,
                )

                if (
                    df15 is None
                    or df1h is None
                    or df4h is None
                ):
                    continue

                market_data[coin] = {
                    "15m": df15,
                    "1h": df1h,
                    "4h": df4h,
                }

            except Exception as exc:
                logger.error(
                    "Fetch bundle error for %s: %s",
                    coin,
                    exc,
                )

        # BTC 5m is used only by volatility_engine.py
        try:
            btc_5m = self._get_ohlcv(
                symbol="BTC/USDT",
                timeframe="5m",
                limit=100,
            )

            if btc_5m is not None:
                market_data["BTC_5m"] = btc_5m

        except Exception as exc:
            logger.error(
                "BTC 5m fetch error: %s",
                exc,
            )

        return market_data

    # ==========================================================
    # CACHE
    # ==========================================================

    def _get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ):

        cache_key = f"{symbol}:{timeframe}"

        now = time.monotonic()
        ttl = self.TIMEFRAME_TTL.get(
            timeframe,
            60,
        )

        cached = self.cache.get(cache_key)

        if cached:
            age = now - cached["time"]

            if age < ttl:
                return cached["data"].copy()

        df = self._fetch_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )

        if df is None or df.empty:
            return None

        self.cache[cache_key] = {
            "time": now,
            "data": df,
        }

        return df.copy()

    # ==========================================================
    # EXCHANGE
    # ==========================================================

    def _fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ):

        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                timeframe,
                limit=limit,
            )

            if not ohlcv:
                return None

            df = pd.DataFrame(
                ohlcv,
                columns=[
                    "timestamp",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ],
            )

            df["timestamp"] = pd.to_datetime(
                df["timestamp"],
                unit="ms",
                utc=True,
            )

            numeric_columns = [
                "open",
                "high",
                "low",
                "close",
                "volume",
            ]

            for column in numeric_columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

            df = df.dropna(
                subset=numeric_columns
            )

            # --------------------------------------------------
            # CRITICAL:
            # Drop the currently forming candle.
            # --------------------------------------------------
            if len(df) >= 3:
                df = df.iloc[:-1].copy()

            # --------------------------------------------------
            # Keep memory bounded.
            # --------------------------------------------------
            df = df.tail(limit - 1).reset_index(
                drop=True
            )

            if len(df) < 50:
                logger.warning(
                    "Not enough CLOSED candles for %s %s: %s",
                    symbol,
                    timeframe,
                    len(df),
                )
                return None

            logger.debug(
                "Fetched %s closed candles: %s %s",
                len(df),
                symbol,
                timeframe,
            )

            return df

        except ccxt.NetworkError as exc:
            logger.warning(
                "Network error %s %s: %s",
                symbol,
                timeframe,
                exc,
            )
            return None

        except ccxt.ExchangeError as exc:
            logger.warning(
                "Exchange error %s %s: %s",
                symbol,
                timeframe,
                exc,
            )
            return None

        except Exception as exc:
            logger.error(
                "Unexpected OHLCV error %s %s: %s",
                symbol,
                timeframe,
                exc,
            )
            return None
