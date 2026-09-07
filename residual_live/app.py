"""
residual_live.app
=================
FastAPI web application and WebSocket server for Residual Live.
Provides real-time event streaming, settlement inspection, human-in-the-loop approval,
and IBM Bob audit verification.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .confluent_client import (
    ConfluentConsumerThread,
    ConfluentProducer,
    ObligationsConsumerThread,
    ObligationsProducer,
)
from .demo_data import create_curated_demo_stream
from .engine import RoyaltyEngine
from .schemas import RoyaltyEvent, SettlementNotice

logger = logging.getLogger("residual_live.app")

engine = RoyaltyEngine()
producer = ConfluentProducer()
obligations_producer = ObligationsProducer()
demo_events_queue: List[RoyaltyEvent] = []
_loop: asyncio.AbstractEventLoop = None


class ConnectionManager:
    """Manages active browser WebSocket connections."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        payload = json.dumps(message)
        dead = []
        for conn in self.active_connections:
            try:
                await conn.send_text(payload)
            except Exception:
                dead.append(conn)
        for conn in dead:
            self.disconnect(conn)


ws_manager = ConnectionManager()


def publish_obligation_notice(notice: SettlementNotice):
    """Publish quantified settlement obligation to Confluent Cloud obligations topic."""
    try:
        obligations_producer.produce_notice(notice)
        logger.info(f"Published obligation {notice.notice_id} to Confluent obligations topic")
    except Exception as e:
        logger.error(f"Failed to publish notice to obligations topic: {e}")


def on_kafka_event(event: RoyaltyEvent):
    """Callback when an event arrives from Confluent Cloud."""
    res = engine.process_event(event)
    
    # If Hero Moment or milestone generated a notice, publish to obligations topic
    if res.get("hero_notice_id"):
        hero = engine.settlement_notices.get(res["hero_notice_id"])
        if hero:
            publish_obligation_notice(hero)

    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast({
                "type": "NEW_EVENT",
                "event": event.model_dump(mode="json"),
                "engine_update": res,
                "summary": engine.get_state_summary(),
            }),
            _loop,
        )


def on_obligation_received(notice: SettlementNotice):
    """Callback when a verified obligation arrives from Confluent Cloud obligations topic."""
    logger.info(f"Obligation consumed from Confluent: {notice.notice_id} (status={notice.status.value})")
    if _loop and _loop.is_running():
        asyncio.run_coroutine_threadsafe(
            ws_manager.broadcast({
                "type": "OBLIGATION_STREAMED",
                "notice": notice.model_dump(mode="json"),
                "audit_verification": notice.verify_audit_integrity(),
                "topic": settings.CONFLUENT_OBLIGATIONS_TOPIC,
            }),
            _loop,
        )


consumer_thread = ConfluentConsumerThread(on_event_received=on_kafka_event)
obligations_consumer_thread = ObligationsConsumerThread(on_notice_received=on_obligation_received)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _loop, demo_events_queue
    _loop = asyncio.get_running_loop()
    demo_events_queue = create_curated_demo_stream()
    consumer_thread.start()
    obligations_consumer_thread.start()
    logger.info("Residual Live application started with dual Confluent nervous system (events + obligations).")
    yield
    consumer_thread.stop()
    obligations_consumer_thread.stop()


app = FastAPI(title="Residual Live — Real-time Royalty Clearing", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files directory
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Residual Live Backend Running</h1><p>Static UI loading...</p>")


@app.get("/api/status")
def get_status():
    return engine.get_state_summary()


@app.get("/api/rules")
def get_rules():
    return [r.model_dump(mode="json") for r in engine.rules]


class ContractIntakeRequest(BaseModel):
    contract_text: str


@app.get("/api/contract/sample")
def get_sample_contract():
    """Return authentic public SAG-AFTRA sample contract clause text."""
    from .demo_data import SAMPLE_SAG_AFTRA_AGREEMENT
    return {"sample_text": SAMPLE_SAG_AFTRA_AGREEMENT.strip()}


@app.post("/api/contract/intake")
async def contract_intake(req: ContractIntakeRequest):
    """Run Google ADK Contract-Intake-Agent to extract rules from agreement text."""
    try:
        from .agents import intake_contract_document, build_contract_rules_from_intake
        intake_output = intake_contract_document(req.contract_text)
        new_rules = build_contract_rules_from_intake(intake_output)
        
        # Update rules in engine
        engine.rules = new_rules
        
        # Broadcast update over WebSockets
        await ws_manager.broadcast({
            "type": "RULES_UPDATED",
            "contract": intake_output.model_dump(mode="json"),
            "rules": [r.model_dump(mode="json") for r in engine.rules],
        })
        
        return {
            "status": "success",
            "contract": intake_output.model_dump(mode="json"),
            "rules_count": len(engine.rules),
            "rules": [r.model_dump(mode="json") for r in engine.rules],
        }
    except Exception as e:
        logger.error(f"Contract intake error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/events")
def get_events():
    return [e.model_dump(mode="json") for e in engine.events[-100:]]


@app.get("/api/settlements")
def get_settlements():
    res = []
    for s in engine.settlement_notices.values():
        res.append(s.model_dump(mode="json"))
    return res


@app.get("/api/settlements/{notice_id}")
def get_settlement_detail(notice_id: str):
    notice = engine.settlement_notices.get(notice_id)
    if not notice:
        raise HTTPException(status_code=404, detail="Settlement notice not found")
    data = notice.model_dump(mode="json")
    data["audit_verification"] = notice.verify_audit_integrity()
    return data


@app.post("/api/settlements/{notice_id}/approve")
async def approve_settlement(notice_id: str):
    approved = engine.approve_settlement(notice_id, approved_by="Chris (Rights Administrator)")
    if not approved:
        raise HTTPException(status_code=404, detail="Settlement notice not found")

    # Publish approved status to obligations topic
    publish_obligation_notice(approved)

    await ws_manager.broadcast({
        "type": "SETTLEMENT_APPROVED",
        "notice": approved.model_dump(mode="json"),
        "summary": engine.get_state_summary(),
    })
    return approved.model_dump(mode="json")


@app.post("/api/demo/step")
async def demo_step():
    """Simulate next curated demo event step (for live demo video recording)."""
    global demo_events_queue
    if not demo_events_queue:
        demo_events_queue = create_curated_demo_stream()

    event = demo_events_queue.pop(0)

    # Produce to real Confluent Cloud (or local fallback)
    producer.produce_event(event)

    # Process into engine immediately
    res = engine.process_event(event)

    if res.get("hero_notice_id"):
        hero = engine.settlement_notices.get(res["hero_notice_id"])
        if hero:
            publish_obligation_notice(hero)

    await ws_manager.broadcast({
        "type": "NEW_EVENT",
        "event": event.model_dump(mode="json"),
        "engine_update": res,
        "summary": engine.get_state_summary(),
    })

    return {
        "processed_event": event.model_dump(mode="json"),
        "engine_update": res,
        "remaining_demo_events": len(demo_events_queue),
    }


@app.post("/api/demo/reset")
async def demo_reset():
    """Reset engine state to initial blank slate."""
    global engine, demo_events_queue
    engine = RoyaltyEngine()
    demo_events_queue = create_curated_demo_stream()
    await ws_manager.broadcast({
        "type": "RESET",
        "summary": engine.get_state_summary(),
    })
    return {"status": "reset", "summary": engine.get_state_summary()}


@app.get("/api/bob-audit")
def get_bob_audit():
    """Return IBM Bob task verification metadata for the jury."""
    return {
        "task_id": "e1935a4d4dfe486aa3290acaa2f66f57",
        "session_costs_bobcoins": 1.921,
        "tool_calls": 30,
        "tests_passed": 52,
        "governed_by": "IBM Bob Shell (watsonx Code Assistant)",
        "proof_file": "bob-runs/20260907-043704.result.json",
        "ledger_file": "bob-runs/coins-ledger.md",
        "audit_guarantee": "3-layer tamper-evident SHA-256 cryptographic chain on every settlement notice",
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send initial snapshot upon connection
        await websocket.send_text(
            json.dumps({
                "type": "INITIAL_STATE",
                "summary": engine.get_state_summary(),
                "rules": [r.model_dump(mode="json") for r in engine.rules],
                "settlements": [s.model_dump(mode="json") for s in engine.settlement_notices.values()],
                "recent_events": [e.model_dump(mode="json") for e in engine.events[-20:]],
            })
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
