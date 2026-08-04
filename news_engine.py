import requests
import logging

logger = logging.getLogger("BG_STAR_PRO_News")

class NewsEngine:
    def __init__(self, news_api_key: str, cryptocompare_api_key: str):
        self.news_api_key = news_api_key
        self.cryptocompare_key = cryptocompare_api_key

    def fetch_news_sentiment(self, coin: str) -> dict:
        """
        Fetch news using Dual-API Fallback Strategy.
        """
        headlines = []
        
        # 1. Primary API: Try CryptoCompare First
        if self.cryptocompare_key:
            logger.info(f"🌐 Fetching news for {coin} via CryptoCompare...")
            headlines = self._fetch_from_cryptocompare(coin)
            
        # 2. Secondary API: Fallback to News API if CryptoCompare fails or is empty
        if not headlines and self.news_api_key:
            logger.warning(f"⚠️ CryptoCompare failed or empty for {coin}. Switching to News API...")
            headlines = self._fetch_from_newsapi(coin)
            
        # 3. If both fail or no news available
        if not headlines:
            logger.info(f"📉 No news found for {coin} from both APIs.")
            return {"sentiment": "NEUTRAL", "context": "No relevant news found."}
            
        # 4. Pre-filter Strategy (Save Gemini API Cost)
        # We do a quick keyword scan to drop 'Neutral' news before calling Gemini
        text_context = " | ".join(headlines).lower()
        
        bull_words = ['surge', 'jump', 'partner', 'launch', 'bull', 'breakout', 'adopt', 'buy', 'growth']
        bear_words = ['hack', 'crash', 'ban', 'lawsuit', 'sec', 'bear', 'drop', 'scam', 'sell', 'illegal']
        
        bull_count = sum(1 for word in bull_words if word in text_context)
        bear_count = sum(1 for word in bear_words if word in text_context)
        
        if bull_count == 0 and bear_count == 0:
            sentiment = "NEUTRAL"
        elif bull_count > bear_count:
            sentiment = "BULLISH"
        elif bear_count > bull_count:
            sentiment = "BEARISH"
        else:
            sentiment = "MIXED"
            
        return {
            "sentiment": sentiment,
            "context": " | ".join(headlines[:5]) # Send top 5 headlines to Gemini
        }

    def _fetch_from_cryptocompare(self, coin: str) -> list:
        try:
            url = f"https://min-api.cryptocompare.com/data/v2/news/?categories={coin}&api_key={self.cryptocompare_key}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                # Return top 5 news titles
                return [item['title'] for item in data.get('Data', [])[:5]]
        except Exception as e:
            logger.error(f"CryptoCompare API Error: {e}")
        return []

    def _fetch_from_newsapi(self, coin: str) -> list:
        try:
            url = f"https://newsapi.org/v2/everything?q={coin} crypto&language=en&sortBy=publishedAt&apiKey={self.news_api_key}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                # Return top 5 news titles
                return [item['title'] for item in data.get('articles', [])[:5]]
        except Exception as e:
            logger.error(f"NewsAPI Error: {e}")
        return []
