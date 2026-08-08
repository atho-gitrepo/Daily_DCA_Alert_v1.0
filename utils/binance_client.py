"""
Binance API Client for DCA Day Trading
Handles all exchange interactions with proper error handling and rate limiting
Version: 1.0.0
"""

import logging
import time
import hmac
import hashlib
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from urllib.parse import urlencode
import requests
import pandas as pd

from settings import config

logger = logging.getLogger(__name__)

EMOJI = {
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "FETCH": "📊",
    "RETRY": "🔄",
    "RATE": "⏱️",
}


class BinanceAPIError(Exception):
    """Custom exception for Binance API errors."""
    pass


class BinanceClient:
    """
    Binance API client with proper error handling, rate limiting, and retries.
    Supports both Spot and Futures markets.
    """

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None,
                 testnet: bool = True, market_type: str = "futures"):
        """
        Initialize Binance client.

        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: Use testnet or mainnet
            market_type: "spot" or "futures"
        """
        self.api_key = api_key or config.binance.api_key
        self.api_secret = api_secret or config.binance.api_secret
        self.testnet = testnet if testnet is not None else config.binance.testnet
        self.market_type = market_type.lower()

        # Set base URLs
        self.base_url = self._get_base_url()
        self.base_websocket = self._get_websocket_url()

        # Rate limiting
        self.request_count = 0
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms minimum between requests

        # Session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'DCA-Trading-Bot/1.0'
        })

        if self.api_key:
            self.session.headers.update({
                'X-MBX-APIKEY': self.api_key
            })

        self.logger = logging.getLogger("binance_client")

        # Initialize
        self._init_client()

    def _get_base_url(self) -> str:
        """Get base URL for API endpoints."""
        if self.testnet:
            if self.market_type == "futures":
                return "https://testnet.binancefuture.com"
            else:
                return "https://testnet.binance.vision"
        else:
            if self.market_type == "futures":
                return "https://fapi.binance.com"
            else:
                return "https://api.binance.com"

    def _get_websocket_url(self) -> str:
        """Get WebSocket URL."""
        if self.testnet:
            if self.market_type == "futures":
                return "wss://stream.binancefuture.com"
            else:
                return "wss://testnet.binance.vision"
        else:
            if self.market_type == "futures":
                return "wss://fstream.binance.com"
            else:
                return "wss://stream.binance.com:9443"

    def _init_client(self):
        """Initialize client and test connection."""
        try:
            # Test connection
            self.ping()
            self.logger.info(f"{EMOJI['SUCCESS']} Binance {self.market_type} client initialized")
            self.logger.info(f"{EMOJI['INFO']} Mode: {'TESTNET' if self.testnet else 'MAINNET'}")

            if self.api_key and self.api_secret:
                # Test authentication
                account_info = self.get_account_info()
                self.logger.info(f"{EMOJI['SUCCESS']} Authentication successful")
                self.logger.info(f"{EMOJI['INFO']} Account: {account_info.get('canTrade', 'Unknown')}")
            else:
                self.logger.warning(f"{EMOJI['WARNING']} API keys not set - read-only mode")

        except Exception as e:
            self.logger.error(f"{EMOJI['ERROR']} Failed to initialize client: {e}")
            raise

    def _rate_limit(self):
        """Apply rate limiting."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        self.last_request_time = time.time()
        self.request_count += 1

    def _sign_request(self, params: Dict) -> Dict:
        """Sign request with HMAC SHA256."""
        if not self.api_secret:
            raise BinanceAPIError("API secret not configured")

        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        params['signature'] = signature
        return params

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                 signed: bool = False, retries: int = 3) -> Dict:
        """
        Make an API request with retries.

        Args:
            method: HTTP method (GET, POST, DELETE, PUT)
            endpoint: API endpoint
            params: Request parameters
            signed: Whether request needs signing
            retries: Number of retry attempts

        Returns:
            API response as dict
        """
        url = f"{self.base_url}{endpoint}"

        for attempt in range(retries):
            try:
                self._rate_limit()

                if signed:
                    if params is None:
                        params = {}
                    params['timestamp'] = int(time.time() * 1000)
                    params = self._sign_request(params)

                response = self.session.request(
                    method=method,
                    url=url,
                    params=params if method == 'GET' else None,
                    json=params if method != 'GET' and params else None,
                    timeout=30
                )

                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 10))
                    self.logger.warning(f"{EMOJI['RATE']} Rate limit hit. Waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue

                if response.status_code == 418:
                    self.logger.error(f"{EMOJI['ERROR']} IP banned!")
                    raise BinanceAPIError("IP banned")

                if response.status_code != 200:
                    error_data = response.json() if response.text else {}
                    error_msg = error_data.get('msg', response.text)
                    self.logger.error(f"API error: {response.status_code} - {error_msg}")
                    raise BinanceAPIError(f"API error {response.status_code}: {error_msg}")

                data = response.json()

                # Check for error in response
                if isinstance(data, dict) and data.get('code') and data['code'] != 200:
                    error_msg = data.get('msg', 'Unknown error')
                    self.logger.error(f"API error: {data['code']} - {error_msg}")
                    raise BinanceAPIError(f"API error {data['code']}: {error_msg}")

                return data

            except requests.exceptions.RequestException as e:
                self.logger.warning(f"Request error (attempt {attempt+1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    raise BinanceAPIError(f"Request failed after {retries} attempts: {e}")
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                if attempt < retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

    # ==================== PUBLIC ENDPOINTS ====================

    def ping(self) -> bool:
        """Test connectivity to API."""
        try:
            response = self._request('GET', '/fapi/v1/ping' if self.market_type == 'futures' else '/api/v3/ping')
            self.logger.debug("Ping successful")
            return True
        except Exception as e:
            self.logger.error(f"Ping failed: {e}")
            return False

    def get_server_time(self) -> int:
        """Get server time."""
        try:
            endpoint = '/fapi/v1/time' if self.market_type == 'futures' else '/api/v3/time'
            response = self._request('GET', endpoint)
            return response.get('serverTime', 0)
        except Exception as e:
            self.logger.error(f"Failed to get server time: {e}")
            return int(time.time() * 1000)

    def get_exchange_info(self) -> Dict:
        """Get exchange information."""
        try:
            endpoint = '/fapi/v1/exchangeInfo' if self.market_type == 'futures' else '/api/v3/exchangeInfo'
            return self._request('GET', endpoint)
        except Exception as e:
            self.logger.error(f"Failed to get exchange info: {e}")
            return {}

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            endpoint = '/fapi/v1/ticker/price' if self.market_type == 'futures' else '/api/v3/ticker/price'
            response = self._request('GET', endpoint, params={'symbol': symbol})
            return float(response.get('price', 0))
        except Exception as e:
            self.logger.error(f"Failed to get price for {symbol}: {e}")
            return None

    def get_24hr_ticker(self, symbol: str) -> Dict:
        """Get 24hr ticker statistics."""
        try:
            endpoint = '/fapi/v1/ticker/24hr' if self.market_type == 'futures' else '/api/v3/ticker/24hr'
            response = self._request('GET', endpoint, params={'symbol': symbol})
            return {
                'symbol': response.get('symbol'),
                'priceChange': float(response.get('priceChange', 0)),
                'priceChangePercent': float(response.get('priceChangePercent', 0)),
                'weightedAvgPrice': float(response.get('weightedAvgPrice', 0)),
                'prevClosePrice': float(response.get('prevClosePrice', 0)),
                'lastPrice': float(response.get('lastPrice', 0)),
                'bidPrice': float(response.get('bidPrice', 0)),
                'askPrice': float(response.get('askPrice', 0)),
                'volume': float(response.get('volume', 0)),
                'quoteVolume': float(response.get('quoteVolume', 0)),
                'highPrice': float(response.get('highPrice', 0)),
                'lowPrice': float(response.get('lowPrice', 0)),
                'count': int(response.get('count', 0)),
            }
        except Exception as e:
            self.logger.error(f"Failed to get 24hr ticker for {symbol}: {e}")
            return {}

    def get_historical_klines(self, symbol: str, interval: str,
                              limit: int = 500, start_time: Optional[int] = None,
                              end_time: Optional[int] = None) -> pd.DataFrame:
        """
        Get historical klines/candlesticks.

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Timeframe ('1m', '5m', '15m', '1h', '4h', '1d', etc.)
            limit: Number of candles (max 1500)
            start_time: Start time in milliseconds
            end_time: End time in milliseconds

        Returns:
            DataFrame with OHLCV data
        """
        try:
            params = {
                'symbol': symbol,
                'interval': interval,
                'limit': limit
            }
            if start_time:
                params['startTime'] = start_time
            if end_time:
                params['endTime'] = end_time

            endpoint = '/fapi/v1/klines' if self.market_type == 'futures' else '/api/v3/klines'
            data = self._request('GET', endpoint, params=params)

            if not data:
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])

            # Keep only needed columns
            df = df[['open_time', 'open', 'high', 'low', 'close', 'volume']].copy()

            # Convert to numeric
            numeric_cols = ['open', 'high', 'low', 'close', 'volume']
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)

            # Convert time
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df.set_index('open_time', inplace=True)
            df.sort_index(inplace=True)

            return df

        except Exception as e:
            self.logger.error(f"Failed to get klines for {symbol}: {e}")
            return pd.DataFrame()

    def get_order_book(self, symbol: str, limit: int = 100) -> Dict:
        """Get order book depth."""
        try:
            endpoint = '/fapi/v1/depth' if self.market_type == 'futures' else '/api/v3/depth'
            response = self._request('GET', endpoint, params={'symbol': symbol, 'limit': limit})
            return {
                'bids': [[float(x[0]), float(x[1])] for x in response.get('bids', [])],
                'asks': [[float(x[0]), float(x[1])] for x in response.get('asks', [])],
                'lastUpdateId': response.get('lastUpdateId', 0),
            }
        except Exception as e:
            self.logger.error(f"Failed to get order book for {symbol}: {e}")
            return {}

    # ==================== PRIVATE ENDPOINTS ====================

    def get_account_info(self) -> Dict:
        """Get account information."""
        if not self.api_key or not self.api_secret:
            return {'canTrade': False, 'balances': []}

        try:
            endpoint = '/fapi/v1/account' if self.market_type == 'futures' else '/api/v3/account'
            response = self._request('GET', endpoint, signed=True)
            return response
        except Exception as e:
            self.logger.error(f"Failed to get account info: {e}")
            return {'canTrade': False, 'balances': []}

    def get_balance(self, asset: Optional[str] = None) -> Dict:
        """Get account balance."""
        try:
            account = self.get_account_info()
            balances = account.get('balances', [])

            if asset:
                for balance in balances:
                    if balance.get('asset') == asset:
                        return {
                            'asset': asset,
                            'free': float(balance.get('free', 0)),
                            'locked': float(balance.get('locked', 0)),
                            'total': float(balance.get('free', 0)) + float(balance.get('locked', 0)),
                        }
                return {'asset': asset, 'free': 0, 'locked': 0, 'total': 0}

            result = {}
            for balance in balances:
                asset_name = balance.get('asset')
                free = float(balance.get('free', 0))
                locked = float(balance.get('locked', 0))
                if free > 0 or locked > 0:
                    result[asset_name] = {
                        'free': free,
                        'locked': locked,
                        'total': free + locked,
                    }
            return result

        except Exception as e:
            self.logger.error(f"Failed to get balance: {e}")
            return {}

    def create_order(self, symbol: str, side: str, order_type: str,
                     quantity: float, price: Optional[float] = None,
                     stop_price: Optional[float] = None,
                     reduce_only: bool = False) -> Dict:
        """
        Create a new order.

        Args:
            symbol: Trading pair
            side: 'BUY' or 'SELL'
            order_type: 'LIMIT', 'MARKET', 'STOP', 'STOP_MARKET', 'TAKE_PROFIT'
            quantity: Order quantity
            price: Limit price (for LIMIT orders)
            stop_price: Stop price (for STOP orders)
            reduce_only: Reduce only (futures)

        Returns:
            Order response
        """
        if not self.api_key or not self.api_secret:
            raise BinanceAPIError("API keys required for order creation")

        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
                'quantity': quantity,
            }

            if price:
                params['price'] = price

            if stop_price:
                params['stopPrice'] = stop_price

            if reduce_only and self.market_type == 'futures':
                params['reduceOnly'] = 'true'

            endpoint = '/fapi/v1/order' if self.market_type == 'futures' else '/api/v3/order'

            # Use POST for order creation
            response = self._request('POST', endpoint, params=params, signed=True)
            return response

        except Exception as e:
            self.logger.error(f"Failed to create order: {e}")
            raise

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open orders."""
        try:
            params = {}
            if symbol:
                params['symbol'] = symbol

            endpoint = '/fapi/v1/openOrders' if self.market_type == 'futures' else '/api/v3/openOrders'
            response = self._request('GET', endpoint, params=params, signed=True)
            return response if isinstance(response, list) else []

        except Exception as e:
            self.logger.error(f"Failed to get open orders: {e}")
            return []

    def cancel_order(self, symbol: str, order_id: Optional[int] = None) -> Dict:
        """Cancel an open order."""
        if not self.api_key or not self.api_secret:
            raise BinanceAPIError("API keys required")

        try:
            params = {'symbol': symbol}
            if order_id:
                params['orderId'] = order_id

            endpoint = '/fapi/v1/order' if self.market_type == 'futures' else '/api/v3/order'
            response = self._request('DELETE', endpoint, params=params, signed=True)
            return response

        except Exception as e:
            self.logger.error(f"Failed to cancel order: {e}")
            raise

    def cancel_all_orders(self, symbol: str) -> Dict:
        """Cancel all open orders for a symbol."""
        if not self.api_key or not self.api_secret:
            raise BinanceAPIError("API keys required")

        try:
            endpoint = '/fapi/v1/allOpenOrders' if self.market_type == 'futures' else '/api/v3/openOrders'
            response = self._request('DELETE', endpoint, params={'symbol': symbol}, signed=True)
            return response

        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            return {}

    # ==================== POSITION MANAGEMENT ====================

    def get_position_info(self, symbol: str) -> Dict:
        """Get position information for a symbol."""
        if not self.api_key or not self.api_secret:
            return {}

        try:
            account = self.get_account_info()
            positions = account.get('positions', [])

            for pos in positions:
                if pos.get('symbol') == symbol:
                    return {
                        'symbol': symbol,
                        'positionAmount': float(pos.get('positionAmt', 0)),
                        'entryPrice': float(pos.get('entryPrice', 0)),
                        'markPrice': float(pos.get('markPrice', 0)),
                        'unrealizedPnl': float(pos.get('unRealizedProfit', 0)),
                        'liquidationPrice': float(pos.get('liquidationPrice', 0)),
                        'leverage': int(pos.get('leverage', 1)),
                    }

            # No position found
            return {
                'symbol': symbol,
                'positionAmount': 0,
                'entryPrice': 0,
                'markPrice': 0,
                'unrealizedPnl': 0,
                'liquidationPrice': 0,
                'leverage': 1,
            }

        except Exception as e:
            self.logger.error(f"Failed to get position info for {symbol}: {e}")
            return {}

    def get_position_risk(self) -> List[Dict]:
        """Get position risk information."""
        if not self.api_key or not self.api_secret:
            return []

        try:
            endpoint = '/fapi/v2/positionRisk' if self.market_type == 'futures' else '/api/v3/account'
            response = self._request('GET', endpoint, signed=True)
            return response if isinstance(response, list) else []

        except Exception as e:
            self.logger.error(f"Failed to get position risk: {e}")
            return []

    def set_leverage(self, symbol: str, leverage: int) -> Dict:
        """Set leverage for a symbol (futures only)."""
        if self.market_type != 'futures':
            return {}

        if not self.api_key or not self.api_secret:
            raise BinanceAPIError("API keys required")

        try:
            params = {
                'symbol': symbol,
                'leverage': leverage,
            }
            response = self._request('POST', '/fapi/v1/leverage', params=params, signed=True)
            return response
        except Exception as e:
            self.logger.error(f"Failed to set leverage for {symbol}: {e}")
            return {}

    def get_all_prices(self, symbols: List[str]) -> Dict[str, float]:
        """Get prices for multiple symbols."""
        try:
            endpoint = '/fapi/v1/ticker/price' if self.market_type == 'futures' else '/api/v3/ticker/price'

            # If many symbols, fetch all and filter
            if len(symbols) > 10:
                response = self._request('GET', endpoint)
                prices = {}
                for item in response:
                    symbol = item.get('symbol')
                    if symbol in symbols:
                        prices[symbol] = float(item.get('price', 0))
                return prices
            else:
                # Fetch individually
                prices = {}
                for symbol in symbols:
                    price = self.get_current_price(symbol)
                    if price:
                        prices[symbol] = price
                return prices

        except Exception as e:
            self.logger.error(f"Failed to get all prices: {e}")
            return {}

    # ==================== UTILITY METHODS ====================

    def get_precision(self, symbol: str) -> Tuple[int, int]:
        """Get price and quantity precision for a symbol."""
        try:
            exchange_info = self.get_exchange_info()
            for info in exchange_info.get('symbols', []):
                if info.get('symbol') == symbol:
                    price_filter = next((f for f in info.get('filters', []) if f.get('filterType') == 'PRICE_FILTER'), {})
                    lot_size_filter = next((f for f in info.get('filters', []) if f.get('filterType') == 'LOT_SIZE'), {})

                    price_precision = len(str(price_filter.get('tickSize', '0.01')).rstrip('0').split('.')[-1]) if '.' in str(price_filter.get('tickSize', '0.01')) else 0
                    qty_precision = len(str(lot_size_filter.get('stepSize', '0.001')).rstrip('0').split('.')[-1]) if '.' in str(lot_size_filter.get('stepSize', '0.001')) else 0

                    return price_precision, qty_precision

            # Default precisions
            return 2, 3

        except Exception as e:
            self.logger.error(f"Failed to get precision for {symbol}: {e}")
            return 2, 3

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to the correct precision."""
        _, qty_precision = self.get_precision(symbol)
        return round(quantity, qty_precision)

    def round_price(self, symbol: str, price: float) -> float:
        """Round price to the correct precision."""
        price_precision, _ = self.get_precision(symbol)
        return round(price, price_precision)

    def is_valid_symbol(self, symbol: str) -> bool:
        """Check if symbol is valid."""
        try:
            exchange_info = self.get_exchange_info()
            symbols = [s.get('symbol') for s in exchange_info.get('symbols', [])]
            return symbol in symbols
        except Exception:
            return False

    def get_min_quantity(self, symbol: str) -> float:
        """Get minimum quantity for a symbol."""
        try:
            exchange_info = self.get_exchange_info()
            for info in exchange_info.get('symbols', []):
                if info.get('symbol') == symbol:
                    lot_size_filter = next((f for f in info.get('filters', []) if f.get('filterType') == 'LOT_SIZE'), {})
                    return float(lot_size_filter.get('minQty', 0.001))
            return 0.001
        except Exception:
            return 0.001

    # ==================== WEBSOCKET ====================

    def get_websocket_url(self, streams: List[str]) -> str:
        """Get WebSocket URL for streams."""
        if len(streams) > 1:
            stream_name = '/'.join(streams)
            return f"{self.base_websocket}/stream?streams={stream_name}"
        else:
            return f"{self.base_websocket}/ws/{streams[0]}"

    # ==================== CLEANUP ====================

    def close(self):
        """Close the client session."""
        if self.session:
            self.session.close()
            self.logger.info("Binance client closed")


__all__ = ["BinanceClient", "BinanceAPIError"]
