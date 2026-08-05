import feedparser
import logging
import re

logger = logging.getLogger("BG_STAR_PRO_NewsEngine")

class NewsEngine:
    def __init__(self, news_api_key=None, cryptocompare_api_key=None):
        # API Keys আর দরকার নেই, কিন্তু app.py যাতে ক্র্যাশ না করে তাই এগুলো রাখা হলো
        self.rss_feeds = [
            "https://cointelegraph.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://cryptoslate.com/feed/"
        ]
        
        # কয়েনের নামের ম্যাপিং যাতে খবর সহজে খুঁজে পায়
        self.coin_map = {
            "BTC": ["BTC", "Bitcoin"],
            "ETH": ["ETH", "Ethereum"],
            "BNB": ["BNB", "Binance"],
            "SOL": ["SOL", "Solana"],
            "XRP": ["XRP", "Ripple"],
            "DOGE": ["DOGE", "Dogecoin"]
        }
        
        # সেন্টিমেন্ট অ্যানালিসিস কিওয়ার্ডস
        self.bullish_words = ['surge', 'jump', 'high', 'adopt', 'partner', 'launch', 'upgrade', 'buy', 'bull', 'positive', 'growth', 'gain', 'soar', 'record', 'approve', 'breakout']
        self.bearish_words = ['crash', 'drop', 'fall', 'hack', 'scam', 'ban', 'illegal', 'sell', 'bear', 'negative', 'lawsuit', 'plunge', 'delay', 'reject', 'investigation', 'dump']

    def fetch_news_sentiment(self, coin: str) -> dict:
        try:
            logger.info(f"📰 Fetching Live RSS news for {coin}...")
            search_terms = self.coin_map.get(coin, [coin])
            
            relevant_news = []
            bullish_score = 0
            bearish_score = 0
            
            # সবগুলো RSS ফিড থেকে লেটেস্ট খবর আনা
            for feed_url in self.rss_feeds:
                feed = feedparser.parse(feed_url)
                
                # প্রতিটি সাইটের লেটেস্ট ১৫টি খবর চেক করা
                for entry in feed.entries[:15]: 
                    title = entry.get('title', '')
                    summary = entry.get('summary', '')
                    text_to_check = (title + " " + summary).lower()
                    
                    # খবরটিতে আমাদের কাঙ্ক্ষিত কয়েনের নাম আছে কিনা চেক করা
                    is_relevant = any(re.search(rf'\b{term.lower()}\b', text_to_check) for term in search_terms)
                    
                    if is_relevant:
                        relevant_news.append(title)
                        
                        # বুলিশ এবং বেয়ারিশ কিওয়ার্ড ম্যাচিং করে পয়েন্ট দেওয়া
                        for word in self.bullish_words:
                            if re.search(rf'\b{word}\b', text_to_check): bullish_score += 1
                        for word in self.bearish_words:
                            if re.search(rf'\b{word}\b', text_to_check): bearish_score += 1
                            
            if not relevant_news:
                logger.info(f"📰 No recent news found for {coin}. Returning NEUTRAL.")
                return {"sentiment": "NEUTRAL", "context": ""}
                
            # ফাইনাল সেন্টিমেন্ট নির্ধারণ করা
            if bullish_score > bearish_score + 1:
                sentiment = "BULLISH"
            elif bearish_score > bullish_score + 1:
                sentiment = "BEARISH"
            elif bullish_score > 0 or bearish_score > 0:
                sentiment = "MIXED"
            else:
                sentiment = "NEUTRAL"
                
            # জেমিনি এআই-এর জন্য লেটেস্ট ৩টি খবরের শিরোনাম একসাথে জুড়ে দেওয়া
            context = " | ".join(relevant_news[:3]) 
            
            logger.info(f"📰 RSS Sentiment for {coin}: {sentiment} (Bull: {bullish_score}, Bear: {bearish_score})")
            return {"sentiment": sentiment, "context": context}
            
        except Exception as e:
            logger.error(f"🛑 RSS Feed Error for {coin}: {e}")
            return {"sentiment": "NEUTRAL", "context": ""}
