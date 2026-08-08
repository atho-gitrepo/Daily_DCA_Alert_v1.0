"""
Hybrid DCA Day Trading Strategy
Combines Super TDI + Bollinger Bands + Multi-Timeframe for DCA entries
Version: 1.0.4 - Enhanced with ATR-based spacing, trailing stop, and position management
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

try:
    from utils.indicators import Indicators, calculate_heikin_ashi
except ImportError:
    from indicators import Indicators, calculate_heikin_ashi
from settings import config

logger = logging.getLogger(__name__)
dca_logger = logging.getLogger("dca_strategy")

EMOJI = {
    "START": "🚀", "SUCCESS": "✅", "ERROR": "❌", "WARNING": "⚠️",
    "INFO": "ℹ️", "BUY": "🟢", "SELL": "🔴", "DCA": "📊",
    "ENTRY": "🎯", "EXIT": "🚪", "PROFIT": "💰", "LOSS": "💸",
    "BREAK": "⚖️", "CLOCK": "🕐", "TARGET": "🎯", "VOLUME": "📊",
    "TDI": "📈", "BB": "📉", "HTF": "📊", "LTF": "⏱️",
    "TRAILING": "🔀", "STOP": "⛔",
}


class TrendDirection(Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL_BULLISH = "NEUTRAL_BULLISH"
    NEUTRAL = "NEUTRAL"
    NEUTRAL_BEARISH = "NEUTRAL_BEARISH"
    BEARISH = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"


@dataclass
class DCAPosition:
    symbol: str
    direction: str
    entry_price: float
    entry_time: datetime
    quantity: float
    total_cost: float
    current_price: float
    tdi_level: float = 0.0
    tdi_zone: str = "NEUTRAL"
    bb_position: float = 0.5
    htf_trend: str = "NEUTRAL"
    mtf_trend: str = "NEUTRAL"
    ltf_trend: str = "NEUTRAL"
    trend_strength: float = 0.0
    dca_level: int = 1
    total_dca_levels: int = 3
    dca_entries: List[Dict] = field(default_factory=list)
    stop_loss: float = 0.0
    take_profits: List[Dict] = field(default_factory=list)
    unrealized_pnl: float = 0.0
    unrealized_pnl_percent: float = 0.0
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    realized_pnl: float = 0.0
    status: str = "ACTIVE"
    entry_score: float = 0.0
    direction_confidence: float = 0.0
    direction_reason: str = ""
    last_dca_time: Optional[datetime] = None
    dca_count: int = 1
    # NEW: Trailing stop tracking
    highest_price: float = 0.0  # For trailing stop (LONG)
    lowest_price: float = float('inf')  # For trailing stop (SHORT)
    trailing_stop_price: float = 0.0
    trailing_activated: bool = False


class DCAHybridStrategy:
    """Hybrid DCA Strategy using Super TDI + Bollinger Bands"""

    def __init__(self, config_override: Optional[Dict] = None):
        # DCA Configuration
        self.DCA_LEVELS = config.dca.dca_levels
        self.DCA_SPACING = config.dca.dca_spacing
        self.POSITION_SIZE_USD = config.dca.position_size_usd

        # Risk Management
        self.STOP_LOSS_PERCENT = config.dca.stop_loss_percent
        self.TP_LEVELS = [
            {"percent": config.dca.tp_level_1, "size": 0.50, "label": "TP1"},
            {"percent": config.dca.tp_level_2, "size": 0.25, "label": "TP2"},
            {"percent": config.dca.tp_level_3, "size": 0.25, "label": "TP3"},
        ]

        # Time-based Exit
        self.EXIT_HOUR = config.dca.exit_hour
        self.EXIT_MINUTE = config.dca.exit_minute
        self.MINUTES_BEFORE_EXIT = config.dca.minutes_before_exit

        # TDI Thresholds
        self.TDI_OVERSOLD = config.dca.tdi_oversold
        self.TDI_SOFT_BUY = config.dca.tdi_soft_buy
        self.TDI_CENTER = config.dca.tdi_center
        self.TDI_SOFT_SELL = config.dca.tdi_soft_sell
        self.TDI_OVERBOUGHT = config.dca.tdi_overbought

        # Confidence Thresholds
        self.MIN_DIRECTION_CONFIDENCE = config.dca.min_direction_confidence
        self.MIN_HTF_ALIGNMENT = config.dca.min_htf_alignment
        self.MIN_LTF_CONFIRMATION = config.dca.min_ltf_confirmation

        # DCA Time Delay
        self.MIN_DCA_INTERVAL_SECONDS = 300

        # NEW: Trailing Stop Configuration
        self.TRAILING_STOP_PERCENT = config.dca.trailing_stop_percent
        self.TRAILING_ACTIVATION_PCT = config.dca.trailing_activation_pct

        # NEW: Position Limits
        self.MAX_ACTIVE_POSITIONS = config.dca.max_active_positions

        # State
        self.active_positions: Dict[str, DCAPosition] = {}
        self.completed_positions: List[DCAPosition] = []
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.market_context: Dict[str, Dict] = {}

        dca_logger.info(f"{EMOJI['START']} DCA_HYBRID: Initialized (v1.0.4)")
        dca_logger.info(f"  - DCA Levels: {self.DCA_LEVELS}")
        dca_logger.info(f"  - Stop Loss: {self.STOP_LOSS_PERCENT*100:.1f}%")
        dca_logger.info(f"  - Trailing Stop: {self.TRAILING_STOP_PERCENT*100:.1f}% (activates at {self.TRAILING_ACTIVATION_PCT*100:.1f}%)")
        dca_logger.info(f"  - Max Positions: {self.MAX_ACTIVE_POSITIONS}")
        dca_logger.info(f"  - Exit Time: {self.EXIT_HOUR:02d}:{self.EXIT_MINUTE:02d} UTC")

    def can_open_new_position(self) -> bool:
        """Check if we can open a new position (respects max positions limit)."""
        active_count = len(self.active_positions)
        if active_count >= self.MAX_ACTIVE_POSITIONS:
            dca_logger.debug(f"Max positions reached: {active_count}/{self.MAX_ACTIVE_POSITIONS}")
            return False
        return True

    def analyze_multi_timeframe(self, df_4h: pd.DataFrame, df_1h: pd.DataFrame,
                                df_15m: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Analyze all timeframes for comprehensive market context."""
        result = {
            'htf': {}, 'mtf': {}, 'ltf': {},
            'trend': 'NEUTRAL', 'trend_strength': 0.0,
            'direction': 'NEUTRAL', 'confidence': 0.0,
            'reason': '', 'tdi_level': 50.0,
            'tdi_zone': 'NEUTRAL', 'bb_position': 0.5,
            'volume_ratio': 1.0,
            'atr': 0.0,  # NEW: ATR for dynamic sizing
        }

        if not df_4h.empty and len(df_4h) >= 10:
            htf_analysis = self._analyze_timeframe(df_4h, "4H")
            result['htf'] = htf_analysis
            result['htf_trend'] = htf_analysis.get('trend', 'NEUTRAL')
            result['htf_tdi'] = htf_analysis.get('tdi_level', 50)
            result['htf_zone'] = htf_analysis.get('tdi_zone', 'NEUTRAL')

        if not df_1h.empty and len(df_1h) >= 10:
            mtf_analysis = self._analyze_timeframe(df_1h, "1H")
            result['mtf'] = mtf_analysis
            result['mtf_trend'] = mtf_analysis.get('trend', 'NEUTRAL')
            result['mtf_tdi'] = mtf_analysis.get('tdi_level', 50)
            result['mtf_zone'] = mtf_analysis.get('tdi_zone', 'NEUTRAL')

        if not df_15m.empty and len(df_15m) >= 10:
            ltf_analysis = self._analyze_timeframe(df_15m, "15M")
            result['ltf'] = ltf_analysis
            result['ltf_trend'] = ltf_analysis.get('trend', 'NEUTRAL')
            result['ltf_tdi'] = ltf_analysis.get('tdi_level', 50)
            result['ltf_zone'] = ltf_analysis.get('tdi_zone', 'NEUTRAL')
            result['ltf_bb_position'] = ltf_analysis.get('bb_position', 0.5)
            # NEW: Get ATR from 15M timeframe
            result['atr'] = ltf_analysis.get('atr', current_price * 0.01)

        direction_result = self._detect_direction(result)
        result.update(direction_result)
        self.market_context[symbol] = result

        return result

    def _analyze_timeframe(self, df: pd.DataFrame, tf_name: str) -> Dict[str, Any]:
        """Analyze a single timeframe for indicators."""
        try:
            df = Indicators.calculate_all_indicators(df)

            if df.empty or len(df) < 10:
                return {'trend': 'NEUTRAL', 'tdi_level': 50, 'tdi_zone': 'NEUTRAL', 'atr': 0}

            last = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else last

            tdi_slow = last.get('tdi_slow_ma', 50)
            tdi_fast = last.get('tdi_fast_ma', 50)
            tdi_prev = prev.get('tdi_slow_ma', 50)
            bb_position = last.get('bb_position', 0.5)
            bb_width = last.get('bb_width_percent', 0)

            ha_color = last.get('ha_color', 0)
            ha_prev_color = prev.get('ha_color', 0)
            volume_ratio = last.get('volume_ratio', 1)

            # NEW: Get ATR
            atr = last.get('atr', 0)

            if tdi_slow == 50 and 'rsi' in last:
                tdi_slow = last.get('rsi', 50)

            trend = self._get_trend(tdi_slow, tdi_fast, tdi_prev, ha_color, ha_prev_color)
            tdi_zone = self._get_tdi_zone(tdi_slow)

            return {
                'trend': trend,
                'tdi_level': tdi_slow,
                'tdi_fast': tdi_fast,
                'tdi_zone': tdi_zone,
                'bb_position': bb_position,
                'bb_width': bb_width,
                'ha_color': ha_color,
                'volume_ratio': volume_ratio,
                'atr': atr,
            }
        except Exception as e:
            dca_logger.error(f"Error analyzing {tf_name}: {e}")
            return {'trend': 'NEUTRAL', 'tdi_level': 50, 'tdi_zone': 'NEUTRAL', 'atr': 0}

    def _get_trend(self, tdi_slow: float, tdi_fast: float, tdi_prev: float,
                   ha_color: int, ha_prev_color: int) -> str:
        if tdi_fast > tdi_slow and tdi_slow > self.TDI_CENTER:
            return "BULLISH"
        elif tdi_fast < tdi_slow and tdi_slow < self.TDI_CENTER:
            return "BEARISH"

        if ha_color == 1 and ha_prev_color == 1:
            if tdi_slow > self.TDI_CENTER:
                return "BULLISH"
            elif tdi_slow > self.TDI_SOFT_BUY:
                return "NEUTRAL_BULLISH"
        elif ha_color == -1 and ha_prev_color == -1:
            if tdi_slow < self.TDI_CENTER:
                return "BEARISH"
            elif tdi_slow < self.TDI_SOFT_SELL:
                return "NEUTRAL_BEARISH"

        if tdi_slow > tdi_prev and tdi_slow > self.TDI_CENTER:
            return "NEUTRAL_BULLISH"
        elif tdi_slow < tdi_prev and tdi_slow < self.TDI_CENTER:
            return "NEUTRAL_BEARISH"

        return "NEUTRAL"

    def _get_tdi_zone(self, tdi_value: float) -> str:
        if tdi_value <= self.TDI_OVERSOLD:
            return "OVERSOLD"
        elif tdi_value <= self.TDI_SOFT_BUY:
            return "SOFT_BUY"
        elif tdi_value < self.TDI_CENTER:
            return "BUY_ZONE"
        elif tdi_value < self.TDI_SOFT_SELL:
            return "NO_TRADE"
        elif tdi_value < self.TDI_OVERBOUGHT:
            return "SOFT_SELL"
        else:
            return "OVERBOUGHT"

    def _detect_direction(self, context: Dict) -> Dict[str, Any]:
        htf = context.get('htf', {})
        mtf = context.get('mtf', {})
        ltf = context.get('ltf', {})

        htf_trend = htf.get('trend', 'NEUTRAL')
        mtf_trend = mtf.get('trend', 'NEUTRAL')
        ltf_trend = ltf.get('trend', 'NEUTRAL')

        long_score = 0
        short_score = 0
        reasons = []

        if htf_trend in ["STRONG_BULLISH", "BULLISH"]:
            long_score += 3
            reasons.append("4H Bullish")
        elif htf_trend in ["STRONG_BEARISH", "BEARISH"]:
            short_score += 3
            reasons.append("4H Bearish")

        if mtf_trend in ["STRONG_BULLISH", "BULLISH"]:
            long_score += 2
            reasons.append("1H Bullish")
        elif mtf_trend in ["STRONG_BEARISH", "BEARISH"]:
            short_score += 2
            reasons.append("1H Bearish")

        if ltf_trend in ["STRONG_BULLISH", "BULLISH"]:
            long_score += 1
            reasons.append("15M Bullish")
        elif ltf_trend in ["STRONG_BEARISH", "BEARISH"]:
            short_score += 1
            reasons.append("15M Bearish")

        htf_tdi = htf.get('tdi_level', 50)
        mtf_tdi = mtf.get('tdi_level', 50)

        if htf_tdi < self.TDI_CENTER and mtf_tdi < self.TDI_CENTER:
            long_score += 1
            reasons.append("TDI aligned LONG")
        elif htf_tdi > self.TDI_CENTER and mtf_tdi > self.TDI_CENTER:
            short_score += 1
            reasons.append("TDI aligned SHORT")

        ltf_bb = ltf.get('bb_position', 0.5)
        if ltf_bb < 0.3:
            long_score += 0.5
            reasons.append("LTF near lower BB")
        elif ltf_bb > 0.7:
            short_score += 0.5
            reasons.append("LTF near upper BB")

        total_score = long_score + short_score
        confidence = 0.0

        if long_score > short_score:
            direction = "LONG"
            confidence = min(0.9, 0.5 + (long_score - short_score) / max(total_score, 1) * 0.4)
            reason = f"LONG: {', '.join(reasons[:3])}"
        elif short_score > long_score:
            direction = "SHORT"
            confidence = min(0.9, 0.5 + (short_score - long_score) / max(total_score, 1) * 0.4)
            reason = f"SHORT: {', '.join(reasons[:3])}"
        else:
            direction = "NEUTRAL"
            confidence = 0.3
            reason = "No clear direction"

        return {
            'direction': direction,
            'confidence': confidence,
            'reason': reason,
            'long_score': long_score,
            'short_score': short_score,
            'trend_strength': abs(long_score - short_score) / max(total_score, 1),
        }

    def get_dca_levels(self, symbol: str, current_price: float,
                       df_15m: pd.DataFrame) -> List[float]:
        """
        Calculate DCA levels with dynamic spacing based on ATR.
        """
        # Get ATR for dynamic spacing
        atr = 0
        if not df_15m.empty and 'atr' in df_15m.columns:
            atr = df_15m['atr'].iloc[-1]

        # Calculate dynamic spacing
        if atr and atr > 0:
            # Use ATR for spacing, but keep within min/max bounds
            spacing = max(atr / current_price, 0.005)  # Minimum 0.5%
            spacing = min(spacing, 0.02)  # Maximum 2%
        else:
            spacing = self.DCA_SPACING * 5  # Default 1%
            spacing = max(spacing, 0.005)
            spacing = min(spacing, 0.02)

        dca_logger.debug(f"{symbol} Dynamic DCA spacing: {spacing*100:.2f}% (ATR: {atr:.2f})")

        # For LONG: levels below current price
        levels = [
            current_price,
            current_price * (1 - spacing),
            current_price * (1 - spacing * 2),
        ]

        return levels[:self.DCA_LEVELS]

    def should_enter_dca(self, symbol: str, current_price: float,
                         df_15m: pd.DataFrame, market_context: Dict) -> Dict:
        """Check if we should enter a DCA position."""
        now = datetime.now()

        # Check position limit before anything else
        if not self.can_open_new_position() and symbol not in self.active_positions:
            return self._no_entry(f"Max positions reached ({self.MAX_ACTIVE_POSITIONS})")

        if symbol in self.active_positions:
            position = self.active_positions[symbol]

            if position.dca_level >= self.DCA_LEVELS:
                return self._no_entry("Max DCA levels reached")

            if position.last_dca_time:
                time_since_dca = (now - position.last_dca_time).total_seconds()
                if time_since_dca < self.MIN_DCA_INTERVAL_SECONDS:
                    remaining = int(self.MIN_DCA_INTERVAL_SECONDS - time_since_dca)
                    return self._no_entry(f"DCA cooldown: {remaining}s remaining")

            dca_levels = self.get_dca_levels(symbol, current_price, df_15m)
            if len(dca_levels) <= position.dca_level:
                return self._no_entry("No more DCA levels available")

            next_level = dca_levels[position.dca_level]

            if position.direction == "LONG":
                if current_price <= next_level:
                    dca_logger.info(f"{symbol}: LONG DCA level {position.dca_level + 1} @ ${next_level:.4f}")
                    return {
                        'should_enter': True,
                        'level': position.dca_level + 1,
                        'entry_price': current_price,
                        'direction': position.direction,
                        'direction_confidence': position.direction_confidence,
                        'direction_reason': position.direction_reason,
                        'reason': f'DCA Level {position.dca_level + 1} at ${current_price:.4f}'
                    }
            else:  # SHORT
                if current_price >= next_level:
                    dca_logger.info(f"{symbol}: SHORT DCA level {position.dca_level + 1} @ ${next_level:.4f}")
                    return {
                        'should_enter': True,
                        'level': position.dca_level + 1,
                        'entry_price': current_price,
                        'direction': position.direction,
                        'direction_confidence': position.direction_confidence,
                        'direction_reason': position.direction_reason,
                        'reason': f'DCA Level {position.dca_level + 1} at ${current_price:.4f}'
                    }

            return self._no_entry(f'Waiting for DCA level {position.dca_level + 1}')

        # ===== NO POSITION - CHECK NEW ENTRY =====
        direction = market_context.get('direction', 'NEUTRAL')
        confidence = market_context.get('confidence', 0)

        if confidence < self.MIN_DIRECTION_CONFIDENCE:
            return self._no_entry(f'Confidence too low: {confidence*100:.0f}%')

        if direction not in ['LONG', 'SHORT']:
            return self._no_entry(f'No clear direction: {direction}')

        # ENTER AT CURRENT PRICE
        dca_logger.info(f"{symbol}: New {direction} position at current price ${current_price:.4f}")
        return {
            'should_enter': True,
            'level': 1,
            'entry_price': current_price,
            'direction': direction,
            'direction_confidence': confidence,
            'direction_reason': market_context.get('reason', ''),
            'reason': f'First DCA entry at ${current_price:.4f}'
        }

    def _no_entry(self, reason: str) -> Dict:
        return {
            'should_enter': False,
            'level': 0,
            'entry_price': 0,
            'direction': 'NEUTRAL',
            'direction_confidence': 0,
            'direction_reason': '',
            'reason': reason
        }

    def check_exit(self, symbol: str, current_price: float, current_time: datetime) -> Dict:
        if symbol not in self.active_positions:
            return self._no_exit('No active position')

        position = self.active_positions[symbol]

        # Update highest/lowest price for trailing stop
        if position.direction == "LONG":
            if current_price > position.highest_price:
                position.highest_price = current_price
                # Update trailing stop
                if position.highest_price > position.entry_price * (1 + self.TRAILING_ACTIVATION_PCT):
                    position.trailing_activated = True
                    position.trailing_stop_price = position.highest_price * (1 - self.TRAILING_STOP_PERCENT)
                    dca_logger.debug(f"{symbol}: Trailing stop updated to ${position.trailing_stop_price:.4f}")
        else:  # SHORT
            if current_price < position.lowest_price:
                position.lowest_price = current_price
                if position.lowest_price < position.entry_price * (1 - self.TRAILING_ACTIVATION_PCT):
                    position.trailing_activated = True
                    position.trailing_stop_price = position.lowest_price * (1 + self.TRAILING_STOP_PERCENT)
                    dca_logger.debug(f"{symbol}: Trailing stop updated to ${position.trailing_stop_price:.4f}")

        # Check trailing stop (NEW)
        if position.trailing_activated:
            if position.direction == "LONG" and current_price <= position.trailing_stop_price:
                dca_logger.info(f"{EMOJI['TRAILING']} {symbol}: Trailing stop hit at ${current_price:.4f}")
                return self._exit_decision(current_price, 'Trailing stop triggered', 1.0)
            elif position.direction == "SHORT" and current_price >= position.trailing_stop_price:
                dca_logger.info(f"{EMOJI['TRAILING']} {symbol}: Trailing stop hit at ${current_price:.4f}")
                return self._exit_decision(current_price, 'Trailing stop triggered', 1.0)

        # Stop loss check
        if position.direction == "LONG":
            if current_price <= position.stop_loss:
                dca_logger.info(f"{EMOJI['STOP']} {symbol}: Stop loss triggered at ${current_price:.4f}")
                return self._exit_decision(current_price, 'Stop loss triggered', 1.0)
        else:
            if current_price >= position.stop_loss:
                dca_logger.info(f"{EMOJI['STOP']} {symbol}: Stop loss triggered at ${current_price:.4f}")
                return self._exit_decision(current_price, 'Stop loss triggered', 1.0)

        # Take profit check
        avg_entry = position.total_cost / position.quantity if position.quantity > 0 else 0
        if avg_entry > 0:
            if position.direction == "LONG":
                pnl_percent = (current_price - avg_entry) / avg_entry
            else:
                pnl_percent = (avg_entry - current_price) / avg_entry

            for tp in self.TP_LEVELS:
                if pnl_percent >= tp['percent']:
                    dca_logger.info(f"{EMOJI['PROFIT']} {symbol}: Take profit {tp['label']} at ${current_price:.4f} ({pnl_percent*100:.2f}%)")
                    return self._exit_decision(current_price, f'Take profit {tp["label"]}', tp['size'])

        # Time-based exit
        exit_time = current_time.replace(hour=self.EXIT_HOUR, minute=self.EXIT_MINUTE, second=0)
        minutes_until_exit = (exit_time - current_time).total_seconds() / 60

        if minutes_until_exit <= self.MINUTES_BEFORE_EXIT:
            if minutes_until_exit <= 5:
                dca_logger.info(f"{EMOJI['CLOCK']} {symbol}: Time-based full exit at ${current_price:.4f}")
                return self._exit_decision(current_price, 'Time-based full exit', 1.0)
            else:
                sell_percent = (self.MINUTES_BEFORE_EXIT - minutes_until_exit) / self.MINUTES_BEFORE_EXIT
                dca_logger.info(f"{EMOJI['CLOCK']} {symbol}: Time-based partial exit at ${current_price:.4f} ({sell_percent*100:.0f}%)")
                return self._exit_decision(current_price, f'Time-based partial ({minutes_until_exit:.0f}min left)',
                                         min(sell_percent, 0.5))

        return self._no_exit('Holding position')

    def _exit_decision(self, price: float, reason: str, sell_percent: float) -> Dict:
        return {
            'should_exit': True,
            'exit_price': price,
            'reason': reason,
            'sell_percent': sell_percent,
        }

    def _no_exit(self, reason: str) -> Dict:
        return {
            'should_exit': False,
            'exit_price': 0,
            'reason': reason,
            'sell_percent': 0
        }

    def add_dca_position(self, symbol: str, entry_price: float, level: int,
                         direction: str, direction_confidence: float,
                         direction_reason: str, market_context: Dict,
                         quantity: float) -> bool:
        try:
            stop_loss = self._calculate_stop_loss(entry_price, direction)
            now = datetime.now()

            if symbol in self.active_positions:
                position = self.active_positions[symbol]

                total_cost = position.total_cost + (entry_price * quantity)
                total_qty = position.quantity + quantity
                avg_entry = total_cost / total_qty if total_qty > 0 else 0

                position.entry_price = avg_entry
                position.total_cost = total_cost
                position.quantity = total_qty
                position.dca_level = level
                position.stop_loss = stop_loss
                position.last_dca_time = now
                position.dca_count += 1
                position.dca_entries.append({
                    'price': entry_price,
                    'quantity': quantity,
                    'time': now.isoformat(),
                    'level': level
                })

                dca_logger.info(f"{EMOJI['DCA']} DCA_ADD: {symbol} Level {level} @ {entry_price:.4f}")
            else:
                position = DCAPosition(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    entry_time=now,
                    quantity=quantity,
                    total_cost=entry_price * quantity,
                    current_price=entry_price,
                    tdi_level=market_context.get('tdi_level', 50),
                    tdi_zone=market_context.get('tdi_zone', 'NEUTRAL'),
                    bb_position=market_context.get('bb_position', 0.5),
                    htf_trend=market_context.get('htf_trend', 'NEUTRAL'),
                    mtf_trend=market_context.get('mtf_trend', 'NEUTRAL'),
                    ltf_trend=market_context.get('ltf_trend', 'NEUTRAL'),
                    trend_strength=market_context.get('trend_strength', 0),
                    dca_level=level,
                    total_dca_levels=self.DCA_LEVELS,
                    dca_entries=[{'price': entry_price, 'quantity': quantity,
                                  'time': now.isoformat(), 'level': level}],
                    stop_loss=stop_loss,
                    direction_confidence=direction_confidence,
                    direction_reason=direction_reason,
                    entry_score=market_context.get('confidence', 0) * 100,
                    last_dca_time=now,
                    dca_count=1,
                    # NEW: Trailing stop initialization
                    highest_price=entry_price,
                    lowest_price=entry_price,
                    trailing_stop_price=0.0,
                    trailing_activated=False,
                )
                self.active_positions[symbol] = position

                dca_logger.info(f"{EMOJI['BUY']} DCA_NEW: {symbol} {direction} Level {level} @ {entry_price:.4f}")

            return True
        except Exception as e:
            dca_logger.error(f"Error adding DCA position: {e}")
            return False

    def _calculate_stop_loss(self, entry_price: float, direction: str) -> float:
        if direction == "LONG":
            return entry_price * (1 - self.STOP_LOSS_PERCENT)
        else:
            return entry_price * (1 + self.STOP_LOSS_PERCENT)

    def exit_position(self, symbol: str, exit_price: float, sell_percent: float = 1.0) -> Optional[DCAPosition]:
        if symbol not in self.active_positions:
            return None

        position = self.active_positions[symbol]
        sell_qty = position.quantity * sell_percent
        avg_entry = position.total_cost / position.quantity if position.quantity > 0 else 0

        if position.direction == "LONG":
            pnl = (exit_price - avg_entry) * sell_qty
            pnl_percent = (exit_price - avg_entry) / avg_entry if avg_entry > 0 else 0
        else:
            pnl = (avg_entry - exit_price) * sell_qty
            pnl_percent = (avg_entry - exit_price) / avg_entry if avg_entry > 0 else 0

        if sell_percent >= 1.0:
            position.exit_price = exit_price
            position.exit_time = datetime.now()
            position.realized_pnl = pnl
            position.status = "CLOSED"

            self.completed_positions.append(position)
            del self.active_positions[symbol]
            self.daily_pnl += pnl
            self.daily_trades += 1
            if pnl > 0:
                self.daily_wins += 1
            else:
                self.daily_losses += 1

            dca_logger.info(f"{EMOJI['EXIT']} DCA_EXIT: {symbol} @ {exit_price:.4f} | PnL: ${pnl:.2f} ({pnl_percent*100:+.2f}%)")
        else:
            remaining_qty = position.quantity - sell_qty
            remaining_cost = position.total_cost * (remaining_qty / position.quantity)
            position.quantity = remaining_qty
            position.total_cost = remaining_cost
            position.status = "PARTIAL"

            dca_logger.info(f"{EMOJI['EXIT']} DCA_PARTIAL: {symbol} @ {exit_price:.4f} | PnL: ${pnl:.2f}")

        return position

    def get_daily_stats(self) -> Dict:
        win_rate = self.daily_wins / self.daily_trades if self.daily_trades > 0 else 0
        return {
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'daily_wins': self.daily_wins,
            'daily_losses': self.daily_losses,
            'win_rate': win_rate,
            'active_positions': len(self.active_positions),
            'completed_positions': len(self.completed_positions),
            'active_symbols': list(self.active_positions.keys()),
            'max_positions': self.MAX_ACTIVE_POSITIONS,
        }

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.completed_positions = []
        self.market_context = {}
        dca_logger.info("Daily stats reset")

    def get_position_summary(self, symbol: str) -> Optional[Dict]:
        """Get detailed summary of a position."""
        if symbol not in self.active_positions:
            return None

        position = self.active_positions[symbol]
        avg_entry = position.total_cost / position.quantity if position.quantity > 0 else 0

        return {
            'symbol': symbol,
            'direction': position.direction,
            'entry_price': position.entry_price,
            'avg_entry': avg_entry,
            'current_price': position.current_price,
            'quantity': position.quantity,
            'total_cost': position.total_cost,
            'dca_level': position.dca_level,
            'dca_count': position.dca_count,
            'stop_loss': position.stop_loss,
            'unrealized_pnl': position.unrealized_pnl,
            'unrealized_pnl_percent': position.unrealized_pnl_percent,
            'trailing_activated': position.trailing_activated,
            'trailing_stop_price': position.trailing_stop_price,
            'highest_price': position.highest_price,
            'lowest_price': position.lowest_price,
        }


dca_strategy = DCAHybridStrategy()

__all__ = ["dca_strategy", "DCAHybridStrategy", "DCAPosition", "TrendDirection"]
