import time
import logging
import requests
import os
import ccxt
import pandas as pd
from typing import Dict

# Importing the engines we built
from technical_engine import TechnicalEngine
from news_engine import NewsEngine
from ai_engine import GeminiAIEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("BG_STAR_PRO_Master")


# ==========================================
# 📡 LIVE DATA FETCHER (KUCOIN)
# ==========================================
class KuCoinFetcher:
    def __init__(self):
        # KuCoin API initialization (No API Key needed for basic market data)
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
                time.sleep(0.5) # Rate limit safety
            except Exception as e:
                logger.error(f"🛑 Error fetching data for {symbol}: {e}")
        return market_data


# ==========================================
# 🧠 MASTER SIGNAL BOT
# ==========================================
class MasterSignalBot:
    def __init__(self, news_api_key: str, cryptocompare_api_key: str, gemini_api_key: str):
        self.tech_engine = TechnicalEngine()
        # দুটি News API Key একসাথে পাঠানো হচ্ছে NewsEngine-এ
        self.news_engine = NewsEngine(news_api_key, cryptocompare_api_key)
        self.ai_engine = GeminiAIEngine(gemini_api_key)
        
        # State Management for Cooldown and Duplicate Protection
        self.signal_history: Dict[str, dict] = {}
        self.last_candle_time: Dict[str, int] = {}

    def is_duplicate_signal(self, coin: str, current_score: int, direction: str, triggers: list) -> bool:
        """
        Advanced Duplicate Protection (Strictly follows Blueprint):
        Blocks signal if: Same Direction AND Score is ±3 AND Triggers are same.
        """
        if coin not in self.signal_history:
            return False
            
        prev = self.signal_history[coin]
        
        same_direction = prev["direction"] == direction
        score_diff_small = abs(prev["score"] - current_score) <= 3
        same_triggers = sorted(prev["triggers"]) == sorted(triggers)

        if same_direction and score_diff_small and same_triggers:
            return True
            
        return False

    def run_cycle(self, live_market_data: dict, current_candle_timestamp: int):
        """
        Main Event Loop. Runs every minute or candle close.
        live_market_data: dict of DataFrames for the target coins.
        """
        logger.info("=========================================")
        logger.info("🔍 STAGE 1: Running Technical Scan...")
        
        # 1. Technical Analysis (Zero API Cost)
        tech_results = self.tech_engine.analyze_market(live_market_data)

        for coin, tech_data in tech_results.items():
            
            # API Cooldown Rule: Skip if we already checked this specific candle
            if self.last_candle_time.get(coin) == current_candle_timestamp:
                continue

            score = tech_data["technical_score"]
            direction = tech_data["direction"]
            triggers = tech_data["trigger_reasons"]
            is_triggered = tech_data["is_triggered"]

            # Initialize final signal state
            final_signal = None
            signal_type = "NO TRADE"

            # ----------------------------------------------------
            # STAGE 2: SMART TRIGGER EVALUATION
            # ----------------------------------------------------
            if not is_triggered:
                if score >= 75:
                    signal_type = "🟡 Technical Signal"
                    final_signal = direction
                else:
                    continue 
            else:
                # ----------------------------------------------------
                # STAGE 3: NEWS API TRIGGER (Dual API Enabled)
                # ----------------------------------------------------
                news_data = self.news_engine.fetch_news_sentiment(coin)
                
                if news_data["sentiment"] == "NEUTRAL":
                    signal_type = "🟡 Technical Signal"
                    final_signal = direction
                else:
                    # ----------------------------------------------------
                    # STAGE 4: GEMINI AI CONFIRMATION
                    # ----------------------------------------------------
                    ai_data = self.ai_engine.evaluate_signal(coin, tech_data, news_data)
                    
                    if ai_data["action"] == "WAIT":
                        signal_type = "🟠 Confirmed by News"
                        final_signal = news_data["sentiment"] 
                    else:
                        signal_type = "🟢 Strong Signal"
                        final_signal = ai_data["action"] 

            # ----------------------------------------------------
            # STAGE 5: DUPLICATE PROTECTION & BROADCAST
            # ----------------------------------------------------
            if final_signal:
                if self.is_duplicate_signal(coin, score, final_signal, triggers):
                    logger.info(f"🛡️ {coin} Signal Blocked by Duplicate Protection (Score {score}).")
                    continue

                # Broadcast Signal (Telegram & Console)
                self.broadcast_signal(coin, signal_type, final_signal, score, triggers)
                
                self.signal_history[coin] = {
                    "direction": final_signal,
                    "score": score,
                    "triggers": triggers
                }
                self.last_candle_time[coin] = current_candle_timestamp

    def broadcast_signal(self, coin: str, signal_type: str, action: str, score: int, triggers: list):
        """
        Sends the final structured alert to Telegram & logs to console.
        """
        # 1. Console Log
        logger.info(f"\n🚀 {signal_type} DETECTED! 🚀")
        logger.info(f"Asset: {coin}")
        logger.info(f"Action: {action}")
        logger.info(f"Technical Score: {score}/100")
        logger.info(f"Active Triggers: {', '.join(triggers)}")
        logger.info("-----------------------------------------\n")

        # 2. Telegram Alert System
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
            payload = {
                "chat_id": chat_id,
                "text": tg_message,
                "parse_mode": "Markdown"
            }

            try:
                response = requests.post(url, json=payload, timeout=5)
                if response.status_code == 200:
                    logger.info("✅ Telegram Alert Sent Successfully!")
                else:
                    logger.error(f"❌ Telegram Error: {response.text}")
            except Exception as e:
                logger.error(f"🛑 Telegram Delivery Failed: {e}")
        else:
            logger.warning("⚠️ Telegram Token or Chat ID is missing! Signal not sent to Telegram.")


# ==========================================
# 🚀 MAIN EXECUTION LOOP (রিয়েল-টাইম রানার)
# ==========================================
if __name__ == "__main__":
    # API Keys Load (Now includes CryptoCompare)
    news_key = os.getenv("NEWS_API_KEY", "")
    cryptocompare_key = os.getenv("CRYPTOCOMPARE_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    
    # Initialize the Engines with all 3 keys
    bot = MasterSignalBot(
        news_api_key=news_key, 
        cryptocompare_api_key=cryptocompare_key, 
        gemini_api_key=gemini_key
    )
    fetcher = KuCoinFetcher()
    
    # আপনার পছন্দের ৬টি কয়েন
    target_coins = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]
    
    logger.info("🔥 BG STAR PRO Backend Started. Waiting for live market data...")
    
    # ইনফিনিট লুপ (বট ২৪ ঘণ্টা চলতে থাকবে)
    while True:
        try:
            # ১. KuCoin থেকে আসল ক্যান্ডেল ডেটা আনা
            live_data = fetcher.fetch_live_data(target_coins, timeframe='15m')
            
            # ২. ডেটাগুলো মাস্টার বটের কাছে পাঠানো স্ক্যানিংয়ের জন্য
            current_timestamp = int(time.time()) 
            bot.run_cycle(live_data, current_timestamp)
            
            # ৩. স্ক্যান শেষে ৫ মিনিট অপেক্ষা করা (যাতে API ব্যান না হয়)
            logger.info("⏳ Cycle complete. Waiting 5 minutes for the next market scan...\n")
            time.sleep(300) 
            
        except Exception as e:
            logger.error(f"🛑 Critical System Error in Main Loop: {e}")
            time.sleep(60) # কোনো ইন্টারনেট সমস্যা হলে ১ মিনিট পর আবার চেষ্টা করবে
