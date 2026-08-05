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

# ==========================================
# 🌐 PROFESSIONAL DASHBOARD UI
# ==========================================
class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        html_dashboard = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta http-equiv="refresh" content="60">
            <title>BG STAR PRO - Active Dashboard</title>
            <style>
                body {
                    background-color: #0f172a;
                    color: #e2e8f0;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                }
                .dashboard {
                    background: #1e293b;
                    padding: 40px;
                    border-radius: 15px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                    text-align: center;
                    max-width: 500px;
                    width: 90%;
                    border: 1px solid #334155;
                }
                h1 { color: #38bdf8; margin-bottom: 5px; font-size: 28px; }
                p.subtitle { color: #94a3b8; margin-bottom: 25px; font-size: 14px; }
                .status {
                    display: inline-block;
                    padding: 8px 20px;
                    background: #059669;
                    color: white;
                    border-radius: 25px;
                    font-weight: bold;
                    font-size: 14px;
                    margin-bottom: 25px;
                    animation: pulse 2s infinite;
                    box-shadow: 0 0 15px rgba(5, 150, 105, 0.4);
                }
                .info-grid {
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 15px;
                    text-align: left;
                }
                .info-box {
                    background: #0f172a;
                    padding: 15px;
                    border-radius: 10px;
                    border: 1px solid #334155;
                }
                .info-box span { display: block; font-size: 12px; color: #94a3b8; margin-bottom: 5px; }
                .info-box strong { color: #f8fafc; font-size: 16px; }
                @keyframes pulse {
                    0% { box-shadow: 0 0 0 0 rgba(5, 150, 105, 0.7); }
                    70% { box-shadow: 0 0 0 10px rgba(5, 150, 105, 0); }
                    100% { box-shadow: 0 0 0 0 rgba(5, 150, 105, 0); }
                }
                .footer { margin-top: 30px; font-size: 12px; color: #64748b; }
            </style>
        </head>
        <body>
            <div class="dashboard">
                <h1>🚀 BG STAR PRO</h1>
                <p class="subtitle">Advanced SMC & AI Algorithmic Trading Bot</p>
                <div class="status">🟢 SYSTEM ONLINE & SCANNING</div>
                <div class="info-grid">
                    <div class="info-box"><span>⚡ Scan Interval</span><strong>30 Seconds</strong></div>
                    <div class="info-box"><span>📰 News Engine</span><strong>Live RSS (Free)</strong></div>
                    <div class="info-box"><span>🎯 Target Assets</span><strong>BTC, ETH, BNB, SOL, XRP, DOGE</strong></div>
                    <div class="info-box"><span>🤖 AI Engine</span><strong>Gemini Pro (Smart Call)</strong></div>
                </div>
                <div class="footer">Dashboard auto-refreshes every 60 seconds.<br>Running securely on Render.</div>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html_dashboard.encode('utf-8'))

def run_dashboard_server():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(('0.0.0.0', port), DashboardHandler).serve_forever()
# ==========================================

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
        
        # Simple Cache System to prevent spamming
        self.api_cache = {}

    def run_cycle(self, live_data: dict):
        logger.info("⚡ Running Unified Market Scan (Score 70+ -> Free News -> Smart Gemini)...")
        tech_results = self.tech_engine.analyze_market(live_data)

        for coin, data in tech_results.items():
            df = live_data.get(coin)
            if df is None or df.empty: continue
            
            score = data["technical_score"]
            direction = data["direction"]
            candle_ts = str(df.iloc[-1]['timestamp'])

            if score < 70:
                continue 

            # 🛡️ Cache Check: Prevent sending the same signal repeatedly in the same 15m candle
            if coin in self.api_cache:
                cache = self.api_cache[coin]
                if cache['candle_ts'] == candle_ts and (time.time() - cache['last_call_time']) < 1800:
                    continue

            signal_type = None
            trade_action = None
            
            try:
                # ---------------------------------------------------------
                # 1. ALWAYS Call News (Since RSS is 100% Free & Unlimited)
                # ---------------------------------------------------------
                news = self.news_engine.fetch_news_sentiment(coin)
                news_sentiment = news["sentiment"]
                
                tech_bullish = (direction == "BULLISH")
                news_bullish = (news_sentiment == "BULLISH")
                tech_bearish = (direction == "BEARISH")
                news_bearish = (news_sentiment == "BEARISH")
                
                if news_sentiment == "NEUTRAL" or not news.get("context"):
                    # No active news -> Just send Technical Signal
                    signal_type = "🟡 Technical Signal"
                    trade_action = "BUY" if tech_bullish else "SELL"
                else:
                    # ---------------------------------------------------------
                    # 2. Check Alignment & Call Gemini
                    # ---------------------------------------------------------
                    if (tech_bullish and news_bearish) or (tech_bearish and news_bullish):
                        logger.info(f"⚠️ {coin}: Technical ({direction}) and News ({news_sentiment}) disagree. Skipping trade.")
                        continue
                    
                    # News matches Technical! Now call Gemini to confirm
                    logger.info(f"🔥 {coin}: News aligns with Technical! Calling Gemini AI...")
                    ai_data = self.ai_engine.evaluate_signal(coin, data, news)
                    ai_action = ai_data.get("action", "WAIT")
                    ai_status = ai_data.get("status", "SUCCESS") 

                    if ai_status == "ERROR":
                        signal_type = "🟠 Confirmed by News (AI Fallback)"
                        trade_action = "BUY" if tech_bullish else "SELL"
                    elif ai_action in ["BUY", "SELL"]:
                        signal_type = "🟢 Strong Signal"
                        trade_action = ai_action
                    else:
                        logger.info(f"🛡️ {coin}: AI returned WAIT. Standing aside.")
                        continue

            except Exception as e:
                # Backup System
                logger.error(f"🛑 API Error on {coin}: {e}. Falling back to Technical.")
                signal_type = "🟡 Technical Signal (Fallback)"
                trade_action = "BUY" if direction == "BULLISH" else "SELL"

            if signal_type and trade_action:
                self.broadcast(coin, signal_type, trade_action, score, data["trigger_reasons"])
                # Save to cache so it doesn't spam
                self.api_cache[coin] = {
                    "candle_ts": candle_ts,
                    "last_call_time": time.time()
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
    threading.Thread(target=run_dashboard_server, daemon=True).start()
    bot = MasterSignalBot(os.getenv("NEWS_API_KEY", ""), os.getenv("CRYPTOCOMPARE_API_KEY", ""), os.getenv("GEMINI_API_KEY", ""))
    fetcher = KuCoinFetcher()
    target_coins = ["BTC", "ETH", "BNB", "SOL", "XRP", "DOGE"]
    
    while True:
        try:
            bot.run_cycle(fetcher.fetch_live_data(target_coins))
            time.sleep(30) 
        except:
            time.sleep(30)
