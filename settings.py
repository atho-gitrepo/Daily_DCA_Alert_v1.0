"""
Configuration management for DCA Day Trading Bot
Version: 1.0.0
"""

import os
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
import json

logger = logging.getLogger(__name__)


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class RunMode(Enum):
    DEMO = "DEMO"
    PRODUCTION = "PRODUCTION"
    BACKTEST = "BACKTEST"


# ------------------- Safe Conversion Functions -------------------

def safe_float_env(key: str, default: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    try:
        value = float(os.getenv(key, str(default)))
        if min_val is not None and value < min_val:
            raise ValueError(f"{key}={value} is below minimum {min_val}")
        if max_val is not None and value > max_val:
            raise ValueError(f"{key}={value} exceeds maximum {max_val}")
        return value
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse {key} as float, using default {default}")
        return default


def safe_int_env(key: str, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    try:
        value = int(os.getenv(key, str(default)))
        if min_val is not None and value < min_val:
            raise ValueError(f"{key}={value} is below minimum {min_val}")
        if max_val is not None and value > max_val:
            raise ValueError(f"{key}={value} exceeds maximum {max_val}")
        return value
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse {key} as integer, using default {default}")
        return default


def safe_bool_env(key: str, default: bool = False) -> bool:
    value = os.getenv(key, str(default)).lower()
    return value in ("true", "1", "yes", "on", "t")


def safe_list_env(key: str, default: List[str], delimiter: str = ",") -> List[str]:
    value = os.getenv(key)
    if not value:
        return default
    try:
        items = [item.strip().upper() for item in value.split(delimiter) if item.strip()]
        return items if items else default
    except Exception:
        logger.warning(f"Failed to parse {key} as list, using default")
        return default


# ------------------- Configuration Classes -------------------

@dataclass
class BinanceConfig:
    api_key: str = ""
    api_secret: str = ""
    use_testnet: bool = True
    testnet: bool = True
    request_timeout: int = 30
    rate_limit: int = 1200


@dataclass
class MarketConfig:
    quote_asset: str = "USDT"
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    timeframe: str = "15m"
    htf_timeframe: str = "4h"
    mtf_timeframe: str = "1h"
    ltf_timeframe: str = "15m"
    polling_interval_seconds: int = 30


@dataclass
class DCATradingConfig:
    """DCA Strategy Configuration"""
    # DCA Settings
    dca_levels: int = 3
    dca_spacing: float = 0.002
    position_size_usd: float = 50.0

    # Risk Management
    stop_loss_percent: float = 0.010
    tp_level_1: float = 0.003
    tp_level_2: float = 0.005
    tp_level_3: float = 0.007

    # Time-based Exit
    exit_hour: int = 21
    exit_minute: int = 0
    minutes_before_exit: int = 30

    # TDI Thresholds
    tdi_oversold: float = 25.0
    tdi_soft_buy: float = 35.0
    tdi_center: float = 50.0
    tdi_soft_sell: float = 65.0
    tdi_overbought: float = 75.0

    # Confidence Thresholds
    min_direction_confidence: float = 0.55
    min_htf_alignment: float = 0.60
    min_ltf_confirmation: float = 0.50

    # Volume & Volatility
    min_volume_ratio: float = 0.5
    max_bb_width: float = 0.05

    # Position Management (NEW)
    max_active_positions: int = 3
    max_position_size_pct: float = 0.5

    # Trailing Stop (NEW)
    trailing_stop_percent: float = 0.01
    trailing_activation_pct: float = 0.02


@dataclass
class DCASetupConfig:
    """DCA Setup Configuration for Futures Trading"""
    # Price Settings
    price_drop_steps: float = 0.01  # 1% per step
    take_profit_per_round: float = 0.02  # 2% per round
    investment_leverage: int = 10  # 10x leverage

    # Order Margins
    base_order_margin: float = 50.0  # USD
    dca_order_margin: float = 50.0  # USD
    max_dca_orders: int = 3
    invested_margin: float = 0.0
    auto_add_margin: bool = False

    # Advanced Settings
    price_deviation_multiplier: float = 1.0
    dca_order_size_multiplier: float = 1.0

    # Conditions
    start_condition: str = "MARKET_PRICE"  # MARKET_PRICE, LIMIT, STOP
    stop_condition: str = "TAKE_PROFIT"  # TAKE_PROFIT, STOP_LOSS, TIME
    stop_loss_percent: float = 0.02  # 2%


@dataclass
class PerformanceConfig:
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    cache_max_size: int = 1000
    max_retries: int = 3
    retry_delay_seconds: int = 5


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""
    enabled: bool = False


@dataclass
class MongoDBConfig:
    uri: str = ""
    db_name: str = "trading_bot"
    active_collection: str = "dca_active_positions"
    resolved_collection: str = "dca_resolved_positions"
    enabled: bool = False


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/dca_bot.log"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


@dataclass
class DeploymentConfig:
    environment: Environment = Environment.DEVELOPMENT
    run_mode: RunMode = RunMode.DEMO
    debug: bool = False
    port: int = 8080
    host: str = "0.0.0.0"


# ------------------- Main Config Class -------------------

class Config:
    VERSION = "1.0.0"

    def __init__(self):
        self.binance = BinanceConfig()
        self.market = MarketConfig()
        self.dca = DCATradingConfig()
        self.dca_setup = DCASetupConfig()  # NEW
        self.performance = PerformanceConfig()
        self.telegram = TelegramConfig()
        self.mongodb = MongoDBConfig()
        self.logging = LoggingConfig()
        self.deployment = DeploymentConfig()

        self._load_from_env()
        self._validate()
        self._setup_directories()

        logger.info(f"DCA Config initialized (v{self.VERSION}, environment: {self.deployment.environment.value})")
        logger.info(f"✅ DCA Levels: {self.dca.dca_levels}")
        logger.info(f"✅ Position Size: ${self.dca.position_size_usd}")
        logger.info(f"✅ Stop Loss: {self.dca.stop_loss_percent*100:.1f}%")
        logger.info(f"✅ Exit Time: {self.dca.exit_hour:02d}:{self.dca.exit_minute:02d} UTC")
        logger.info(f"✅ Max Active Positions: {self.dca.max_active_positions}")

    def _load_from_env(self):
        # ====== BINANCE ======
        use_testnet = safe_bool_env("BINANCE_USE_TESTNET", True)
        self.binance = BinanceConfig(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            use_testnet=use_testnet,
            testnet=use_testnet,
            request_timeout=safe_int_env("BINANCE_REQUEST_TIMEOUT", 30, min_val=5, max_val=60),
            rate_limit=safe_int_env("BINANCE_RATE_LIMIT", 1200, min_val=100, max_val=5000),
        )

        # ====== MARKET ======
        default_symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]
        self.market = MarketConfig(
            quote_asset=os.getenv("QUOTE_ASSET", "USDT"),
            symbols=safe_list_env("SYMBOLS", default_symbols),
            timeframe=os.getenv("TIMEFRAME", "15m"),
            htf_timeframe=os.getenv("HTF_TIMEFRAME", "4h"),
            mtf_timeframe=os.getenv("MTF_TIMEFRAME", "1h"),
            ltf_timeframe=os.getenv("LTF_TIMEFRAME", "15m"),
            polling_interval_seconds=safe_int_env("POLLING_INTERVAL_SECONDS", 30, min_val=5, max_val=120),
        )

        # ====== DCA STRATEGY ======
        self.dca = DCATradingConfig(
            dca_levels=safe_int_env("DCA_LEVELS", 3, min_val=1, max_val=5),
            dca_spacing=safe_float_env("DCA_SPACING", 0.002, min_val=0.001, max_val=0.01),
            position_size_usd=safe_float_env("POSITION_SIZE_USD", 50, min_val=5, max_val=1000),
            stop_loss_percent=safe_float_env("STOP_LOSS_PERCENT", 0.010, min_val=0.002, max_val=0.03),
            tp_level_1=safe_float_env("TP_LEVEL_1", 0.003, min_val=0.001, max_val=0.01),
            tp_level_2=safe_float_env("TP_LEVEL_2", 0.005, min_val=0.002, max_val=0.02),
            tp_level_3=safe_float_env("TP_LEVEL_3", 0.007, min_val=0.003, max_val=0.03),
            exit_hour=safe_int_env("EXIT_HOUR", 21, min_val=0, max_val=23),
            exit_minute=safe_int_env("EXIT_MINUTE", 0, min_val=0, max_val=59),
            minutes_before_exit=safe_int_env("MINUTES_BEFORE_EXIT", 30, min_val=5, max_val=120),
            tdi_oversold=safe_float_env("TDI_OVERSOLD", 25.0, min_val=10, max_val=35),
            tdi_soft_buy=safe_float_env("TDI_SOFT_BUY", 35.0, min_val=25, max_val=45),
            tdi_center=safe_float_env("TDI_CENTER", 50.0, min_val=40, max_val=60),
            tdi_soft_sell=safe_float_env("TDI_SOFT_SELL", 65.0, min_val=55, max_val=75),
            tdi_overbought=safe_float_env("TDI_OVERBOUGHT", 75.0, min_val=65, max_val=85),
            min_direction_confidence=safe_float_env("MIN_DIRECTION_CONFIDENCE", 0.55, min_val=0.3, max_val=0.8),
            min_htf_alignment=safe_float_env("MIN_HTF_ALIGNMENT", 0.60, min_val=0.3, max_val=0.9),
            min_ltf_confirmation=safe_float_env("MIN_LTF_CONFIRMATION", 0.50, min_val=0.3, max_val=0.8),
            min_volume_ratio=safe_float_env("MIN_VOLUME_RATIO", 0.5, min_val=0.1, max_val=2.0),
            max_bb_width=safe_float_env("MAX_BB_WIDTH", 0.05, min_val=0.01, max_val=0.10),
            # NEW: Position Management
            max_active_positions=safe_int_env("MAX_ACTIVE_POSITIONS", 3, min_val=1, max_val=10),
            max_position_size_pct=safe_float_env("MAX_POSITION_SIZE_PCT", 0.5, min_val=0.1, max_val=1.0),
            # NEW: Trailing Stop
            trailing_stop_percent=safe_float_env("TRAILING_STOP_PERCENT", 0.01, min_val=0.005, max_val=0.02),
            trailing_activation_pct=safe_float_env("TRAILING_ACTIVATION_PCT", 0.02, min_val=0.01, max_val=0.05),
        )

        # ====== DCA SETUP (NEW) ======
        self.dca_setup = DCASetupConfig(
            price_drop_steps=safe_float_env("DCA_PRICE_DROP_STEPS", 0.01, min_val=0.001, max_val=0.05),
            take_profit_per_round=safe_float_env("DCA_TAKE_PROFIT", 0.02, min_val=0.005, max_val=0.05),
            investment_leverage=safe_int_env("DCA_LEVERAGE", 10, min_val=1, max_val=20),
            base_order_margin=safe_float_env("DCA_BASE_MARGIN", 50.0, min_val=5, max_val=1000),
            dca_order_margin=safe_float_env("DCA_ORDER_MARGIN", 50.0, min_val=5, max_val=1000),
            max_dca_orders=safe_int_env("DCA_MAX_ORDERS", 3, min_val=1, max_val=10),
            invested_margin=safe_float_env("DCA_INVESTED_MARGIN", 0.0),
            auto_add_margin=safe_bool_env("DCA_AUTO_ADD_MARGIN", False),
            price_deviation_multiplier=safe_float_env("DCA_PRICE_DEVIATION", 1.0, min_val=0.5, max_val=2.0),
            dca_order_size_multiplier=safe_float_env("DCA_SIZE_MULTIPLIER", 1.0, min_val=0.5, max_val=2.0),
            start_condition=os.getenv("DCA_START_CONDITION", "MARKET_PRICE"),
            stop_condition=os.getenv("DCA_STOP_CONDITION", "TAKE_PROFIT"),
            stop_loss_percent=safe_float_env("DCA_STOP_LOSS", 0.02, min_val=0.005, max_val=0.05),
        )

        # ====== PERFORMANCE ======
        self.performance = PerformanceConfig(
            cache_enabled=safe_bool_env("CACHE_ENABLED", True),
            cache_ttl_seconds=safe_int_env("CACHE_TTL_SECONDS", 300, min_val=30, max_val=3600),
            cache_max_size=safe_int_env("CACHE_MAX_SIZE", 1000, min_val=10, max_val=10000),
            max_retries=safe_int_env("MAX_RETRIES", 3, min_val=1, max_val=10),
            retry_delay_seconds=safe_int_env("RETRY_DELAY_SECONDS", 5, min_val=1, max_val=30),
        )

        # ====== TELEGRAM ======
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram = TelegramConfig(
            bot_token=telegram_token,
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            enabled=bool(telegram_token),
        )

        # ====== MONGODB ======
        mongodb_uri = os.getenv("MONGODB_URI", os.getenv("MONGODB_URL", ""))
        self.mongodb = MongoDBConfig(
            uri=mongodb_uri,
            db_name=os.getenv("MONGODB_DB", os.getenv("MONGO_DB", "trading_bot")),
            active_collection=os.getenv("MONGODB_ACTIVE_COLLECTION", "dca_active_positions"),
            resolved_collection=os.getenv("MONGODB_RESOLVED_COLLECTION", "dca_resolved_positions"),
            enabled=bool(mongodb_uri),
        )

        # ====== LOGGING ======
        self.logging = LoggingConfig(
            level=os.getenv("LOG_LEVEL", "INFO").upper(),
            file=os.getenv("LOG_FILE", "logs/dca_bot.log"),
            format=os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"),
        )

        # ====== DEPLOYMENT ======
        env_str = os.getenv("ENVIRONMENT", "development").lower().strip()
        try:
            environment = Environment(env_str)
        except ValueError:
            logger.warning(f"Invalid environment '{env_str}', using DEVELOPMENT")
            environment = Environment.DEVELOPMENT

        run_mode_str = os.getenv("RUN_MODE", "DEMO").upper().strip()
        try:
            run_mode = RunMode(run_mode_str)
        except ValueError:
            logger.warning(f"Invalid run mode '{run_mode_str}', using DEMO")
            run_mode = RunMode.DEMO

        self.deployment = DeploymentConfig(
            environment=environment,
            run_mode=run_mode,
            debug=safe_bool_env("DEBUG", False),
            port=safe_int_env("PORT", 8080, min_val=1024, max_val=65535),
            host=os.getenv("HOST", "0.0.0.0"),
        )

    def _validate(self):
        errors = []
        warnings = []

        if self.deployment.environment == Environment.PRODUCTION:
            if not self.binance.api_key:
                errors.append("BINANCE_API_KEY is required in production")
            if not self.binance.api_secret:
                errors.append("BINANCE_API_SECRET is required in production")

        # Validate DCA config
        if self.dca.dca_levels < 1:
            errors.append("DCA_LEVELS must be at least 1")

        if self.dca.stop_loss_percent <= 0:
            errors.append("STOP_LOSS_PERCENT must be positive")

        if self.dca.position_size_usd <= 0:
            warnings.append("POSITION_SIZE_USD is 0 - bot will not trade")

        # TP levels should be increasing
        if not (self.dca.tp_level_1 < self.dca.tp_level_2 < self.dca.tp_level_3):
            warnings.append("TP levels should be increasing: TP1 < TP2 < TP3")

        # Validate DCA Setup
        if self.dca_setup.max_dca_orders < 1:
            warnings.append("DCA_MAX_ORDERS should be at least 1")

        if self.dca_setup.stop_loss_percent <= 0:
            warnings.append("DCA_STOP_LOSS must be positive")

        for warning in warnings:
            logger.warning(f"Configuration warning: {warning}")

        if errors:
            error_msg = "Configuration errors:\n" + "\n".join(f"  - {err}" for err in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _setup_directories(self):
        directories = ["logs", "data"]
        for directory in directories:
            try:
                Path(directory).mkdir(exist_ok=True)
            except Exception as e:
                logger.warning(f"Failed to create directory {directory}: {e}")

    def is_demo(self) -> bool:
        """Check if running in demo mode."""
        return self.deployment.run_mode == RunMode.DEMO

    def get_dca_config(self) -> Dict[str, Any]:
        """Get DCA strategy configuration."""
        return {
            "dca_levels": self.dca.dca_levels,
            "dca_spacing": self.dca.dca_spacing,
            "position_size_usd": self.dca.position_size_usd,
            "stop_loss_percent": self.dca.stop_loss_percent,
            "tp_levels": [
                self.dca.tp_level_1,
                self.dca.tp_level_2,
                self.dca.tp_level_3,
            ],
            "exit_hour": self.dca.exit_hour,
            "exit_minute": self.dca.exit_minute,
            "minutes_before_exit": self.dca.minutes_before_exit,
            "max_active_positions": self.dca.max_active_positions,
            "trailing_stop_percent": self.dca.trailing_stop_percent,
            "trailing_activation_pct": self.dca.trailing_activation_pct,
        }

    def get_dca_setup_config(self) -> Dict[str, Any]:
        """Get DCA setup configuration for display."""
        total_margin = self.dca_setup.base_order_margin + (self.dca_setup.dca_order_margin * self.dca_setup.max_dca_orders)
        max_loss = total_margin * self.dca_setup.stop_loss_percent
        risk = self.dca_setup.stop_loss_percent
        reward = self.dca_setup.take_profit_per_round
        risk_reward = round(reward / risk, 2) if risk > 0 else 0

        return {
            "price_drop_steps": f"{self.dca_setup.price_drop_steps * 100:.1f}%",
            "take_profit_per_round": f"{self.dca_setup.take_profit_per_round * 100:.1f}%",
            "investment_leverage": f"{self.dca_setup.investment_leverage}x",
            "base_order_margin": f"${self.dca_setup.base_order_margin:.2f}",
            "dca_order_margin": f"${self.dca_setup.dca_order_margin:.2f}",
            "max_dca_orders": self.dca_setup.max_dca_orders,
            "invested_margin": f"${self.dca_setup.invested_margin:.2f}",
            "auto_add_margin": "Enabled" if self.dca_setup.auto_add_margin else "Disabled",
            "price_deviation_multiplier": self.dca_setup.price_deviation_multiplier,
            "dca_order_size_multiplier": self.dca_setup.dca_order_size_multiplier,
            "start_condition": self.dca_setup.start_condition,
            "stop_condition": self.dca_setup.stop_condition,
            "stop_loss_percent": f"{self.dca_setup.stop_loss_percent * 100:.1f}%",
            "total_margin_required": f"${total_margin:.2f}",
            "max_loss_per_trade": f"${max_loss:.2f}",
            "risk_reward_ratio": risk_reward,
        }


# Singleton instance
config = Config()

__all__ = [
    "config",
    "Config",
    "Environment",
    "RunMode",
]
