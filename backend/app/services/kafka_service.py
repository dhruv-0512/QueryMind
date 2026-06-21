import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from aiokafka import AIOKafkaProducer
from app.config import settings

logger = logging.getLogger(__name__)

class KafkaService:
    def __init__(self):
        self.producer: Optional[AIOKafkaProducer] = None
        self.bootstrap_servers = settings.KAFKA_BOOTSTRAP_SERVERS

    async def start(self) -> None:
        """Initialize and start the Kafka asynchronous producer."""
        try:
            logger.info(f"Starting Kafka producer on {self.bootstrap_servers}...")
            self.producer = AIOKafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                retry_backoff_ms=500,
                request_timeout_ms=10000
            )
            await self.producer.start()
            logger.info("Kafka producer started successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            self.producer = None

    async def stop(self) -> None:
        """Gracefully stop the Kafka producer."""
        if self.producer:
            try:
                await self.producer.stop()
                logger.info("Kafka producer stopped.")
            except Exception as e:
                logger.error(f"Error stopping Kafka producer: {e}")
            finally:
                self.producer = None

    async def publish_event(
        self, topic: str, event_type: str, user_id: Optional[str], payload: Dict[str, Any]
    ) -> None:
        """Publish a structured audit event to the specified Kafka topic asynchronously."""
        if not self.producer:
            logger.warning(f"Kafka producer not active. Skipping event publishing: {event_type} to {topic}")
            return

        event = {
            "event_type": event_type,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload
        }

        try:
            # Send and wait checks for delivery confirmation in a non-blocking way
            await self.producer.send_and_wait(topic, event)
            logger.info(f"Published event '{event_type}' to topic '{topic}'")
        except Exception as e:
            logger.error(f"Failed to publish event to Kafka on topic '{topic}': {e}")

kafka_service = KafkaService()
