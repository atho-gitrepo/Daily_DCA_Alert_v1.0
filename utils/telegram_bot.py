"""
Telegram Bot Integration for DCA Day Trading
Sends notifications for entries, exits, and daily summaries
Version: 1.0.0
"""

import logging
import requests
import asyncio
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
}


class TelegramBot:
    """Telegram bot for DCA trading notifications."""

    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or config.telegram.bot_token
        self.chat_id = chat_id or config.telegram.chat_id
        self.enabled = bool(self.token and self.chat_id)
        self.message_queue = Queue()
        self.running = True

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
        message = f"""
{EMOJI['START']} <b>DCA Day Trading Bot</b>
━━━━━━━━━━━━━━━━━━━━━

<b>Status:</b> Online {EMOJI['HEALTH']}
<b>Strategy:</b> Hybrid DCA + Super TDI
<b>DCA Levels:</b> {config.dca.dca_levels}
<b>Position Size:</b> ${config.dca.position_size_usd}
<b>Stop Loss:</b> {config.dca.stop_loss_percent*100:.1f}%
<b>Exit Time:</b> {config.dca.exit_hour:02d}:{config.dca.exit_minute:02d} UTC

<b>Monitoring:</b>
{', '.join(config.market.symbols[:5])}
{EMOJI['TELEGRAM']} <i>Ready for action!</i>
"""
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

    def send_dca_entry(self, symbol: str, entry_price: float, dca_level: int,
                       total_levels: int, stop_loss: float, position_size: float,
                       current_price: float, direction: str, direction_confidence: float,
                       direction_reason: str):
        """Send DCA entry notification."""
        if not self.enabled:
            return

        direction_emoji = EMOJI['BUY'] if direction == "LONG" else EMOJI['SELL']
        pos_size_usd = position_size * entry_price

        message = f"""
{direction_emoji} <b>DCA ENTRY</b> {direction_emoji}
━━━━━━━━━━━━━━━━━━━━━

<b>Symbol:</b> {symbol}
<b>Direction:</b> {direction}
<b>Level:</b> {dca_level}/{total_levels}
<b>Entry Price:</b> ${entry_price:.4f}
<b>Position Size:</b> ${pos_size_usd:.2f}

<b>Current Price:</b> ${current_price:.4f}
<b>Stop Loss:</b> ${stop_loss:.4f}
<b>Distance:</b> {abs(entry_price - stop_loss) / entry_price * 100:.2f}%

<b>Confidence:</b> {direction_confidence*100:.0f}%
<b>Reason:</b> {direction_reason}

{EMOJI['CLOCK']} {datetime.now().strftime('%H:%M:%S')}
"""
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

        # Calculate average entry
        avg_entry = entry_price

        message = f"""
{pnl_emoji} <b>DCA EXIT</b> {pnl_emoji}
━━━━━━━━━━━━━━━━━━━━━

<b>Symbol:</b> {symbol}
<b>Type:</b> {exit_type}
<b>Reason:</b> {reason}

<b>Avg Entry:</b> ${avg_entry:.4f}
<b>Exit Price:</b> ${exit_price:.4f}
<b>DCA Level:</b> {dca_level}/{total_levels}

<b>PnL:</b> {pnl_color} ${pnl:.2f} ({pnl_percent:+.2f}%)
<b>Quantity:</b> {quantity:.4f}

{EMOJI['CLOCK']} {datetime.now().strftime('%H:%M:%S')}
"""
        self.queue_message(message)

    def send_dca_start(self, symbols: List[str], strategy_config: Dict):
        """Send DCA bot start notification."""
        if not self.enabled:
            return

        message = f"""
{EMOJI['START']} <b>DCA DAY TRADING STARTED</b> {EMOJI['START']}
━━━━━━━━━━━━━━━━━━━━━

<b>Strategy:</b> Hybrid DCA + Super TDI
<b>DCA Levels:</b> {strategy_config.get('dca_levels', 3)}
<b>Position Size:</b> ${strategy_config.get('position_size', 50)}
<b>Stop Loss:</b> {strategy_config.get('stop_loss', 1.0)}%
<b>Exit Time:</b> {strategy_config.get('exit_time', '21:00')}

<b>Monitoring:</b>
{', '.join(symbols[:8])}
{'' if len(symbols) <= 8 else f'\n+{len(symbols)-8} more'}

{EMOJI['TELEGRAM']} <i>Bot is now active</i>
"""
        self.queue_message(message)

    def send_dca_stop(self, stats: Dict):
        """Send DCA bot stop notification with final stats."""
        if not self.enabled:
            return

        message = f"""
{EMOJI['STOP']} <b>DCA DAY TRADING STOPPED</b> {EMOJI['STOP']}
━━━━━━━━━━━━━━━━━━━━━

<b>Session Summary:</b>
• Total PnL: ${stats.get('total_pnl', 0):.2f}
• Daily PnL: ${stats.get('daily_pnl', 0):.2f}
• DCA Entries: {stats.get('dca_entries', 0)}
• DCA Exits: {stats.get('dca_exits', 0)}
• Active Positions: {stats.get('active_positions', 0)}
• Completed Trades: {stats.get('completed_trades', 0)}
• Win Rate: {stats.get('win_rate', 0)*100:.1f}%

{EMOJI['CLOCK']} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.queue_message(message)

    def send_dca_daily_summary(self, summary: Dict):
        """Send daily summary."""
        if not self.enabled:
            return

        pnl_emoji = EMOJI['PROFIT'] if summary.get('total_pnl', 0) > 0 else EMOJI['LOSS']

        message = f"""
{pnl_emoji} <b>DCA DAILY SUMMARY</b> {pnl_emoji}
━━━━━━━━━━━━━━━━━━━━━

<b>Date:</b> {datetime.now().strftime('%Y-%m-%d')}

<b>Performance:</b>
• Total PnL: ${summary.get('total_pnl', 0):.2f}
• Total Trades: {summary.get('total_trades', 0)}
• Winning Trades: {summary.get('winning_trades', 0)}
• Losing Trades: {summary.get('losing_trades', 0)}
• Win Rate: {summary.get('win_rate', 0)*100:.1f}%

<b>Activity:</b>
• Symbols Traded: {', '.join(summary.get('symbols_traded', []))[:3]}
• DCA Entries: {summary.get('dca_entries', 0)}

{EMOJI['TARGET']} <i>See you tomorrow!</i>
"""
        self.queue_message(message)

    def send_error(self, error: str, context: Optional[Dict] = None):
        """Send error notification."""
        if not self.enabled:
            return

        message = f"""
{EMOJI['WARNING']} <b>DCA ERROR</b> {EMOJI['WARNING']}
━━━━━━━━━━━━━━━━━━━━━

<b>Error:</b> {error}
<b>Time:</b> {datetime.now().strftime('%H:%M:%S')}
"""
        if context:
            message += f"\n<b>Context:</b>\n{str(context)[:200]}"

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

        message = f"""
{emoji} <b>{title}</b> {emoji}
━━━━━━━━━━━━━━━━━━━━━

{message_body}

{EMOJI['CLOCK']} {datetime.now().strftime('%H:%M:%S')}
"""
        self.queue_message(message)

    def send_health_check(self, status: Dict):
        """Send health check status."""
        if not self.enabled:
            return

        health_emoji = EMOJI['HEALTH'] if status.get('status') == 'healthy' else EMOJI['WARNING']

        message = f"""
{health_emoji} <b>DCA HEALTH CHECK</b> {health_emoji}
━━━━━━━━━━━━━━━━━━━━━

<b>Status:</b> {status.get('status', 'unknown')}
<b>Active Positions:</b> {status.get('active_positions', 0)}
<b>Daily PnL:</b> ${status.get('daily_pnl', 0):.2f}
<b>Total PnL:</b> ${status.get('total_pnl', 0):.2f}
<b>Uptime:</b> {status.get('uptime', 'N/A')}

{EMOJI['CLOCK']} {datetime.now().strftime('%H:%M:%S')}
"""
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
