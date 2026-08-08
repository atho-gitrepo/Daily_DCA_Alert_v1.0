"""
Signal Manager for DCA Day Trading
Manages trading signals with deduplication, expiration, and priority
Version: 1.0.1 - Fixed duplicate prevention
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
    TAKE_PROFIT = "TAKE_PROFIT"
    STOP_LOSS = "STOP_LOSS"
    REBALANCE = "REBALANCE"


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


@dataclass
class TradingSignal:
    """Trading signal data structure."""
    signal_id: str
    symbol: str
    signal_type: SignalType
    direction: str  # LONG or SHORT
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


class SignalManager:
    """
    Manages trading signals with deduplication, expiration, and priority.
    """

    def __init__(self):
        self.active_signals: Dict[str, TradingSignal] = {}
        self.pending_signals: Dict[str, TradingSignal] = {}
        self.executed_signals: Dict[str, TradingSignal] = {}
        self.rejected_signals: Dict[str, TradingSignal] = {}
        self.expired_signals: Dict[str, TradingSignal] = {}

        # Track signals by symbol
        self._symbol_signals: Dict[str, Set[str]] = {}

        # Lock for thread safety
        self._lock = threading.Lock()

        # Statistics
        self.stats = {
            "total_signals": 0,
            "executed_signals": 0,
            "rejected_signals": 0,
            "expired_signals": 0,
            "duplicate_signals_prevented": 0,
        }

        logger.info("SignalManager initialized")

    def create_signal(self, symbol: str, signal_type: SignalType,
                      direction: str, price: float, quantity: float,
                      priority: SignalPriority = SignalPriority.NORMAL,
                      dca_level: int = 1, stop_loss: Optional[float] = None,
                      confidence: float = 0.5, reason: str = "",
                      metadata: Optional[Dict] = None,
                      expires_in_seconds: int = 120) -> Optional[TradingSignal]:
        """
        Create a new trading signal with deduplication.
        """
        with self._lock:
            # Check for duplicate signals - STRONGER DEDUPLICATION
            if self._is_duplicate(symbol, signal_type, direction, dca_level):
                self.stats["duplicate_signals_prevented"] += 1
                logger.warning(f"Duplicate signal prevented for {symbol} {signal_type.value} Level {dca_level}")
                return None

            # Check if there's already an active signal for this symbol and level
            for sig in self.active_signals.values():
                if (sig.symbol == symbol and
                    sig.signal_type == signal_type and
                    sig.dca_level == dca_level and
                    sig.status in [SignalStatus.PENDING, SignalStatus.ACTIVE]):
                    self.stats["duplicate_signals_prevented"] += 1
                    logger.warning(f"Active signal already exists for {symbol} Level {dca_level}")
                    return None

            # Check if there's already a pending signal for this symbol and level
            for sig in self.pending_signals.values():
                if (sig.symbol == symbol and
                    sig.signal_type == signal_type and
                    sig.dca_level == dca_level):
                    self.stats["duplicate_signals_prevented"] += 1
                    logger.warning(f"Pending signal already exists for {symbol} Level {dca_level}")
                    return None

            # Generate unique ID
            signal_id = f"{symbol}_{signal_type.value}_{uuid.uuid4().hex[:8]}"

            # Calculate expiration
            created_at = datetime.now()
            expires_at = created_at + timedelta(seconds=expires_in_seconds)

            # Create signal
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
                metadata=metadata or {}
            )

            # Store signal
            self.pending_signals[signal_id] = signal
            self.stats["total_signals"] += 1

            # Track by symbol
            if symbol not in self._symbol_signals:
                self._symbol_signals[symbol] = set()
            self._symbol_signals[symbol].add(signal_id)

            logger.debug(f"Signal created: {signal_id} for {symbol} Level {dca_level}")
            return signal

    def _is_duplicate(self, symbol: str, signal_type: SignalType,
                      direction: str, dca_level: int) -> bool:
        """Check if a similar signal already exists."""
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
        """Activate a pending signal."""
        with self._lock:
            if signal_id not in self.pending_signals:
                logger.warning(f"Signal {signal_id} not found in pending")
                return False

            signal = self.pending_signals[signal_id]

            # Check if expired
            if datetime.now() > signal.expires_at:
                self._expire_signal(signal_id)
                return False

            # Activate
            signal.status = SignalStatus.ACTIVE
            self.active_signals[signal_id] = signal
            del self.pending_signals[signal_id]

            logger.info(f"Signal activated: {signal_id} for {signal.symbol}")
            return True

    def execute_signal(self, signal_id: str, execution_price: float) -> bool:
        """Execute an active signal."""
        with self._lock:
            if signal_id not in self.active_signals:
                logger.warning(f"Signal {signal_id} not found in active")
                return False

            signal = self.active_signals[signal_id]
            signal.status = SignalStatus.EXECUTED
            signal.executed_at = datetime.now()
            signal.execution_price = execution_price

            self.executed_signals[signal_id] = signal
            del self.active_signals[signal_id]
            self.stats["executed_signals"] += 1

            logger.info(f"Signal executed: {signal_id} at ${execution_price:.4f}")
            return True

    def reject_signal(self, signal_id: str, reason: str = "") -> bool:
        """Reject a signal."""
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
        """Expire a signal."""
        if signal_id in self.pending_signals:
            signal = self.pending_signals[signal_id]
            del self.pending_signals[signal_id]
        elif signal_id in self.active_signals:
            signal = self.active_signals[signal_id]
            del self.active_signals[signal_id]
        else:
            return

        signal.status = SignalStatus.EXPIRED
        self.expired_signals[signal_id] = signal
        self.stats["expired_signals"] += 1
        logger.debug(f"Signal expired: {signal_id}")

    def check_expired_signals(self):
        """Check and expire any expired signals."""
        now = datetime.now()
        expired_ids = []

        # Check pending signals
        for signal_id, signal in self.pending_signals.items():
            if now > signal.expires_at:
                expired_ids.append(signal_id)

        # Check active signals
        for signal_id, signal in self.active_signals.items():
            if now > signal.expires_at:
                expired_ids.append(signal_id)

        for signal_id in expired_ids:
            self._expire_signal(signal_id)

        if expired_ids:
            logger.debug(f"Expired {len(expired_ids)} signals")

    def get_signal(self, signal_id: str) -> Optional[TradingSignal]:
        """Get a signal by ID."""
        for collection in [self.pending_signals, self.active_signals,
                          self.executed_signals, self.rejected_signals,
                          self.expired_signals]:
            if signal_id in collection:
                return collection[signal_id]
        return None

    def get_pending_signals(self, symbol: Optional[str] = None) -> List[TradingSignal]:
        """Get pending signals."""
        if symbol:
            return [s for s in self.pending_signals.values() if s.symbol == symbol]
        return list(self.pending_signals.values())

    def get_active_signals(self, symbol: Optional[str] = None) -> List[TradingSignal]:
        """Get active signals."""
        if symbol:
            return [s for s in self.active_signals.values() if s.symbol == symbol]
        return list(self.active_signals.values())

    def get_all_active_signals(self) -> Dict[str, TradingSignal]:
        """Get all active signals as dict."""
        return self.active_signals.copy()

    def get_recent_signals(self, symbol: str, seconds: int = 60) -> List[TradingSignal]:
        """Get recent signals for a symbol."""
        cutoff = datetime.now() - timedelta(seconds=seconds)
        recent = []

        for signal in list(self.pending_signals.values()) + list(self.active_signals.values()):
            if signal.symbol == symbol and signal.created_at > cutoff:
                recent.append(signal)

        return recent

    def get_active_count(self) -> int:
        """Get number of active signals."""
        return len(self.active_signals)

    def get_pending_count(self) -> int:
        """Get number of pending signals."""
        return len(self.pending_signals)

    def is_symbol_locked(self, symbol: str) -> bool:
        """Check if a symbol has active signals."""
        if symbol not in self._symbol_signals:
            return False

        for signal_id in self._symbol_signals[symbol]:
            if signal_id in self.active_signals:
                return True
        return False

    def remove_signal(self, symbol: str) -> bool:
        """Remove all signals for a symbol."""
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
                del self._symbol_signals[symbol]

            if removed > 0:
                logger.debug(f"Removed {removed} signals for {symbol}")
                return True
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get signal manager statistics."""
        return {
            **self.stats,
            "active_signals": len(self.active_signals),
            "pending_signals": len(self.pending_signals),
            "executed_signals": len(self.executed_signals),
            "rejected_signals": len(self.rejected_signals),
            "expired_signals": len(self.expired_signals),
            "total_signals": self.stats["total_signals"],
        }

    def clear_expired(self):
        """Clear expired signals from memory."""
        with self._lock:
            self.expired_signals.clear()
            logger.debug("Cleared expired signals")

    def clear_all(self):
        """Clear all signals (use with caution)."""
        with self._lock:
            self.pending_signals.clear()
            self.active_signals.clear()
            self.executed_signals.clear()
            self.rejected_signals.clear()
            self.expired_signals.clear()
            self._symbol_signals.clear()
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
