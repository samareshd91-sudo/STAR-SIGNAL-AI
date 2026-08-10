import gc
import hashlib
import logging
import os
import threading
import time
import warnings
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

from technical_engine import TechnicalEngine
from news_engine import NewsEngine
from ai_engine import GeminiAIEngine
from volatility_engine import VolatilityEngine
from data_fetcher import KuCoinFetcher


warnings.filterwarnings(
    "ignore",
    category=FutureWarning,
)


# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(
    "BG_STAR_PRO_StrongSignal"
)


# ==========================================================
# GLOBAL SETTINGS
# ==========================================================

TARGET_COINS = [
    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "DOGE",
]

# ----------------------------------------------------------
# Render 512 MB friendly:
# 60 sec polling is enough because final signals are based
# on completed 15m candles.
# ----------------------------------------------------------

SCAN_INTERVAL_SECONDS = 60

MIN_SIGNAL_SCORE = 85

# Strong reversal needs more evidence.
REVERSAL_SCORE = 90

SIGNAL_COOLDOWN_MINUTES = 60

# Gemini confirmation threshold.
MIN_AI_CONFIDENCE = 70

# Medium volatility penalty.
MEDIUM_VOLATILITY_PENALTY = 5

VOLATILITY_STATUS = "NORMAL"


# ==========================================================
# DASHBOARD
# ==========================================================

class DashboardHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        return

    def do_GET(self):
        global VOLATILITY_STATUS

        self.send_response(200)
        self.send_header(
            "Content-type",
            "text/html; charset=utf-8",
        )
        self.end_headers()

        status_color = "#059669"
        status_text = "🟢 STRONG SIGNAL ENGINE ONLINE"

        if VOLATILITY_STATUS == "HIGH":
            status_color = "#dc2626"
            status_text = (
                "🔴 HIGH VOLATILITY — SIGNALS PAUSED"
            )

        elif VOLATILITY_STATUS == "MEDIUM":
            status_color = "#f59e0b"
            status_text = (
                "🟠 MEDIUM VOLATILITY — STRICT MODE"
            )

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport"
                  content="width=device-width, initial-scale=1.0">

            <meta http-equiv="refresh" content="60">

            <title>BG STAR PRO Strong Signal Engine</title>

            <style>
                body {{
                    background:#0f172a;
                    color:#e2e8f0;
                    font-family:Arial,sans-serif;
                    display:flex;
                    justify-content:center;
                    align-items:center;
                    min-height:100vh;
                    margin:0;
                }}

                .card {{
                    background:#1e293b;
                    padding:30px;
                    border-radius:18px;
                    width:90%;
                    max-width:620px;
                    box-shadow:0 10px 30px
                        rgba(0,0,0,.45);
                    border:1px solid #334155;
                }}

                h1 {{
                    color:#38bdf8;
                    margin-bottom:6px;
                }}

                .subtitle {{
                    color:#94a3b8;
                    margin-bottom:24px;
                }}

                .status {{
                    background:{status_color};
                    color:white;
                    padding:12px 18px;
                    border-radius:30px;
                    font-weight:bold;
                    text-align:center;
                    margin-bottom:24px;
                }}

                .grid {{
                    display:grid;
                    grid-template-columns:
                        repeat(2, 1fr);
                    gap:12px;
                }}

                .box {{
                    background:#0f172a;
                    border:1px solid #334155;
                    border-radius:12px;
                    padding:14px;
                }}

                .label {{
                    color:#94a3b8;
                    font-size:12px;
                }}

                .value {{
                    color:#f8fafc;
                    font-weight:bold;
                    margin-top:5px;
                }}

                .full {{
                    grid-column:1 / -1;
                    text-align:center;
                }}

                .footer {{
                    color:#64748b;
                    font-size:12px;
                    text-align:center;
                    margin-top:25px;
                }}
            </style>
        </head>

        <body>
            <div class="card">

                <h1>🚀 BG STAR PRO</h1>

                <div class="subtitle">
                    Strong Signal / Anti-Whipsaw Engine
                </div>

                <div class="status">
                    {status_text}
                </div>

                <div class="grid">

                    <div class="box">
                        <div class="label">
                            Scan
                        </div>
                        <div class="value">
                            60 Seconds
                        </div>
                    </div>

                    <div class="box">
                        <div class="label">
                            Final Candle
                        </div>
                        <div class="value">
                            CLOSED 15m
                        </div>
                    </div>

                    <div class="box">
                        <div class="label">
                            Minimum Score
                        </div>
                        <div class="value">
                            85 / 100
                        </div>
                    </div>

                    <div class="box">
                        <div class="label">
                            Reversal Score
                        </div>
                        <div class="value">
                            90 / 100
                        </div>
                    </div>

                    <div class="box">
                        <div class="label">
                            Cooldown
                        </div>
                        <div class="value">
                            60 Minutes
                        </div>
                    </div>

                    <div class="box">
                        <div class="label">
                            HTF
                        </div>
                        <div class="value">
                            1H + 4H
                        </div>
                    </div>

                    <div class="box full">
                        <div class="label">
                            Target Assets
                        </div>

                        <div class="value">
                            BTC · ETH · BNB · SOL · XRP · DOGE
                        </div>
                    </div>

                    <div class="box full">
                        <div class="label">
                            Volatility
                        </div>

                        <div class="value">
                            {VOLATILITY_STATUS}
                        </div>
                    </div>

                </div>

                <div class="footer">
                    Strong signals only.
                    No low-quality fallback signals.
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
        os.environ.get(
            "PORT",
            10000,
        )
    )

    server = HTTPServer(
        ("0.0.0.0", port),
        DashboardHandler,
    )

    logger.info(
        "Dashboard listening on port %s",
        port,
    )

    server.serve_forever()


# ==========================================================
# MASTER SIGNAL BOT
# ==========================================================

class MasterSignalBot:

    def __init__(
        self,
        news_key,
        crypto_key,
        gemini_key,
    ):

        self.tech_engine = TechnicalEngine()

        self.news_engine = NewsEngine(
            news_key,
            crypto_key,
        )

        self.ai_engine = GeminiAIEngine(
            gemini_key,
        )

        self.vol_engine = VolatilityEngine()

        # --------------------------------------------------
        # In-memory state.
        #
        # This is intentionally tiny for 512 MB Render.
        # --------------------------------------------------

        self.signal_state = {}

        self.last_processed_candle = {}

        self.sent_fingerprints = set()

        self.stats = {
            "cycles": 0,
            "technical_candidates": 0,
            "rejected": 0,
            "signals": 0,
        }

    # ======================================================
    # VOLATILITY ALERT
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
            "⚠️ <b>HIGH MARKET VOLATILITY</b>\n\n"
            "Signal generation has been paused "
            "until volatility returns to a safer level."
        )

        try:
            requests.post(
                (
                    "https://api.telegram.org/"
                    f"bot{bot_token}/sendMessage"
                ),
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                },
                timeout=5,
            )

        except Exception as exc:
            logger.warning(
                "Volatility alert failed: %s",
                exc,
            )

    # ======================================================
    # MAIN CYCLE
    # ======================================================

    def run_cycle(
        self,
        live_data: dict,
    ):

        global VOLATILITY_STATUS

        self.stats["cycles"] += 1

        # ==================================================
        # VOLATILITY
        # ==================================================

        btc_df = live_data.get(
            "BTC_5m"
        )

        if btc_df is None:
            btc_bundle = live_data.get(
                "BTC"
            )

            if isinstance(
                btc_bundle,
                dict,
            ):
                btc_df = btc_bundle.get(
                    "15m"
                )

        if btc_df is not None and not btc_df.empty:

            try:
                new_high_triggered = (
                    self.vol_engine.update(
                        btc_df
                    )
                )

                VOLATILITY_STATUS = (
                    self.vol_engine.current_level
                )

                if new_high_triggered:
                    self.send_volatility_alert()

            except Exception as exc:
                logger.warning(
                    "Volatility engine error: %s",
                    exc,
                )

        is_paused = self.vol_engine.is_paused()

        if is_paused:
            logger.warning(
                "HIGH volatility: signal generation paused."
            )

            return

        # ==================================================
        # TECHNICAL ANALYSIS
        # ==================================================

        tech_results = (
            self.tech_engine.analyze_market(
                live_data
            )
        )

        for coin, data in tech_results.items():

            try:
                self._process_coin(
                    coin,
                    data,
                    live_data,
                )

            except Exception as exc:
                logger.exception(
                    "Coin processing error %s: %s",
                    coin,
                    exc,
                )

        # ==================================================
        # MEMORY CLEANUP
        # ==================================================

        if self.stats["cycles"] % 20 == 0:
            self._trim_state()
            gc.collect()

    # ======================================================
    # COIN PROCESSOR
    # ======================================================

    def _process_coin(
        self,
        coin,
        data,
        live_data,
    ):

        bundle = live_data.get(
            coin
        )

        if not isinstance(
            bundle,
            dict,
        ):
            return

        df15 = bundle.get(
            "15m"
        )

        if df15 is None or df15.empty:
            return

        score = int(
            data.get(
                "technical_score",
                0,
            )
        )

        direction = data.get(
            "direction",
            "NEUTRAL",
        )

        candle_ts = str(
            df15.iloc[-1]["timestamp"]
        )

        # ==================================================
        # CANDLE LOCK
        # ==================================================

        if (
            self.last_processed_candle.get(
                coin
            )
            == candle_ts
        ):
            return

        # Mark candle as processed BEFORE API calls.
        #
        # This prevents duplicate processing during a
        # Streamlit/process loop or repeated cycle.
        self.last_processed_candle[
            coin
        ] = candle_ts

        # ==================================================
        # TECHNICAL SCORE
        # ==================================================

        if score < MIN_SIGNAL_SCORE:

            self.stats["rejected"] += 1

            logger.info(
                "REJECT %s: score=%s < %s | %s",
                coin,
                score,
                MIN_SIGNAL_SCORE,
                data.get(
                    "rejection_reasons",
                    [],
                ),
            )

            return

        self.stats[
            "technical_candidates"
        ] += 1

        # ==================================================
        # TECHNICAL HARD GATE
        # ==================================================

        if not data.get(
            "is_triggered",
            False,
        ):

            self.stats["rejected"] += 1

            logger.info(
                "REJECT %s: technical hard gate | %s",
                coin,
                data.get(
                    "rejection_reasons",
                    [],
                ),
            )

            return

        if direction not in (
            "BULLISH",
            "BEARISH",
        ):
            return

        trade_action = (
            "BUY"
            if direction == "BULLISH"
            else "SELL"
        )

        # ==================================================
        # MEDIUM VOLATILITY PENALTY
        # ==================================================

        adjusted_score = score

        if VOLATILITY_STATUS == "MEDIUM":

            adjusted_score = max(
                0,
                score - MEDIUM_VOLATILITY_PENALTY,
            )

            if adjusted_score < MIN_SIGNAL_SCORE:

                logger.info(
                    "REJECT %s: medium volatility "
                    "reduced score %s -> %s",
                    coin,
                    score,
                    adjusted_score,
                )

                return

        # ==================================================
        # STATE / COOLDOWN / REVERSAL
        # ==================================================

        if not self._passes_state_gate(
            coin=coin,
            action=trade_action,
            score=adjusted_score,
        ):
            return

        # ==================================================
        # NEWS
        # ==================================================

        news = (
            self.news_engine.fetch_news_sentiment(
                coin
            )
        )

        news_sentiment = news.get(
            "sentiment",
            "NEUTRAL",
        )

        # Directly opposing news is a hard veto.
        if (
            trade_action == "BUY"
            and news_sentiment == "BEARISH"
        ):
            logger.info(
                "REJECT %s BUY: bearish news veto.",
                coin,
            )
            return

        if (
            trade_action == "SELL"
            and news_sentiment == "BULLISH"
        ):
            logger.info(
                "REJECT %s SELL: bullish news veto.",
                coin,
            )
            return

        # ==================================================
        # GEMINI CONFIRMATION
        # ==================================================

        ai_data = {
            "action": "WAIT",
            "confidence": 0,
            "reason": "Not called.",
            "status": "SKIPPED",
        }

        gemini_available = (
            self.ai_engine.mode != "NONE"
        )

        if gemini_available:

            ai_data = (
                self.ai_engine.evaluate_signal(
                    coin,
                    data,
                    news,
                )
            )

            if ai_data.get(
                "status"
            ) != "SUCCESS":

                # No technical fallback after an AI error.
                # Strong engine prefers NO SIGNAL.
                logger.warning(
                    "REJECT %s: Gemini confirmation unavailable.",
                    coin,
                )

                return

            ai_action = ai_data.get(
                "action",
                "WAIT",
            )

            ai_confidence = int(
                ai_data.get(
                    "confidence",
                    0,
                )
            )

            # AI cannot reverse technical direction.
            if ai_action != trade_action:

                logger.info(
                    "REJECT %s: AI action=%s, "
                    "technical=%s",
                    coin,
                    ai_action,
                    trade_action,
                )

                return

            if ai_confidence < MIN_AI_CONFIDENCE:

                logger.info(
                    "REJECT %s: AI confidence=%s < %s",
                    coin,
                    ai_confidence,
                    MIN_AI_CONFIDENCE,
                )

                return

        # ==================================================
        # FINAL FINGERPRINT
        # ==================================================

        fingerprint = self._fingerprint(
            coin,
            trade_action,
            candle_ts,
        )

        if fingerprint in self.sent_fingerprints:

            logger.warning(
                "REJECT %s: duplicate fingerprint.",
                coin,
            )

            return

        # ==================================================
        # FINAL SIGNAL
        # ==================================================

        tier = self._signal_tier(
            adjusted_score
        )

        signal_type = (
            "💎 ELITE SIGNAL"
            if tier == "ELITE"
            else
            "🔥 STRONG SIGNAL"
            if tier == "STRONG"
            else
            "🟢 VALID SIGNAL"
        )

        self.broadcast(
            coin=coin,
            sig_type=signal_type,
            action=trade_action,
            score=adjusted_score,
            data=data,
            news=news,
            ai_data=ai_data,
            candle_ts=candle_ts,
            tier=tier,
        )

        # ==================================================
        # STATE UPDATE
        # ==================================================

        self.sent_fingerprints.add(
            fingerprint
        )

        self.signal_state[coin] = {
            "last_direction": trade_action,
            "last_signal_time": time.time(),
            "last_candle_ts": candle_ts,
            "fingerprint": fingerprint,
        }

        self.stats["signals"] += 1

    # ======================================================
    # STATE GATE
    # ======================================================

    def _passes_state_gate(
        self,
        coin,
        action,
        score,
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
            0,
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
                    "REJECT %s: same-direction cooldown "
                    "%.1f/%.1f min",
                    coin,
                    elapsed_minutes,
                    SIGNAL_COOLDOWN_MINUTES,
                )

                return False

            return True

        # --------------------------------------------------
        # OPPOSITE DIRECTION
        # --------------------------------------------------

        # Opposite signal is a reversal.
        # It requires stronger score.
        if score < REVERSAL_SCORE:

            logger.info(
                "REJECT %s: reversal %s -> %s "
                "requires score >= %s; got %s",
                coin,
                previous_action,
                action,
                REVERSAL_SCORE,
                score,
            )

            return False

        # Require a minimum cool-off even for reversals.
        if elapsed_minutes < 15:

            logger.info(
                "REJECT %s: reversal cool-off %.1f min",
                coin,
                elapsed_minutes,
            )

            return False

        logger.info(
            "REVERSAL CANDIDATE %s: %s -> %s | score=%s",
            coin,
            previous_action,
            action,
            score,
        )

        return True

    # ======================================================
    # FINGERPRINT
    # ======================================================

    @staticmethod
    def _fingerprint(
        coin,
        action,
        candle_ts,
    ):

        raw = (
            f"BGSTAR-V2|"
            f"{coin}|"
            f"{action}|"
            f"{candle_ts}"
        )

        return hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()

    # ======================================================
    # TIER
    # ======================================================

    @staticmethod
    def _signal_tier(
        score,
    ):

        if score >= 95:
            return "ELITE"

        if score >= 90:
            return "STRONG"

        return "VALID"

    # ======================================================
    # TELEGRAM
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
        tier,
    ):

        logger.info(
            "🚀 %s | %s | %s | %s",
            sig_type,
            coin,
            action,
            score,
        )

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

        features = data.get(
            "features",
            {},
        )

        action_text = (
            "🟢 <b>BUY (লং)</b>"
            if action == "BUY"
            else
            "🔴 <b>SELL (শর্ট)</b>"
        )

        news_sentiment = news.get(
            "sentiment",
            "NEUTRAL",
        )

        ai_confidence = ai_data.get(
            "confidence",
            0,
        )

        ai_reason = ai_data.get(
            "reason",
            "",
        )

        msg = (
            f"🚀 <b>{sig_type}</b> 🚀\n\n"

            f"🪙 <b>Asset:</b> #{coin}/USDT\n"

            f"🎯 <b>Action:</b> "
            f"{action_text}\n"

            f"📊 <b>Score:</b> "
            f"{score}/100\n"

            f"🏆 <b>Tier:</b> "
            f"{tier}\n\n"

            f"━━━━━━━━━━━━━━\n"

            f"📉 <b>STRUCTURE</b>\n"
            f"BOS/Structure: "
            f"{features.get('structure_direction')} "
            f"{'✅' if features.get('structure_confirmation') else '❌'}\n"

            f"📐 <b>HTF</b>\n"
            f"1H: "
            f"{features.get('one_hour_direction')} "
            f"{'✅' if features.get('one_hour_direction') == features.get('htf_direction') and features.get('htf_alignment') else '❌'}\n"

            f"4H: "
            f"{features.get('four_hour_direction')} "
            f"{'✅' if features.get('four_hour_direction') == features.get('htf_direction') and features.get('htf_alignment') else '❌'}\n"

            f"EMA: "
            f"{features.get('ema_direction')} "
            f"{'✅' if features.get('ema_trend') else '❌'}\n\n"

            f"⚡ <b>MOMENTUM</b>\n"
            f"ADX: "
            f"{features.get('adx_value')} "
            f"{'✅' if features.get('adx_strength') else '❌'}\n"

            f"Pressure: "
            f"{features.get('pressure_direction')} "
            f"{'✅' if features.get('pressure_confirmation') else '❌'}\n"

            f"Displacement: "
            f"{features.get('displacement_ratio')} ATR "
            f"{'✅' if features.get('displacement') else '❌'}\n"

            f"2-Candle: "
            f"{'Confirmed ✅' if features.get('candle_confirmation') else 'Failed ❌'}\n\n"

            f"💧 <b>LIQUIDITY / LOCATION</b>\n"
            f"Sweep: "
            f"{features.get('liquidity_direction')} "
            f"{'✅' if features.get('liquidity_sweep') else '—'}\n"

            f"OB/FVG: "
            f"{features.get('ob_fvg_direction')} "
            f"{'✅' if features.get('ob_fvg') else '—'}\n"

            f"Volume: "
            f"{'Confirmed ✅' if features.get('volume_confirmation') else 'Normal'}\n\n"

            f"📰 <b>NEWS:</b> "
            f"{news_sentiment}\n"
        )

        if ai_data.get(
            "status"
        ) == "SUCCESS":

            msg += (
                f"\n🤖 <b>AI CONFIRMATION</b>\n"
                f"Action: "
                f"{ai_data.get('action')} ✅\n"
                f"Confidence: "
                f"{ai_confidence}/100\n"
                f"Reason: "
                f"{ai_reason}\n"
            )

        msg += (
            f"\n⏱️ <b>Closed Candle:</b> "
            f"{candle_ts}\n"

            f"🛡️ <b>Signal Policy:</b> "
            f"85+ score / Anti-Whipsaw\n"
        )

        try:

            response = requests.post(
                (
                    "https://api.telegram.org/"
                    f"bot{bot_token}/sendMessage"
                ),
                json={
                    "chat_id": chat_id,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=7,
            )

            if not response.ok:
                logger.warning(
                    "Telegram HTTP %s: %s",
                    response.status_code,
                    response.text[:200],
                )

        except requests.RequestException as exc:
            logger.error(
                "Telegram delivery failed: %s",
                exc,
            )

    # ======================================================
    # STATE MEMORY CONTROL
    # ======================================================

    def _trim_state(self):

        # Fingerprints are intentionally tiny.
        # Keep only a bounded amount.
        if len(
            self.sent_fingerprints
        ) > 1000:

            self.sent_fingerprints = set(
                list(
                    self.sent_fingerprints
                )[-300:]
            )

        if len(
            self.last_processed_candle
        ) > 50:

            self.last_processed_candle = dict(
                list(
                    self.last_processed_candle.items()
                )[-20:]
            )


# ==========================================================
# MAIN
# ==========================================================

def main():

    logger.info(
        "================================================"
    )

    logger.info(
        "🚀 BG STAR PRO STRONG SIGNAL ENGINE STARTING"
    )

    logger.info(
        "Minimum score: %s",
        MIN_SIGNAL_SCORE,
    )

    logger.info(
        "Reversal score: %s",
        REVERSAL_SCORE,
    )

    logger.info(
        "Cooldown: %s minutes",
        SIGNAL_COOLDOWN_MINUTES,
    )

    logger.info(
        "Scan interval: %s seconds",
        SCAN_INTERVAL_SECONDS,
    )

    logger.info(
        "================================================"
    )

    # ------------------------------------------------------
    # Dashboard thread
    # ------------------------------------------------------

    threading.Thread(
        target=run_dashboard_server,
        daemon=True,
        name="dashboard",
    ).start()

    # ------------------------------------------------------
    # Engines
    # ------------------------------------------------------

    bot = MasterSignalBot(
        os.getenv(
            "NEWS_API_KEY",
            "",
        ),
        os.getenv(
            "CRYPTOCOMPARE_API_KEY",
            "",
        ),
        os.getenv(
            "GEMINI_API_KEY",
            "",
        ),
    )

    fetcher = KuCoinFetcher()

    # ------------------------------------------------------
    # Main loop
    # ------------------------------------------------------

    while True:

        cycle_start = time.monotonic()

        try:

            live_data = (
                fetcher.fetch_live_data(
                    TARGET_COINS
                )
            )

            if live_data:

                bot.run_cycle(
                    live_data
                )

            elapsed = (
                time.monotonic()
                - cycle_start
            )

            sleep_for = max(
                5,
                SCAN_INTERVAL_SECONDS
                - elapsed,
            )

            logger.info(
                "Cycle complete | "
                "elapsed=%.1fs | "
                "signals=%s | "
                "candidates=%s",
                elapsed,
                bot.stats["signals"],
                bot.stats[
                    "technical_candidates"
                ],
            )

            time.sleep(
                sleep_for
            )

        except KeyboardInterrupt:

            logger.info(
                "Shutdown requested."
            )

            break

        except Exception as exc:

            logger.exception(
                "Critical main-loop error: %s",
                exc,
            )

            # Prevent tight crash loops.
            time.sleep(20)


if __name__ == "__main__":
    main()
