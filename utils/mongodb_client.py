"""
MongoDB Client for DCA Day Trading
Persistent storage for positions, trades, performance, and DCA setups
Version: 1.1.0 - Enhanced with DCA setup tracking and performance metrics
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
    Handles storing/retrieving positions, trades, stats, and DCA setups.
    Version: 1.1.0
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
        # NEW: DCA Setup collection
        self.dca_setup_collection: Optional[Collection] = None
        # NEW: Performance collection
        self.performance_collection: Optional[Collection] = None

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
            # NEW: DCA Setup collection
            self.dca_setup_collection = self.db.get_collection("dca_setups")
            # NEW: Performance collection
            self.performance_collection = self.db.get_collection("performance")

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
            # Active positions indexes
            if self.active_collection is not None:
                self.active_collection.create_index("symbol", unique=False)
                self.active_collection.create_index("entry_time")
                self.active_collection.create_index("status")
                self.active_collection.create_index([("symbol", 1), ("status", 1)])

            # Resolved positions indexes
            if self.resolved_collection is not None:
                self.resolved_collection.create_index("symbol")
                self.resolved_collection.create_index("exit_time")
                self.resolved_collection.create_index("entry_time")
                self.resolved_collection.create_index("status")
                self.resolved_collection.create_index([("symbol", 1), ("exit_time", -1)])

            # Trades indexes
            if self.trades_collection is not None:
                self.trades_collection.create_index("symbol")
                self.trades_collection.create_index("exit_time")
                self.trades_collection.create_index("entry_time")
                self.trades_collection.create_index("direction")
                self.trades_collection.create_index([("symbol", 1), ("exit_time", -1)])

            # Stats indexes
            if self.stats_collection is not None:
                self.stats_collection.create_index("date", unique=True)
                self.stats_collection.create_index([("date", -1)])

            # NEW: DCA Setup indexes
            if self.dca_setup_collection is not None:
                self.dca_setup_collection.create_index("symbol", unique=True)
                self.dca_setup_collection.create_index("created_at")
                self.dca_setup_collection.create_index("status")
                self.dca_setup_collection.create_index([("symbol", 1), ("status", 1)])

            # NEW: Performance indexes
            if self.performance_collection is not None:
                self.performance_collection.create_index("date", unique=True)
                self.performance_collection.create_index([("date", -1)])

        except Exception as e:
            logger.warning(f"Index creation issue: {e}")

    def _parse_document(self, doc: Dict) -> Dict:
        """Parse MongoDB document with ObjectId to string."""
        if doc and '_id' in doc:
            doc['_id'] = str(doc['_id'])
        return doc

    # ==================== POSITION METHODS ====================

    def save_active_position(self, position: Any) -> bool:
        """Save an active DCA position."""
        if not self.enabled or self.active_collection is None:
            return False

        try:
            position_dict = self._position_to_dict(position)

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
            if self.active_collection is not None:
                active_doc = self.active_collection.find_one({"symbol": position.symbol, "status": "ACTIVE"})

                if active_doc:
                    # Delete from active
                    self.active_collection.delete_one({"_id": active_doc["_id"]})

            # Save to resolved
            if self.resolved_collection is not None:
                position_dict = self._position_to_dict(position)
                position_dict["status"] = "CLOSED"
                position_dict["resolved_at"] = datetime.now()

                result = self.resolved_collection.insert_one(position_dict)

                # Also save to trades collection
                if self.trades_collection is not None:
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
                        "dca_count": getattr(position, 'dca_count', 1),
                        "trailing_activated": getattr(position, 'trailing_activated', False),
                    }
                    self.trades_collection.insert_one(trade_doc)

                return result.acknowledged

            return False

        except Exception as e:
            logger.error(f"Failed to move position to resolved: {e}")
            return False

    def get_active_positions(self) -> List[Dict]:
        """Get all active positions."""
        if not self.enabled or self.active_collection is None:
            return []

        try:
            positions = list(self.active_collection.find({"status": "ACTIVE"}))
            return [self._parse_document(p) for p in positions]
        except Exception as e:
            logger.error(f"Failed to get active positions: {e}")
            return []

    def get_active_position(self, symbol: str) -> Optional[Dict]:
        """Get a specific active position."""
        if not self.enabled or self.active_collection is None:
            return None

        try:
            doc = self.active_collection.find_one({"symbol": symbol, "status": "ACTIVE"})
            return self._parse_document(doc) if doc else None
        except Exception as e:
            logger.error(f"Failed to get active position for {symbol}: {e}")
            return None

    def get_resolved_positions(self, limit: int = 100,
                               symbol: Optional[str] = None) -> List[Dict]:
        """Get resolved positions."""
        if not self.enabled or self.resolved_collection is None:
            return []

        try:
            query = {}
            if symbol:
                query["symbol"] = symbol

            positions = list(self.resolved_collection.find(query)
                           .sort("exit_time", -1)
                           .limit(limit))
            return [self._parse_document(p) for p in positions]
        except Exception as e:
            logger.error(f"Failed to get resolved positions: {e}")
            return []

    def get_trades(self, symbol: Optional[str] = None,
                   limit: int = 100, start_date: Optional[datetime] = None,
                   end_date: Optional[datetime] = None) -> List[Dict]:
        """Get trade history with optional date filters."""
        if not self.enabled or self.trades_collection is None:
            return []

        try:
            query = {}
            if symbol:
                query["symbol"] = symbol

            if start_date or end_date:
                query["exit_time"] = {}
                if start_date:
                    query["exit_time"]["$gte"] = start_date
                if end_date:
                    query["exit_time"]["$lte"] = end_date

            trades = list(self.trades_collection.find(query)
                         .sort("exit_time", -1)
                         .limit(limit))
            return [self._parse_document(t) for t in trades]
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []

    def update_position_price(self, symbol: str, current_price: float) -> bool:
        """Update current price for a position."""
        if not self.enabled or self.active_collection is None:
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
        if not self.enabled or self.active_collection is None:
            return False

        try:
            result = self.active_collection.delete_one({"symbol": symbol})
            return result.deleted_count > 0
        except Exception as e:
            logger.error(f"Failed to delete position: {e}")
            return False

    # ==================== DCA SETUP METHODS ====================

    def save_dca_setup(self, symbol: str, setup_info: Dict[str, Any]) -> bool:
        """Save or update DCA setup for a symbol."""
        if not self.enabled or self.dca_setup_collection is None:
            return False

        try:
            setup_doc = {
                "symbol": symbol,
                "setup_info": setup_info,
                "updated_at": datetime.now(),
                "status": "ACTIVE"
            }

            result = self.dca_setup_collection.update_one(
                {"symbol": symbol},
                {"$set": setup_doc},
                upsert=True
            )
            return result.acknowledged

        except Exception as e:
            logger.error(f"Failed to save DCA setup for {symbol}: {e}")
            return False

    def get_dca_setup(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get DCA setup for a symbol."""
        if not self.enabled or self.dca_setup_collection is None:
            return None

        try:
            doc = self.dca_setup_collection.find_one({"symbol": symbol})
            return self._parse_document(doc) if doc else None
        except Exception as e:
            logger.error(f"Failed to get DCA setup for {symbol}: {e}")
            return None

    def get_all_dca_setups(self) -> List[Dict[str, Any]]:
        """Get all active DCA setups."""
        if not self.enabled or self.dca_setup_collection is None:
            return []

        try:
            setups = list(self.dca_setup_collection.find({"status": "ACTIVE"}))
            return [self._parse_document(s) for s in setups]
        except Exception as e:
            logger.error(f"Failed to get DCA setups: {e}")
            return []

    def update_dca_setup_status(self, symbol: str, status: str) -> bool:
        """Update DCA setup status."""
        if not self.enabled or self.dca_setup_collection is None:
            return False

        try:
            result = self.dca_setup_collection.update_one(
                {"symbol": symbol},
                {"$set": {"status": status, "updated_at": datetime.now()}}
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Failed to update DCA setup status for {symbol}: {e}")
            return False

    # ==================== PERFORMANCE METHODS ====================

    def save_performance_metric(self, metric: Dict[str, Any]) -> bool:
        """Save a performance metric."""
        if not self.enabled or self.performance_collection is None:
            return False

        try:
            metric["timestamp"] = datetime.now()
            metric["date"] = datetime.now().strftime("%Y-%m-%d")

            result = self.performance_collection.insert_one(metric)
            return result.acknowledged

        except Exception as e:
            logger.error(f"Failed to save performance metric: {e}")
            return False

    def get_performance_metrics(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get performance metrics for the last N days."""
        if not self.enabled or self.performance_collection is None:
            return []

        try:
            cutoff = datetime.now() - timedelta(days=days)
            metrics = list(self.performance_collection.find(
                {"timestamp": {"$gte": cutoff}}
            ).sort("timestamp", -1))
            return [self._parse_document(m) for m in metrics]
        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return []

    # ==================== STATS METHODS ====================

    def save_daily_stats(self, stats: Dict) -> bool:
        """Save daily statistics."""
        if not self.enabled or self.stats_collection is None:
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
                "max_positions": stats.get("max_positions", 0),
                "daily_wins": stats.get("daily_wins", 0),
                "daily_losses": stats.get("daily_losses", 0),
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
        if not self.enabled or self.stats_collection is None:
            return []

        try:
            stats = list(self.stats_collection.find()
                        .sort("date", -1)
                        .limit(days))
            return [self._parse_document(s) for s in stats]
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return []

    # ==================== PERFORMANCE SUMMARY ====================

    def get_performance_summary(self) -> Dict:
        """Get overall performance summary."""
        if not self.enabled:
            return {}

        result = {
            "total_trades": 0,
            "total_pnl": 0.0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0.0,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "average_pnl": 0.0,
            "total_dca_setups": 0,
            "active_dca_setups": 0,
        }

        try:
            # Get trade statistics
            if self.trades_collection is not None:
                total_trades = self.trades_collection.count_documents({})
                if total_trades > 0:
                    # Aggregate PnL
                    pipeline = [
                        {"$group": {
                            "_id": None,
                            "total_pnl": {"$sum": "$realized_pnl"},
                            "winning_trades": {"$sum": {"$cond": [{"$gt": ["$realized_pnl", 0]}, 1, 0]}},
                            "losing_trades": {"$sum": {"$cond": [{"$lt": ["$realized_pnl", 0]}, 1, 0]}},
                            "best_trade": {"$max": "$realized_pnl"},
                            "worst_trade": {"$min": "$realized_pnl"},
                        }}
                    ]

                    agg_result = list(self.trades_collection.aggregate(pipeline))
                    if agg_result:
                        data = agg_result[0]
                        result.update({
                            "total_trades": total_trades,
                            "total_pnl": data.get("total_pnl", 0),
                            "winning_trades": data.get("winning_trades", 0),
                            "losing_trades": data.get("losing_trades", 0),
                            "best_trade": data.get("best_trade", 0),
                            "worst_trade": data.get("worst_trade", 0),
                            "win_rate": (data.get("winning_trades", 0) / total_trades * 100) if total_trades > 0 else 0,
                            "average_pnl": data.get("total_pnl", 0) / total_trades if total_trades > 0 else 0,
                        })

            # Get DCA setup statistics
            if self.dca_setup_collection is not None:
                result["total_dca_setups"] = self.dca_setup_collection.count_documents({})
                result["active_dca_setups"] = self.dca_setup_collection.count_documents({"status": "ACTIVE"})

        except Exception as e:
            logger.error(f"Failed to get performance summary: {e}")

        return result

    # ==================== UTILITY METHODS ====================

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
            # NEW fields
            "dca_count": getattr(position, 'dca_count', 1),
            "trailing_activated": getattr(position, 'trailing_activated', False),
            "trailing_stop_price": getattr(position, 'trailing_stop_price', 0.0),
            "highest_price": getattr(position, 'highest_price', position.entry_price),
            "lowest_price": getattr(position, 'lowest_price', position.entry_price),
        }

    def clear_collection(self, collection_name: str) -> bool:
        """Clear a collection (use with caution)."""
        if not self.enabled:
            return False

        collection_map = {
            "active": self.active_collection,
            "resolved": self.resolved_collection,
            "trades": self.trades_collection,
            "stats": self.stats_collection,
            "dca_setups": self.dca_setup_collection,
            "performance": self.performance_collection,
        }

        collection = collection_map.get(collection_name)
        if collection is None:
            return False

        try:
            result = collection.delete_many({})
            logger.info(f"Cleared {result.deleted_count} documents from {collection_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to clear {collection_name}: {e}")
            return False

    def get_collection_stats(self) -> Dict[str, int]:
        """Get statistics for all collections."""
        stats = {}
        collections = {
            "active": self.active_collection,
            "resolved": self.resolved_collection,
            "trades": self.trades_collection,
            "stats": self.stats_collection,
            "dca_setups": self.dca_setup_collection,
            "performance": self.performance_collection,
        }

        for name, collection in collections.items():
            if collection is not None:
                try:
                    stats[name] = collection.count_documents({})
                except:
                    stats[name] = 0
            else:
                stats[name] = 0

        return stats

    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")


# Singleton instance
mongodb_client = MongoDBClient()

__all__ = ["mongodb_client", "MongoDBClient"]
