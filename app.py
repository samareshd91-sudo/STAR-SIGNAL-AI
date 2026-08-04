import time
import logging
import requests
import os
import ccxt
import pandas as pd
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict

from technical_engine import TechnicalEngine
from news_engine import NewsEngine
from ai_engine import GeminiAIEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("BG_STAR_PRO_Production")

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"BG STAR PRO Production Bot is Running Perfectly!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, DummyHandler)
    logger.info(f"🌐 Dummy Web Server started on port {port}.")
    httpd.serve_forever()

class KuCoinFetcher:
    def __init__(self):
        self.exchange = ccxt.kucoin({'enableRateLimit': True})
        
    def fetch_live_data(self, coins: list, timeframe: str = '15m', limit: int = 100) -> dict:
        market_data = {}
        for coin in coins:
            symbol = f"{coin}/USDT"
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                market_data[coin] = df
                time.sleep(0.5) 
            except Exception as e:
                logger.error(f"🛑 Error fetching data for {symbol}: {e}")
        return market_data

class MasterSignalBot:
    def __init__(self, news_api_key: str, cryptocompare_api_key: str, gemini_api_key: str):
        self.tech_engine = TechnicalEngine()
        self.news_engine = NewsEngine(news_api_key, cryptocompare_api_key)
        self.ai_engine = GeminiAIEngine(gemini_api_key)
        
        # Track last processed candle timestamp per coin to prevent duplicate processing
        self.last_candle_timestamp: Dict[str, str] = {}

    def run_cycle(self, live_market_data: dict):
        logger.info("=========================================")
        logger.info("🔍 Running Production Market Scan...")
        
        tech_results = self.tech_engine.analyze_market(live_market_data)

        for coin, tech_data in tech_results.items():
            df = live_market_data.get(coin)
            if df is None or df.empty:
                continue
            
            # Use exact latest candle timestamp from DataFrame instead of system time
            current_candle_ts = str(df.iloc[-1]['timestamp'])
            if self.last_candle_timestamp.get(coin) == current_candle_ts:
                continue

            score = tech_data["technical_score"]
            direction = tech_data["direction"] # BULLISH or BEARISH
            triggers = tech_data["trigger_reasons"]
            is_triggered = tech_data["is_triggered"]

            signal_type = None
            trade_action = None

            # ---------------------------------------------------------
            # STEP 1: Trigger Passed?
            # ---------------------------------------------------------
            if not is_triggered:
                # Without explicit smart triggers, drop signal to avoid false positives
                continue 

            # ---------------------------------------------------------
            # STEP 2: News Available?
            # ---------------------------------------------------------
            news_data = self.news_engine.fetch_news_sentiment(coin)
            news_sentiment = news_data["sentiment"]
            
            if news_sentiment == "NEUTRAL" or not news_data.get("context"):
                # No strong news, fallback to pure technical confirmation if score is high
                if score >= 75:
                    signal_type = "🟡 Technical Signal"
                    trade_action = "BUY" if direction == "BULLISH" else "SELL"
                else:
                    continue
            else:
                # ---------------------------------------------------------
                # STEP 3: Technical + News Agree?
                # ---------------------------------------------------------
                tech_bullish = (direction == "BULLISH")
                news_bullish = (news_sentiment == "BULLISH")
                
                # If Technical and News directly contradict each other, safe action is WAIT
                if tech_bullish != news_bullish and news_sentiment != "MIXED":
                    logger.info(f"⚠️ {coin}: Technical ({direction}) and News ({news_sentiment}) disagree. Skipping trade.")
                    continue

                # ---------------------------------------------------------
                # STEP 4: Call Gemini AI
                # ---------------------------------------------------------
                ai_data = self.ai_engine.evaluate_signal(coin, tech_data, news_data)
                ai_action = ai_data.get("action", "WAIT")
                ai_status = ai_data.get("status", "SUCCESS") # SUCCESS or ERROR

                if ai_status == "ERROR":
                    # AI API Error / Timeout / Quota Exceeded -> Fallback to News & Tech agreement
                    signal_type = "🟠 Confirmed by News (AI Fallback)"
                    trade_action = "BUY" if (tech_bullish or news_bullish) else "SELL"
                elif ai_action in ["BUY", "SELL"]:
                    # AI successfully agreed and gave action
                    signal_type = "🟢 Strong Signal (AI + News Confirmed)"
                    trade_action = ai_action
                else:
                    # AI intentionally returned WAIT -> Respect it, do NOT fallback
                    logger.info(f"🛡️ {coin}: AI intentionally returned WAIT. Standing aside.")
                    continue

            # ---------------------------------------------------------
            # STEP 5: Broadcast Verified Signal
            # ---------------------------------------------------------
            if trade_action and signal_type:
                self.broadcast_signal(coin, signal_type, trade_action, score, triggers)
                self.last_candle_timestamp[coin] = current_candle_ts

    def broadcast_signal(self, coin: str, signal_type: str, action: str, score: int, triggers: list):
        logger.info(f"🚀 {signal_type} | Asset: {coin} | Action: {action} | Score: {score}")
        
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if bot_token and chat_id:
            action_emoji = "🟢 <b>BUY (লং)</b>" if action == "BUY" else "🔴 <b>SELL (শর্ট)</b>"
            
            tg_message = (
                f"🚀 <b>{signal_type}</b> 🚀\n\n"
                f"🪙 <b>Asset:</b> #{coin}\n"
                f"🎯 <b>Action:</b> {action_emoji}\n"
                f"📊 <b>Score:</b> {score}/100\n"
                f"⚡ <b>Triggers:</b> {', '.join(triggers)}"
            )
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            
            # Telegram Retry Mechanism
            for attempt in range(3):
                try:
                    res = requests.post(url, json={"chat_id": chat_id, "text": tg_message, "parse_mode": "HTML"}, timeout=5)
                    if res.status_code == 200:
                        break
                except Exception as e:
                    logger.error(f"🛑 Telegram Retry {attempt+1} Failed: {e}")
                    time.sleep(2)

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()

    news_key = os.getenv("NEWS_API_KEY", "")
    cryptocompare_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    
    bot = MasterSignalBot(news_api_key=news_key, cryptocompare_api_key=cryptocompare_key, gemini_api_key=gemini_key)
    fetcher = KuCoinFetcher()
    
    target_coins = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]
    logger.info("🔥 BG STAR PRO Production Backend Started Successfully!")
    
    while True:
        try:
            live_data = fetcher.fetch_live_data(target_coins, timeframe='15m')
            bot.run_cycle(live_data)
            time.sleep(300) 
        except Exception as e:
            logger.error(f"🛑 Critical Error in Main Loop: {e}")
            time.sleep(60)
