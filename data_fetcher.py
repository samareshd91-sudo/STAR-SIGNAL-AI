import ccxt
import pandas as pd
import logging
import time

logger = logging.getLogger("BG_STAR_PRO_DataFetcher")

class KuCoinFetcher:
    def __init__(self):
        # Initialize KuCoin exchange via CCXT
        self.exchange = ccxt.kucoin({'enableRateLimit': True})
        
    def fetch_live_data(self, coins: list, timeframe: str = '15m', limit: int = 100) -> dict:
        """
        KuCoin থেকে নির্দিষ্ট কয়েনগুলোর রিয়েল-টাইম OHLCV (ক্যান্ডেল) ডেটা আনবে।
        """
        market_data = {}
        
        for coin in coins:
            symbol = f"{coin}/USDT"
            try:
                # Fetching Open, High, Low, Close, Volume data
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                
                # Converting to Pandas DataFrame for the Technical Engine
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                market_data[coin] = df
                logger.info(f"✅ Successfully fetched {len(df)} candles for {symbol}")
                
                # API Rate limit safe pause
                time.sleep(0.5) 
                
            except Exception as e:
                logger.error(f"🛑 Error fetching data for {symbol}: {e}")
                
        return market_data
