import os
import time
import logging
import threading
import warnings
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any

import ccxt
import pandas as pd
import requests

from technical_engine import TechnicalEngine
from news_engine import NewsEngine
from volatility_engine import VolatilityEngine

# Gemini is OPTIONAL.
try:
    from ai_engine import GeminiAIEngine
    GEMINI_MODULE_AVAILABLE = True
except Exception as e:
    GEMINI_MODULE_AVAILABLE = False
    GeminiAIEngine = None
    logging.warning("⚠️ Gemini module unavailable: %s", e)

warnings.filterwarnings("ignore", category=FutureWarning)

# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("BG_STAR_PRO")

# ==========================================================
# CONFIG
# ==========================================================

TARGET_COINS = [
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "DOGE",
]

TIMEFRAME_15M = "15m"
TIMEFRAME_5M = "5m"

OHLCV_LIMIT = 100

SCAN_INTERVAL = 60

# Strong signal minimum.
MIN_SIGNAL_SCORE = 70

# Score required for strongest tier.
STRONG_SIGNAL_SCORE = 82
ELITE_SIGNAL_SCORE = 90

# Same-direction cooldown.
SIGNAL_COOLDOWN_MINUTES = 60

# Opposite direction needs stronger confirmation.
REVERSAL_SCORE = 85

# Medium volatility penalty.
MEDIUM_VOLATILITY_PENALTY = 5

# Gemini is optional.
MIN_AI_CONFIDENCE = 75

# News disagreement = hard veto.
NEWS_HARD_VETO = True

# ==========================================================
# GLOBAL DASHBOARD STATUS
# ==========================================================

VOLATILITY_STATUS = "NORMAL"

SYSTEM_STATUS = "STARTING"

LAST_SCAN_TIME = 0

LAST_SCAN_RESULT = {
    "signals": 0,
    "candidates": 0,
    "rejected": 0,
}

LATEST_SIGNALS = []

# ==========================================================
# DASHBOARD
# ==========================================================


class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        return

    def do_GET(self):

        global VOLATILITY_STATUS
        global SYSTEM_STATUS
        global LAST_SCAN_TIME
        global LAST_SCAN_RESULT
        global LATEST_SIGNALS

        self.send_response(200)
        self.send_header(
            "Content-type",
            "text/html; charset=utf-8"
        )
        self.end_headers()

        if VOLATILITY_STATUS == "HIGH":
            status_color = "#dc2626"
            status_text = "🔴 HIGH VOLATILITY — SIGNALS PAUSED"

        elif VOLATILITY_STATUS == "MEDIUM":
            status_color = "#f59e0b"
            status_text = "🟠 MEDIUM VOLATILITY"

        else:
            status_color = "#059669"
            status_text = "🟢 SYSTEM ONLINE"

        last_scan = (
            time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(LAST_SCAN_TIME)
            )
            if LAST_SCAN_TIME
            else "Waiting..."
        )

        signal_rows = ""

        for signal in LATEST_SIGNALS[-10:][::-1]:

            action = signal.get(
                "action",
                "WAIT"
            )

            action_color = (
                "#22c55e"
                if action == "BUY"
                else "#ef4444"
            )

            signal_rows += f"""
            <tr>
                <td>{signal.get("time", "-")}</td>
                <td><b>{signal.get("coin", "-")}</b></td>
                <td style="color:{action_color};font-weight:bold">
                    {action}
                </td>
                <td>{signal.get("score", 0)}/100</td>
                <td>{signal.get("tier", "-")}</td>
            </tr>
            """

        if not signal_rows:
            signal_rows = """
            <tr>
                <td colspan="5">
                    No signals yet.
                </td>
            </tr>
            """

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>

        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width,
            initial-scale=1.0"
        >

        <meta
            http-equiv="refresh"
            content="30"
        >

        <title>BG STAR PRO</title>

        <style>

        body {{
            margin: 0;
            background: #0f172a;
            color: #e2e8f0;
            font-family:
                Arial,
                Helvetica,
                sans-serif;
        }}

        .container {{
            max-width: 1100px;
            margin: 0 auto;
            padding: 25px;
        }}

        h1 {{
            margin-bottom: 5px;
            color: #38bdf8;
        }}

        .subtitle {{
            color: #94a3b8;
        }}

        .status {{
            display: inline-block;
            padding: 10px 18px;
            border-radius: 20px;
            background: {status_color};
            color: white;
            font-weight: bold;
            margin: 15px 0;
        }}

        .grid {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(180px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }}

        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 18px;
        }}

        .label {{
            color: #94a3b8;
            font-size: 12px;
        }}

        .value {{
            font-size: 22px;
            font-weight: bold;
            margin-top: 7px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            background: #1e293b;
            border-radius: 12px;
            overflow: hidden;
        }}

        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom:
                1px solid #334155;
        }}

        th {{
            color: #94a3b8;
            font-size: 12px;
        }}

        .footer {{
            margin-top: 25px;
            color: #64748b;
            font-size: 12px;
        }}

        </style>

        </head>

        <body>

        <div class="container">

            <h1>⭐ BG STAR PRO</h1>

            <div class="subtitle">
                Smart Technical + News + Volatility Signal Engine
            </div>

            <div class="status">
                {status_text}
            </div>

            <div class="grid">

                <div class="card">
                    <div class="label">SYSTEM</div>
                    <div class="value">
                        {SYSTEM_STATUS}
                    </div>
                </div>

                <div class="card">
                    <div class="label">VOLATILITY</div>
                    <div class="value">
                        {VOLATILITY_STATUS}
                    </div>
                </div>

                <div class="card">
                    <div class="label">LAST SCAN</div>
                    <div class="value"
                         style="font-size:15px">
                        {last_scan}
                    </div>
                </div>

                <div class="card">
                    <div class="label">SIGNALS</div>
                    <div class="value">
                        {LAST_SCAN_RESULT.get("signals", 0)}
                    </div>
                </div>

                <div class="card">
                    <div class="label">CANDIDATES</div>
                    <div class="value">
                        {LAST_SCAN_RESULT.get("candidates", 0)}
                    </div>
                </div>

                <div class="card">
                    <div class="label">REJECTED</div>
                    <div class="value">
                        {LAST_SCAN_RESULT.get("rejected", 0)}
                    </div>
                </div>

            </div>

            <h2>📡 Latest Signals</h2>

            <table>

                <thead>
                    <tr>
                        <th>TIME</th>
                        <th>ASSET</th>
                        <th>ACTION</th>
                        <th>SCORE</th>
                        <th>TIER</th>
                    </tr>
                </thead>

                <tbody>
                    {signal_rows}
                </tbody>

            </table>

            <div class="footer">
                BG STAR PRO • 15m Technical Engine • 5m Volatility Engine
                <br>
                Scan interval: {SCAN_INTERVAL} seconds
            </div>

        </div>

        </body>
        </html>
        """

        self.wfile.write(
            html.encode("utf-8")
        )


def run_dashboard_server():

    port = int(
        os.getenv("PORT", "10000")
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        DashboardHandler
    )

    logger.info(
        "Dashboard listening on port %s",
        port
    )

    server.serve_forever()


# ==========================================================
# KUCOIN FETCHER
# ==========================================================


class KuCoinFetcher:

    def __init__(self):

        self.exchange = ccxt.kucoin({
            "enableRateLimit": True,
            "timeout": 10000,
        })

    def fetch_live_data(
        self,
        coins
    ) -> Dict[str, Dict[str, pd.DataFrame]]:

        market_data = {}

        for coin in coins:

            try:

                symbol = f"{coin}/USDT"

                ohlcv = self.exchange.fetch_ohlcv(
                    symbol,
                    TIMEFRAME_15M,
                    limit=OHLCV_LIMIT
                )

                df15 = self._to_dataframe(
                    ohlcv
                )

                if df15 is None or df15.empty:

                    logger.warning(
                        "%s: no 15m data",
                        coin
                    )

                    continue

                market_data[coin] = {
                    "15m": df15
                }

                logger.info(
                    "%s | 15m candles=%s",
                    coin,
                    len(df15)
                )

            except Exception as exc:

                logger.error(
                    "15m fetch error %s: %s",
                    coin,
                    exc
                )

        # --------------------------------------------------
        # BTC 5m volatility data
        # --------------------------------------------------

        try:

            btc_5m = self.exchange.fetch_ohlcv(
                "BTC/USDT",
                TIMEFRAME_5M,
                limit=OHLCV_LIMIT
            )

            btc5 = self._to_dataframe(
                btc_5m
            )

            if btc5 is not None and not btc5.empty:

                if "BTC" not in market_data:
                    market_data["BTC"] = {}

                market_data["BTC"]["5m"] = btc5

        except Exception as exc:

            logger.error(
                "BTC 5m fetch error: %s",
                exc
            )

        return market_data

    @staticmethod
    def _to_dataframe(
        ohlcv
    ):

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
            ]
        )

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            unit="ms"
        )

        for col in [
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:

            df[col] = pd.to_numeric(
                df[col],
                errors="coerce"
            )

        df = df.dropna(
            subset=[
                "open",
                "high",
                "low",
                "close",
            ]
        )

        return df.reset_index(
            drop=True
        )


# ==========================================================
# MASTER SIGNAL BOT
# ==========================================================


class MasterSignalBot:

    def __init__(
        self,
        news_key="",
        crypto_key="",
        gemini_key=""
    ):

        self.tech_engine = TechnicalEngine()

        self.news_engine = NewsEngine(
            news_key,
            crypto_key
        )

        self.vol_engine = VolatilityEngine()

        self.ai_engine = None

        # --------------------------------------------------
        # Gemini optional
        # --------------------------------------------------

        if (
            GEMINI_MODULE_AVAILABLE
            and gemini_key
        ):

            try:

                self.ai_engine = GeminiAIEngine(
                    gemini_key
                )

                logger.info(
                    "Gemini engine initialized."
                )

            except Exception as exc:

                logger.warning(
                    "Gemini initialization failed: %s",
                    exc
                )

                self.ai_engine = None

        else:

            logger.warning(
                "Gemini unavailable. "
                "Technical + News mode enabled."
            )

        # --------------------------------------------------
        # State
        # --------------------------------------------------

        self.signal_state = {}

        self.sent_fingerprints = set()

        self.last_processed_candle = {}

        self.stats = {
            "signals": 0,
            "technical_candidates": 0,
            "rejected": 0,
        }

    # ======================================================
    # MAIN CYCLE
    # ======================================================

    def run_cycle(
        self,
        live_data
    ):

        global VOLATILITY_STATUS
        global SYSTEM_STATUS
        global LAST_SCAN_TIME
        global LAST_SCAN_RESULT

        cycle_start = time.time()

        SYSTEM_STATUS = "SCANNING"

        # --------------------------------------------------
        # VOLATILITY
        # --------------------------------------------------

        btc_bundle = live_data.get(
            "BTC"
        )

        btc_5m = None

        if isinstance(
            btc_bundle,
            dict
        ):

            btc_5m = btc_bundle.get(
                "5m"
            )

        if btc_5m is None:

            if isinstance(
                btc_bundle,
                pd.DataFrame
            ):
                btc_5m = btc_bundle

        if btc_5m is not None:

            try:

                new_high = self.vol_engine.update(
                    btc_5m
                )

                VOLATILITY_STATUS = (
                    self.vol_engine.current_level
                )

                if new_high:
                    self.send_volatility_alert()

            except Exception as exc:

                logger.error(
                    "Volatility engine error: %s",
                    exc
                )

                VOLATILITY_STATUS = "NORMAL"

        is_paused = self.vol_engine.is_paused()

        # --------------------------------------------------
        # TECHNICAL ANALYSIS
        # --------------------------------------------------

        # New TechnicalEngine expects:
        #
        # coin -> DataFrame
        #
        # But fetcher stores:
        #
        # coin -> {"15m": DataFrame}
        #
        # Therefore convert here.

        technical_input = {}

        for coin in TARGET_COINS:

            bundle = live_data.get(
                coin
            )

            if not isinstance(
                bundle,
                dict
            ):
                continue

            df15 = bundle.get(
                "15m"
            )

            if (
                isinstance(
                    df15,
                    pd.DataFrame
                )
                and not df15.empty
            ):
                technical_input[coin] = df15

        try:

            tech_results = (
                self.tech_engine.analyze_market(
                    technical_input
                )
            )

        except Exception as exc:

            logger.exception(
                "Technical engine failure: %s",
                exc
            )

            tech_results = {}

        candidates = 0
        rejected = 0

        # --------------------------------------------------
        # PROCESS COINS
        # --------------------------------------------------

        for coin, data in tech_results.items():

            try:

                result = self._process_coin(
                    coin=coin,
                    data=data,
                    live_data=live_data,
                    is_paused=is_paused
                )

                if result == "candidate":
                    candidates += 1

                elif result == "rejected":
                    rejected += 1

            except Exception as exc:

                rejected += 1

                logger.exception(
                    "Processing error %s: %s",
                    coin,
                    exc
                )

        elapsed = (
            time.time()
            - cycle_start
        )

        LAST_SCAN_TIME = time.time()

        LAST_SCAN_RESULT = {
            "signals": self.stats["signals"],
            "candidates": candidates,
            "rejected": rejected,
        }

        SYSTEM_STATUS = "ONLINE"

        logger.info(
            "Cycle complete | "
            "elapsed=%.2fs | "
            "signals=%s | "
            "candidates=%s | "
            "rejected=%s",
            elapsed,
            self.stats["signals"],
            candidates,
            rejected
        )

    # ======================================================
    # COIN PROCESSOR
    # ======================================================

    def _process_coin(
        self,
        coin,
        data,
        live_data,
        is_paused=False
    ):

        if not isinstance(
            data,
            dict
        ):
            return "rejected"

        # --------------------------------------------------
        # DATA COMPATIBILITY
        # --------------------------------------------------

        score = int(
            data.get(
                "score",
                data.get(
                    "technical_score",
                    0
                )
            )
        )

        action = data.get(
            "action",
            "WAIT"
        )

        # New engine:
        # BUY / SELL / WAIT

        # Old compatibility:
        # direction

        if action not in (
            "BUY",
            "SELL"
        ):

            direction = data.get(
                "direction",
                "NEUTRAL"
            )

            if direction == "BULLISH":
                action = "BUY"

            elif direction == "BEARISH":
                action = "SELL"

            else:
                action = "WAIT"

        # --------------------------------------------------
        # CANDLE
        # --------------------------------------------------

        bundle = live_data.get(
            coin
        )

        if not isinstance(
            bundle,
            dict
        ):
            return "rejected"

        df15 = bundle.get(
            "15m"
        )

        if (
            df15 is None
            or df15.empty
            or len(df15) < 2
        ):
            return "rejected"

        candle_ts = str(
            df15.iloc[-1]["timestamp"]
        )

        # --------------------------------------------------
        # CANDLE LOCK
        # --------------------------------------------------

        if (
            self.last_processed_candle.get(
                coin
            )
            == candle_ts
        ):
            return "rejected"

        self.last_processed_candle[
            coin
        ] = candle_ts

        # --------------------------------------------------
        # WAIT / SCORE GATE
        # --------------------------------------------------

        if action not in (
            "BUY",
            "SELL"
        ):

            logger.info(
                "REJECT %s: action=WAIT | score=%s | reason=%s",
                coin,
                score,
                data.get(
                    "reason",
                    "weak_setup"
                )
            )

            return "rejected"

        if score < MIN_SIGNAL_SCORE:

            logger.info(
                "REJECT %s: score=%s < %s",
                coin,
                score,
                MIN_SIGNAL_SCORE
            )

            return "rejected"

        # --------------------------------------------------
        # TECHNICAL CONFIRMATION
        # --------------------------------------------------

        structure = bool(
            data.get(
                "structure_confirmed",
                False
            )
        )

        momentum = bool(
            data.get(
                "momentum_confirmed",
                False
            )
        )

        volume = bool(
            data.get(
                "volume_confirmed",
                False
            )
        )

        # New engine normally supplies these.
        #
        # If old output is used, signal can still pass
        # through the score/action gate.

        new_engine_format = any(
            key in data
            for key in (
                "structure_confirmed",
                "momentum_confirmed",
                "volume_confirmed"
            )
        )

        if new_engine_format:

            confirmations = sum(
                [
                    structure,
                    momentum,
                    volume,
                ]
            )

            if confirmations < 2:

                logger.info(
                    "REJECT %s: confirmation=%s/3 | score=%s",
                    coin,
                    confirmations,
                    score
                )

                return "rejected"

        # --------------------------------------------------
        # VOLATILITY
        # --------------------------------------------------

        adjusted_score = score

        if VOLATILITY_STATUS == "HIGH":

            logger.info(
                "REJECT %s: HIGH volatility pause.",
                coin
            )

            return "rejected"

        if VOLATILITY_STATUS == "MEDIUM":

            adjusted_score = max(
                0,
                score - MEDIUM_VOLATILITY_PENALTY
            )

            if adjusted_score < MIN_SIGNAL_SCORE:

                logger.info(
                    "REJECT %s: volatility score "
                    "%s -> %s",
                    coin,
                    score,
                    adjusted_score
                )

                return "rejected"

        # --------------------------------------------------
        # CANDIDATE
        # --------------------------------------------------

        self.stats[
            "technical_candidates"
        ] += 1

        # --------------------------------------------------
        # STATE / COOLDOWN
        # --------------------------------------------------

        if not self._passes_state_gate(
            coin=coin,
            action=action,
            score=adjusted_score
        ):

            return "rejected"

        # --------------------------------------------------
        # NEWS
        # --------------------------------------------------

        try:

            news = (
                self.news_engine
                .fetch_news_sentiment(
                    coin
                )
            )

        except Exception as exc:

            logger.warning(
                "News error %s: %s",
                coin,
                exc
            )

            news = {
                "sentiment": "NEUTRAL",
                "context": ""
            }

        news_sentiment = news.get(
            "sentiment",
            "NEUTRAL"
        )

        # --------------------------------------------------
        # NEWS HARD VETO
        # --------------------------------------------------

        if NEWS_HARD_VETO:

            if (
                action == "BUY"
                and news_sentiment == "BEARISH"
            ):

                logger.info(
                    "REJECT %s BUY: bearish news veto.",
                    coin
                )

                return "rejected"

            if (
                action == "SELL"
                and news_sentiment == "BULLISH"
            ):

                logger.info(
                    "REJECT %s SELL: bullish news veto.",
                    coin
                )

                return "rejected"

        # --------------------------------------------------
        # GEMINI OPTIONAL
        # --------------------------------------------------

        ai_data = {
            "action": "WAIT",
            "confidence": 0,
            "reason": "Gemini unavailable / skipped.",
            "status": "SKIPPED",
        }

        # Only use Gemini for high-quality setups.
        use_gemini = (
            self.ai_engine is not None
            and adjusted_score >= 80
            and news_sentiment in (
                "BULLISH",
                "BEARISH"
            )
        )

        if use_gemini:

            try:

                ai_data = (
                    self.ai_engine
                    .evaluate_signal(
                        coin,
                        self._prepare_ai_data(
                            coin,
                            data,
                            action,
                            adjusted_score
                        ),
                        news
                    )
                )

            except Exception as exc:

                logger.warning(
                    "Gemini error %s: %s",
                    coin,
                    exc
                )

                ai_data = {
                    "action": "WAIT",
                    "confidence": 0,
                    "reason": "Gemini exception.",
                    "status": "ERROR",
                }

            # --------------------------------------------------
            # IMPORTANT:
            #
            # Gemini is confirmation.
            # It must not cause good technical setups to vanish
            # when Gemini itself is unavailable.
            # --------------------------------------------------

            if ai_data.get(
                "status"
            ) == "SUCCESS":

                ai_action = ai_data.get(
                    "action",
                    "WAIT"
                )

                ai_confidence = int(
                    ai_data.get(
                        "confidence",
                        0
                    )
                )

                # AI cannot reverse technical direction.
                if ai_action != action:

                    logger.info(
                        "REJECT %s: "
                        "AI=%s technical=%s",
                        coin,
                        ai_action,
                        action
                    )

                    return "rejected"

                if (
                    ai_confidence
                    < MIN_AI_CONFIDENCE
                ):

                    logger.info(
                        "REJECT %s: "
                        "AI confidence=%s < %s",
                        coin,
                        ai_confidence,
                        MIN_AI_CONFIDENCE
                    )

                    return "rejected"

            else:

                # Gemini unavailable/error:
                # do NOT kill a strong technical signal.
                logger.warning(
                    "%s: Gemini unavailable; "
                    "continuing with technical/news confirmation.",
                    coin
                )

        # --------------------------------------------------
        # SIGNAL TIER
        # --------------------------------------------------

        tier = self._signal_tier(
            adjusted_score
        )

        if tier == "ELITE":

            signal_type = "💎 ELITE SIGNAL"

        elif tier == "STRONG":

            signal_type = "🔥 STRONG SIGNAL"

        else:

            signal_type = "🟢 VALID SIGNAL"

        # --------------------------------------------------
        # FINGERPRINT
        # --------------------------------------------------

        fingerprint = self._fingerprint(
            coin,
            action,
            candle_ts
        )

        if fingerprint in self.sent_fingerprints:

            logger.info(
                "REJECT %s: duplicate fingerprint.",
                coin
            )

            return "rejected"

        # --------------------------------------------------
        # BROADCAST
        # --------------------------------------------------

        self.broadcast(
            coin=coin,
            sig_type=signal_type,
            action=action,
            score=adjusted_score,
            data=data,
            news=news,
            ai_data=ai_data,
            candle_ts=candle_ts,
            tier=tier
        )

        # --------------------------------------------------
        # STATE UPDATE
        # --------------------------------------------------

        self.sent_fingerprints.add(
            fingerprint
        )

        self.signal_state[
            coin
        ] = {
            "last_direction": action,
            "last_signal_time": time.time(),
            "last_candle_ts": candle_ts,
            "fingerprint": fingerprint,
        }

        self.stats[
            "signals"
        ] += 1

        return "candidate"

    # ======================================================
    # STATE GATE
    # ======================================================

    def _passes_state_gate(
        self,
        coin,
        action,
        score
    ):

        state = self.signal_state.get(
            coin
        )

        if not state:
            return True

        previous_action = state.get(
            "last_direction"
        )

        last_signal_time = state.get(
            "last_signal_time",
            0
        )

        elapsed_minutes = (
            time.time()
            - last_signal_time
        ) / 60.0

        # --------------------------------------------------
        # SAME DIRECTION
        # --------------------------------------------------

        if previous_action == action:

            if (
                elapsed_minutes
                < SIGNAL_COOLDOWN_MINUTES
            ):

                logger.info(
                    "REJECT %s: cooldown "
                    "%.1f/%s min",
                    coin,
                    elapsed_minutes,
                    SIGNAL_COOLDOWN_MINUTES
                )

                return False

            return True

        # --------------------------------------------------
        # REVERSAL
        # --------------------------------------------------

        if score < REVERSAL_SCORE:

            logger.info(
                "REJECT %s: reversal "
                "%s -> %s requires %s; got %s",
                coin,
                previous_action,
                action,
                REVERSAL_SCORE,
                score
            )

            return False

        if elapsed_minutes < 15:

            logger.info(
                "REJECT %s: reversal cool-off "
                "%.1f min",
                coin,
                elapsed_minutes
            )

            return False

        return True

    # ======================================================
    # AI DATA COMPATIBILITY
    # ======================================================

    @staticmethod
    def _prepare_ai_data(
        coin,
        data,
        action,
        score
    ):

        output = dict(data)

        output["coin"] = coin
        output["action"] = action
        output["technical_score"] = score

        output["direction"] = (
            "BULLISH"
            if action == "BUY"
            else "BEARISH"
        )

        output["trigger_reasons"] = (
            data.get(
                "triggers",
                []
            )
        )

        return output

    # ======================================================
    # FINGERPRINT
    # ======================================================

    @staticmethod
    def _fingerprint(
        coin,
        action,
        candle_ts
    ):

        return (
            f"BGSTAR|"
            f"{coin}|"
            f"{action}|"
            f"{candle_ts}"
        )

    # ======================================================
    # SIGNAL TIER
    # ======================================================

    @staticmethod
    def _signal_tier(
        score
    ):

        if score >= ELITE_SIGNAL_SCORE:
            return "ELITE"

        if score >= STRONG_SIGNAL_SCORE:
            return "STRONG"

        return "VALID"

    # ======================================================
    # TELEGRAM VOLATILITY ALERT
    # ======================================================

    def send_volatility_alert(self):

        bot_token = os.getenv(
            "TELEGRAM_BOT_TOKEN"
        )

        chat_id = os.getenv(
            "TELEGRAM_CHAT_ID"
        )

        if not bot_token or not chat_id:
            return

        message = (
            "⚠️ <b>BG STAR PRO</b>\n\n"
            "🔴 <b>High Market Volatility</b>\n\n"
            "Signal generation paused temporarily."
        )

        try:

            requests.post(
                f"https://api.telegram.org/"
                f"bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                },
                timeout=5
            )

        except Exception:
            pass

    # ======================================================
    # TELEGRAM BROADCAST
    # ======================================================

    def broadcast(
        self,
        coin,
        sig_type,
        action,
        score,
        data,
        news,
        ai_data,
        candle_ts,
        tier
    ):

        global LATEST_SIGNALS

        logger.info(
            "🚀 %s | %s | %s | score=%s",
            sig_type,
            coin,
            action,
            score
        )

        # --------------------------------------------------
        # Save dashboard signal
        # --------------------------------------------------

        signal_record = {
            "time": time.strftime(
                "%H:%M:%S"
            ),
            "coin": coin,
            "action": action,
            "score": score,
            "tier": tier,
        }

        LATEST_SIGNALS.append(
            signal_record
        )

        if len(LATEST_SIGNALS) > 50:

            del LATEST_SIGNALS[:-50]

        # --------------------------------------------------
        # Telegram
        # --------------------------------------------------

        bot_token = os.getenv(
            "TELEGRAM_BOT_TOKEN"
        )

        chat_id = os.getenv(
            "TELEGRAM_CHAT_ID"
        )

        if not bot_token or not chat_id:

            logger.warning(
                "Telegram credentials missing."
            )

            return

        action_text = (
            "🟢 <b>BUY (LONG)</b>"
            if action == "BUY"
            else
            "🔴 <b>SELL (SHORT)</b>"
        )

        triggers = data.get(
            "triggers",
            data.get(
                "trigger_reasons",
                []
            )
        )

        if not isinstance(
            triggers,
            list
        ):

            triggers = [
                str(triggers)
            ]

        trigger_text = (
            ", ".join(
                str(x)
                for x in triggers
            )
            if triggers
            else "Technical Confirmation"
        )

        news_sentiment = news.get(
            "sentiment",
            "NEUTRAL"
        )

        ai_status = ai_data.get(
            "status",
            "SKIPPED"
        )

        ai_confidence = ai_data.get(
            "confidence",
            0
        )

        reason = ai_data.get(
            "reason",
            ""
        )

        message = (
            f"🚀 <b>{sig_type}</b> 🚀\n\n"

            f"🪙 <b>Asset:</b> #{coin}\n"

            f"🎯 <b>Action:</b> "
            f"{action_text}\n"

            f"📊 <b>Score:</b> "
            f"{score}/100\n"

            f"🏆 <b>Tier:</b> "
            f"{tier}\n\n"

            f"⚡ <b>Triggers:</b> "
            f"{trigger_text}\n"

            f"📰 <b>News:</b> "
            f"{news_sentiment}\n"

            f"🤖 <b>AI:</b> "
            f"{ai_status}\n"

            f"🎯 <b>AI Confidence:</b> "
            f"{ai_confidence}%"
        )

        if reason:

            message += (
                f"\n\n🧠 <b>Reason:</b> "
                f"{str(reason)[:250]}"
            )

        try:

            requests.post(
                f"https://api.telegram.org/"
                f"bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                },
                timeout=5
            )

        except Exception as exc:

            logger.error(
                "Telegram error: %s",
                exc
            )


# ==========================================================
# MAIN
# ==========================================================


def main():

    global SYSTEM_STATUS

    # ------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------

    dashboard_thread = threading.Thread(
        target=run_dashboard_server,
        daemon=True
    )

    dashboard_thread.start()

    # ------------------------------------------------------
    # Environment
    # ------------------------------------------------------

    news_key = os.getenv(
        "NEWS_API_KEY",
        ""
    )

    crypto_key = os.getenv(
        "CRYPTOCOMPARE_API_KEY",
        ""
    )

    gemini_key = os.getenv(
        "GEMINI_API_KEY",
        ""
    )

    # ------------------------------------------------------
    # Engines
    # ------------------------------------------------------

    bot = MasterSignalBot(
        news_key=news_key,
        crypto_key=crypto_key,
        gemini_key=gemini_key
    )

    fetcher = KuCoinFetcher()

    SYSTEM_STATUS = "ONLINE"

    logger.info(
        "=================================================="
    )

    logger.info(
        "⭐ BG STAR PRO STARTED"
    )

    logger.info(
        "Assets: %s",
        ", ".join(TARGET_COINS)
    )

    logger.info(
        "Timeframe: 15m"
    )

    logger.info(
        "Volatility timeframe: 5m"
    )

    logger.info(
        "Minimum signal score: %s",
        MIN_SIGNAL_SCORE
    )

    logger.info(
        "Cooldown: %s minutes",
        SIGNAL_COOLDOWN_MINUTES
    )

    logger.info(
        "Scan interval: %s seconds",
        SCAN_INTERVAL
    )

    logger.info(
        "Gemini available: %s",
        bot.ai_engine is not None
    )

    logger.info(
        "=================================================="
    )

    # ------------------------------------------------------
    # Main loop
    # ------------------------------------------------------

    while True:

        cycle_start = time.time()

        try:

            live_data = (
                fetcher.fetch_live_data(
                    TARGET_COINS
                )
            )

            if not live_data:

                logger.warning(
                    "No market data received."
                )

            else:

                bot.run_cycle(
                    live_data
                )

        except Exception as exc:

            logger.exception(
                "Critical cycle error: %s",
                exc
            )

        elapsed = (
            time.time()
            - cycle_start
        )

        sleep_for = max(
            5,
            SCAN_INTERVAL - elapsed
        )

        time.sleep(
            sleep_for
        )


# ==========================================================
# ENTRY
# ==========================================================

if __name__ == "__main__":
    main()
