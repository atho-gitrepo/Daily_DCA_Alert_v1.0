"""
Telegram Bot Integration for DCA Day Trading
Sends notifications for entries, exits, daily summaries, and DCA setup
Version: 1.0.1 - Added DCA Setup and Performance notifications
"""

import logging
import requests
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime
from queue import Queue

from settings import config

logger = logging.getLogger(__name__)

EMOJI = {
    "BUY": "🟢",
    "SELL": "🔴",
    "DCA": "📊",
    "ENTRY": "🎯",
    "EXIT": "🚪",
    "PROFIT": "💰",
    "LOSS": "💸",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
    "START": "🚀",
    "STOP": "🛑",
    "SUCCESS": "✅",
    "CLOCK": "🕐",
    "TARGET": "🎯",
    "VOLUME": "📊",
    "TELEGRAM": "📨",
    "HEALTH": "💚",
    "FIRE": "🔥",
    "TRIANGLE": "🔺",
    "DASH": "➖",
    "SETUP": "⚙️",
    "CONFIG": "🔧",
    "LEVEL": "📈",
    "MARGIN": "💵",
    "RISK": "🛡️",
    "TRENDING": "📉",
    "STOP_LOSS": "⛔",
    "TAKE_PROFIT": "🎯",
}


class TelegramBot:
    """Telegram bot for DCA trading notifications."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or config.telegram.bot_token
        self.chat_id = chat_id or config.telegram.chat_id
        self.enabled = bool(self.token and self.chat_id)
        self.message_queue = Queue()
        self.running = True
        self._last_setup_message: Dict[str, datetime] = {}  # Track last setup message per symbol

        if self.enabled:
            self._start_worker()
            logger.info(f"{EMOJI['TELEGRAM']} Telegram bot initialized")
            self._send_startup_message()
        else:
            logger.warning(f"{EMOJI['WARNING']} Telegram bot disabled - no token/chat_id")

    def _start_worker(self):
        """Start background worker for queued messages."""
        thread = threading.Thread(target=self._worker_loop, daemon=True)
        thread.start()

    def _worker_loop(self):
        """Process messages from queue."""
        while self.running:
            try:
                message = self.message_queue.get(timeout=1)
                self._send_message_sync(message)
            except Exception as e:
                if str(e) != "":
                    logger.debug(f"Telegram worker: {e}")

    def _send_startup_message(self):
        """Send startup notification."""
        separator = "=" * 30
        message = (
            f"{EMOJI['START']} <b>DCA Day Trading Bot</b>\n"
            f"{separator}\n\n"
            f"<b>Status:</b> Online {EMOJI['HEALTH']}\n"
            f"<b>Strategy:</b> Hybrid DCA + Super TDI\n"
            f"<b>DCA Levels:</b> {config.dca.dca_levels}\n"
            f"<b>Position Size:</b> ${config.dca.position_size_usd}\n"
            f"<b>Stop Loss:</b> {config.dca.stop_loss_percent*100:.1f}%\n"
            f"<b>Exit Time:</b> {config.dca.exit_hour:02d}:{config.dca.exit_minute:02d} UTC\n\n"
            f"<b>Monitoring:</b>\n"
            f"{', '.join(config.market.symbols[:5])}\n"
            f"{EMOJI['TELEGRAM']} <i>Ready for action!</i>"
        )
        self.queue_message(message)

    def _send_message_sync(self, message: str):
        """Send message synchronously."""
        if not self.enabled:
            return

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }

            response = requests.post(url, json=payload, timeout=5)

            if response.status_code != 200:
                logger.error(f"Telegram send failed: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"Telegram error: {e}")

    def queue_message(self, message: str):
        """Queue message for sending."""
        if not self.enabled:
            return

        # Truncate if too long
        if len(message) > 4000:
            message = message[:3500] + "\n\n... (truncated)"

        self.message_queue.put(message)

    def send_message(self, message: str, async_mode: bool = True):
        """Send message (async by default)."""
        if async_mode:
            self.queue_message(message)
        else:
            self._send_message_sync(message)

    # ==================== DCA SETUP MESSAGES ====================

    def send_dca_setup(self, symbol: str, setup_info: Dict[str, Any],
                       current_price: float, force: bool = False) -> None:
        """
        Send DCA setup information to Telegram.
        Includes all DCA configuration details.
        """
        if not self.enabled:
            return

        # Rate limit: Don't send same setup more than once per hour
        if not force:
            if symbol in self._last_setup_message:
                time_since = (datetime.now() - self._last_setup_message[symbol]).total_seconds()
                if time_since < 3600:  # 1 hour
                    return

        self._last_setup_message[symbol] = datetime.now()

        separator = "=" * 30

        # Price Settings
        price_settings = setup_info.get('price_settings', {})
        order_margins = setup_info.get('order_margins', {})
        dca_levels = setup_info.get('dca_levels', {})
        conditions = setup_info.get('conditions', {})
        advanced = setup_info.get('advanced', {})
        risk_mgmt = setup_info.get('risk_management', {})

        message = (
            f"{EMOJI['SETUP']} <b>FUTURES DCA SETUP</b> {EMOJI['SETUP']}\n"
            f"{separator}\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Current Price:</b> ${current_price:.2f}\n\n"

            f"<b>{EMOJI['CONFIG']} Price Settings</b>\n"
            f"• Price Drop Steps: {price_settings.get('price_drop_steps', 'N/A')}\n"
            f"• Take Profit Per Round: {price_settings.get('take_profit_per_round', 'N/A')}\n"
            f"• Investment: {price_settings.get('investment_leverage', 'N/A')}\n\n"

            f"<b>{EMOJI['MARGIN']} Order Margins</b>\n"
            f"• Base Order: {order_margins.get('base_order_margin', 'N/A')}\n"
            f"• DCA Order: {order_margins.get('dca_order_margin', 'N/A')}\n"
            f"• Max DCA Orders: {order_margins.get('max_dca_orders', 'N/A')}\n"
            f"• Invested Margin: {order_margins.get('invested_margin', 'N/A')}\n"
            f"• Auto-add Margin: {order_margins.get('auto_add_margin', 'N/A')}\n\n"

            f"<b>{EMOJI['LEVEL']} DCA Order Details</b>\n"
        )

        # Add DCA levels
        levels = dca_levels.get('levels', [])
        for level in levels:
            message += (
                f"• Level {level.get('level', 'N/A')}: "
                f"${level.get('price', 0):.2f} | "
                f"{level.get('drop_from_entry', 'N/A')} | "
                f"Margin: ${level.get('margin', 0):.2f} | "
                f"Size: ${level.get('size', 0):.2f}\n"
            )

        message += (
            f"\n<b>Total Margin Required:</b> ${dca_levels.get('total_margin_required', 0):.2f}\n\n"

            f"<b>{EMOJI['TARGET']} Start Condition:</b> {conditions.get('start_condition', 'N/A')}\n"
            f"<b>{EMOJI['STOP_LOSS']} Stop Condition:</b> {conditions.get('stop_condition', 'N/A')}\n"
            f"<b>{EMOJI['STOP_LOSS']} Stop Loss:</b> {risk_mgmt.get('stop_loss', 'N/A')}\n\n"

            f"<b>{EMOJI['CONFIG']} Advanced</b>\n"
            f"• Price Deviation Multiplier: {advanced.get('price_deviation_multiplier', 'N/A')}\n"
            f"• DCA Order Size Multiplier: {advanced.get('dca_order_size_multiplier', 'N/A')}\n\n"

            f"<b>{EMOJI['RISK']} Risk Management</b>\n"
            f"• Max Loss Per Trade: {risk_mgmt.get('max_loss_per_trade', 'N/A')}\n"
            f"• Risk/Reward Ratio: {risk_mgmt.get('risk_reward_ratio', 'N/A')}\n"
            f"• Total Margin Required: {risk_mgmt.get('total_margin_required', 'N/A')}\n\n"

            f"{EMOJI['CLOCK']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        self.queue_message(message)

    def send_dca_setup_summary(self, setups: Dict[str, Dict[str, Any]]) -> None:
        """
        Send summary of all active DCA setups.
        """
        if not self.enabled or not setups:
            return

        separator = "=" * 30
        message = (
            f"{EMOJI['SETUP']} <b>ACTIVE DCA SETUPS</b> {EMOJI['SETUP']}\n"
            f"{separator}\n\n"
        )

        for symbol, setup in setups.items():
            status = setup.get('status', 'UNKNOWN')
            entry_price = setup.get('entry_price', 0)
            setup_info = setup.get('setup_info', {})

            status_emoji = "🟢" if status == "ACTIVE_TRADE" else "🟡" if status == "ACTIVE" else "🔴"

            message += (
                f"<b>{symbol}</b> {status_emoji}\n"
                f"• Status: {status}\n"
                f"• Entry: ${entry_price:.2f}\n"
                f"• Levels: {setup_info.get('max_dca_orders', 'N/A')}\n"
                f"• Drop: {setup_info.get('price_drop_steps', 'N/A')}\n"
                f"• TP: {setup_info.get('take_profit_per_round', 'N/A')}\n"
                f"• Leverage: {setup_info.get('investment_leverage', 'N/A')}x\n"
                f"• PnL: ${setup.get('pnl', 0):.2f}\n\n"
            )

        message += f"{EMOJI['CLOCK']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.queue_message(message)

    # ==================== TRADING MESSAGES ====================

    def send_dca_entry(self, symbol: str, entry_price: float, dca_level: int,
                       total_levels: int, stop_loss: float, position_size: float,
                       current_price: float, direction: str, direction_confidence: float,
                       direction_reason: str):
        """Send DCA entry notification."""
        if not self.enabled:
            return

        direction_emoji = EMOJI['BUY'] if direction == "LONG" else EMOJI['SELL']
        pos_size_usd = position_size * entry_price
        separator = "=" * 30

        message = (
            f"{direction_emoji} <b>DCA ENTRY</b> {direction_emoji}\n"
            f"{separator}\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Direction:</b> {direction}\n"
            f"<b>Level:</b> {dca_level}/{total_levels}\n"
            f"<b>Entry Price:</b> ${entry_price:.4f}\n"
            f"<b>Position Size:</b> ${pos_size_usd:.2f}\n\n"
            f"<b>Current Price:</b> ${current_price:.4f}\n"
            f"<b>Stop Loss:</b> ${stop_loss:.4f}\n"
            f"<b>Distance:</b> {abs(entry_price - stop_loss) / entry_price * 100:.2f}%\n\n"
            f"<b>Confidence:</b> {direction_confidence*100:.0f}%\n"
            f"<b>Reason:</b> {direction_reason}\n\n"
            f"{EMOJI['CLOCK']} {datetime.now().strftime('%H:%M:%S')}"
        )
        self.queue_message(message)

    def send_dca_exit(self, symbol: str, entry_price: float, exit_price: float,
                       pnl: float, pnl_percent: float, reason: str,
                       quantity: float, dca_level: int, total_levels: int,
                       exit_type: str = "FULL"):
        """Send DCA exit notification."""
        if not self.enabled:
            return

        pnl_emoji = EMOJI['PROFIT'] if pnl > 0 else EMOJI['LOSS']
        pnl_color = "🟢" if pnl > 0 else "🔴"
        separator = "=" * 30

        message = (
            f"{pnl_emoji} <b>DCA EXIT</b> {pnl_emoji}\n"
            f"{separator}\n\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Type:</b> {exit_type}\n"
            f"<b>Reason:</b> {reason}\n\n"
            f"<b>Avg Entry:</b> ${entry_price:.4f}\n"
            f"<b>Exit Price:</b> ${exit_price:.4f}\n"
            f"<b>DCA Level:</b> {dca_level}/{total_levels}\n\n"
            f"<b>PnL:</b> {pnl_color} ${pnl:.2f} ({pnl_percent:+.2f}%)\n"
            f"<b>Quantity:</b> {quantity:.4f}\n\n"
            f"{EMOJI['CLOCK']} {datetime.now().strftime('%H:%M:%S')}"
        )
        self.queue_message(message)

    def send_dca_start(self, symbols: List[str], strategy_config: Dict):
        """Send DCA bot start notification."""
        if not self.enabled:
            return

        separator = "=" * 30
        symbols_text = ", ".join(symbols[:8])
        if len(symbols) > 8:
            symbols_text += f"\n+{len(symbols)-8} more"

        message = (
            f"{EMOJI['START']} <b>DCA DAY TRADING STARTED</b> {EMOJI['START']}\n"
            f"{separator}\n\n"
            f"<b>Strategy:</b> Hybrid DCA + Super TDI\n"
            f"<b>DCA Levels:</b> {strategy_config.get('dca_levels', 3)}\n"
            f"<b>Position Size:</b> ${strategy_config.get('position_size', 50)}\n"
            f"<b>Stop Loss:</b> {strategy_config.get('stop_loss', 1.0)}%\n"
            f"<b>Exit Time:</b> {strategy_config.get('exit_time', '21:00')}\n\n"
            f"<b>Monitoring:</b>\n"
            f"{symbols_text}\n\n"
            f"{EMOJI['TELEGRAM']} <i>Bot is now active</i>"
        )
        self.queue_message(message)

    def send_dca_stop(self, stats: Dict):
        """Send DCA bot stop notification with final stats."""
        if not self.enabled:
            return

        separator = "=" * 30

        message = (
            f"{EMOJI['STOP']} <b>DCA DAY TRADING STOPPED</b> {EMOJI['STOP']}\n"
            f"{separator}\n\n"
            f"<b>Session Summary:</b>\n"
            f"• Total PnL: ${stats.get('total_pnl', 0):.2f}\n"
            f"• Daily PnL: ${stats.get('daily_pnl', 0):.2f}\n"
            f"• DCA Entries: {stats.get('dca_entries', 0)}\n"
            f"• DCA Exits: {stats.get('dca_exits', 0)}\n"
            f"• Active Positions: {stats.get('active_positions', 0)}\n"
            f"• Completed Trades: {stats.get('completed_trades', 0)}\n"
            f"• Win Rate: {stats.get('win_rate', 0)*100:.1f}%\n\n"
            f"{EMOJI['CLOCK']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.queue_message(message)

    def send_dca_daily_summary(self, summary: Dict):
        """Send daily summary."""
        if not self.enabled:
            return

        pnl_emoji = EMOJI['PROFIT'] if summary.get('total_pnl', 0) > 0 else EMOJI['LOSS']
        separator = "=" * 30
        symbols_traded = ", ".join(summary.get('symbols_traded', [])[:3])

        message = (
            f"{pnl_emoji} <b>DCA DAILY SUMMARY</b> {pnl_emoji}\n"
            f"{separator}\n\n"
            f"<b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}\n\n"
            f"<b>Performance:</b>\n"
            f"• Total PnL: ${summary.get('total_pnl', 0):.2f}\n"
            f"• Total Trades: {summary.get('total_trades', 0)}\n"
            f"• Winning Trades: {summary.get('winning_trades', 0)}\n"
            f"• Losing Trades: {summary.get('losing_trades', 0)}\n"
            f"• Win Rate: {summary.get('win_rate', 0)*100:.1f}%\n\n"
            f"<b>Activity:</b>\n"
            f"• Symbols Traded: {symbols_traded}\n"
            f"• DCA Entries: {summary.get('dca_entries', 0)}\n\n"
            f"{EMOJI['TARGET']} <i>See you tomorrow!</i>"
        )
        self.queue_message(message)

    # ==================== PERFORMANCE MESSAGES ====================

    def send_performance_report(self, performance: Dict[str, Any]) -> None:
        """
        Send performance report to Telegram.
        """
        if not self.enabled:
            return

        separator = "=" * 30
        pnl_emoji = EMOJI['PROFIT'] if performance.get('total_pnl', 0) > 0 else EMOJI['LOSS']

        message = (
            f"{pnl_emoji} <b>PERFORMANCE REPORT</b> {pnl_emoji}\n"
            f"{separator}\n\n"
            f"<b>Overall Performance:</b>\n"
            f"• Total PnL: ${performance.get('total_pnl', 0):.2f}\n"
            f"• Total Trades: {performance.get('total_trades', 0)}\n"
            f"• Win Rate: {performance.get('win_rate', 0):.1f}%\n"
            f"• Average PnL: ${performance.get('average_pnl', 0):.2f}\n\n"
            f"<b>Trade Statistics:</b>\n"
            f"• Winning Trades: {performance.get('winning_trades', 0)}\n"
            f"• Losing Trades: {performance.get('losing_trades', 0)}\n"
            f"• Best Trade: ${performance.get('best_trade', 0):.2f}\n"
            f"• Worst Trade: ${performance.get('worst_trade', 0):.2f}\n\n"
            f"<b>DCA Setups:</b>\n"
            f"• Active: {performance.get('dca_setups_active', 0)}\n"
            f"• Completed: {performance.get('dca_setups_completed', 0)}\n\n"
            f"{EMOJI['CLOCK']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.queue_message(message)

    # ==================== SIGNAL MESSAGES ====================

    def send_signal_summary(self, signal_stats: Dict[str, Any]) -> None:
        """
        Send signal manager summary to Telegram.
        """
        if not self.enabled:
            return

        separator = "=" * 30

        message = (
            f"{EMOJI['SIGNAL']} <b>SIGNAL MANAGER SUMMARY</b> {EMOJI['SIGNAL']}\n"
            f"{separator}\n\n"
            f"<b>Signal Statistics:</b>\n"
            f"• Total Signals: {signal_stats.get('total_signals', 0)}\n"
            f"• Executed: {signal_stats.get('executed_signals', 0)}\n"
            f"• Rejected: {signal_stats.get('rejected_signals', 0)}\n"
            f"• Expired: {signal_stats.get('expired_signals', 0)}\n"
            f"• Duplicates Prevented: {signal_stats.get('duplicate_signals_prevented', 0)}\n\n"
            f"<b>Current Status:</b>\n"
            f"• Active Signals: {signal_stats.get('active_signals', 0)}\n"
            f"• Pending Signals: {signal_stats.get('pending_signals', 0)}\n"
            f"• DCA Setups Active: {signal_stats.get('dca_setups_active', 0)}\n\n"
            f"{EMOJI['CLOCK']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        self.queue_message(message)

    # ==================== ERROR MESSAGES ====================

    def send_error(self, error: str, context: Optional[Dict] = None):
        """Send error notification."""
        if not self.enabled:
            return

        separator = "=" * 30
        message = (
            f"{EMOJI['WARNING']} <b>DCA ERROR</b> {EMOJI['WARNING']}\n"
            f"{separator}\n\n"
            f"<b>Error:</b> {error}\n"
            f"<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}"
        )
        if context:
            message += f"\n\n<b>Context:</b>\n{str(context)[:200]}"

        self.queue_message(message)

    def send_alert(self, title: str, message_body: str,
                   alert_type: str = "INFO"):
        """Send generic alert."""
        if not self.enabled:
            return

        emoji_map = {
            "INFO": EMOJI['INFO'],
            "WARNING": EMOJI['WARNING'],
            "SUCCESS": EMOJI['SUCCESS'],
            "ERROR": EMOJI['ERROR'],
        }
        emoji = emoji_map.get(alert_type, EMOJI['INFO'])
        separator = "=" * 30

        message = (
            f"{emoji} <b>{title}</b> {emoji}\n"
            f"{separator}\n\n"
            f"{message_body}\n\n"
            f"{EMOJI['CLOCK']} {datetime.now().strftime('%H:%M:%S')}"
        )
        self.queue_message(message)

    def send_health_check(self, status: Dict):
        """Send health check status."""
        if not self.enabled:
            return

        health_emoji = EMOJI['HEALTH'] if status.get('status') == 'healthy' else EMOJI['WARNING']
        separator = "=" * 30

        message = (
            f"{health_emoji} <b>DCA HEALTH CHECK</b> {health_emoji}\n"
            f"{separator}\n\n"
            f"<b>Status:</b> {status.get('status', 'unknown')}\n"
            f"<b>Active Positions:</b> {status.get('active_positions', 0)}\n"
            f"<b>Daily PnL:</b> ${status.get('daily_pnl', 0):.2f}\n"
            f"<b>Total PnL:</b> ${status.get('total_pnl', 0):.2f}\n"
            f"<b>Uptime:</b> {status.get('uptime', 'N/A')}\n\n"
            f"{EMOJI['CLOCK']} {datetime.now().strftime('%H:%M:%S')}"
        )
        self.queue_message(message)

    def shutdown(self):
        """Shutdown the Telegram bot."""
        self.running = False
        if self.enabled:
            self.send_message(f"{EMOJI['STOP']} Telegram bot shutting down...")
            logger.info(f"{EMOJI['STOP']} Telegram bot shutdown")


# Singleton instance
telegram_bot = TelegramBot()

__all__ = ["telegram_bot", "TelegramBot"]
