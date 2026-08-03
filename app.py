import time
import logging
import requests
import os
from typing import Dict

# Importing the engines we built
from technical_engine import TechnicalEngine
from news_engine import NewsEngine
from ai_engine import GeminiAIEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("BG_STAR_PRO_Master")

class MasterSignalBot:
    def __init__(self, news_api_key: str, gemini_api_key: str):
        self.tech_engine = TechnicalEngine()
        self.news_engine = NewsEngine(news_api_key)
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
        live_market_data: dict of DataFrames for the 6 coins.
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
                # No trigger? No API. Check if it's a valid backup Technical Signal
                if score >= 75:
                    signal_type = "🟡 Technical Signal"
                    final_signal = direction
                else:
                    continue # Ignore completely (Score < 75, No Trigger)
            else:
                # ----------------------------------------------------
                # STAGE 3: NEWS API TRIGGER
                # ----------------------------------------------------
                news_data = self.news_engine.fetch_news_sentiment(coin)
                
                if news_data["sentiment"] == "NEUTRAL":
                    # News Neutral -> Stop API Funnel -> Send Technical Signal
                    signal_type = "🟡 Technical Signal"
                    final_signal = direction
                else:
                    # News is Bullish or Bearish -> Moving to Gemini
                    # ----------------------------------------------------
                    # STAGE 4: GEMINI AI CONFIRMATION
                    # ----------------------------------------------------
                    ai_data = self.ai_engine.evaluate_signal(coin, tech_data, news_data)
                    
                    if ai_data["action"] == "WAIT":
                        # AI failed or says wait -> Downgrade to News Confirmed
                        signal_type = "🟠 Confirmed by News"
                        final_signal = news_data["sentiment"] # Bullish/Bearish
                    else:
                        # ALL ALIGNED! Technical + News + AI
                        signal_type = "🟢 Strong Signal"
                        final_signal = ai_data["action"] # BUY/SELL

            # ----------------------------------------------------
            # STAGE 5: DUPLICATE PROTECTION & BROADCAST
            # ----------------------------------------------------
            if final_signal:
                # Check Duplicate Logic
                if self.is_duplicate_signal(coin, score, final_signal, triggers):
                    logger.info(f"🛡️ {coin} Signal Blocked by Duplicate Protection (Score {score}).")
                    continue

                # Broadcast Signal (Telegram & Console)
                self.broadcast_signal(coin, signal_type, final_signal, score, triggers)
                
                # Update State
                self.signal_history[coin] = {
                    "direction": final_signal,
                    "score": score,
                    "triggers": triggers
                }
                
                # Apply Candle Cooldown (Rule 5: After sending, skip candle)
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
            logger.warning("⚠️ Telegram Token or Chat ID is missing in environment variables! Signal not sent to Telegram.")


# ==========================================
# USAGE EXAMPLE (MOCK)
# ==========================================
if __name__ == "__main__":
    import pandas as pd
    
    # Initialize the Bot with environment variables
    news_key = os.getenv("NEWS_API_KEY", "DEMO_NEWS")
    gemini_key = os.getenv("GEMINI_API_KEY", "DEMO_GEMINI")
    
    bot = MasterSignalBot(news_api_key=news_key, gemini_api_key=gemini_key)
    
    # Mock Market Data for iteration
    mock_market_data = {
        "BTC": pd.DataFrame(), 
        "ETH": pd.DataFrame()
    }
    
    current_timestamp = int(time.time()) 
    # bot.run_cycle(mock_market_data, current_timestamp)
