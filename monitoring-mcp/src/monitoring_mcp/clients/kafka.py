"""
Kafka Admin API client.

Provides async methods for consumer lag and broker health monitoring.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from monitoring_mcp.auth import get_auth_provider
from monitoring_mcp.config import get_config
from monitoring_mcp.models import (
    HealthStatus,
    KafkaBrokerInfo,
    KafkaClusterHealth,
    KafkaLagResult,
    PartitionLag,
    TopicLag,
)

logger = logging.getLogger(__name__)


class KafkaClient:
    """Async client for Kafka Admin operations using aiokafka."""
    
    def __init__(self):
        self.config = get_config().kafka
        self.thresholds = get_config().thresholds
        self.auth = get_auth_provider("kafka")
        self._admin_client = None
        self._consumer = None
    
    async def _get_admin_client(self):
        """Get or create Kafka admin client."""
        if self._admin_client is None:
            try:
                from aiokafka.admin import AIOKafkaAdminClient
            except ImportError:
                raise ImportError("aiokafka is required for Kafka monitoring")
            
            creds = await self.auth.get_credentials()
            
            self._admin_client = AIOKafkaAdminClient(
                bootstrap_servers=creds["bootstrap_servers"],
                security_protocol=creds.get("security_protocol", "PLAINTEXT"),
                sasl_mechanism=creds.get("sasl_mechanism"),
                sasl_plain_username=creds.get("sasl_plain_username"),
                sasl_plain_password=creds.get("sasl_plain_password"),
                ssl_context=self._get_ssl_context(creds) if creds.get("security_protocol", "").endswith("SSL") else None,
            )
            await self._admin_client.start()
        
        return self._admin_client
    
    async def _get_consumer(self, group_id: str = "monitoring-mcp-consumer"):
        """Get or create Kafka consumer for offset queries."""
        try:
            from aiokafka import AIOKafkaConsumer
        except ImportError:
            raise ImportError("aiokafka is required for Kafka monitoring")
        
        creds = await self.auth.get_credentials()
        
        consumer = AIOKafkaConsumer(
            bootstrap_servers=creds["bootstrap_servers"],
            group_id=group_id,
            enable_auto_commit=False,
            security_protocol=creds.get("security_protocol", "PLAINTEXT"),
            sasl_mechanism=creds.get("sasl_mechanism"),
            sasl_plain_username=creds.get("sasl_plain_username"),
            sasl_plain_password=creds.get("sasl_plain_password"),
        )
        await consumer.start()
        return consumer
    
    def _get_ssl_context(self, creds: Dict[str, Any]):
        """Create SSL context if needed."""
        import ssl
        
        ssl_context = ssl.create_default_context()
        
        if creds.get("ssl_cafile"):
            ssl_context.load_verify_locations(creds["ssl_cafile"])
        if creds.get("ssl_certfile") and creds.get("ssl_keyfile"):
            ssl_context.load_cert_chain(
                creds["ssl_certfile"],
                creds["ssl_keyfile"],
            )
        
        return ssl_context
    
    async def close(self) -> None:
        """Close Kafka clients."""
        if self._admin_client:
            await self._admin_client.close()
            self._admin_client = None
        if self._consumer:
            await self._consumer.stop()
            self._consumer = None
    
    async def check_consumer_lag(
        self,
        consumer_group: str,
        topics: Optional[List[str]] = None,
    ) -> KafkaLagResult:
        """
        Check consumer group lag for specified topics.
        
        Args:
            consumer_group: Consumer group name
            topics: List of topics to check (optional, checks all if not specified)
            
        Returns:
            KafkaLagResult with lag metrics
        """
        logger.info(f"Checking lag for consumer group: {consumer_group}")
        
        result = KafkaLagResult(
            consumer_group=consumer_group,
            status=HealthStatus.HEALTHY,
            lag_threshold_warning=self.thresholds.kafka_lag_warning,
            lag_threshold_critical=self.thresholds.kafka_lag_critical,
        )
        
        try:
            from aiokafka import AIOKafkaConsumer, TopicPartition
            from aiokafka.admin import AIOKafkaAdminClient
            
            admin = await self._get_admin_client()
            
            # Get consumer group offsets
            group_offsets = await admin.list_consumer_group_offsets(consumer_group)
            
            if not group_offsets:
                result.status = HealthStatus.WARNING
                result.alerts.append(f"Consumer group '{consumer_group}' not found or has no offsets")
                return result
            
            # Get unique topics from offsets
            offset_topics: Set[str] = {tp.topic for tp in group_offsets.keys()}
            
            # Filter topics if specified
            if topics:
                offset_topics = offset_topics.intersection(set(topics))
            
            if not offset_topics:
                result.status = HealthStatus.WARNING
                result.alerts.append(f"No matching topics found for consumer group")
                return result
            
            # Create temporary consumer to get end offsets
            consumer = await self._get_consumer()
            
            try:
                topic_lags: List[TopicLag] = []
                total_lag = 0
                
                for topic in offset_topics:
                    # Get partition info
                    partitions = consumer.partitions_for_topic(topic)
                    if not partitions:
                        continue
                    
                    # Build TopicPartitions
                    topic_partitions = [TopicPartition(topic, p) for p in partitions]
                    
                    # Get end offsets (latest)
                    end_offsets = await consumer.end_offsets(topic_partitions)
                    
                    partition_lags: List[PartitionLag] = []
                    topic_total_lag = 0
                    max_partition_lag = 0
                    
                    for tp in topic_partitions:
                        current_offset = group_offsets.get(tp)
                        if current_offset is None:
                            current_offset = 0
                        else:
                            current_offset = current_offset.offset
                        
                        end_offset = end_offsets.get(tp, 0)
                        lag = max(0, end_offset - current_offset)
                        
                        partition_lags.append(PartitionLag(
                            partition=tp.partition,
                            current_offset=current_offset,
                            end_offset=end_offset,
                            lag=lag,
                        ))
                        
                        topic_total_lag += lag
                        max_partition_lag = max(max_partition_lag, lag)
                    
                    topic_lags.append(TopicLag(
                        topic=topic,
                        partitions=partition_lags,
                        total_lag=topic_total_lag,
                        max_partition_lag=max_partition_lag,
                    ))
                    
                    total_lag += topic_total_lag
                    
                    # Check thresholds per topic
                    if max_partition_lag >= self.thresholds.kafka_lag_critical:
                        result.status = HealthStatus.CRITICAL
                        result.alerts.append(
                            f"Critical: Topic '{topic}' max partition lag {max_partition_lag} >= {self.thresholds.kafka_lag_critical}"
                        )
                    elif max_partition_lag >= self.thresholds.kafka_lag_warning:
                        if result.status != HealthStatus.CRITICAL:
                            result.status = HealthStatus.WARNING
                        result.alerts.append(
                            f"Warning: Topic '{topic}' max partition lag {max_partition_lag} >= {self.thresholds.kafka_lag_warning}"
                        )
                
                result.topics = topic_lags
                result.total_lag = total_lag
                
            finally:
                await consumer.stop()
            
            return result
            
        except ImportError as e:
            logger.error(f"aiokafka not installed: {e}")
            result.status = HealthStatus.CRITICAL
            result.alerts.append("aiokafka package not installed")
            return result
        except Exception as e:
            logger.error(f"Kafka lag check failed: {e}")
            result.status = HealthStatus.CRITICAL
            result.alerts.append(f"Error: {str(e)}")
            return result
    
    async def get_broker_health(self) -> KafkaClusterHealth:
        """
        Get Kafka cluster and broker health status.
        
        Returns:
            KafkaClusterHealth with broker information
        """
        logger.info("Checking Kafka broker health")
        
        result = KafkaClusterHealth(
            status=HealthStatus.HEALTHY,
        )
        
        try:
            admin = await self._get_admin_client()
            
            # Get cluster metadata
            cluster_metadata = await admin.describe_cluster()
            
            # Get broker info
            brokers: List[KafkaBrokerInfo] = []
            controller_id = cluster_metadata.controller_id if hasattr(cluster_metadata, 'controller_id') else None
            
            for broker in cluster_metadata.brokers:
                brokers.append(KafkaBrokerInfo(
                    broker_id=broker.node_id,
                    host=broker.host,
                    port=broker.port,
                    rack=broker.rack,
                    is_controller=(broker.node_id == controller_id),
                ))
            
            result.brokers = brokers
            result.broker_count = len(brokers)
            result.controller_id = controller_id
            
            # Get topic count
            topics = await admin.list_topics()
            result.topic_count = len(topics)
            
            # Calculate total partitions
            total_partitions = 0
            for topic_metadata in topics:
                total_partitions += len(topic_metadata.partitions)
            result.partition_count = total_partitions
            
            # Check broker count (warn if only 1 broker)
            if result.broker_count < 2:
                result.status = HealthStatus.WARNING
                result.alerts.append(f"Only {result.broker_count} broker(s) - no redundancy")
            
            if controller_id is None:
                result.status = HealthStatus.CRITICAL
                result.alerts.append("No controller elected")
            
            return result
            
        except Exception as e:
            logger.error(f"Broker health check failed: {e}")
            result.status = HealthStatus.CRITICAL
            result.alerts.append(f"Error: {str(e)}")
            return result
