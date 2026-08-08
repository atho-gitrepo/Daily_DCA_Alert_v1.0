"""
MongoDB Client for DCA Day Trading
Persistent storage for positions and performance
Version: 1.0.0
"""

import logging
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
import json

from settings import config

logger = logging.getLogger(__name__)

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, DuplicateKeyError
    from pymongo.collection import Collection
    from bson import ObjectId, json_util
    MONGODB_AVAILABLE = True
except ImportError:
    MONGODB_AVAILABLE = False
    logger.warning("pymongo not installed - MongoDB disabled")


class MongoDBClient:
    """
    MongoDB client for DCA trading bot.
    Handles storing/retrieving positions, trades, and stats.
    """

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.uri = uri or config.mongodb.uri
        self.db_name = db_name or config.mongodb.db_name
        self.enabled = bool(self.uri) and MONGODB_AVAILABLE

        self.client: Optional[MongoClient] = None
        self.db = None
        self.active_collection: Optional[Collection] = None
        self.resolved_collection: Optional[Collection] = None
        self.trades_collection: Optional[Collection] = None
        self.stats_collection: Optional[Collection] = None

        if self.enabled:
            self._connect()
        else:
            logger.info("MongoDB disabled - using in-memory storage")

    def _connect(self):
        """Connect to MongoDB."""
        try:
            self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000)
            self.client.server_info()  # Test connection
            self.db = self.client[self.db_name]

            # Collections
            self.active_collection = self.db[config.mongodb.active_collection]
            self.resolved_collection = self.db[config.mongodb.resolved_collection]
            self.trades_collection = self.db.get_collection("trades")
            self.stats_collection = self.db.get_collection("stats")

            # Create indexes
            self._create_indexes()

            logger.info(f"MongoDB connected: {self.db_name}")

        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"MongoDB connection failed: {e}")
            self.enabled = False
            self.client = None
        except Exception as e:
            logger.error(f"MongoDB initialization error: {e}")
            self.enabled = False

    def _create_indexes(self):
    """Create necessary indexes."""
    try:
        if self.active_collection is not None:
            self.active_collection.create_index("symbol", unique=False)
            self.active_collection.create_index("entry_time")
            self.active_collection.create_index("status")

        if self.resolved_collection is not None:
            self.resolved_collection.create_index("symbol")
            self.resolved_collection.create_index("exit_time")
            self.resolved_collection.create_index("entry_time")
            self.resolved_collection.create_index("status")

        if self.trades_collection is not None:
            self.trades_collection.create_index("symbol")
            self.trades_collection.create_index("exit_time")
            self.trades_collection.create_index("entry_time")
            self.trades_collection.create_index("direction")

        if self.stats_collection is not None:
            self.stats_collection.create_index("date", unique=True)

    except Exception as e:
        logger.warning(f"Index creation issue: {e}")

    def _parse_document(self, doc: Dict) -> Dict:
        """Parse MongoDB document with ObjectId to string."""
        if doc and '_id' in doc:
            doc['_id'] = str(doc['_id'])
        return doc

    def save_active_position(self, position: Any) -> bool:
        """Save an active DCA position."""
        if not self.enabled or not self.active_collection:
            return False

        try:
            # Convert position to dict
            position_dict = self._position_to_dict(position)

            # Update or insert
            result = self.active_collection.update_one(
                {"symbol": position.symbol, "status": "ACTIVE"},
                {"$set": position_dict},
                upsert=True
            )
            return result.acknowledged

        except Exception as e:
            logger.error(f"Failed to save active position: {e}")
            return False

    def move_to_resolved(self, position: Any) -> bool:
        """Move a position from active to resolved."""
        if not self.enabled:
            return False

        try:
            # Get active position
            active_doc = self.active_collection.find_one({"symbol": position.symbol, "status": "ACTIVE"})

            if active_doc:
                # Delete from active
                self.active_collection.delete_one({"_id": active_doc["_id"]})

            # Save to resolved
            position_dict = self._position_to_dict(position)
            position_dict["status"] = "CLOSED"
            position_dict["resolved_at"] = datetime.now()

            result = self.resolved_collection.insert_one(position_dict)

            # Also save to trades collection
            trade_doc = {
                "symbol": position.symbol,
                "direction": position.direction,
                "entry_price": position.entry_price,
                "exit_price": position.exit_price,
                "quantity": position.quantity,
                "total_cost": position.total_cost,
                "realized_pnl": position.realized_pnl,
                "entry_time": position.entry_time,
                "exit_time": position.exit_time,
                "dca_levels": position.dca_level,
                "total_dca_levels": position.total_dca_levels,
                "stop_loss": position.stop_loss,
                "direction_confidence": position.direction_confidence,
                "direction_reason": position.direction_reason,
            }
            self.trades_collection.insert_one(trade_doc)

            return result.acknowledged

        except Exception as e:
            logger.error(f"Failed to move position to resolved: {e}")
            return False

    def get_active_positions(self) -> List[Dict]:
        """Get all active positions."""
        if not self.enabled or not self.active_collection:
            return []

        try:
            positions = list(self.active_collection.find({"status": "ACTIVE"}))
            return [self._parse_document(p) for p in positions]
        except Exception as e:
            logger.error(f"Failed to get active positions: {e}")
            return []

    def get_active_position(self, symbol: str) -> Optional[Dict]:
        """Get a specific active position."""
        if not self.enabled or not self.active_collection:
            return None

        try:
            doc = self.active_collection.find_one({"symbol": symbol, "status": "ACTIVE"})
            return self._parse_document(doc) if doc else None
        except Exception as e:
            logger.error(f"Failed to get active position for {symbol}: {e}")
            return None

    def get_resolved_positions(self, limit: int = 100) -> List[Dict]:
        """Get resolved positions."""
        if not self.enabled or not self.resolved_collection:
            return []

        try:
            positions = list(self.resolved_collection.find()
                           .sort("exit_time", -1)
                           .limit(limit))
            return [self._parse_document(p) for p in positions]
        except Exception as e:
            logger.error(f"Failed to get resolved positions: {e}")
            return []

    def get_trades(self, symbol: Optional[str] = None,
                   limit: int = 100) -> List[Dict]:
        """Get trade history."""
        if not self.enabled or not self.trades_collection:
            return []

        try:
            query = {}
            if symbol:
                query["symbol"] = symbol

            trades = list(self.trades_collection.find(query)
                         .sort("exit_time", -1)
                         .limit(limit))
            return [self._parse_document(t) for t in trades]
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    def save_daily_stats(self, stats: Dict) -> bool:
        """Save daily statistics."""
        if not self.enabled or not self.stats_collection:
            return False

        try:
            date_str = datetime.now().strftime("%Y-%m-%d")
            stats_doc = {
                "date": date_str,
                "timestamp": datetime.now(),
                "stats": stats,
                "daily_pnl": stats.get("daily_pnl", 0),
                "daily_trades": stats.get("daily_trades", 0),
                "win_rate": stats.get("win_rate", 0),
                "active_positions": stats.get("active_positions", 0),
            }

            result = self.stats_collection.update_one(
                {"date": date_str},
                {"$set": stats_doc},
                upsert=True
            )
            return result.acknowledged

        except Exception as e:
            logger.error(f"Failed to save daily stats: {e}")
            return False

    def get_daily_stats(self, days: int = 7) -> List[Dict]:
        """Get daily statistics for last N days."""
        if not self.enabled or not self.stats_collection:
            return []

        try:
            date_limit = datetime.now()
            # Simple approach - get last N documents
            stats = list(self.stats_collection.find()
                        .sort("date", -1)
                        .limit(days))
            return [self._parse_document(s) for s in stats]
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return []

    def update_position_price(self, symbol: str, current_price: float) -> bool:
        """Update current price for a position."""
        if not self.enabled or not self.active_collection:
            return False

        try:
            result = self.active_collection.update_one(
                {"symbol": symbol, "status": "ACTIVE"},
                {"$set": {"current_price": current_price, "updated_at": datetime.now()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update position price: {e}")
            return False

    def delete_position(self, symbol: str) -> bool:
        """Delete a position (use with caution)."""
        if not self.enabled or not self.active_collection:
            return False

        try:
            result = self.active_collection.delete_one({"symbol": symbol})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete position: {e}")
            return False

    def _position_to_dict(self, position: Any) -> Dict:
        """Convert a DCAPosition object to dictionary."""
        return {
            "symbol": position.symbol,
            "direction": position.direction,
            "entry_price": position.entry_price,
            "entry_time": position.entry_time,
            "quantity": position.quantity,
            "total_cost": position.total_cost,
            "current_price": position.current_price,
            "tdi_level": position.tdi_level,
            "tdi_zone": position.tdi_zone,
            "bb_position": position.bb_position,
            "htf_trend": position.htf_trend,
            "mtf_trend": position.mtf_trend,
            "ltf_trend": position.ltf_trend,
            "trend_strength": position.trend_strength,
            "dca_level": position.dca_level,
            "total_dca_levels": position.total_dca_levels,
            "dca_entries": position.dca_entries,
            "stop_loss": position.stop_loss,
            "take_profits": position.take_profits,
            "unrealized_pnl": position.unrealized_pnl,
            "unrealized_pnl_percent": position.unrealized_pnl_percent,
            "exit_price": position.exit_price,
            "exit_time": position.exit_time,
            "realized_pnl": position.realized_pnl,
            "status": position.status,
            "entry_score": position.entry_score,
            "direction_confidence": position.direction_confidence,
            "direction_reason": position.direction_reason,
            "updated_at": datetime.now(),
        }

    def get_performance_summary(self) -> Dict:
        """Get overall performance summary."""
        if not self.enabled:
            return {}

        try:
            # Get all resolved positions
            total_trades = self.resolved_collection.count_documents({})

            if total_trades == 0:
                return {
                    "total_trades": 0,
                    "total_pnl": 0,
                    "winning_trades": 0,
                    "losing_trades": 0,
                    "win_rate": 0,
                }

            # Aggregate PnL
            pipeline = [
                {"$group": {
                    "_id": None,
                    "total_pnl": {"$sum": "$realized_pnl"},
                    "winning_trades": {"$sum": {"$cond": [{"$gt": ["$realized_pnl", 0]}, 1, 0]}},
                    "losing_trades": {"$sum": {"$cond": [{"$lt": ["$realized_pnl", 0]}, 1, 0]}},
                }}
            ]

            result = list(self.resolved_collection.aggregate(pipeline))

            if result:
                data = result[0]
                return {
                    "total_trades": total_trades,
                    "total_pnl": data.get("total_pnl", 0),
                    "winning_trades": data.get("winning_trades", 0),
                    "losing_trades": data.get("losing_trades", 0),
                    "win_rate": data.get("winning_trades", 0) / total_trades if total_trades > 0 else 0,
                }

            return {}

        except Exception as e:
            logger.error(f"Failed to get performance summary: {e}")
            return {}

    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")


# Singleton instance
mongodb_client = MongoDBClient()

__all__ = ["mongodb_client", "MongoDBClient"]
