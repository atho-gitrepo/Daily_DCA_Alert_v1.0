"""
DCA Setup Manager for Futures Trading
Manages DCA configuration and provides setup information
Version: 1.0.0
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import json

from settings import config

logger = logging.getLogger(__name__)


@dataclass
class DCAOrderDetails:
    """Individual DCA order details"""
    order_number: int
    price: float
    size: float
    margin: float
    status: str = "PENDING"  # PENDING, FILLED, CANCELLED
    filled_time: Optional[datetime] = None


class DCASetupManager:
    """
    Manages DCA setup configuration and provides order details.
    """
    
    def __init__(self):
        self.setup = config.dca_setup
        self.active_setups: Dict[str, Dict] = {}
        self.order_history: List[Dict] = []
        
        logger.info("DCA Setup Manager initialized")
    
    def get_setup_info(self, symbol: str, current_price: Optional[float] = None) -> Dict[str, Any]:
        """
        Get complete DCA setup information for a symbol.
        """
        # Calculate DCA levels
        levels = self._calculate_dca_levels(symbol, current_price)
        
        # Calculate order details
        order_details = self._get_order_details(symbol, current_price)
        
        return {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "current_price": current_price or 0,
            "price_settings": self._get_price_settings(),
            "order_margins": self._get_order_margins(),
            "dca_levels": levels,
            "order_details": order_details,
            "conditions": self._get_conditions(),
            "advanced": self._get_advanced_settings(),
            "risk_management": self._get_risk_management(),
        }
    
    def _calculate_dca_levels(self, symbol: str, current_price: Optional[float] = None) -> Dict[str, Any]:
        """Calculate DCA price levels."""
        if not current_price:
            return {}
        
        levels = []
        price_drop = self.setup.price_drop_steps
        
        for i in range(self.setup.max_dca_orders):
            level_num = i + 1
            if i == 0:
                price = current_price
                drop_pct = 0
            else:
                price = current_price * (1 - (price_drop * i))
                drop_pct = price_drop * i * 100
            
            levels.append({
                "level": level_num,
                "price": round(price, 2),
                "drop_from_entry": f"{drop_pct:.1f}%",
                "margin": self._get_level_margin(level_num),
                "size": self._get_level_size(level_num),
            })
        
        return {
            "current_price": current_price,
            "levels": levels,
            "max_levels": self.setup.max_dca_orders,
            "total_margin_required": sum([l["margin"] for l in levels]),
        }
    
    def _get_order_details(self, symbol: str, current_price: Optional[float] = None) -> List[Dict]:
        """Get detailed order information for each DCA level."""
        if not current_price:
            return []
        
        orders = []
        price_drop = self.setup.price_drop_steps
        
        for i in range(self.setup.max_dca_orders):
            level_num = i + 1
            if i == 0:
                price = current_price
            else:
                price = current_price * (1 - (price_drop * i))
            
            margin = self._get_level_margin(level_num)
            size = margin * self.setup.investment_leverage
            
            orders.append({
                "order_number": level_num,
                "price": round(price, 2),
                "size": round(size, 2),
                "margin": round(margin, 2),
                "status": "PENDING"
            })
        
        return orders
    
    def _get_price_settings(self) -> Dict[str, Any]:
        """Get price-related settings."""
        return {
            "price_drop_steps": f"{self.setup.price_drop_steps * 100:.1f}%",
            "take_profit_per_round": f"{self.setup.take_profit_per_round * 100:.1f}%",
            "investment_leverage": f"{self.setup.investment_leverage}x",
        }
    
    def _get_order_margins(self) -> Dict[str, Any]:
        """Get order margin settings."""
        return {
            "base_order_margin": f"${self.setup.base_order_margin:.2f}",
            "dca_order_margin": f"${self.setup.dca_order_margin:.2f}",
            "max_dca_orders": self.setup.max_dca_orders,
            "invested_margin": f"${self.setup.invested_margin:.2f}",
            "auto_add_margin": "Enabled" if self.setup.auto_add_margin else "Disabled",
        }
    
    def _get_advanced_settings(self) -> Dict[str, Any]:
        """Get advanced settings."""
        return {
            "price_deviation_multiplier": self.setup.price_deviation_multiplier,
            "dca_order_size_multiplier": self.setup.dca_order_size_multiplier,
        }
    
    def _get_conditions(self) -> Dict[str, Any]:
        """Get start and stop conditions."""
        return {
            "start_condition": self.setup.start_condition,
            "stop_condition": self.setup.stop_condition,
        }
    
    def _get_risk_management(self) -> Dict[str, Any]:
        """Get risk management settings."""
        total_margin = self.setup.base_order_margin + (self.setup.dca_order_margin * self.setup.max_dca_orders)
        max_loss = total_margin * self.setup.stop_loss_percent
        risk = self.setup.stop_loss_percent
        reward = self.setup.take_profit_per_round
        risk_reward = round(reward / risk, 2) if risk > 0 else 0
        
        return {
            "stop_loss": f"{self.setup.stop_loss_percent * 100:.1f}%",
            "max_loss_per_trade": f"${max_loss:.2f}",
            "risk_reward_ratio": risk_reward,
            "total_margin_required": f"${total_margin:.2f}",
        }
    
    def _get_level_margin(self, level: int) -> float:
        """Get margin for a specific DCA level."""
        if level == 1:
            return self.setup.base_order_margin
        else:
            multiplier = self.setup.dca_order_size_multiplier ** (level - 1)
            return self.setup.dca_order_margin * multiplier
    
    def _get_level_size(self, level: int) -> float:
        """Get position size for a specific DCA level."""
        margin = self._get_level_margin(level)
        return margin * self.setup.investment_leverage
    
    def format_setup_message(self, symbol: str, current_price: float) -> str:
        """
        Format DCA setup information as a Telegram message.
        """
        info = self.get_setup_info(symbol, current_price)
        if not info:
            return "❌ Unable to get DCA setup information"
        
        message = f"""
📊 <b>FUTURES DCA SETUP</b>
━━━━━━━━━━━━━━━━━━━━━

<b>Symbol:</b> {symbol}
<b>Current Price:</b> ${current_price:.2f}

<b>💰 Price Settings</b>
• Price Drop Steps: {info['price_settings']['price_drop_steps']}
• Take Profit Per Round: {info['price_settings']['take_profit_per_round']}
• Investment: {info['price_settings']['investment_leverage']}

<b>💵 Order Margins</b>
• Base Order: {info['order_margins']['base_order_margin']}
• DCA Order: {info['order_margins']['dca_order_margin']}
• Max DCA Orders: {info['order_margins']['max_dca_orders']}
• Invested Margin: {info['order_margins']['invested_margin']}
• Auto-add Margin: {info['order_margins']['auto_add_margin']}

<b>📋 DCA Order Details</b>
"""
        
        # Add DCA levels
        levels = info.get('dca_levels', {}).get('levels', [])
        for level in levels:
            message += f"""
• Level {level['level']}: ${level['price']:.2f} | {level['drop_from_entry']} | Margin: ${level['margin']:.2f} | Size: ${level['size']:.2f}
"""
        
        message += f"""
<b>🎯 Start Condition:</b> {info['conditions']['start_condition']}
<b>🛑 Stop Condition:</b> {info['conditions']['stop_condition']}
<b>⛔ Stop Loss:</b> {info['risk_management']['stop_loss']}

<b>📊 Advanced</b>
• Price Deviation Multiplier: {info['advanced']['price_deviation_multiplier']}
• DCA Order Size Multiplier: {info['advanced']['dca_order_size_multiplier']}

<b>📈 Risk Management</b>
• Max Loss Per Trade: {info['risk_management']['max_loss_per_trade']}
• Risk/Reward Ratio: {info['risk_management']['risk_reward_ratio']}
• Total Margin Required: {info['risk_management']['total_margin_required']}

🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        return message
    
    def get_active_setups(self) -> Dict[str, Dict]:
        """Get all active DCA setups."""
        return self.active_setups.copy()
    
    def add_setup(self, symbol: str, setup_info: Dict) -> None:
        """Add a new DCA setup."""
        self.active_setups[symbol] = {
            "symbol": symbol,
            "setup_info": setup_info,
            "created_at": datetime.now(),
            "status": "ACTIVE"
        }
        logger.info(f"DCA setup added for {symbol}")
    
    def update_setup_status(self, symbol: str, status: str) -> bool:
        """Update DCA setup status."""
        if symbol in self.active_setups:
            self.active_setups[symbol]["status"] = status
            self.active_setups[symbol]["updated_at"] = datetime.now()
            logger.info(f"DCA setup status updated for {symbol}: {status}")
            return True
        return False
    
    def get_setup(self, symbol: str) -> Optional[Dict]:
        """Get DCA setup for a symbol."""
        return self.active_setups.get(symbol)
    
    def remove_setup(self, symbol: str) -> bool:
        """Remove a DCA setup."""
        if symbol in self.active_setups:
            del self.active_setups[symbol]
            logger.info(f"DCA setup removed for {symbol}")
            return True
        return False
    
    def get_all_dca_setups(self) -> Dict[str, Dict]:
        """Get all DCA setups (alias for get_active_setups)."""
        return self.get_active_setups()


# ============================================================
# CRITICAL: The singleton instance MUST be created here
# This is what main.py imports
# ============================================================
dca_setup_manager = DCASetupManager()

# Export everything
__all__ = [
    "dca_setup_manager",
    "DCASetupManager",
    "DCAOrderDetails",
]