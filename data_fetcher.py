"""
Market data fetcher for Binance - DCA Day Trading
Version: 1.1.0 - Enhanced with better error handling, retry logic, and data validation
"""

import pandas as pd
import numpy as np
import logging
import time
import json
import hashlib
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

# Binance imports
try:
    from binance.client import Client as BinanceClient
    from binance.exceptions import BinanceAPIException, BinanceRequestException, BinanceOrderException
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
    "RATE_LIMIT": "⏱️",
    "VALID": "✔️",
}


class DataFetcher:
    """
    Handles data fetching from Binance with caching, retry logic, and validation.
    Version: 1.1.0
    """

    def __init__(self, demo_mode: Optional[bool] = None):
        self.demo_mode = demo_mode if demo_mode is not None else config.is_demo()
        self.cache = {}
        self.cache_ttl = config.performance.cache_ttl_seconds
        self.cache_timestamps = {}
        self.cache_hits = 0
        self.cache_misses = 0
        self.total_requests = 0
        self.failed_requests = 0

        self.client = None
        self._last_request_time = 0
        self._min_request_interval = 0.1  # 100ms minimum between requests

        if not self.demo_mode and BINANCE_AVAILABLE:
            self._init_binance_client()

        data_logger.info(f"{EMOJI['START']} DataFetcher initialized (demo: {self.demo_mode})")

    def _init_binance_client(self):
        """Initialize Binance client with proper error handling."""
        try:
            self.client = BinanceClient(
                api_key=config.binance.api_key,
                api_secret=config.binance.api_secret,
                testnet=config.binance.testnet,
                requests_params={'timeout': config.binance.request_timeout}
            )
            # Test connection
            self.client.ping()
            data_logger.info(f"{EMOJI['SUCCESS']} Binance client initialized")

            # Get exchange info for validation
            self._exchange_info = self.client.get_exchange_info()
            data_logger.info(f"{EMOJI['INFO']} Exchange info loaded")

        except Exception as e:
            data_logger.error(f"{EMOJI['ERROR']} Failed to initialize Binance client: {e}")
            self.client = None
            self._exchange_info = None

    def _rate_limit(self):
        """Apply rate limiting to avoid hitting API limits."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._min_request_interval:
            time.sleep(self._min_request_interval - time_since_last)
        self._last_request_time = time.time()

    def fetch_klines(self, symbol: str, interval: str, limit: int,
                     use_cache: bool = True, validate: bool = True) -> Optional[pd.DataFrame]:
        """
        Fetch historical klines data with caching and validation.

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Timeframe interval (e.g., '1h', '4h', '15m')
            limit: Number of candles to fetch
            use_cache: Whether to use cached data
            validate: Whether to validate the data

        Returns:
            DataFrame with OHLCV data or None if fetch fails
        """
        self.total_requests += 1

        cache_key = f"{symbol}_{interval}_{limit}"

        # Check cache
        if use_cache and cache_key in self.cache:
            if time.time() - self.cache_timestamps[cache_key] < self.cache_ttl:
                self.cache_hits += 1
                data_logger.debug(f"{EMOJI['CACHE']} Cache hit for {symbol} ({interval})")
                return self.cache[cache_key].copy()
            else:
                self.cache_misses += 1
                data_logger.debug(f"{EMOJI['CACHE']} Cache expired for {symbol} ({interval})")

        try:
            # Apply rate limiting
            self._rate_limit()

            # Fetch data
            if self.demo_mode or not self.client:
                df = self._fetch_demo_klines(symbol, interval, limit)
            else:
                df = self._fetch_live_klines(symbol, interval, limit)

            # Validate data
            if df is not None and not df.empty and validate:
                if self._validate_dataframe(df, symbol, interval):
                    if use_cache:
                        self.cache[cache_key] = df.copy()
                        self.cache_timestamps[cache_key] = time.time()
                    return df
                else:
                    data_logger.warning(f"{EMOJI['WARNING']} Data validation failed for {symbol}")
                    self.failed_requests += 1
                    return None

            if df is not None and not df.empty:
                if use_cache:
                    self.cache[cache_key] = df.copy()
                    self.cache_timestamps[cache_key] = time.time()
                return df

            self.failed_requests += 1
            return None

        except Exception as e:
            data_logger.error(f"{EMOJI['ERROR']} Failed to fetch {symbol}: {e}")
            self.failed_requests += 1
            return None

    def _fetch_live_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """Fetch live klines from Binance with retry logic."""
        if not self.client:
            return None

        max_retries = config.performance.max_retries
        retry_delay = config.performance.retry_delay_seconds

        for attempt in range(max_retries):
            try:
                data_logger.debug(f"{EMOJI['FETCH']} Fetching {symbol} {interval} (attempt {attempt+1}/{max_retries})")

                raw_klines = None

                # Try get_klines first (more reliable for Spot API)
                if hasattr(self.client, 'get_klines'):
                    try:
                        raw_klines = self.client.get_klines(
                            symbol=symbol,
                            interval=interval,
                            limit=limit
                        )
                    except (BinanceAPIException, BinanceRequestException) as e:
                        if 'rate limit' in str(e).lower():
                            data_logger.warning(f"{EMOJI['RATE_LIMIT']} Rate limit hit for {symbol}")
                            wait_time = retry_delay * (attempt + 1) * 2
                            data_logger.info(f"{EMOJI['RETRY']} Waiting {wait_time}s before retry")
                            time.sleep(wait_time)
                            continue
                        data_logger.debug(f"get_klines failed: {e}")

                # Fallback to get_historical_klines
                if raw_klines is None and hasattr(self.client, 'get_historical_klines'):
                    try:
                        raw_klines = self.client.get_historical_klines(
                            symbol=symbol,
                            interval=interval,
                            limit=limit
                        )
                    except (BinanceAPIException, BinanceRequestException) as e:
                        data_logger.debug(f"get_historical_klines failed: {e}")

                if raw_klines:
                    df = self._convert_klines_to_dataframe(raw_klines)
                    if df is not None and not df.empty:
                        data_logger.debug(f"{EMOJI['SUCCESS']} Fetched {len(df)} candles for {symbol}")
                        return df

            except Exception as e:
                data_logger.warning(f"Attempt {attempt+1}/{max_retries} failed for {symbol}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                else:
                    data_logger.error(f"{EMOJI['ERROR']} Failed after {max_retries} retries: {e}")

        return None

    def _fetch_demo_klines(self, symbol: str, interval: str, limit: int) -> Optional[pd.DataFrame]:
        """Generate demo klines for testing."""
        try:
            base_price = self._get_base_price(symbol)
            np.random.seed(hash(symbol) % 2**32)

            end_time = datetime.now()
            interval_minutes = self._interval_to_minutes(interval)

            # Generate realistic price movement
            timestamps = pd.date_range(
                end=end_time,
                periods=limit,
                freq=f"{interval_minutes}min"
            )

            # Brownian motion with drift and volatility
            drift = 0.0001  # slight upward drift
            volatility = 0.005  # 0.5% volatility
            returns = np.random.normal(drift, volatility, limit)
            price = base_price * np.exp(np.cumsum(returns))

            # Add some trends and patterns
            trend_pattern = np.sin(np.linspace(0, 4*np.pi, limit)) * 0.02 * base_price
            price = price + trend_pattern

            # Generate OHLC data
            df = pd.DataFrame({
                'open_time': timestamps,
                'open': price * (1 + np.random.uniform(-0.001, 0.001, limit)),
                'high': price * (1 + np.abs(np.random.uniform(0, 0.01, limit))),
                'low': price * (1 - np.abs(np.random.uniform(0, 0.01, limit))),
                'close': price,
                'volume': np.random.exponential(100, limit) * base_price / 10000
            })

            # Ensure high is max and low is min
            df['high'] = df[['open', 'high', 'close']].max(axis=1)
            df['low'] = df[['open', 'low', 'close']].min(axis=1)
            df.set_index('open_time', inplace=True)

            data_logger.debug(f"{EMOJI['FETCH']} Generated {len(df)} demo candles for {symbol}")
            return df

        except Exception as e:
            data_logger.error(f"Error generating demo data: {e}")
            return None

    def _convert_klines_to_dataframe(self, raw_klines: List) -> pd.DataFrame:
        """Convert raw klines data to DataFrame."""
        if not raw_klines:
            return pd.DataFrame()

        try:
            df = pd.DataFrame(raw_klines)

            # Handle different response formats
            if len(df.columns) >= 6:
                df.columns = [
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_asset_volume', 'number_of_trades',
                    'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
                ][:len(df.columns)]

            # Keep only essential columns
            keep_cols = ['open_time', 'open', 'high', 'low', 'close', 'volume']
            df = df[[col for col in keep_cols if col in df.columns]].copy()

            # Convert to numeric
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            # Convert time
            if 'open_time' in df.columns:
                df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
                df.set_index('open_time', inplace=True)

            df.sort_index(inplace=True)

            # Remove any rows with NaN values
            df = df.dropna()

            return df

        except Exception as e:
            data_logger.error(f"Error converting klines: {e}")
            return pd.DataFrame()

    def _validate_dataframe(self, df: pd.DataFrame, symbol: str, interval: str) -> bool:
        """Validate the DataFrame for data quality."""
        if df.empty:
            data_logger.warning(f"{EMOJI['WARNING']} Empty DataFrame for {symbol}")
            return False

        # Check required columns
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            data_logger.warning(f"{EMOJI['WARNING']} Missing columns for {symbol}: {missing_cols}")
            return False

        # Check for NaN values
        if df[required_cols].isna().any().any():
            data_logger.warning(f"{EMOJI['WARNING']} NaN values detected for {symbol}")
            return False

        # Check for valid price relationships
        invalid_rows = (df['high'] < df['low']) | (df['high'] < df['open']) | (df['high'] < df['close'])
        if invalid_rows.any():
            data_logger.warning(f"{EMOJI['WARNING']} Invalid price relationships for {symbol}")
            return False

        # Check for zero or negative prices
        if (df[['open', 'high', 'low', 'close']] <= 0).any().any():
            data_logger.warning(f"{EMOJI['WARNING']} Zero or negative prices for {symbol}")
            return False

        # Check volume is non-negative
        if (df['volume'] < 0).any():
            data_logger.warning(f"{EMOJI['WARNING']} Negative volume for {symbol}")
            return False

        data_logger.debug(f"{EMOJI['VALID']} Data validated for {symbol} ({len(df)} candles)")
        return True

    def _interval_to_minutes(self, interval: str) -> int:
        """Convert interval string to minutes."""
        interval_map = {
            '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
            '1h': 60, '2h': 120, '4h': 240, '6h': 360,
            '8h': 480, '12h': 720, '1d': 1440, '1w': 10080,
        }
        return interval_map.get(interval, 15)

    def _get_base_price(self, symbol: str) -> float:
        """Get base price for demo data generation."""
        base_prices = {
            'BTCUSDT': 45000.0, 'ETHUSDT': 3000.0, 'BNBUSDT': 600.0,
            'SOLUSDT': 120.0, 'XRPUSDT': 0.60, 'ADAUSDT': 0.40,
            'DOGEUSDT': 0.08, 'AVAXUSDT': 40.0, 'DOTUSDT': 8.0,
            'TRXUSDT': 0.08, 'LTCUSDT': 80.0, 'UNIUSDT': 8.0,
            'LINKUSDT': 15.0, 'MATICUSDT': 1.0, 'ATOMUSDT': 10.0,
        }
        return base_prices.get(symbol, 100.0)

    def fetch_multiple(self, symbols: List[str], interval: str, limit: int,
                       max_workers: int = 10) -> Dict[str, pd.DataFrame]:
        """
        Fetch data for multiple symbols in parallel.

        Args:
            symbols: List of symbols to fetch
            interval: Timeframe interval
            limit: Number of candles per symbol
            max_workers: Maximum number of parallel workers

        Returns:
            Dictionary of symbol -> DataFrame
        """
        results = {}

        if not symbols:
            return results

        with ThreadPoolExecutor(max_workers=min(len(symbols), max_workers)) as executor:
            future_to_symbol = {
                executor.submit(self.fetch_klines, symbol, interval, limit): symbol
                for symbol in symbols
            }

            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    result = future.result(timeout=30)
                    if result is not None and not result.empty:
                        results[symbol] = result
                        data_logger.debug(f"{EMOJI['SUCCESS']} Fetched {symbol} ({len(result)} candles)")
                    else:
                        data_logger.warning(f"{EMOJI['WARNING']} No data for {symbol}")
                except Exception as e:
                    data_logger.error(f"{EMOJI['ERROR']} Failed to fetch {symbol}: {e}")
                    self.failed_requests += 1

        data_logger.info(f"{EMOJI['FETCH']} Fetched {len(results)}/{len(symbols)} symbols")
        return results

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "cache_size": len(self.cache),
            "total_requests": self.total_requests,
            "failed_requests": self.failed_requests,
            "success_rate": ((self.total_requests - self.failed_requests) / self.total_requests * 100) if self.total_requests > 0 else 0,
        }

    def clear_cache(self, symbol: Optional[str] = None):
        """Clear cache for a specific symbol or all symbols."""
        if symbol:
            keys_to_remove = [k for k in self.cache.keys() if k.startswith(symbol)]
            for key in keys_to_remove:
                del self.cache[key]
                if key in self.cache_timestamps:
                    del self.cache_timestamps[key]
            data_logger.info(f"{EMOJI['CACHE']} Cleared cache for {symbol}")
        else:
            self.cache.clear()
            self.cache_timestamps.clear()
            data_logger.info(f"{EMOJI['CACHE']} Cleared all cache")

    def get_available_intervals(self) -> List[str]:
        """Get list of available interval strings."""
        return [
            '1m', '3m', '5m', '15m', '30m',
            '1h', '2h', '4h', '6h', '8h', '12h',
            '1d', '1w'
        ]

    def validate_symbol(self, symbol: str) -> bool:
        """Validate if a symbol exists on Binance."""
        if not self.client:
            return True  # Skip validation in demo mode

        try:
            self._rate_limit()
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return ticker is not None
        except Exception:
            return False

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Get the latest price for a symbol."""
        try:
            self._rate_limit()
            if self.client:
                ticker = self.client.get_symbol_ticker(symbol=symbol)
                if ticker:
                    return float(ticker['price'])

            # Fallback: fetch last kline
            df = self.fetch_klines(symbol, '1m', 1, use_cache=False, validate=False)
            if df is not None and not df.empty:
                return float(df['close'].iloc[-1])
            return None
        except Exception as e:
            data_logger.debug(f"Error getting price for {symbol}: {e}")
            return None

    def get_24hr_stats(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get 24-hour statistics for a symbol."""
        if not self.client:
            return None

        try:
            self._rate_limit()
            stats = self.client.get_24hr_ticker(symbol=symbol)
            return {
                'symbol': stats.get('symbol'),
                'price_change': float(stats.get('priceChange', 0)),
                'price_change_percent': float(stats.get('priceChangePercent', 0)),
                'weighted_avg_price': float(stats.get('weightedAvgPrice', 0)),
                'last_price': float(stats.get('lastPrice', 0)),
                'volume': float(stats.get('volume', 0)),
                'quote_volume': float(stats.get('quoteVolume', 0)),
                'high': float(stats.get('highPrice', 0)),
                'low': float(stats.get('lowPrice', 0)),
                'count': int(stats.get('count', 0)),
            }
        except Exception as e:
            data_logger.debug(f"Error getting 24hr stats for {symbol}: {e}")
            return None

    def cleanup(self):
        """Clean up resources."""
        self.cache.clear()
        self.cache_timestamps.clear()
        data_logger.info(f"{EMOJI['SUCCESS']} DataFetcher cleanup complete")
        data_logger.info(f"{EMOJI['INFO']} Cache stats: {self.get_cache_stats()}")


# Singleton instance
data_fetcher = DataFetcher()

__all__ = ["data_fetcher", "DataFetcher"]
