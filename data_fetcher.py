"""
Market data fetcher for Binance - DCA Day Trading
Version: 1.0.0
"""

import pandas as pd
import numpy as np
import logging
import time
import json
import hashlib
from typing import Optional, List, Dict, Any
from datetime import datetime
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# Binance imports
try:
    from binance.client import Client as BinanceClient
    from binance.exceptions import BinanceAPIException, BinanceRequestException
    BINANCE_AVAILABLE = True
except ImportError:
    BINANCE_AVAILABLE = False
    logging.warning("Binance Python library not installed")

from settings import config

logger = logging.getLogger(__name__)
data_logger = logging.getLogger("data_fetcher")

EMOJI = {
    "START": "🚀",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "DEBUG": "🔍",
    "CACHE": "💾",
    "FETCH": "📊",
    "RETRY": "🔄",
}


class DataFetcher:
    """Handles data fetching from Binance with caching."""

    def __init__(self, demo_mode: Optional[bool] = None):
        self.demo_mode = demo_mode if demo_mode is not None else False
        self.cache = {}
        self.cache_ttl = config.performance.cache_ttl_seconds
        self.cache_timestamps = {}
   

        self.client = None
        if not self.demo_mode and BINANCE_AVAILABLE:
            self._init_binance_client()

        data_logger.info(f"{EMOJI['START']} DataFetcher initialized (demo: {self.demo_mode})")

    def _init_binance_client(self):
        try:
            self.client = BinanceClient(
                api_key=config.binance.api_key,
                api_secret=config.binance.api_secret,
                testnet=config.binance.testnet,
                requests_params={'timeout': config.binance.request_timeout}
            )
            self.client.ping()
            data_logger.info(f"{EMOJI['SUCCESS']} Binance client initialized")
        except Exception as e:
            data_logger.error(f"{EMOJI['ERROR']} Failed to initialize Binance client: {e}")
            self.client = None

    def fetch_klines(self, symbol: str, interval: str, limit: int,
                     use_cache: bool = True) -> Optional[pd.DataFrame]:
        """Fetch historical klines data."""
        cache_key = f"{symbol}_{interval}_{limit}"

        if use_cache and cache_key in self.cache:
            if time.time() - self.cache_timestamps[cache_key] < self.cache_ttl:
                data_logger.debug(f"{EMOJI['CACHE']} Cache hit for {symbol}")
                return self.cache[cache_key]

        try:
            if self.demo_mode or not self.client:
                df = self._fetch_demo_klines(symbol, interval, limit)
            else:
                df = self._fetch_live_klines(symbol, interval, limit)

            if df is not None and not df.empty:
                if use_cache:
                    self.cache[cache_key] = df
                    self.cache_timestamps[cache_key] = time.time()
                return df

            return None

        except Exception as e:
            data_logger.error(f"{EMOJI['ERROR']} Failed to fetch {symbol}: {e}")
            return None

    def _fetch_live_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        if not self.client:
            return None

        max_retries = config.performance.max_retries
        for attempt in range(max_retries):
            try:
                raw_klines = self.client.get_historical_klines(
                    symbol=symbol,
                    interval=interval,
                    limit=limit
                )
                if raw_klines:
                    return self._convert_klines_to_dataframe(raw_klines)

            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(config.performance.retry_delay_seconds * (attempt + 1))
                else:
                    data_logger.error(f"{EMOJI['ERROR']} Failed after {max_retries} retries: {e}")

        return None

    def _fetch_demo_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        base_price = self._get_base_price(symbol)
        np.random.seed(hash(symbol) % 2**32)

        end_time = datetime.now()
        interval_minutes = self._interval_to_minutes(interval)
        timestamps = pd.date_range(
            end=end_time,
            periods=limit,
            freq=f"{interval_minutes}min"
        )

        returns = np.random.normal(0.0002, 0.005, limit)
        price = base_price * np.exp(np.cumsum(returns))

        df = pd.DataFrame({
            'open_time': timestamps,
            'open': price * (1 + np.random.uniform(-0.001, 0.001, limit)),
            'high': price * (1 + np.abs(np.random.uniform(0, 0.01, limit))),
            'low': price * (1 - np.abs(np.random.uniform(0, 0.01, limit))),
            'close': price,
            'volume': np.random.exponential(100, limit) * base_price / 10000
        })

        df['high'] = df[['open', 'high', 'close']].max(axis=1)
        df['low'] = df[['open', 'low', 'close']].min(axis=1)
        df.set_index('open_time', inplace=True)

        return df

    def _convert_klines_to_dataframe(self, raw_klines: List) -> pd.DataFrame:
        df = pd.DataFrame(raw_klines)
        df.columns = [
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ]
        df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']].copy()
        numeric_cols = ['open', 'high', 'low', 'close', 'volume']
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df.set_index('open_time', inplace=True)
        df.sort_index(inplace=True)
        return df

    def _interval_to_minutes(self, interval: str) -> int:
        interval_map = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360,
            '8h': 480, '12h': 720, '1d': 1440
        }
        return interval_map.get(interval, 15)

    def _get_base_price(self, symbol: str) -> float:
        base_prices = {
            'BTCUSDT': 45000.0, 'ETHUSDT': 3000.0, 'BNBUSDT': 600.0,
            'SOLUSDT': 120.0, 'XRPUSDT': 0.60, 'ADAUSDT': 0.40,
            'DOGEUSDT': 0.08, 'AVAXUSDT': 40.0, 'DOTUSDT': 8.0,
            'TRXUSDT': 0.08, 'LTCUSDT': 80.0, 'UNIUSDT': 8.0,
        }
        return base_prices.get(symbol, 100.0)

    def fetch_multiple(self, symbols: List[str], interval: str, limit: int) -> Dict[str, pd.DataFrame]:
        results = {}
        with ThreadPoolExecutor(max_workers=min(len(symbols), 10)) as executor:
            future_to_symbol = {
                executor.submit(self.fetch_klines, symbol, interval, limit): symbol
                for symbol in symbols
            }
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result(timeout=30)
                    if result is not None:
                        results[symbol] = result
                except Exception as e:
                    data_logger.error(f"{EMOJI['ERROR']} Failed to fetch {symbol}: {e}")
        return results

    def cleanup(self):
        self.cache.clear()
        data_logger.info(f"{EMOJI['SUCCESS']} DataFetcher cleanup complete")


data_fetcher = DataFetcher()

__all__ = ["data_fetcher", "DataFetcher"]
