"""
Signal Manager for DCA Day Trading
Manages trading signals with deduplication, expiration, and priority
Version: 1.0.3 - Fixed update_dca_setup_status method signature
"""

import logging
import uuid
from typing import Dict, Optional, List, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class SignalType(Enum):
    DCA_ENTRY = "DCA_ENTRY"
    DCA_EXIT = "DCA_EXIT"
    DCA_SETUP = "DCA_SETUP"
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    REBALANCE = "REBALANCE"
    TRAILING_STOP = "TRAILING_STOP"


class SignalPriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class SignalStatus(Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    SETUP = "SETUP"


@dataclass
class TradingSignal:
    """Trading signal data structure."""
    signal_id: str
    symbol: str
    signal_type: SignalType
    direction: str
    price: float
    quantity: float
    priority: SignalPriority
    status: SignalStatus
    created_at: datetime
    expires_at: datetime
    executed_at: Optional[datetime] = None
    execution_price: Optional[float] = None
    dca_level: int = 1
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    confidence: float = 0.5
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    setup_info: Optional[Dict[str, Any]] = None
    execution_time_ms: Optional[float] = None


class SignalManager:
    """
    Manages trading signals with deduplication, expiration, and priority.
    Enhanced with DCA setup tracking and performance metrics.
    """

    def __init__(self):
        self.active_signals: Dict[str, TradingSignal] = {}
        self.pending_signals: Dict[str, TradingSignal] = {}
        self.executed_signals: Dict[str, TradingSignal] = {}
        self.rejected_signals: Dict[str, TradingSignal] = {}
        self.expired_signals: Dict[str, TradingSignal] = {}
        self.setup_signals: Dict[str, TradingSignal] = {}

        self._symbol_signals: Dict[str, Set[str]] = {}
        self._dca_setups: Dict[str, Dict[str, Any]] = {}

        self._lock = threading.Lock()

        self.stats = {
            "total_signals": 0,
            "executed_signals": 0,
            "rejected_signals": 0,
            "expired_signals": 0,
            "duplicate_signals_prevented": 0,
            "total_pnl": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "average_pnl": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "total_trades": 0,
            "dca_setups_created": 0,
            "dca_setups_active": 0,
            "dca_setups_completed": 0,
        }

        logger.info("SignalManager initialized (v1.0.3)")

    def create_signal(self, symbol: str, signal_type: SignalType,
                      direction: str, price: float, quantity: float,
                      priority: SignalPriority = SignalPriority.NORMAL,
                      dca_level: int = 1, stop_loss: Optional[float] = None,
                      confidence: float = 0.5, reason: str = "",
                      metadata: Optional[Dict] = None,
                      expires_in_seconds: int = 120,
                      setup_info: Optional[Dict] = None) -> Optional[TradingSignal]:

        with self._lock:
            if signal_type == SignalType.DCA_SETUP:
                return self._create_setup_signal(symbol, price, quantity, setup_info, metadata)

            if self._is_duplicate(symbol, signal_type, direction, dca_level):
                self.stats["duplicate_signals_prevented"] += 1
                logger.warning(f"Duplicate signal prevented for {symbol} {signal_type.value} Level {dca_level}")
                return None

            for sig in self.active_signals.values():
                if (sig.symbol == symbol and
                    sig.signal_type == signal_type and
                    sig.dca_level == dca_level and
                    sig.status in [SignalStatus.PENDING, SignalStatus.ACTIVE]):
                    self.stats["duplicate_signals_prevented"] += 1
                    logger.warning(f"Active signal already exists for {symbol} Level {dca_level}")
                    return None

            for sig in self.pending_signals.values():
                if (sig.symbol == symbol and
                    sig.signal_type == signal_type and
                    sig.dca_level == dca_level):
                    self.stats["duplicate_signals_prevented"] += 1
                    logger.warning(f"Pending signal already exists for {symbol} Level {dca_level}")
                    return None

            signal_id = f"{symbol}_{signal_type.value}_{uuid.uuid4().hex[:8]}"
            created_at = datetime.now()
            expires_at = created_at + timedelta(seconds=expires_in_seconds)

            signal = TradingSignal(
                signal_id=signal_id,
                symbol=symbol,
                signal_type=signal_type,
                direction=direction,
                price=price,
                quantity=quantity,
                priority=priority,
                status=SignalStatus.PENDING,
                created_at=created_at,
                expires_at=expires_at,
                dca_level=dca_level,
                stop_loss=stop_loss,
                confidence=confidence,
                reason=reason,
                metadata=metadata or {},
                setup_info=setup_info
            )

            self.pending_signals[signal_id] = signal
            self.stats["total_signals"] += 1

            if symbol not in self._symbol_signals:
                self._symbol_signals[symbol] = set()
            self._symbol_signals[symbol].add(signal_id)

            logger.debug(f"Signal created: {signal_id} for {symbol} Level {dca_level}")
            return signal

    def _create_setup_signal(self, symbol: str, price: float, quantity: float,
                             setup_info: Optional[Dict], metadata: Optional[Dict]) -> Optional[TradingSignal]:
        signal_id = f"{symbol}_DCA_SETUP_{uuid.uuid4().hex[:8]}"
        created_at = datetime.now()
        expires_at = created_at + timedelta(hours=24)

        signal = TradingSignal(
            signal_id=signal_id,
            symbol=symbol,
            signal_type=SignalType.DCA_SETUP,
            direction="NEUTRAL",
            price=price,
            quantity=quantity,
            priority=SignalPriority.NORMAL,
            status=SignalStatus.SETUP,
            created_at=created_at,
            expires_at=expires_at,
            dca_level=0,
            confidence=1.0,
            reason="DCA Setup Created",
            metadata=metadata or {},
            setup_info=setup_info or {}
        )

        self.setup_signals[signal_id] = signal
        self.stats["dca_setups_created"] += 1
        self.stats["dca_setups_active"] += 1

        self._dca_setups[symbol] = {
            "signal_id": signal_id,
            "price": price,
            "quantity": quantity,
            "created_at": created_at,
            "setup_info": setup_info,
            "status": "ACTIVE"
        }

        logger.info(f"DCA Setup created: {signal_id} for {symbol}")
        return signal

    def _is_duplicate(self, symbol: str, signal_type: SignalType,
                      direction: str, dca_level: int) -> bool:
        if symbol not in self._symbol_signals:
            return False

        for signal_id in self._symbol_signals[symbol]:
            if signal_id in self.pending_signals:
                signal = self.pending_signals[signal_id]
                if (signal.signal_type == signal_type and
                    signal.direction == direction and
                    signal.dca_level == dca_level and
                    signal.status in [SignalStatus.PENDING, SignalStatus.ACTIVE]):
                    return True
        return False

    def activate_signal(self, signal_id: str) -> bool:
        with self._lock:
            if signal_id not in self.pending_signals:
                logger.warning(f"Signal {signal_id} not found in pending")
                return False

            signal = self.pending_signals[signal_id]

            if datetime.now() > signal.expires_at:
                self._expire_signal(signal_id)
                return False

            signal.status = SignalStatus.ACTIVE
            self.active_signals[signal_id] = signal
            del self.pending_signals[signal_id]

            logger.info(f"Signal activated: {signal_id} for {signal.symbol}")
            return True

    def execute_signal(self, signal_id: str, execution_price: float,
                       pnl: Optional[float] = None,
                       pnl_percent: Optional[float] = None) -> bool:
        with self._lock:
            if signal_id in self.active_signals:
                signal = self.active_signals[signal_id]
                del self.active_signals[signal_id]
            elif signal_id in self.pending_signals:
                signal = self.pending_signals[signal_id]
                del self.pending_signals[signal_id]
            else:
                logger.warning(f"Signal {signal_id} not found in active or pending")
                return False

            signal.status = SignalStatus.EXECUTED
            signal.executed_at = datetime.now()
            signal.execution_price = execution_price

            if pnl is not None:
                signal.pnl = pnl
                signal.pnl_percent = pnl_percent
                self._update_pnl_stats(pnl)

            if signal.created_at:
                signal.execution_time_ms = (signal.executed_at - signal.created_at).total_seconds() * 1000

            self.executed_signals[signal_id] = signal
            self.stats["executed_signals"] += 1

            if signal.signal_type == SignalType.DCA_ENTRY and signal.symbol in self._dca_setups:
                self._dca_setups[signal.symbol]["status"] = "ACTIVE_TRADE"
                self._dca_setups[signal.symbol]["entry_price"] = execution_price
                self._dca_setups[signal.symbol]["entry_time"] = signal.executed_at

            logger.info(f"Signal executed: {signal_id} at ${execution_price:.4f}" +
                       (f" | PnL: ${pnl:.2f}" if pnl is not None else ""))
            return True

    def _update_pnl_stats(self, pnl: float):
        self.stats["total_pnl"] += pnl
        self.stats["total_trades"] += 1

        if pnl > 0:
            self.stats["winning_trades"] += 1
            if pnl > self.stats["best_trade"]:
                self.stats["best_trade"] = pnl
        else:
            self.stats["losing_trades"] += 1
            if pnl < self.stats["worst_trade"]:
                self.stats["worst_trade"] = pnl

        self.stats["win_rate"] = (self.stats["winning_trades"] / self.stats["total_trades"]) * 100 if self.stats["total_trades"] > 0 else 0
        self.stats["average_pnl"] = self.stats["total_pnl"] / self.stats["total_trades"] if self.stats["total_trades"] > 0 else 0

    def reject_signal(self, signal_id: str, reason: str = "") -> bool:
        with self._lock:
            if signal_id in self.pending_signals:
                signal = self.pending_signals[signal_id]
                del self.pending_signals[signal_id]
            elif signal_id in self.active_signals:
                signal = self.active_signals[signal_id]
                del self.active_signals[signal_id]
            else:
                logger.warning(f"Signal {signal_id} not found")
                return False

            signal.status = SignalStatus.REJECTED
            signal.error = reason
            self.rejected_signals[signal_id] = signal
            self.stats["rejected_signals"] += 1

            logger.info(f"Signal rejected: {signal_id} - {reason}")
            return True

    def _expire_signal(self, signal_id: str):
        if signal_id in self.pending_signals:
            signal = self.pending_signals[signal_id]
            del self.pending_signals[signal_id]
        elif signal_id in self.active_signals:
            signal = self.active_signals[signal_id]
            del self.active_signals[signal_id]
        elif signal_id in self.setup_signals:
            signal = self.setup_signals[signal_id]
            del self.setup_signals[signal_id]
            if signal.symbol in self._dca_setups:
                self._dca_setups[signal.symbol]["status"] = "EXPIRED"
            return
        else:
            return

        signal.status = SignalStatus.EXPIRED
        self.expired_signals[signal_id] = signal
        self.stats["expired_signals"] += 1
        logger.debug(f"Signal expired: {signal_id}")

    def check_expired_signals(self):
        now = datetime.now()
        expired_ids = []

        for signal_id, signal in self.pending_signals.items():
            if now > signal.expires_at:
                expired_ids.append(signal_id)

        for signal_id, signal in self.active_signals.items():
            if now > signal.expires_at:
                expired_ids.append(signal_id)

        for signal_id, signal in self.setup_signals.items():
            if now > signal.expires_at:
                expired_ids.append(signal_id)

        for signal_id in expired_ids:
            self._expire_signal(signal_id)

        if expired_ids:
            logger.debug(f"Expired {len(expired_ids)} signals")

    def get_signal(self, signal_id: str) -> Optional[TradingSignal]:
        for collection in [self.pending_signals, self.active_signals,
                          self.executed_signals, self.rejected_signals,
                          self.expired_signals, self.setup_signals]:
            if signal_id in collection:
                return collection[signal_id]
        return None

    def get_pending_signals(self, symbol: Optional[str] = None) -> List[TradingSignal]:
        if symbol:
            return [s for s in self.pending_signals.values() if s.symbol == symbol]
        return list(self.pending_signals.values())

    def get_active_signals(self, symbol: Optional[str] = None) -> List[TradingSignal]:
        if symbol:
            return [s for s in self.active_signals.values() if s.symbol == symbol]
        return list(self.active_signals.values())

    def get_all_active_signals(self) -> Dict[str, TradingSignal]:
        return self.active_signals.copy()

    def get_setup_signals(self, symbol: Optional[str] = None) -> List[TradingSignal]:
        if symbol:
            return [s for s in self.setup_signals.values() if s.symbol == symbol]
        return list(self.setup_signals.values())

    def get_dca_setup(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._dca_setups.get(symbol)

    def get_all_dca_setups(self) -> Dict[str, Dict[str, Any]]:
        return self._dca_setups.copy()

    def update_dca_setup_status(self, symbol: str, status: str,
                                 exit_price: Optional[float] = None,
                                 pnl: Optional[float] = None,
                                 entry_price: Optional[float] = None) -> bool:
        """Update DCA setup status with optional entry_price parameter."""
        with self._lock:
            if symbol not in self._dca_setups:
                return False

            self._dca_setups[symbol]["status"] = status
            
            if entry_price is not None:
                self._dca_setups[symbol]["entry_price"] = entry_price
                self._dca_setups[symbol]["entry_time"] = datetime.now()
            
            if exit_price is not None:
                self._dca_setups[symbol]["exit_price"] = exit_price
                self._dca_setups[symbol]["exit_time"] = datetime.now()
                
            if pnl is not None:
                self._dca_setups[symbol]["pnl"] = pnl

            if status in ["CLOSED", "COMPLETED", "STOPPED"]:
                self.stats["dca_setups_completed"] += 1
                self.stats["dca_setups_active"] -= 1

            logger.info(f"DCA Setup {symbol} status updated: {status}")
            return True

    def get_recent_signals(self, symbol: str, seconds: int = 60) -> List[TradingSignal]:
        cutoff = datetime.now() - timedelta(seconds=seconds)
        recent = []

        for signal in list(self.pending_signals.values()) + list(self.active_signals.values()):
            if signal.symbol == symbol and signal.created_at > cutoff:
                recent.append(signal)

        return recent

    def get_active_count(self) -> int:
        return len(self.active_signals)

    def get_pending_count(self) -> int:
        return len(self.pending_signals)

    def is_symbol_locked(self, symbol: str) -> bool:
        if symbol not in self._symbol_signals:
            return False

        for signal_id in self._symbol_signals[symbol]:
            if signal_id in self.active_signals:
                return True
        return False

    def remove_signal(self, symbol: str) -> bool:
        with self._lock:
            removed = 0
            if symbol in self._symbol_signals:
                for signal_id in list(self._symbol_signals[symbol]):
                    if signal_id in self.pending_signals:
                        del self.pending_signals[signal_id]
                        removed += 1
                    elif signal_id in self.active_signals:
                        del self.active_signals[signal_id]
                        removed += 1
                    elif signal_id in self.setup_signals:
                        del self.setup_signals[signal_id]
                        removed += 1
                del self._symbol_signals[symbol]

            if symbol in self._dca_setups:
                del self._dca_setups[symbol]

            if removed > 0:
                logger.debug(f"Removed {removed} signals for {symbol}")
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "active_signals": len(self.active_signals),
            "pending_signals": len(self.pending_signals),
            "executed_signals": len(self.executed_signals),
            "rejected_signals": len(self.rejected_signals),
            "expired_signals": len(self.expired_signals),
            "setup_signals": len(self.setup_signals),
            "total_signals": self.stats["total_signals"],
            "dca_setups_active": len(self._dca_setups),
        }

    def get_performance_summary(self) -> Dict[str, Any]:
        return {
            "total_pnl": self.stats["total_pnl"],
            "total_trades": self.stats["total_trades"],
            "winning_trades": self.stats["winning_trades"],
            "losing_trades": self.stats["losing_trades"],
            "win_rate": self.stats["win_rate"],
            "average_pnl": self.stats["average_pnl"],
            "best_trade": self.stats["best_trade"],
            "worst_trade": self.stats["worst_trade"],
            "dca_setups_active": self.stats["dca_setups_active"],
            "dca_setups_completed": self.stats["dca_setups_completed"],
        }

    def clear_expired(self):
        with self._lock:
            self.expired_signals.clear()
            logger.debug("Cleared expired signals")

    def clear_all(self):
        with self._lock:
            self.pending_signals.clear()
            self.active_signals.clear()
            self.executed_signals.clear()
            self.rejected_signals.clear()
            self.expired_signals.clear()
            self.setup_signals.clear()
            self._symbol_signals.clear()
            self._dca_setups.clear()
            logger.warning("All signals cleared")


# Singleton instance
signal_manager = SignalManager()

__all__ = [
    "signal_manager",
    "SignalManager",
    "SignalType",
    "SignalPriority",
    "SignalStatus",
    "TradingSignal",
]