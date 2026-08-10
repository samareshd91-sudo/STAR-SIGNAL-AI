import logging
import re
import time
from typing import Dict

import feedparser
import requests


logger = logging.getLogger("BG_STAR_PRO_NewsEngine")


class NewsEngine:

    CACHE_TTL_SECONDS = 600
    REQUEST_TIMEOUT = 5

    def __init__(
        self,
        news_api_key=None,
        cryptocompare_api_key=None,
    ):
        self.rss_feeds = [
            "https://cointelegraph.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://cryptoslate.com/feed/",
        ]

        self.coin_map = {
            "BTC": ["BTC", "Bitcoin"],
            "ETH": ["ETH", "Ethereum"],
            "BNB": ["BNB", "Binance"],
            "SOL": ["SOL", "Solana"],
            "XRP": ["XRP", "Ripple"],
            "DOGE": ["DOGE", "Dogecoin"],
        }

        self.bullish_words = [
            "surge",
            "jump",
            "adopt",
            "partner",
            "launch",
            "upgrade",
            "buy",
            "bull",
            "positive",
            "growth",
            "gain",
            "soar",
            "record",
            "approve",
            "breakout",
            "inflow",
        ]

        self.bearish_words = [
            "crash",
            "drop",
            "fall",
            "hack",
            "scam",
            "ban",
            "illegal",
            "sell",
            "bear",
            "negative",
            "lawsuit",
            "plunge",
            "delay",
            "reject",
            "investigation",
            "dump",
            "outflow",
        ]

        self.cache: Dict[str, dict] = {}

    # ==========================================================
    # PUBLIC
    # ==========================================================

    def fetch_news_sentiment(
        self,
        coin: str,
    ) -> dict:

        now = time.monotonic()

        cached = self.cache.get(coin)

        if cached:
            if now - cached["time"] < self.CACHE_TTL_SECONDS:
                return dict(cached["data"])

        try:
            result = self._fetch_fresh(coin)

            self.cache[coin] = {
                "time": now,
                "data": result,
            }

            return dict(result)

        except Exception as exc:
            logger.error(
                "News error %s: %s",
                coin,
                exc,
            )

            # Fail closed for news:
            # technical engine may still decide based on
            # strong technical conditions, but news will not
            # pretend to be bullish/bearish.
            return {
                "sentiment": "NEUTRAL",
                "context": "",
            }

    # ==========================================================
    # FRESH RSS
    # ==========================================================

    def _fetch_fresh(
        self,
        coin: str,
    ) -> dict:

        search_terms = self.coin_map.get(
            coin,
            [coin],
        )

        relevant_news = []

        bullish_score = 0
        bearish_score = 0

        for feed_url in self.rss_feeds:

            try:
                response = requests.get(
                    feed_url,
                    timeout=self.REQUEST_TIMEOUT,
                    headers={
                        "User-Agent": (
                            "BG-STAR-PRO/StrongSignalBot "
                            "RSSReader/1.0"
                        )
                    },
                )

                response.raise_for_status()

                feed = feedparser.parse(
                    response.content
                )

                for entry in feed.entries[:12]:

                    title = str(
                        entry.get(
                            "title",
                            "",
                        )
                    )

                    summary = str(
                        entry.get(
                            "summary",
                            "",
                        )
                    )

                    text = (
                        title
                        + " "
                        + summary
                    ).lower()

                    relevant = any(
                        re.search(
                            rf"\b{re.escape(term.lower())}\b",
                            text,
                        )
                        for term in search_terms
                    )

                    if not relevant:
                        continue

                    relevant_news.append(
                        title.strip()
                    )

                    for word in self.bullish_words:
                        if re.search(
                            rf"\b{re.escape(word)}\b",
                            text,
                        ):
                            bullish_score += 1

                    for word in self.bearish_words:
                        if re.search(
                            rf"\b{re.escape(word)}\b",
                            text,
                        ):
                            bearish_score += 1

            except requests.RequestException as exc:
                logger.warning(
                    "RSS request failed %s: %s",
                    feed_url,
                    exc,
                )

            except Exception as exc:
                logger.warning(
                    "RSS parse failed %s: %s",
                    feed_url,
                    exc,
                )

        if not relevant_news:
            return {
                "sentiment": "NEUTRAL",
                "context": "",
            }

        # Require a meaningful gap.
        if bullish_score >= bearish_score + 2:
            sentiment = "BULLISH"

        elif bearish_score >= bullish_score + 2:
            sentiment = "BEARISH"

        else:
            sentiment = "MIXED"

        # Remove duplicate titles.
        unique_titles = list(
            dict.fromkeys(relevant_news)
        )

        context = " | ".join(
            unique_titles[:3]
        )

        logger.info(
            "News %s -> %s | Bull=%s Bear=%s",
            coin,
            sentiment,
            bullish_score,
            bearish_score,
        )

        return {
            "sentiment": sentiment,
            "context": context,
        }
