import asyncio
import json
import logging
import sys
import os
from uuid import UUID
from aiokafka import AIOKafkaConsumer
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

# Ensure project root is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app.config import settings
from app.models.audit import AuditLog

# Configure consumer logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("audit_consumer")

async def consume_events() -> None:
    """
    Subscribes to all event topics and records events in PostgreSQL audit_logs.
    """
    logger.info("Initializing Audit Consumer database connection...")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)

    topics = ["auth-events", "query-events", "schema-events", "audit-events"]
    
    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id="audit-group",
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        retry_backoff_ms=1000
    )

    # Boot retry loop
    while True:
        try:
            logger.info(f"Connecting to Kafka brokers on {settings.KAFKA_BOOTSTRAP_SERVERS}...")
            await consumer.start()
            logger.info(f"Kafka consumer active. Subscribed to topics: {topics}")
            break
        except Exception as e:
            logger.error(f"Kafka broker connection failed. Retrying in 5 seconds... Error: {e}")
            await asyncio.sleep(5)

    try:
        async for msg in consumer:
            try:
                event = msg.value
                event_type = event.get("event_type", "Unknown")
                user_id_str = event.get("user_id")
                payload = event.get("payload", {})

                logger.info(f"Received event '{event_type}' from topic '{msg.topic}'")

                # Parse UUID safely
                user_id = None
                if user_id_str:
                    try:
                        user_id = UUID(user_id_str)
                    except ValueError:
                        logger.warning(f"Invalid UUID string format for user_id: {user_id_str}")

                # Insert into DB
                async with SessionLocal() as session:
                    audit_record = AuditLog(
                        user_id=user_id,
                        event_type=event_type,
                        payload=payload
                    )
                    session.add(audit_record)
                    await session.commit()
                    logger.info(f"Recorded event '{event_type}' to audit_logs successfully.")

            except Exception as item_error:
                logger.error(f"Error processing consumed message: {item_error}")

    except Exception as loop_error:
        logger.error(f"Fatal error in consumer event loop: {loop_error}")
    finally:
        logger.info("Stopping consumer connection...")
        await consumer.stop()
        await engine.dispose()
        logger.info("Consumer stopped and engine connections released.")

if __name__ == "__main__":
    try:
        asyncio.run(consume_events())
    except KeyboardInterrupt:
        logger.info("Audit Consumer manually interrupted. Exiting.")
