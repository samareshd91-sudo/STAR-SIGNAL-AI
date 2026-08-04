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
logger = logging.getLogger("BG_STAR_PRO_SmartAPI")

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"BG STAR PRO Active Scanner is Running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(('0.0.0.0', port), DummyHandler).serve_forever()

class KuCoinFetcher:
    def __init__(self):
        self.exchange = ccxt.kucoin({'enableRateLimit': True})
        
    def fetch_live_data(self, coins: list) -> dict:
        data = {}
        for coin in coins:
            try:
                ohlcv = self.exchange.fetch_ohlcv(f"{coin}/USDT", '15m', limit=100)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                data[coin] = df
                time.sleep(0.3)
            except Exception as e:
                logger.error(f"Fetch Error {coin}: {e}")
        return data

class MasterSignalBot:
    def __init__(self, news_key, crypto_key, gemini_key):
        self.tech_engine = TechnicalEngine()
        self.news_engine = NewsEngine(news_key, crypto_key)
        self.ai_engine = GeminiAIEngine(gemini_key)
        
        # Smart Cache System
        self.api_cache = {}

    def get_tier(self, score: int) -> int:
        if score < 70: return 0
        elif score <= 75: return 1  # 70-75: Technical Only
        elif score < 85: return 2   # 76-84: News Only
        else: return 3              # 85+: News + Gemini

    def should_call_api(self, coin: str, current_ts: str, current_tier: int) -> bool:
        if coin not in self.api_cache: return True
        
        cache = self.api_cache[coin]
        # Rule 1: New Candle
        if cache['candle_ts'] != current_ts: return True
        # Rule 2: 30 minutes passed
        if (time.time() - cache['last_call_time']) >= 1800: return True
        # Rule 3: Tier Upgraded
        if current_tier > cache['tier']: return True
        
        return False

    def run_cycle(self, live_data: dict):
        logger.info("⚡ Running Custom Tiered Market Scan (70-75 Tech | 76-84 News | 85+ Gemini)...")
        tech_results = self.tech_engine.analyze_market(live_data)

        for coin, data in tech_results.items():
            df = live_data.get(coin)
            if df is None or df.empty: continue
            
            score = data["technical_score"]
            direction = data["direction"]
            candle_ts = str(df.iloc[-1]['timestamp'])
            tier = self.get_tier(score)

            if score < 70:
                continue # Skip processing below 70

            # Smart Cache Check
            if not self.should_call_api(coin, candle_ts, tier):
                continue

            signal_type = None
            trade_action = None
            
            try:
                # ---------------------------------------------------------
                # SCORE 70-75: Technical Signal Only (No API Calls)
                # ---------------------------------------------------------
                if 70 <= score <= 75:
                    signal_type = "🟡 Technical Signal"
                    trade_action = "BUY" if direction == "BULLISH" else "SELL"

                # ---------------------------------------------------------
                # SCORE 76-84: Trigger News API Only
                # ---------------------------------------------------------
                elif 76 <= score < 85:
                    news = self.news_engine.fetch_news_sentiment(coin)
                    news_sentiment = news["sentiment"]
                    
                    if news_sentiment == "NEUTRAL" or not news.get("context"):
                        signal_type = "🟡 Technical Signal"
                        trade_action = "BUY" if direction == "BULLISH" else "SELL"
                    else:
                        tech_bullish = (direction == "BULLISH")
                        news_bullish = (news_sentiment == "BULLISH")
                        
                        if tech_bullish != news_bullish and news_sentiment != "MIXED":
                            logger.info(f"⚠️ {coin}: Technical and News disagree. Skipping trade.")
                            continue
                        
                        signal_type = "🟠 Confirmed by News"
                        trade_action = "BUY" if direction == "BULLISH" else "SELL"

                # ---------------------------------------------------------
                # SCORE 85-100: Trigger News -> If Positive -> Trigger Gemini
                # ---------------------------------------------------------
                elif score >= 85:
                    news = self.news_engine.fetch_news_sentiment(coin)
                    news_sentiment = news["sentiment"]
                    
                    if news_sentiment == "NEUTRAL" or not news.get("context"):
                        signal_type = "🟡 Technical Signal"
                        trade_action = "BUY" if direction == "BULLISH" else "SELL"
                    else:
                        tech_bullish = (direction == "BULLISH")
                        news_bullish = (news_sentiment == "BULLISH")
                        
                        if tech_bullish != news_bullish and news_sentiment != "MIXED":
                            logger.info(f"⚠️ {coin}: Technical and News disagree. Skipping trade.")
                            continue
                        
                        # News is Positive, calling Gemini!
                        ai_data = self.ai_engine.evaluate_signal(coin, data, news)
                        ai_action = ai_data.get("action", "WAIT")
                        ai_status = ai_data.get("status", "SUCCESS") 

                        if ai_status == "ERROR":
                            signal_type = "🟠 Confirmed by News (AI Fallback)"
                            trade_action = "BUY" if direction == "BULLISH" else "SELL"
                        elif ai_action in ["BUY", "SELL"]:
                            signal_type = "🟢 Strong Signal"
                            trade_action = ai_action
                        else:
                            logger.info(f"🛡️ {coin}: AI returned WAIT. Standing aside.")
                            continue

            except Exception as e:
                # Backup System: Total API Failure -> Technical Fallback
                logger.error(f"🛑 API Error on {coin}: {e}. Falling back to Technical.")
                signal_type = "🟡 Technical Signal (Fallback)"
                trade_action = "BUY" if direction == "BULLISH" else "SELL"

            if signal_type and trade_action:
                self.broadcast(coin, signal_type, trade_action, score, data["trigger_reasons"])
            
            # Update Cache
            self.api_cache[coin] = {
                "candle_ts": candle_ts,
                "last_call_time": time.time(),
                "tier": tier
            }

    def broadcast(self, coin, sig_type, action, score, triggers):
        logger.info(f"🚀 {sig_type} | {coin} | {action} | {score}")
        bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not bot_token: return

        emoji = "🟢 <b>BUY (লং)</b>" if action == "BUY" else "🔴 <b>SELL (শর্ট)</b>"
        msg = f"🚀 <b>{sig_type}</b> 🚀\n\n🪙 <b>Asset:</b> #{coin}\n🎯 <b>Action:</b> {emoji}\n📊 <b>Score:</b> {score}/100\n⚡ <b>Triggers:</b> {', '.join(triggers)}"
        
        try:
            requests.post(f"https://api.telegram.org/bot{bot_token}/sendMessage", json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
        except: pass

if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    bot = MasterSignalBot(os.getenv("NEWS_API_KEY", ""), os.getenv("CRYPTOCOMPARE_API_KEY", ""), os.getenv("GEMINI_API_KEY", ""))
    fetcher = KuCoinFetcher()
    target_coins = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]
    
    while True:
        try:
            bot.run_cycle(fetcher.fetch_live_data(target_coins))
            time.sleep(30) 
        except:
            time.sleep(30)
