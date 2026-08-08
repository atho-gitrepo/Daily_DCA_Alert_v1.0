"""
Hybrid DCA Day Trading Strategy
Combines Super TDI + Bollinger Bands + Multi-Timeframe for DCA entries
Version: 1.0.0
"""

import pandas as pd
import numpy as np
import logging
from typing import Dict, Optional, Tuple, List, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from utils.indicators import Indicators, calculate_heikin_ashi

logger = logging.getLogger(__name__)
dca_logger = logging.getLogger("dca_strategy")

EMOJI = {
    "START": "🚀",
    "SUCCESS": "✅",
    "ERROR": "❌",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "BUY": "🟢",
    "SELL": "🔴",
    "DCA": "📊",
    "ENTRY": "🎯",
    "EXIT": "🚪",
    "PROFIT": "💰",
    "LOSS": "💸",
    "BREAK": "⚖️",
    "CLOCK": "🕐",
    "TARGET": "🎯",
    "VOLUME": "📊",
    "TDI": "📈",
    "BB": "📉",
    "HTF": "📊",
    "LTF": "⏱️",
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

        # State
        self.active_positions: Dict[str, DCAPosition] = {}
        self.completed_positions: List[DCAPosition] = []
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.market_context: Dict[str, Dict] = {}

        dca_logger.info(f"{EMOJI['START']} DCA_HYBRID: Initialized")
        dca_logger.info(f"  - DCA Levels: {self.DCA_LEVELS}")
        dca_logger.info(f"  - Stop Loss: {self.STOP_LOSS_PERCENT*100:.1f}%")
        dca_logger.info(f"  - Exit Time: {self.EXIT_HOUR:02d}:{self.EXIT_MINUTE:02d} UTC")

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
        }

        if not df_4h.empty and len(df_4h) >= 20:
            htf_analysis = self._analyze_timeframe(df_4h, "4H")
            result['htf'] = htf_analysis
            result['htf_trend'] = htf_analysis.get('trend', 'NEUTRAL')
            result['htf_tdi'] = htf_analysis.get('tdi_level', 50)
            result['htf_zone'] = htf_analysis.get('tdi_zone', 'NEUTRAL')

        if not df_1h.empty and len(df_1h) >= 20:
            mtf_analysis = self._analyze_timeframe(df_1h, "1H")
            result['mtf'] = mtf_analysis
            result['mtf_trend'] = mtf_analysis.get('trend', 'NEUTRAL')
            result['mtf_tdi'] = mtf_analysis.get('tdi_level', 50)
            result['mtf_zone'] = mtf_analysis.get('tdi_zone', 'NEUTRAL')

        if not df_15m.empty and len(df_15m) >= 20:
            ltf_analysis = self._analyze_timeframe(df_15m, "15M")
            result['ltf'] = ltf_analysis
            result['ltf_trend'] = ltf_analysis.get('trend', 'NEUTRAL')
            result['ltf_tdi'] = ltf_analysis.get('tdi_level', 50)
            result['ltf_zone'] = ltf_analysis.get('tdi_zone', 'NEUTRAL')
            result['ltf_bb_position'] = ltf_analysis.get('bb_position', 0.5)

        direction_result = self._detect_direction(result)
        result.update(direction_result)
        self.market_context[symbol] = result

        return result

    def _analyze_timeframe(self, df: pd.DataFrame, tf_name: str) -> Dict[str, Any]:
        try:
            df = Indicators.calculate_tdi(df)
            df = Indicators.calculate_bollinger_bands(df, period=34, dev=1.750)
            df = calculate_heikin_ashi(df)

            if df.empty or len(df) < 20:
                return {'trend': 'NEUTRAL', 'tdi_level': 50, 'tdi_zone': 'NEUTRAL'}

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
            }
        except Exception as e:
            dca_logger.error(f"Error analyzing {tf_name}: {e}")
            return {'trend': 'NEUTRAL', 'tdi_level': 50, 'tdi_zone': 'NEUTRAL'}

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
        if df_15m.empty or len(df_15m) < 20:
            return [
                current_price * (1 - 0.002),
                current_price * (1 - 0.004),
                current_price * (1 - 0.006),
            ]

        last = df_15m.iloc[-1]
        bb_lower = last.get('bb_lower', current_price * 0.98)
        bb_upper = last.get('bb_upper', current_price * 1.02)
        tdi_slow = last.get('tdi_slow_ma', 50)

        if tdi_slow < self.TDI_CENTER and bb_lower > 0:
            base = bb_lower
        elif tdi_slow > self.TDI_CENTER and bb_upper > 0:
            base = bb_upper
        else:
            base = current_price

        levels = []
        spacing = self.DCA_SPACING

        if tdi_slow < self.TDI_CENTER:
            levels.append(base)
            levels.append(base * (1 - spacing))
            levels.append(base * (1 - spacing * 2))
        else:
            levels.append(base)
            levels.append(base * (1 + spacing))
            levels.append(base * (1 + spacing * 2))

        return levels

    def should_enter_dca(self, symbol: str, current_price: float,
                         df_15m: pd.DataFrame, market_context: Dict) -> Dict:
        if symbol in self.active_positions:
            position = self.active_positions[symbol]

            if position.dca_level >= self.DCA_LEVELS:
                return self._no_entry("Max DCA levels reached")

            dca_levels = self.get_dca_levels(symbol, current_price, df_15m)
            next_level = dca_levels[position.dca_level] if len(dca_levels) > position.dca_level else 0

            if position.direction == "LONG" and next_level > 0 and current_price <= next_level:
                return {
                    'should_enter': True,
                    'level': position.dca_level + 1,
                    'entry_price': next_level,
                    'direction': position.direction,
                    'direction_confidence': position.direction_confidence,
                    'direction_reason': position.direction_reason,
                    'reason': f'DCA Level {position.dca_level + 1}'
                }
            elif position.direction == "SHORT" and next_level > 0 and current_price >= next_level:
                return {
                    'should_enter': True,
                    'level': position.dca_level + 1,
                    'entry_price': next_level,
                    'direction': position.direction,
                    'direction_confidence': position.direction_confidence,
                    'direction_reason': position.direction_reason,
                    'reason': f'DCA Level {position.dca_level + 1}'
                }
            else:
                return self._no_entry(f'Waiting for DCA level {position.dca_level + 1}')

        direction = market_context.get('direction', 'NEUTRAL')
        confidence = market_context.get('confidence', 0)

        if confidence < self.MIN_DIRECTION_CONFIDENCE:
            return self._no_entry(f'Confidence too low: {confidence*100:.0f}%')

        if direction not in ['LONG', 'SHORT']:
            return self._no_entry(f'No clear direction: {direction}')

        ltf_trend = market_context.get('ltf_trend', 'NEUTRAL')
        if direction == "LONG" and ltf_trend not in ['BULLISH', 'NEUTRAL_BULLISH']:
            return self._no_entry('LTF not confirming LONG')
        elif direction == "SHORT" and ltf_trend not in ['BEARISH', 'NEUTRAL_BEARISH']:
            return self._no_entry('LTF not confirming SHORT')

        dca_levels = self.get_dca_levels(symbol, current_price, df_15m)
        if not dca_levels:
            return self._no_entry('No DCA levels')

        entry_price = dca_levels[0]

        if direction == "LONG" and current_price > entry_price * 1.001:
            return self._no_entry(f'Price above LONG entry: {current_price:.4f}')
        elif direction == "SHORT" and current_price < entry_price * 0.999:
            return self._no_entry(f'Price below SHORT entry: {current_price:.4f}')

        return {
            'should_enter': True,
            'level': 1,
            'entry_price': entry_price,
            'direction': direction,
            'direction_confidence': confidence,
            'direction_reason': market_context.get('reason', ''),
            'reason': f'First DCA entry - {direction}'
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

        if position.direction == "LONG":
            if current_price <= position.stop_loss:
                return self._exit_decision(current_price, 'Stop loss triggered', 1.0)
        else:
            if current_price >= position.stop_loss:
                return self._exit_decision(current_price, 'Stop loss triggered', 1.0)

        avg_entry = position.total_cost / position.quantity if position.quantity > 0 else 0
        if avg_entry > 0:
            if position.direction == "LONG":
                pnl_percent = (current_price - avg_entry) / avg_entry
            else:
                pnl_percent = (avg_entry - current_price) / avg_entry

            for tp in self.TP_LEVELS:
                if pnl_percent >= tp['percent']:
                    return self._exit_decision(current_price, f'Take profit {tp["label"]}', tp['size'])

        exit_time = current_time.replace(hour=self.EXIT_HOUR, minute=self.EXIT_MINUTE, second=0)
        minutes_until_exit = (exit_time - current_time).total_seconds() / 60

        if minutes_until_exit <= self.MINUTES_BEFORE_EXIT:
            if minutes_until_exit <= 5:
                return self._exit_decision(current_price, 'Time-based full exit', 1.0)
            else:
                sell_percent = (self.MINUTES_BEFORE_EXIT - minutes_until_exit) / self.MINUTES_BEFORE_EXIT
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
                position.dca_entries.append({
                    'price': entry_price,
                    'quantity': quantity,
                    'time': datetime.now().isoformat(),
                    'level': level
                })

                dca_logger.info(f"{EMOJI['DCA']} DCA_ADD: {symbol} Level {level} @ {entry_price:.4f}")
            else:
                position = DCAPosition(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    entry_time=datetime.now(),
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
                                  'time': datetime.now().isoformat(), 'level': level}],
                    stop_loss=stop_loss,
                    direction_confidence=direction_confidence,
                    direction_reason=direction_reason,
                    entry_score=market_context.get('confidence', 0) * 100,
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

            dca_logger.info(f"{EMOJI['EXIT']} DCA_EXIT: {symbol} @ {exit_price:.4f} | PnL: ${pnl:.2f}")
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
        }

    def reset_daily(self):
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.completed_positions = []
        self.market_context = {}


dca_strategy = DCAHybridStrategy()

__all__ = ["dca_strategy", "DCAHybridStrategy", "DCAPosition", "TrendDirection"]
