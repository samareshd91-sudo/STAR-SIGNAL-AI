import requests
import logging

logger = logging.getLogger("BG_STAR_PRO_News")

class NewsEngine:
    def __init__(self, news_api_key: str, cryptocompare_api_key: str):
        self.news_api_key = news_api_key
        self.cryptocompare_key = cryptocompare_api_key

    def fetch_news_sentiment(self, coin: str) -> dict:
        headlines = []
        
        # 1. Try CryptoCompare First
        if self.cryptocompare_key:
            headlines = self._fetch_from_cryptocompare(coin)
            
        # 2. Fallback to News API
        if not headlines and self.news_api_key:
            headlines = self._fetch_from_newsapi(coin)
            
        if not headlines:
            return {"sentiment": "NEUTRAL", "context": "No relevant news found."}
            
        text_context = " | ".join(headlines).lower()
        
        bull_words = ['surge', 'jump', 'partner', 'launch', 'bull', 'breakout', 'adopt', 'buy', 'growth']
        bear_words = ['hack', 'crash', 'ban', 'lawsuit', 'sec', 'bear', 'drop', 'scam', 'sell', 'illegal']
        
        bull_count = sum(1 for word in bull_words if word in text_context)
        bear_count = sum(1 for word in bear_words if word in text_context)
        
        if bull_count > bear_count: sentiment = "BULLISH"
        elif bear_count > bull_count: sentiment = "BEARISH"
        else: sentiment = "NEUTRAL"
            
        return {
            "sentiment": sentiment,
            "context": text_context[:200]
        }

    def _fetch_from_cryptocompare(self, coin: str) -> list:
        try:
            url = f"https://min-api.cryptocompare.com/data/v2/news/?categories={coin}&api_key={self.cryptocompare_key}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                raw_data = data.get('Data', [])
                if isinstance(raw_data, list):
                    return [item.get('title', '') for item in raw_data[:5] if isinstance(item, dict)]
        except Exception as e:
            logger.error(f"CryptoCompare API Error: {e}")
        return []

    def _fetch_from_newsapi(self, coin: str) -> list:
        try:
            url = f"https://newsapi.org/v2/everything?q={coin} crypto&language=en&sortBy=publishedAt&apiKey={self.news_api_key}"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                articles = data.get('articles', [])
                if isinstance(articles, list):
                    return [item.get('title', '') for item in articles[:5] if isinstance(item, dict)]
        except Exception as e:
            logger.error(f"NewsAPI Error: {e}")
        return []
