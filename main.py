#!/usr/bin/env python3
"""
DCA Day Trading Bot - Main Entry Point
Hybrid DCA Strategy with Multi-Timeframe Analysis & Signal Manager
Version: 1.0.0 - Signal Manager Integration
"""

import os
import sys
import time
import logging
import signal
import threading
from typing import Dict, Optional, Tuple, Any, List
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import traceback

import pandas as pd
import numpy as np

from settings import config
from data_fetcher import data_fetcher
from strategy.dca_hybrid_strategy import dca_strategy
from utils.telegram_bot import telegram_bot
from utils.mongodb_client import mongodb_client
from utils.signal_manager import signal_manager, SignalType, SignalPriority, SignalStatus, TradingSignal

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.logging.level),
    format=config.logging.format,
    handlers=[
        logging.FileHandler(config.logging.file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
main_logger = logging.getLogger("main")

EMOJI = {
    "START": "🚀",
    "STOP": "🛑",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "DCA": "📊",
    "ENTRY": "🎯",
    "EXIT": "🚪",
    "PROFIT": "💰",
    "LOSS": "💸",
    "BREAK": "⚖️",
    "CLOCK": "🕐",
    "TARGET": "🎯",
    "VOLUME": "📊",
    "BUY": "🟢",
    "SELL": "🔴",
    "TELEGRAM": "📨",
    "HEALTH": "💚",
    "SIGNAL": "📡",
    "LOCK": "🔒",
    "UNLOCK": "🔓",
    "PENDING": "⏳",
    "ACTIVE": "🔥",
    "REJECT": "🚫",
    "CACHE": "💾",
    "DB": "🍃",
    "HEARTBEAT": "💓",
    "SCAN": "🔄",
}

# Global state
running = True
bot_stats: Dict[str, Any] = {
    "status": "initializing",
    "start_time": datetime.now().isoformat(),
    "dca_entries": 0,
    "dca_exits": 0,
    "total_pnl": 0.0,
    "daily_pnl": 0.0,
    "active_positions": 0,
    "completed_trades": 0,
    "win_rate": 0.0,
    "errors": 0,
    "cycles_completed": 0,
    "wins": 0,
    "losses": 0,
    "signals_generated": 0,
    "signals_executed": 0,
    "signals_rejected": 0,
    "signals_expired": 0,
    "duplicate_signals_prevented": 0,
    "signal_outcomes": {
        "profitable": 0,
        "losing": 0,
        "break_even": 0,
        "active": 0,
        "total_pnl": 0.0,
    },
    "last_status_sent": None,
    "last_heartbeat": None,
    "last_price_time": None,
}

# ========== POSITION SIZE ==========
POSITION_SIZE_USD = config.dca.position_size_usd

# ========== SIGNAL CONFIGURATION ==========
MAX_PENDING_SIGNALS_PER_SYMBOL = 2
SIGNAL_EXPIRY_SECONDS = 120
SIGNAL_COOLDOWN_SECONDS = 60

# ========== STATUS REPORTING ==========
# Send status once per day at a specific time (e.g., 00:05 UTC)
STATUS_HOUR = 0  # Midnight UTC
STATUS_MINUTE = 5  # 5 minutes past midnight

# ========== HEARTBEAT CONFIGURATION ==========
# Log heartbeat every N cycles (~1 minute with 6 symbols at 10s interval)
HEARTBEAT_INTERVAL_CYCLES = 2

# ========== HELPER: JSON Serializer ==========
def json_serializer(obj):
    """Custom JSON serializer for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


# ==================== BINANCE CLIENT ====================

class BinanceDataClient:
    """Client for fetching data from Binance."""

    def __init__(self):
        self.api_key = config.binance.api_key
        self.api_secret = config.binance.api_secret
        self.is_testnet = config.binance.testnet
        base_url = "https://testnet.binancefuture.com" if self.is_testnet else "https://fapi.binance.com"
        self.futures_client = None
        self.spot_client = None
        self.client_type = "None"

        try:
            from binance.um_futures import UMFutures
            if self.api_key and self.api_secret:
                self.futures_client = UMFutures(key=self.api_key, secret=self.api_secret, base_url=base_url)
            else:
                self.futures_client = UMFutures(base_url=base_url)
            self.client_type = "Futures"
            main_logger.info(f"{EMOJI['SUCCESS']} Binance Futures client initialized")
        except ImportError:
            try:
                from binance.client import Client as BinanceSpotClient
                if self.api_key and self.api_secret:
                    self.spot_client = BinanceSpotClient(api_key=self.api_key, api_secret=self.api_secret, testnet=self.is_testnet)
                else:
                    self.spot_client = BinanceSpotClient()
                self.client_type = "Spot"
                main_logger.info(f"{EMOJI['SUCCESS']} Binance Spot client initialized")
            except ImportError:
                main_logger.warning(f"{EMOJI['WARNING']} Binance SDK not available")
                self.client_type = "DataFetcher"

        self.price_precisions = {symbol: 2 for symbol in config.market.symbols}

    def get_current_price(self, symbol: str) -> Optional[float]:
        try:
            if self.futures_client and hasattr(self.futures_client, 'ticker_price'):
                ticker = self.futures_client.ticker_price(symbol=symbol)
                return float(ticker['price'])
            if self.spot_client and hasattr(self.spot_client, 'get_symbol_ticker'):
                ticker = self.spot_client.get_symbol_ticker(symbol=symbol)
                return float(ticker['price'])
            df = data_fetcher.fetch_klines(symbol, config.market.timeframe, 1)
            if df is not None and not df.empty:
                return float(df['close'].iloc[-1])
            return None
        except Exception as e:
            main_logger.debug(f"Price fetch error for {symbol}: {e}")
            return None

    def get_historical_klines(self, symbol: str, interval: str = None, limit: int = 500) -> pd.DataFrame:
        interval = interval or config.market.timeframe
        try:
            if self.futures_client and hasattr(self.futures_client, 'klines'):
                klines = self.futures_client.klines(symbol=symbol, interval=interval, limit=limit)
                if klines:
                    return self._convert_klines_to_dataframe(klines)
            if self.spot_client and hasattr(self.spot_client, 'get_klines'):
                klines = self.spot_client.get_klines(symbol=symbol, interval=interval, limit=limit)
                if klines:
                    return self._convert_klines_to_dataframe(klines)
            result = data_fetcher.fetch_klines(symbol, interval, limit)
            if result is not None and not result.empty:
                return result
            return pd.DataFrame()
        except Exception as e:
            main_logger.debug(f"Klines fetch error for {symbol}: {e}")
            return pd.DataFrame()

    def _convert_klines_to_dataframe(self, raw_klines: List) -> pd.DataFrame:
        if not raw_klines:
            return pd.DataFrame()
        df = pd.DataFrame(raw_klines)
        if len(df.columns) >= 6:
            df.columns = ['open_time', 'open', 'high', 'low', 'close', 'volume'] + list(df.columns[6:])
        keep_cols = ['open_time', 'open', 'high', 'low', 'close', 'volume']
        df = df[[col for col in keep_cols if col in df.columns]].copy()
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        if 'open_time' in df.columns:
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df.set_index('open_time', inplace=True)
        df.sort_index(inplace=True)
        return df


# ==================== SIGNAL HELPER FUNCTIONS ====================

def can_generate_signal(symbol: str) -> Tuple[bool, str]:
    """Check if we can generate a new signal for a symbol."""
    if signal_manager.is_symbol_locked(symbol):
        return False, "Symbol already locked with active signal"

    pending = signal_manager.get_pending_signals(symbol)
    if len(pending) >= MAX_PENDING_SIGNALS_PER_SYMBOL:
        return False, f"Too many pending signals ({len(pending)})"

    recent_signals = signal_manager.get_recent_signals(symbol, seconds=SIGNAL_COOLDOWN_SECONDS)
    if recent_signals:
        return False, f"Cooldown active ({SIGNAL_COOLDOWN_SECONDS}s)"

    return True, "OK"


def create_dca_signal(symbol: str, signal_type: str, entry_price: float,
                      direction: str, confidence: float, dca_level: int,
                      stop_loss: float, market_context: Dict) -> Optional[TradingSignal]:

    signal_type_enum = SignalType.DCA_ENTRY if signal_type == "entry" else SignalType.DCA_EXIT

    if dca_level == 1:
        priority = SignalPriority.HIGH
    elif dca_level == dca_strategy.DCA_LEVELS:
        priority = SignalPriority.CRITICAL
    else:
        priority = SignalPriority.NORMAL

    signal = signal_manager.create_signal(
        symbol=symbol,
        signal_type=signal_type_enum,
        direction=direction,
        price=entry_price,
        quantity=POSITION_SIZE_USD / entry_price,
        priority=priority,
        dca_level=dca_level,
        stop_loss=stop_loss,
        confidence=confidence,
        reason=market_context.get('reason', ''),
        metadata={
            'market_context': market_context,
            'current_price': entry_price,
            'dca_level': dca_level,
            'total_dca_levels': dca_strategy.DCA_LEVELS,
            'htf_trend': market_context.get('htf_trend', 'NEUTRAL'),
            'mtf_trend': market_context.get('mtf_trend', 'NEUTRAL'),
            'ltf_trend': market_context.get('ltf_trend', 'NEUTRAL'),
            'tdi_level': market_context.get('tdi_level', 50),
            'tdi_zone': market_context.get('tdi_zone', 'NEUTRAL'),
            'bb_position': market_context.get('bb_position', 0.5),
            'direction_confidence': confidence,
        },
        expires_in_seconds=SIGNAL_EXPIRY_SECONDS
    )

    if signal:
        bot_stats['signals_generated'] += 1
        main_logger.info(
            f"{EMOJI['SIGNAL']} Signal created: {symbol} {direction} Level {dca_level} "
            f"@ ${entry_price:.4f} (ID: {signal.signal_id})"
        )

    return signal


# ==================== DCA PROCESSING ====================

def process_dca_symbol(symbol: str, client, state: Dict) -> Dict:
    """Process a symbol for DCA hybrid strategy with Signal Manager."""
    try:
        # ===== DEBUG: Starting processing =====
        main_logger.debug(f"🔍 Processing {symbol}...")

        # ===== 1. FETCH ALL TIMEFRAMES =====
        current_price = client.get_current_price(symbol)
        if current_price is None:
            main_logger.warning(f"⚠️ No price for {symbol}")
            return {"action": "none", "reason": "No price"}

        # Track that we got a price
        bot_stats['last_price_time'] = datetime.now()
        main_logger.debug(f"✅ {symbol} price: ${current_price:.2f}")

        # 4H data (HTF) - Reduced minimum required to 15 candles
        df_4h = client.get_historical_klines(symbol, interval="4h", limit=50)  # Reduced limit
        if df_4h.empty or len(df_4h) < 15:  # Changed from 30 to 15
            main_logger.warning(f"⚠️ Insufficient 4H data for {symbol}: {len(df_4h)} candles (need 15)")
            return {"action": "none", "reason": "Insufficient 4H data"}

        main_logger.debug(f"✅ {symbol} 4H data: {len(df_4h)} candles")

        # 1H data (MTF)
        df_1h = client.get_historical_klines(symbol, interval="1h", limit=100)
        if df_1h.empty or len(df_1h) < 20:
            main_logger.warning(f"⚠️ Insufficient 1H data for {symbol}: {len(df_1h)} candles (need 20)")
            return {"action": "none", "reason": "Insufficient 1H data"}

        main_logger.debug(f"✅ {symbol} 1H data: {len(df_1h)} candles")

        # 15M data (LTF)
        df_15m = client.get_historical_klines(symbol, interval="15m", limit=200)
        if df_15m.empty or len(df_15m) < 20:
            main_logger.warning(f"⚠️ Insufficient 15M data for {symbol}: {len(df_15m)} candles (need 20)")
            return {"action": "none", "reason": "Insufficient 15M data"}

        main_logger.debug(f"✅ {symbol} 15M data: {len(df_15m)} candles")

        # ===== 2. MULTI-TIMEFRAME ANALYSIS =====
        market_context = dca_strategy.analyze_multi_timeframe(
            df_4h, df_1h, df_15m, symbol
        )

        direction = market_context.get('direction', 'NEUTRAL')
        confidence = market_context.get('confidence', 0)
        htf_trend = market_context.get('htf_trend', 'NEUTRAL')
        mtf_trend = market_context.get('mtf_trend', 'NEUTRAL')
        ltf_trend = market_context.get('ltf_trend', 'NEUTRAL')
        tdi_level = market_context.get('tdi_level', 50)
        tdi_zone = market_context.get('tdi_zone', 'NEUTRAL')
        bb_position = market_context.get('bb_position', 0.5)

        # Log detailed signal analysis (ALWAYS show this)
        main_logger.info(
            f"{EMOJI['SCAN']} {symbol}: "
            f"Price=${current_price:.2f} | "
            f"Dir={direction} ({confidence*100:.0f}%) | "
            f"HTF={htf_trend} | MTF={mtf_trend} | LTF={ltf_trend} | "
            f"TDI={tdi_level:.0f} ({tdi_zone}) | BB={bb_position:.2f}"
        )

        # ===== 3. CHECK ACTIVE POSITION =====
        if symbol in dca_strategy.active_positions:
            exit_check = dca_strategy.check_exit(symbol, current_price, datetime.now())

            if exit_check['should_exit']:
                main_logger.info(
                    f"{EMOJI['EXIT']} Exit detected for {symbol}: {exit_check['reason']} "
                    f"@ ${exit_check['exit_price']:.4f}"
                )

                exit_signal = create_dca_signal(
                    symbol=symbol,
                    signal_type="exit",
                    entry_price=exit_check['exit_price'],
                    direction=dca_strategy.active_positions[symbol].direction,
                    confidence=1.0,
                    dca_level=dca_strategy.active_positions[symbol].dca_level,
                    stop_loss=0,
                    market_context=market_context
                )

                if exit_signal and signal_manager.activate_signal(exit_signal.signal_id):
                    position = dca_strategy.exit_position(
                        symbol,
                        exit_check['exit_price'],
                        exit_check['sell_percent']
                    )

                    if position:
                        signal_manager.execute_signal(exit_signal.signal_id, exit_check['exit_price'])

                        bot_stats['dca_exits'] += 1
                        bot_stats['active_positions'] = len(dca_strategy.active_positions)
                        bot_stats['signals_executed'] += 1

                        if position.realized_pnl > 0:
                            bot_stats['wins'] += 1
                            bot_stats['signal_outcomes']['profitable'] += 1
                        else:
                            bot_stats['losses'] += 1
                            bot_stats['signal_outcomes']['losing'] += 1

                        bot_stats['total_pnl'] += position.realized_pnl
                        bot_stats['daily_pnl'] = dca_strategy.daily_pnl
                        bot_stats['signal_outcomes']['total_pnl'] += position.realized_pnl

                        signal_manager.remove_signal(symbol)

                        if telegram_bot.enabled:
                            telegram_bot.send_dca_exit(
                                symbol=symbol,
                                entry_price=position.entry_price,
                                exit_price=exit_check['exit_price'],
                                pnl=position.realized_pnl,
                                pnl_percent=position.realized_pnl / position.total_cost * 100 if position.total_cost > 0 else 0,
                                reason=exit_check['reason'],
                                quantity=position.quantity,
                                dca_level=position.dca_level,
                                total_levels=position.total_dca_levels,
                                exit_type="PARTIAL" if exit_check['sell_percent'] < 1.0 else "FULL"
                            )

                        main_logger.info(
                            f"{EMOJI['EXIT']} EXIT: {symbol} @ ${exit_check['exit_price']:.4f} | "
                            f"Reason: {exit_check['reason']} | "
                            f"PnL: ${position.realized_pnl:.2f} ({position.realized_pnl/position.total_cost*100:+.2f}%)"
                        )

                        return {
                            "action": "exit",
                            "price": exit_check['exit_price'],
                            "pnl": position.realized_pnl,
                            "reason": exit_check['reason'],
                            "signal_id": exit_signal.signal_id
                        }

            entry_check = dca_strategy.should_enter_dca(symbol, current_price, df_15m, market_context)

            if entry_check['should_enter']:
                main_logger.info(
                    f"{EMOJI['DCA']} DCA condition met for {symbol}: "
                    f"Level {entry_check['level']} @ ${entry_check['entry_price']:.4f}"
                )

                can_gen, reason = can_generate_signal(symbol)
                if not can_gen:
                    main_logger.debug(f"⏳ Signal blocked for {symbol}: {reason}")
                    return {"action": "pending", "reason": reason}

                entry_signal = create_dca_signal(
                    symbol=symbol,
                    signal_type="entry",
                    entry_price=entry_check['entry_price'],
                    direction=entry_check['direction'],
                    confidence=entry_check['direction_confidence'],
                    dca_level=entry_check['level'],
                    stop_loss=dca_strategy._calculate_stop_loss(entry_check['entry_price'], entry_check['direction']),
                    market_context=market_context
                )

                if entry_signal and signal_manager.activate_signal(entry_signal.signal_id):
                    position_size = POSITION_SIZE_USD / current_price

                    success = dca_strategy.add_dca_position(
                        symbol,
                        entry_check['entry_price'],
                        entry_check['level'],
                        entry_check['direction'],
                        entry_check['direction_confidence'],
                        entry_check['direction_reason'],
                        market_context,
                        position_size
                    )

                    if success:
                        signal_manager.execute_signal(entry_signal.signal_id, entry_check['entry_price'])

                        bot_stats['dca_entries'] += 1
                        bot_stats['active_positions'] = len(dca_strategy.active_positions)
                        bot_stats['signals_executed'] += 1
                        bot_stats['signal_outcomes']['active'] += 1

                        if telegram_bot.enabled:
                            telegram_bot.send_dca_entry(
                                symbol=symbol,
                                entry_price=entry_check['entry_price'],
                                dca_level=entry_check['level'],
                                total_levels=dca_strategy.DCA_LEVELS,
                                stop_loss=dca_strategy._calculate_stop_loss(
                                    entry_check['entry_price'],
                                    entry_check['direction']
                                ),
                                position_size=position_size,
                                current_price=current_price,
                                direction=entry_check['direction'],
                                direction_confidence=entry_check['direction_confidence'],
                                direction_reason=entry_check['direction_reason']
                            )

                        main_logger.info(
                            f"{EMOJI['ENTRY']} ENTRY: {symbol} {entry_check['direction']} Level {entry_check['level']} "
                            f"@ ${entry_check['entry_price']:.4f} | "
                            f"Size: ${position_size * entry_check['entry_price']:.2f}"
                        )

                        return {
                            "action": "entry",
                            "price": entry_check['entry_price'],
                            "level": entry_check['level'],
                            "direction": entry_check['direction'],
                            "reason": entry_check['reason'],
                            "signal_id": entry_signal.signal_id
                        }

        # ===== 4. NO POSITION - CHECK NEW ENTRY =====
        else:
            can_gen, reason = can_generate_signal(symbol)
            if not can_gen:
                main_logger.debug(f"⏳ New position blocked for {symbol}: {reason}")
                return {"action": "pending", "reason": reason}

            entry_check = dca_strategy.should_enter_dca(symbol, current_price, df_15m, market_context)

            if entry_check['should_enter']:
                main_logger.info(
                    f"{EMOJI['ENTRY']} New position detected for {symbol}: "
                    f"{entry_check['direction']} @ ${entry_check['entry_price']:.4f}"
                )

                entry_signal = create_dca_signal(
                    symbol=symbol,
                    signal_type="entry",
                    entry_price=entry_check['entry_price'],
                    direction=entry_check['direction'],
                    confidence=entry_check['direction_confidence'],
                    dca_level=1,
                    stop_loss=dca_strategy._calculate_stop_loss(entry_check['entry_price'], entry_check['direction']),
                    market_context=market_context
                )

                if entry_signal and signal_manager.activate_signal(entry_signal.signal_id):
                    position_size = POSITION_SIZE_USD / current_price

                    success = dca_strategy.add_dca_position(
                        symbol,
                        entry_check['entry_price'],
                        1,
                        entry_check['direction'],
                        entry_check['direction_confidence'],
                        entry_check['direction_reason'],
                        market_context,
                        position_size
                    )

                    if success:
                        signal_manager.execute_signal(entry_signal.signal_id, entry_check['entry_price'])

                        bot_stats['dca_entries'] += 1
                        bot_stats['active_positions'] = len(dca_strategy.active_positions)
                        bot_stats['signals_executed'] += 1
                        bot_stats['signal_outcomes']['active'] += 1

                        if telegram_bot.enabled:
                            telegram_bot.send_dca_entry(
                                symbol=symbol,
                                entry_price=entry_check['entry_price'],
                                dca_level=1,
                                total_levels=dca_strategy.DCA_LEVELS,
                                stop_loss=dca_strategy._calculate_stop_loss(
                                    entry_check['entry_price'],
                                    entry_check['direction']
                                ),
                                position_size=position_size,
                                current_price=current_price,
                                direction=entry_check['direction'],
                                direction_confidence=entry_check['direction_confidence'],
                                direction_reason=entry_check['direction_reason']
                            )

                        main_logger.info(
                            f"{EMOJI['ENTRY']} NEW POSITION: {symbol} {entry_check['direction']} Level 1 "
                            f"@ ${entry_check['entry_price']:.4f} | "
                            f"Size: ${position_size * entry_check['entry_price']:.2f}"
                        )

                        return {
                            "action": "entry",
                            "price": entry_check['entry_price'],
                            "level": 1,
                            "direction": entry_check['direction'],
                            "reason": entry_check['reason'],
                            "signal_id": entry_signal.signal_id
                        }

        signal_manager.check_expired_signals()

        pending_signals = len(signal_manager.get_pending_signals())
        if pending_signals > 0:
            bot_stats['signals_pending'] = pending_signals

        return {"action": "none", "reason": "No action"}

    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} Error processing {symbol}: {e}")
        import traceback
        main_logger.error(traceback.format_exc())
        bot_stats['errors'] += 1
        return {"action": "error", "reason": str(e)}


# ==================== CHECK SIGNAL MANAGER STATUS ====================

def check_signal_manager_status():
    """Check and update signal manager status in bot stats."""
    try:
        stats = signal_manager.get_stats()
        bot_stats['signals_generated'] = stats.get('total_signals', 0)
        bot_stats['signals_executed'] = stats.get('executed_signals', 0)
        bot_stats['signals_rejected'] = stats.get('rejected_signals', 0)
        bot_stats['signals_expired'] = stats.get('expired_signals', 0)
        bot_stats['duplicate_signals_prevented'] = stats.get('duplicate_signals_prevented', 0)
    except Exception as e:
        main_logger.debug(f"Signal manager stats error: {e}")


# ==================== TELEGRAM STATUS ====================

def send_dca_status():
    """Send DCA status to Telegram with Signal Manager info."""
    if not telegram_bot.enabled:
        return

    stats = dca_strategy.get_daily_stats()
    signal_stats = signal_manager.get_stats()

    message = f"""
📊 <b>DCA Day Trading Status</b>

📈 <b>Today's Performance</b>
• PnL: <b>${stats['daily_pnl']:.2f}</b>
• Trades: <b>{stats['daily_trades']}</b>
• Win Rate: <b>{stats['win_rate']*100:.1f}%</b>

🟢 <b>Active Positions</b>
• Count: <b>{stats['active_positions']}</b>
• Symbols: {', '.join(stats['active_symbols']) if stats['active_symbols'] else 'None'}

📡 <b>Signal Manager</b>
• Active Signals: <b>{len(signal_manager.active_signals)}</b>
• Pending: <b>{len(signal_manager.get_pending_signals())}</b>
• Generated: <b>{signal_stats.get('total_signals', 0)}</b>

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    telegram_bot.send_message(message)
    main_logger.info(f"{EMOJI['TELEGRAM']} Daily status sent to Telegram")


def should_send_daily_status() -> bool:
    """Check if we should send the daily status (once per day)."""
    now = datetime.now()

    if now.hour != STATUS_HOUR or now.minute != STATUS_MINUTE:
        return False

    today = now.date()
    if bot_stats.get('last_status_date') == today:
        return False

    return True


def send_daily_performance_summary():
    """Send daily performance summary to Telegram."""
    if not telegram_bot.enabled:
        return

    stats = dca_strategy.get_daily_stats()

    message = f"""
📊 <b>DAILY PERFORMANCE SUMMARY</b>
━━━━━━━━━━━━━━━━━━━━━

<b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}

<b>Performance:</b>
• Daily PnL: <b>${stats['daily_pnl']:.2f}</b>
• Total Trades: <b>{stats['daily_trades']}</b>
• Win Rate: <b>{stats['win_rate']*100:.1f}%</b>
• Wins: <b>{stats['daily_wins']}</b>
• Losses: <b>{stats['daily_losses']}</b>

<b>Positions:</b>
• Active: <b>{stats['active_positions']}</b>
• Completed: <b>{stats['completed_positions']}</b>
• Symbols: {', '.join(stats['active_symbols']) if stats['active_symbols'] else 'None'}

<b>Signals:</b>
• Generated: <b>{bot_stats['signals_generated']}</b>
• Executed: <b>{bot_stats['signals_executed']}</b>
• Rejected: <b>{bot_stats['signals_rejected']}</b>
• Expired: <b>{bot_stats['signals_expired']}</b>

🕐 {datetime.now().strftime('%H:%M:%S')}
"""
    telegram_bot.send_message(message)
    main_logger.info(f"{EMOJI['TELEGRAM']} Daily performance summary sent")


# ==================== HEARTBEAT FUNCTION ====================

def log_heartbeat(cycle_count: int):
    """Log a heartbeat to show the bot is actively running."""
    now = datetime.now()
    active_positions = len(dca_strategy.active_positions)
    active_signals = len(signal_manager.active_signals)
    pending_signals = len(signal_manager.get_pending_signals())
    errors = bot_stats['errors']

    # Check if we're getting data
    last_price = bot_stats.get('last_price_time')
    if last_price:
        seconds_since_price = (now - last_price).seconds
        price_status = "✅" if seconds_since_price < 120 else f"⚠️ {seconds_since_price}s ago"
    else:
        price_status = "❌ No data"

    main_logger.info(
        f"{EMOJI['HEARTBEAT']} Bot Active - "
        f"Cycle #{cycle_count} | "
        f"Time: {now.strftime('%H:%M:%S')} | "
        f"Price: {price_status} | "
        f"Positions: {active_positions} | "
        f"Signals: {active_signals} active, {pending_signals} pending | "
        f"Daily PnL: ${dca_strategy.daily_pnl:.2f} | "
        f"Errors: {errors}"
    )

    bot_stats['last_heartbeat'] = now.isoformat()


# ==================== MAIN LOOP ====================

def run_processing_loop():
    global running

    main_logger.info(f"{EMOJI['START']} Starting DCA Day Trading Bot v2.0.0 with Signal Manager...")

    try:
        client = BinanceDataClient()
    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} Init error: {e}")
        return

    symbols = config.market.symbols
    if not symbols:
        main_logger.error(f"{EMOJI['ERROR']} No symbols configured")
        return

    # Send startup message
    if telegram_bot.enabled:
        dca_config = config.get_dca_config()
        telegram_bot.send_dca_start(symbols, {
            'dca_levels': dca_config['dca_levels'],
            'position_size': dca_config['position_size_usd'],
            'stop_loss': dca_config['stop_loss_percent'] * 100,
            'exit_time': f"{dca_config['exit_hour']:02d}:{dca_config['exit_minute']:02d}",
        })

    main_logger.info(f"{EMOJI['SUCCESS']} Monitoring {len(symbols)} symbols")
    main_logger.info(f"{EMOJI['INFO']} Position Size: ${POSITION_SIZE_USD}")
    main_logger.info(f"{EMOJI['INFO']} DCA Levels: {dca_strategy.DCA_LEVELS}")
    main_logger.info(f"{EMOJI['INFO']} Stop Loss: {dca_strategy.STOP_LOSS_PERCENT*100:.1f}%")
    main_logger.info(f"{EMOJI['INFO']} Exit Time: {dca_strategy.EXIT_HOUR:02d}:{dca_strategy.EXIT_MINUTE:02d} UTC")
    main_logger.info(f"{EMOJI['SIGNAL']} Signal Manager: Active")
    main_logger.info(f"{EMOJI['INFO']} Status Reports: Daily at {STATUS_HOUR:02d}:{STATUS_MINUTE:02d} UTC")
    main_logger.info(f"{EMOJI['HEARTBEAT']} Heartbeat every {HEARTBEAT_INTERVAL_CYCLES} cycles (~1 minute)")

    cycle_count = 0

    while running:
        try:
            cycle_start = time.time()
            cycle_count += 1

            for symbol in symbols:
                if not running:
                    break

                result = process_dca_symbol(symbol, client, {})

                if result.get('action') in ['entry', 'exit']:
                    bot_stats['cycles_completed'] += 1

            # Update stats
            bot_stats['cycles_completed'] += 1
            stats = dca_strategy.get_daily_stats()
            bot_stats['daily_pnl'] = stats['daily_pnl']
            bot_stats['completed_trades'] = stats['completed_positions']
            bot_stats['win_rate'] = stats['win_rate']
            bot_stats['active_positions'] = stats['active_positions']

            # Update Signal Manager stats
            check_signal_manager_status()

            # Log heartbeat every N cycles
            if cycle_count % HEARTBEAT_INTERVAL_CYCLES == 0:
                log_heartbeat(cycle_count)

            # Send daily status (once per day)
            if should_send_daily_status():
                send_dca_status()
                send_daily_performance_summary()
                bot_stats['last_status_date'] = datetime.now().date()
                main_logger.info(f"{EMOJI['CLOCK']} Daily status sent for {datetime.now().strftime('%Y-%m-%d')}")

            # Check if it's end of day (after exit hour)
            now = datetime.now()
            if now.hour >= dca_strategy.EXIT_HOUR and now.minute >= 30:
                if dca_strategy.daily_trades > 0:
                    if telegram_bot.enabled:
                        summary = {
                            'total_pnl': dca_strategy.daily_pnl,
                            'total_trades': dca_strategy.daily_trades,
                            'winning_trades': dca_strategy.daily_wins,
                            'losing_trades': dca_strategy.daily_losses,
                            'win_rate': dca_strategy.daily_wins / dca_strategy.daily_trades if dca_strategy.daily_trades > 0 else 0,
                            'symbols_traded': list(set([p.symbol for p in dca_strategy.completed_positions])),
                            'dca_entries': bot_stats['dca_entries'],
                        }
                        telegram_bot.send_dca_daily_summary(summary)

                    dca_strategy.reset_daily()

            # Sleep
            cycle_time = time.time() - cycle_start
            if running:
                sleep_time = max(0, config.market.polling_interval_seconds - cycle_time)
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            running = False
            break
        except Exception as e:
            main_logger.error(f"{EMOJI['ERROR']} Loop error: {e}")
            import traceback
            main_logger.error(traceback.format_exc())
            bot_stats['errors'] += 1
            time.sleep(10)

    if telegram_bot.enabled:
        telegram_bot.send_dca_stop(bot_stats)

    main_logger.info(f"{EMOJI['STOP']} Processing loop stopped")


# ==================== HEALTH SERVER ====================

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self._handle_health()
        elif self.path == '/metrics':
            self._handle_metrics()
        elif self.path == '/signals':
            self._handle_signals()
        else:
            self._handle_root()

    def _handle_root(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b"""
        <html>
        <body>
            <h1>DCA Day Trading Bot v2.0.0</h1>
            <ul>
                <li><a href='/health'>Health Status</a></li>
                <li><a href='/metrics'>Metrics</a></li>
                <li><a href='/signals'>Signal Status</a></li>
            </ul>
        </body>
        </html>
        """)

    def _handle_health(self):
        signal_stats = signal_manager.get_stats()

        # Convert datetime objects to strings for JSON serialization
        status = {
            "status": "healthy" if running else "stopped",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0",
            "stats": bot_stats,
            "active_positions": len(dca_strategy.active_positions),
            "daily_pnl": dca_strategy.daily_pnl,
            "signal_manager": {
                "active_signals": len(signal_manager.active_signals),
                "pending_signals": len(signal_manager.get_pending_signals()),
                "total_signals": signal_stats.get('total_signals', 0),
                "executed_signals": signal_stats.get('executed_signals', 0),
                "rejected_signals": signal_stats.get('rejected_signals', 0),
                "expired_signals": signal_stats.get('expired_signals', 0),
            },
            "strategy": {
                "dca_levels": dca_strategy.DCA_LEVELS,
                "stop_loss": dca_strategy.STOP_LOSS_PERCENT,
                "exit_hour": dca_strategy.EXIT_HOUR,
            }
        }
        is_healthy = status['status'] == 'healthy'
        self.send_response(200 if is_healthy else 503)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        # Use custom serializer for datetime
        self.wfile.write(json.dumps(status, indent=2, default=json_serializer).encode())

    def _handle_metrics(self):
        signal_stats = signal_manager.get_stats()
        metrics = [
            f"dca_active_positions {len(dca_strategy.active_positions)}",
            f"dca_daily_pnl {dca_strategy.daily_pnl:.2f}",
            f"dca_total_trades {dca_strategy.daily_trades}",
            f"dca_total_pnl {bot_stats['total_pnl']:.2f}",
            f"dca_entries {bot_stats['dca_entries']}",
            f"dca_exits {bot_stats['dca_exits']}",
            f"dca_errors {bot_stats['errors']}",
            f"signal_active {len(signal_manager.active_signals)}",
            f"signal_pending {len(signal_manager.get_pending_signals())}",
            f"signal_total {signal_stats.get('total_signals', 0)}",
            f"signal_executed {signal_stats.get('executed_signals', 0)}",
            f"signal_rejected {signal_stats.get('rejected_signals', 0)}",
            f"signal_expired {signal_stats.get('expired_signals', 0)}",
        ]
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain')
        self.end_headers()
        self.wfile.write("\n".join(metrics).encode())

    def _handle_signals(self):
        """Handle signal status endpoint."""
        try:
            active_signals = signal_manager.get_all_active_signals()
            pending_signals = signal_manager.get_pending_signals()
            signal_stats = signal_manager.get_stats()

            # Convert datetime objects to strings
            def convert_signal(s):
                result = dict(s)
                for key in ['entry_time', 'created_at', 'expires_at', 'executed_at']:
                    if key in result and result[key] and isinstance(result[key], datetime):
                        result[key] = result[key].isoformat()
                return result

            status = {
                "timestamp": datetime.now().isoformat(),
                "statistics": signal_stats,
                "active_count": len(active_signals),
                "pending_count": len(pending_signals),
                "active_signals": [
                    {
                        'symbol': s.get('symbol'),
                        'type': s.get('signal_type'),
                        'status': s.get('status'),
                        'entry_price': s.get('entry_price'),
                        'entry_time': s.get('entry_time'),
                        'direction': s.get('direction'),
                        'dca_level': s.get('dca_level'),
                        'age_seconds': (datetime.now() - datetime.fromisoformat(s.get('entry_time', datetime.now().isoformat()))).seconds if s.get('entry_time') else 0,
                        'signal_id': s.get('signal_id'),
                    }
                    for s in list(active_signals.values())[:20]
                ],
                "pending_signals": [
                    {
                        'symbol': s.get('symbol'),
                        'type': s.get('signal_type'),
                        'direction': s.get('direction'),
                        'entry_price': s.get('entry_price'),
                        'confidence': s.get('confidence'),
                        'dca_level': s.get('dca_level'),
                        'signal_id': s.get('signal_id'),
                    }
                    for s in pending_signals[:10]
                ]
            }

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(status, indent=2, default=json_serializer).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, format, *args):
        pass


def run_health_server():
    try:
        server = HTTPServer(('0.0.0.0', config.deployment.port), HealthHandler)
        main_logger.info(f"{EMOJI['HEALTH']} Health server running on port {config.deployment.port}")
        server.serve_forever()
    except Exception as e:
        main_logger.error(f"Health server error: {e}")


# ==================== SIGNAL HANDLER ====================

def signal_handler(sig, frame):
    global running
    main_logger.info(f"{EMOJI['STOP']} Shutdown signal ({sig})")
    running = False


# ==================== MAIN ====================

def main():
    global running

    main_logger.info("=" * 70)
    main_logger.info(f"{EMOJI['START']} DCA DAY TRADING BOT v2.0.0")
    main_logger.info(f"{EMOJI['DCA']} Strategy: Hybrid DCA with Multi-Timeframe")
    main_logger.info(f"{EMOJI['DCA']} DCA Levels: {dca_strategy.DCA_LEVELS}")
    main_logger.info(f"{EMOJI['TARGET']} Exit Time: {dca_strategy.EXIT_HOUR:02d}:{dca_strategy.EXIT_MINUTE:02d} UTC")
    main_logger.info(f"{EMOJI['SIGNAL']} Signal Manager: Active tracking & deduplication")
    main_logger.info(f"{EMOJI['INFO']} Database: {'MongoDB' if config.mongodb.enabled else 'In-Memory'}")
    main_logger.info("=" * 70)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    bot_stats["status"] = "running"
    bot_stats["start_time"] = datetime.now().isoformat()

    threading.Thread(target=run_health_server, daemon=True).start()

    try:
        run_processing_loop()
    except Exception as e:
        main_logger.error(f"{EMOJI['ERROR']} Fatal: {e}")
        traceback.print_exc()

    signal_stats = signal_manager.get_stats()
    main_logger.info(f"{EMOJI['SIGNAL']} Final Signal Manager Stats:")
    main_logger.info(f"  - Total Signals: {signal_stats.get('total_signals', 0)}")
    main_logger.info(f"  - Executed: {signal_stats.get('executed_signals', 0)}")
    main_logger.info(f"  - Rejected: {signal_stats.get('rejected_signals', 0)}")
    main_logger.info(f"  - Expired: {signal_stats.get('expired_signals', 0)}")

    main_logger.info(f"{EMOJI['STOP']} Shutting down...")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        main_logger.error(f"Fatal: {e}")
        traceback.print_exc()
        sys.exit(1)
