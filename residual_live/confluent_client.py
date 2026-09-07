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
from .schemas import RightsTerritory, RoyaltyEvent, SettlementNotice, UsageChannel

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
            logger.error("Confluent credentials missing — producer must hard fail.")
            raise ValueError("Confluent credentials missing.")
        else:
            conf = get_kafka_config(is_consumer=False)
            self._producer = Producer(conf)

    def produce_event(self, event: RoyaltyEvent, topic: Optional[str] = None) -> bool:
        t = topic or settings.CONFLUENT_TOPIC
        payload = event.model_dump_json()
        key = f"{event.title_id}:{event.event_id}"

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
            logger.error("Confluent credentials missing. Consumer thread must hard fail.")
            raise ValueError("Confluent credentials missing.")

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


class ObligationsProducer:
    """
    Produces SettlementNotice records to the Confluent obligations topic.

    Each notice is serialised as JSON and keyed by ``notice_id`` so that
    Kafka's log-compaction preserves the latest state per notice.
    """

    def __init__(self):
        if not settings.has_confluent_credentials():
            logger.error("Confluent credentials missing — obligations producer must hard fail.")
            raise ValueError("Confluent credentials missing.")
        conf = get_kafka_config(is_consumer=False)
        self._producer = Producer(conf)

    def produce_notice(self, notice: SettlementNotice, topic: Optional[str] = None) -> bool:
        """
        Publish a SettlementNotice to the obligations topic.

        The notice is JSON-serialised via Pydantic so all Decimal and datetime
        values are rendered to strings deterministically.  The message key is
        the notice_id, enabling consumer idempotency and log-compaction.
        """
        t = topic or settings.CONFLUENT_OBLIGATIONS_TOPIC
        payload = notice.model_dump_json()
        key = notice.notice_id
        try:
            self._producer.produce(
                t,
                key=key.encode("utf-8"),
                value=payload.encode("utf-8"),
            )
            self._producer.flush(timeout=5.0)
            logger.info(
                "Produced settlement notice %s (status=%s) to %s",
                notice.notice_id, notice.status.value, t,
            )
            return True
        except Exception as e:
            logger.error("Failed to produce settlement notice %s: %s", notice.notice_id, e)
            return False


class ObligationsConsumerThread(threading.Thread):
    """
    Background consumer for the obligations topic.

    On every message, the notice is deserialised and its full audit-chain
    integrity is verified via ``SettlementNotice.verify_audit_integrity()``.
    Only notices that pass all three checks (entry hashes, chain hash, notice
    hash) and carry the current ``HASH_SCHEMA_VERSION`` are forwarded to the
    caller-supplied callback.  Tampered or stale-schema notices are logged as
    errors and dropped — they are never silently accepted.
    """

    def __init__(
        self,
        on_notice_received: Callable[[SettlementNotice], None],
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
    ):
        super().__init__(daemon=True)
        self.on_notice_received = on_notice_received
        self.topic = topic or settings.CONFLUENT_OBLIGATIONS_TOPIC
        self.group_id = group_id or f"{settings.CONFLUENT_GROUP_ID}-obligations-{uuid.uuid4().hex[:6]}"
        self._running = False
        self._consumer = None

    def run(self):
        self._running = True
        if not settings.has_confluent_credentials():
            logger.error("Confluent credentials missing. Obligations consumer thread must hard fail.")
            raise ValueError("Confluent credentials missing.")

        conf = get_kafka_config(is_consumer=True, group_id=self.group_id)
        try:
            self._consumer = Consumer(conf)
            self._consumer.subscribe([self.topic])
            logger.info(
                "Obligations consumer subscribed to %s with group %s",
                self.topic, self.group_id,
            )

            while self._running:
                msg = self._consumer.poll(timeout=1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    logger.error("Kafka obligations error: %s", msg.error())
                    continue

                try:
                    raw_val = msg.value().decode("utf-8")
                    data = json.loads(raw_val)
                    notice = SettlementNotice.model_validate(data)
                except Exception as ex:
                    logger.error(
                        "Could not deserialise obligations message (offset=%s): %s",
                        msg.offset(), ex,
                    )
                    continue

                # --- Audit-chain integrity gate ----------------------------
                integrity = notice.verify_audit_integrity()
                if not integrity["all_valid"]:
                    logger.error(
                        "INTEGRITY FAILURE for notice %s (offset=%s): "
                        "entries_valid=%s chain_valid=%s notice_valid=%s "
                        "schema_version_match=%s failed_entries=%s — notice DROPPED.",
                        notice.notice_id,
                        msg.offset(),
                        integrity["entries_valid"],
                        integrity["chain_valid"],
                        integrity["notice_valid"],
                        integrity["schema_version_match"],
                        integrity["failed_entry_indices"],
                    )
                    continue
                # ----------------------------------------------------------

                self.on_notice_received(notice)

        except Exception as e:
            logger.error("Obligations consumer error: %s", e)
        finally:
            if self._consumer:
                self._consumer.close()
                logger.info("Obligations consumer closed cleanly.")

    def stop(self):
        self._running = False
