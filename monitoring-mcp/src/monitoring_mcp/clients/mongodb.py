"""
MongoDB client for server status and replica health.

Provides async methods for MongoDB monitoring using motor.
"""

import logging
from typing import Any, Dict, List, Optional

from monitoring_mcp.auth import get_auth_provider
from monitoring_mcp.config import get_config
from monitoring_mcp.models import (
    HealthStatus,
    MongoDBConnectionStats,
    MongoDBOperationStats,
    MongoDBReplicaMember,
    MongoDBStatus,
)

logger = logging.getLogger(__name__)


class MongoDBClient:
    """Async client for MongoDB monitoring using motor."""
    
    def __init__(self):
        self.config = get_config().mongodb
        self.thresholds = get_config().thresholds
        self.auth = get_auth_provider("mongodb")
        self._client = None
    
    async def _get_client(self):
        """Get or create MongoDB client."""
        if self._client is None:
            try:
                from motor.motor_asyncio import AsyncIOMotorClient
            except ImportError:
                raise ImportError("motor is required for MongoDB monitoring")
            
            creds = await self.auth.get_credentials()
            self._client = AsyncIOMotorClient(creds["uri"])
        
        return self._client
    
    async def close(self) -> None:
        """Close MongoDB client."""
        if self._client:
            self._client.close()
            self._client = None
    
    async def get_server_status(
        self,
        database: Optional[str] = None,
    ) -> MongoDBStatus:
        """
        Get MongoDB server status and metrics.
        
        Args:
            database: Database name (optional, uses admin by default)
            
        Returns:
            MongoDBStatus with server metrics
        """
        logger.info("Getting MongoDB server status")
        
        result = MongoDBStatus(
            status=HealthStatus.HEALTHY,
            connections_threshold_warning=self.thresholds.mongodb_connections_warning,
            connections_threshold_critical=self.thresholds.mongodb_connections_critical,
        )
        
        try:
            client = await self._get_client()
            db_name = database or self.config.database
            db = client[db_name]
            
            # Get server status
            status = await db.command("serverStatus")
            
            # Basic info
            result.host = status.get("host", "")
            result.version = status.get("version", "")
            result.uptime_seconds = status.get("uptime", 0)
            
            # Connection stats
            connections = status.get("connections", {})
            result.connections = MongoDBConnectionStats(
                current=connections.get("current", 0),
                available=connections.get("available", 0),
                total_created=connections.get("totalCreated", 0),
                active=connections.get("active", 0),
            )
            
            # Operation stats (opcounters)
            opcounters = status.get("opcounters", {})
            result.operations = MongoDBOperationStats(
                insert=opcounters.get("insert", 0),
                query=opcounters.get("query", 0),
                update=opcounters.get("update", 0),
                delete=opcounters.get("delete", 0),
                getmore=opcounters.get("getmore", 0),
                command=opcounters.get("command", 0),
            )
            
            # Memory
            mem = status.get("mem", {})
            result.resident_mb = mem.get("resident", 0)
            result.virtual_mb = mem.get("virtual", 0)
            
            # Check connection thresholds
            current_connections = result.connections.current
            if current_connections >= self.thresholds.mongodb_connections_critical:
                result.status = HealthStatus.CRITICAL
                result.alerts.append(
                    f"Critical: {current_connections} connections >= {self.thresholds.mongodb_connections_critical}"
                )
            elif current_connections >= self.thresholds.mongodb_connections_warning:
                result.status = HealthStatus.WARNING
                result.alerts.append(
                    f"Warning: {current_connections} connections >= {self.thresholds.mongodb_connections_warning}"
                )
            
            # Check if replica set
            repl = status.get("repl")
            if repl:
                result.is_replica_set = True
                result.replica_set_name = repl.get("setName")
                
                # Get replica set status
                try:
                    rs_status = await db.command("replSetGetStatus")
                    await self._parse_replica_status(result, rs_status)
                except Exception as e:
                    logger.warning(f"Could not get replica set status: {e}")
            
            return result
            
        except ImportError as e:
            logger.error(f"motor not installed: {e}")
            result.status = HealthStatus.CRITICAL
            result.alerts.append("motor package not installed")
            return result
        except Exception as e:
            logger.error(f"MongoDB status check failed: {e}")
            result.status = HealthStatus.CRITICAL
            result.alerts.append(f"Error: {str(e)}")
            return result
    
    async def _parse_replica_status(
        self,
        result: MongoDBStatus,
        rs_status: Dict[str, Any],
    ) -> None:
        """Parse replica set status and update result."""
        members: List[MongoDBReplicaMember] = []
        primary_found = False
        
        for member in rs_status.get("members", []):
            state = member.get("state", 0)
            state_str = member.get("stateStr", "")
            health = member.get("health", 0)
            
            is_primary = state == 1
            is_secondary = state == 2
            
            if is_primary:
                primary_found = True
            
            # Calculate lag for secondaries
            lag_seconds = None
            if is_secondary:
                # optimeDate is the oplog timestamp
                primary_optime = rs_status.get("optimes", {}).get("lastCommittedOpTime", {}).get("ts")
                member_optime = member.get("optimeDate")
                
                if primary_optime and member_optime:
                    # This is a simplification - actual lag calculation may vary
                    lag_seconds = member.get("optimeLag", 0)
            
            members.append(MongoDBReplicaMember(
                name=member.get("name", ""),
                state=str(state),
                state_str=state_str,
                health=int(health),
                uptime=member.get("uptime", 0),
                lag_seconds=lag_seconds,
                is_primary=is_primary,
                is_secondary=is_secondary,
            ))
            
            # Check member health
            if health != 1:
                result.status = HealthStatus.CRITICAL
                result.alerts.append(f"Critical: Member {member.get('name')} is unhealthy (state: {state_str})")
            
            # Check replication lag
            if lag_seconds is not None:
                if lag_seconds >= self.thresholds.mongodb_replication_lag_critical:
                    result.status = HealthStatus.CRITICAL
                    result.alerts.append(
                        f"Critical: Member {member.get('name')} replication lag {lag_seconds}s"
                    )
                elif lag_seconds >= self.thresholds.mongodb_replication_lag_warning:
                    if result.status != HealthStatus.CRITICAL:
                        result.status = HealthStatus.WARNING
                    result.alerts.append(
                        f"Warning: Member {member.get('name')} replication lag {lag_seconds}s"
                    )
        
        result.members = members
        
        # Check for primary
        if not primary_found:
            result.status = HealthStatus.CRITICAL
            result.alerts.append("Critical: No PRIMARY member in replica set")
    
    async def check_replica_health(self) -> MongoDBStatus:
        """
        Check MongoDB replica set health.
        
        Returns:
            MongoDBStatus with replica set information
        """
        logger.info("Checking MongoDB replica set health")
        
        result = await self.get_server_status()
        
        if not result.is_replica_set:
            result.alerts.append("Server is not part of a replica set")
        
        return result
    
    async def get_database_stats(
        self,
        database: str,
    ) -> Dict[str, Any]:
        """
        Get database statistics.
        
        Args:
            database: Database name
            
        Returns:
            Database statistics dictionary
        """
        try:
            client = await self._get_client()
            db = client[database]
            stats = await db.command("dbStats")
            
            return {
                "database": database,
                "collections": stats.get("collections", 0),
                "objects": stats.get("objects", 0),
                "dataSize": stats.get("dataSize", 0),
                "storageSize": stats.get("storageSize", 0),
                "indexes": stats.get("indexes", 0),
                "indexSize": stats.get("indexSize", 0),
            }
            
        except Exception as e:
            logger.error(f"Database stats failed: {e}")
            return {"database": database, "error": str(e)}
