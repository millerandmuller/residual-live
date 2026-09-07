"""
residual_live.confluent_client
==============================
Confluent Cloud Kafka producer and consumer implementation.
Directly based on verified parameters from spikes/confluent/spike.py.
"""

from datetime import datetime, timezone
import json
import logging
import socket
import threading
import time
from typing import Callable, Generator, List, Optional
import uuid

from confluent_kafka import Consumer, KafkaError, KafkaException, Producer

from .config import settings
from .schemas import RightsTerritory, RoyaltyEvent, UsageChannel

logger = logging.getLogger("residual_live.confluent")


def get_kafka_config(is_consumer: bool = False, group_id: Optional[str] = None) -> dict:
    conf = {
        "bootstrap.servers": settings.CONFLUENT_BOOTSTRAP,
        "security.protocol": "SASL_SSL",
        "sasl.mechanism": "PLAIN",
        "sasl.username": settings.CONFLUENT_API_KEY,
        "sasl.password": settings.CONFLUENT_API_SECRET,
        "client.id": f"residual-live-{socket.gethostname()}",
    }
    if is_consumer:
        gid = group_id or settings.CONFLUENT_GROUP_ID
        conf.update({
            "group.id": gid,
            "auto.offset.reset": "latest",
            "enable.auto.commit": True,
        })
    return conf


class ConfluentProducer:
    """Thread-safe Kafka producer for royalty events."""

    def __init__(self):
        if not settings.has_confluent_credentials():
            logger.warning("Confluent credentials missing — producer initialized in mock mode.")
            self._producer = None
        else:
            conf = get_kafka_config(is_consumer=False)
            self._producer = Producer(conf)

    def produce_event(self, event: RoyaltyEvent, topic: Optional[str] = None) -> bool:
        t = topic or settings.CONFLUENT_TOPIC
        payload = event.model_dump_json()
        key = f"{event.title_id}:{event.event_id}"

        if self._producer:
            try:
                self._producer.produce(
                    t,
                    key=key.encode("utf-8"),
                    value=payload.encode("utf-8"),
                )
                self._producer.flush(timeout=5.0)
                logger.info(f"Produced event {event.event_id} to {t}")
                return True
            except Exception as e:
                logger.error(f"Failed to produce event {event.event_id}: {e}")
                return False
        else:
            logger.info(f"[MOCK PRODUCE] Event {event.event_id} -> {t}")
            return True

    def produce_batch(self, events: List[RoyaltyEvent], topic: Optional[str] = None) -> int:
        success = 0
        for ev in events:
            if self.produce_event(ev, topic=topic):
                success += 1
        return success


class ConfluentConsumerThread(threading.Thread):
    """Background listener consuming events from Confluent Cloud topic."""

    def __init__(
        self,
        on_event_received: Callable[[RoyaltyEvent], None],
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
    ):
        super().__init__(daemon=True)
        self.on_event_received = on_event_received
        self.topic = topic or settings.CONFLUENT_TOPIC
        self.group_id = group_id or f"{settings.CONFLUENT_GROUP_ID}-{uuid.uuid4().hex[:6]}"
        self._running = False
        self._consumer = None

    def run(self):
        self._running = True
        if not settings.has_confluent_credentials():
            logger.warning("Confluent credentials missing. Consumer thread will idle.")
            while self._running:
                time.sleep(1.0)
            return

        conf = get_kafka_config(is_consumer=True, group_id=self.group_id)
        try:
            self._consumer = Consumer(conf)
            self._consumer.subscribe([self.topic])
            logger.info(f"Confluent consumer subscribed to {self.topic} with group {self.group_id}")

            while self._running:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        logger.error(f"Kafka error: {msg.error()}")
                        continue

                try:
                    raw_val = msg.value().decode("utf-8")
                    data = json.loads(raw_val)
                    event = RoyaltyEvent.model_validate(data)
                    self.on_event_received(event)
                except Exception as ex:
                    logger.warning(f"Could not parse incoming Kafka message: {ex}")

        except Exception as e:
            logger.error(f"Consumer error: {e}")
        finally:
            if self._consumer:
                self._consumer.close()
                logger.info("Confluent consumer closed cleanly.")

    def stop(self):
        self._running = False
