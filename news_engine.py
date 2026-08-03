import requests
import logging
import time

logger = logging.getLogger("BG_STAR_PRO_NewsEngine")

class NewsEngine:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # Example endpoint - will be replaced by your actual news provider
        self.endpoint = "https://financialmodelingprep.com/api/v3/stock_news" 
        self.timeout = 5.0  # Strict timeout for crash protection

    def fetch_news_sentiment(self, coin: str) -> dict:
        """
        Stage 3 Execution: Fetches recent news and analyzes sentiment.
        Returns: BULLISH, BEARISH, or NEUTRAL.
        """
        logger.info(f"📰 Smart Trigger received for {coin}. Calling News API...")
        
        fallback_response = {"sentiment": "NEUTRAL", "reason": "No impactful news or API unavailable."}

        # Emergency Fallback System: Protects against API Limit, Timeout, or Internet drop
        try:
            # Assuming 'BTC' needs to be mapped to crypto news search, standardizing query
            query = f"{coin} crypto"
            
            # Simulated API call (replace with actual API parameters)
            response = requests.get(
                self.endpoint, 
                params={"tickers": coin, "limit": 3, "apikey": self.api_key},
                timeout=self.timeout
            )

            # Check for Rate Limits (429) or Server Errors (5xx)
            if response.status_code == 429:
                logger.warning("⚠️ News API Rate Limit Reached! Switching to Technical Fallback.")
                return fallback_response
            elif response.status_code != 200:
                logger.error(f"⚠️ News API Error {response.status_code}. Switching to Technical Fallback.")
                return fallback_response

            data = response.json()
            
            if not data:
                return fallback_response

            # Mock Sentiment Logic: In production, API usually provides a sentiment score
            # Here we simulate evaluating the sentiment from API response
            bullish_count = 0
            bearish_count = 0
            
            for article in data:
                sentiment = article.get("sentiment", "Neutral").upper()
                if sentiment == "BULLISH": bullish_count += 1
                elif sentiment == "BEARISH": bearish_count += 1

            if bullish_count > bearish_count:
                return {"sentiment": "BULLISH", "reason": "Positive macro/news catalysts detected."}
            elif bearish_count > bullish_count:
                return {"sentiment": "BEARISH", "reason": "Negative macro/news catalysts detected."}
            else:
                return {"sentiment": "NEUTRAL", "reason": "News is neutral or mixed. Holding back AI."}

        except requests.exceptions.Timeout:
            logger.error("🛑 News API Timeout. Switching to Technical Fallback.")
            return fallback_response
        except requests.exceptions.ConnectionError:
            logger.error("🛑 Internet Connection Error. Switching to Technical Fallback.")
            return fallback_response
        except Exception as e:
            logger.error(f"🛑 Unexpected News API Error: {e}. Switching to Technical Fallback.")
            return fallback_response

# Usage in Main App Loop:
# if tech_data["is_triggered"]:
#     news_data = news_engine.fetch_news_sentiment(tech_data["coin"])
#     if news_data["sentiment"] in ["BULLISH", "BEARISH"]:
#         # Proceed to Gemini
#     else:
#         # Send Technical Signal, STOP API funnel here

