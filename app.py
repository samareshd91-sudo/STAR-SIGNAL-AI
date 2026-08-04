import time
import logging
import requests
import os
import ccxt
import pandas as pd
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict

# Importing the engines we built
from technical_engine import TechnicalEngine
from news_engine import NewsEngine
from ai_engine import GeminiAIEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("BG_STAR_PRO_Master")


# ==========================================
# 🌐 DUMMY WEB SERVER (To keep Render Free Tier awake)
# ==========================================
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"BG STAR PRO Bot is Running Perfectly!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, DummyHandler)
    logger.info(f"🌐 Dummy Web Server started on port {port} for Render Free Tier.")
    httpd.serve_forever()


# ==========================================
# 📡 LIVE DATA FETCHER (KUCOIN)
# ==========================================
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
                logger.info(f"✅ Downloaded {len(df)} live candles for {symbol}")
                time.sleep(0.5) 
            except Exception as e:
                logger.error(f"🛑 Error fetching data for {symbol}: {e}")
        return market_data


# ==========================================
# 🧠 MASTER SIGNAL BOT
# ==========================================
class MasterSignalBot:
    def __init__(self, news_api_key: str, cryptocompare_api_key: str, gemini_api_key: str):
        self.tech_engine = TechnicalEngine()
        self.news_engine = NewsEngine(news_api_key, cryptocompare_api_key)
        self.ai_engine = GeminiAIEngine(gemini_api_key)
        
        self.signal_history: Dict[str, dict] = {}
        self.last_candle_time: Dict[str, int] = {}

    def is_duplicate_signal(self, coin: str, current_score: int, direction: str, triggers: list) -> bool:
        if coin not in self.signal_history: return False
        prev = self.signal_history[coin]
        same_direction = prev["direction"] == direction
        score_diff_small = abs(prev["score"] - current_score) <= 3
        same_triggers = sorted(prev["triggers"]) == sorted(triggers)
        return same_direction and score_diff_small and same_triggers

    def run_cycle(self, live_market_data: dict, current_candle_timestamp: int):
        logger.info("=========================================")
        logger.info("🔍 STAGE 1: Running Technical Scan...")
        
        tech_results = self.tech_engine.analyze_market(live_market_data)

        for coin, tech_data in tech_results.items():
            if self.last_candle_time.get(coin) == current_candle_timestamp: continue

            score = tech_data["technical_score"]
            direction = tech_data["direction"]
            triggers = tech_data["trigger_reasons"]
            is_triggered = tech_data["is_triggered"]

            final_signal = None
            signal_type = "NO TRADE"

            if not is_triggered:
                if score >= 75:
                    signal_type = "🟡 Technical Signal"
                    final_signal = direction
                else: continue 
            else:
                news_data = self.news_engine.fetch_news_sentiment(coin)
                
                if news_data["sentiment"] == "NEUTRAL":
                    signal_type = "🟡 Technical Signal"
                    final_signal = direction
                else:
                    ai_data = self.ai_engine.evaluate_signal(coin, tech_data, news_data)
                    if ai_data["action"] == "WAIT":
                        signal_type = "🟠 Confirmed by News"
                        final_signal = news_data["sentiment"] 
                    else:
                        signal_type = "🟢 Strong Signal"
                        final_signal = ai_data["action"] 

            if final_signal:
                if self.is_duplicate_signal(coin, score, final_signal, triggers):
                    logger.info(f"🛡️ {coin} Signal Blocked by Duplicate Protection (Score {score}).")
                    continue

                self.broadcast_signal(coin, signal_type, final_signal, score, triggers)
                
                self.signal_history[coin] = {"direction": final_signal, "score": score, "triggers": triggers}
                self.last_candle_time[coin] = current_candle_timestamp

    def broadcast_signal(self, coin: str, signal_type: str, action: str, score: int, triggers: list):
        logger.info(f"\n🚀 {signal_type} DETECTED! 🚀")
        logger.info(f"Asset: {coin} | Action: {action} | Score: {score}/100")
        
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")

        if bot_token and chat_id:
            tg_message = (
                f"🚀 *{signal_type}* 🚀\n\n"
                f"🪙 *Asset:* #{coin}\n"
                f"🎯 *Action:* {action}\n"
                f"📊 *Score:* {score}/100\n"
                f"⚡ *Triggers:* {', '.join(triggers)}"
            )
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            try:
                requests.post(url, json={"chat_id": chat_id, "text": tg_message, "parse_mode": "Markdown"}, timeout=5)
                logger.info("✅ Telegram Alert Sent Successfully!")
            except Exception as e:
                logger.error(f"🛑 Telegram Failed: {e}")


# ==========================================
# 🚀 MAIN EXECUTION LOOP 
# ==========================================
if __name__ == "__main__":
    # Start the dummy web server in the background for Render
    threading.Thread(target=run_dummy_server, daemon=True).start()

    news_key = os.getenv("NEWS_API_KEY", "")
    cryptocompare_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    
    bot = MasterSignalBot(news_api_key=news_key, cryptocompare_api_key=cryptocompare_key, gemini_api_key=gemini_key)
    fetcher = KuCoinFetcher()
    
    target_coins = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]
    logger.info("🔥 BG STAR PRO Backend Started. Waiting for live market data...")
    
    while True:
        try:
            live_data = fetcher.fetch_live_data(target_coins, timeframe='15m')
            current_timestamp = int(time.time()) 
            bot.run_cycle(live_data, current_timestamp)
            
            logger.info("⏳ Cycle complete. Waiting 5 minutes for the next market scan...\n")
            time.sleep(300) 
            
        except Exception as e:
            logger.error(f"🛑 Critical System Error in Main Loop: {e}")
            time.sleep(60) 
