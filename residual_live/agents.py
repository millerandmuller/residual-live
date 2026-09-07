"""
residual_live.agents
====================
Google ADK agents for reading contract clauses and generating settlement notices.
"""

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field
import logging
from decimal import Decimal
import json
import uuid

from .config import settings

logger = logging.getLogger("residual_live.agents")

class ClauseAnalysis(BaseModel):
    is_applicable: bool = Field(description="Whether the clause triggers a milestone bonus based on streams.")
    threshold_value: int = Field(description="The stream minutes threshold required.")
    bonus_amount: float = Field(description="The fixed bonus amount in USD.")


clause_reader_agent = LlmAgent(
    name="clause_reader",
    model=settings.GEMINI_MODEL,
    instruction="""
    Analyze the following contract clause.
    Extract the streaming threshold (in minutes) and the fixed bonus amount (in USD).
    """,
    output_schema=ClauseAnalysis
)

notice_generator_agent = LlmAgent(
    name="notice_generator",
    model="gemini-3.5-flash",
    instruction="""
    Write a formal settlement notice computation note (1-2 short sentences) stating that a milestone has been reached.
    You MUST cite the exact clause directly in your message.
    You MUST include the provided verification_flag in the final message.
    Keep it professional, concise, and suitable for an official audit log.
    """
)

session_service = InMemorySessionService()

def analyze_contract_clause(clause_text: str) -> ClauseAnalysis:
    """Agent 1: Klausel-Leser zur Vertragsanalyse"""
    logger.info(f"Agent 1 (Klausel-Leser) ist aktiv... Modell: {clause_reader_agent.model.name if hasattr(clause_reader_agent.model, 'name') else clause_reader_agent.model}")
    runner = Runner(
        agent=clause_reader_agent,
        app_name="residual_live_app",
        session_service=session_service,
        auto_create_session=True
    )
    
    events = runner.run(
        user_id="system",
        session_id=f"clause_analysis_session_{uuid.uuid4().hex[:8]}",
        new_message=types.Content(parts=[types.Part.from_text(text=f"Clause: {clause_text}")])
    )
    
    final_text = ""
    for event in events:
        if getattr(event, "message", None) and getattr(event.message, "parts", None):
            for part in event.message.parts:
                if getattr(part, "text", None):
                    final_text += part.text

    final_text = final_text.strip()
    if final_text.startswith("```json"):
        final_text = final_text[7:]
    if final_text.startswith("```"):
        final_text = final_text[3:]
    if final_text.endswith("```"):
        final_text = final_text[:-3]
    final_text = final_text.strip()
    
    data = json.loads(final_text)
    return ClauseAnalysis.model_validate(data)

def generate_settlement_message(clause_text: str, total_stream_minutes: int, bonus_amount: Decimal, verification_flag: str = "") -> str:
    """Agent 2: Bezifferung/Mitteilungserstellung"""
    logger.info(f"Agent 2 (Mitteilungs-Ersteller) ist aktiv... Modell: {notice_generator_agent.model.name if hasattr(notice_generator_agent.model, 'name') else notice_generator_agent.model}")
    runner = Runner(
        agent=notice_generator_agent,
        app_name="residual_live_app",
        session_service=session_service,
        auto_create_session=True
    )
    
    prompt = f"""
    Total stream minutes achieved: {total_stream_minutes:,}.
    Bonus amount triggered: ${bonus_amount:,.2f}.
    Clause to cite: "{clause_text}"
    Verification flag to include: {verification_flag}
    """
    
    events = runner.run(
        user_id="system",
        session_id=f"notice_gen_session_{uuid.uuid4().hex[:8]}",
        new_message=types.Content(parts=[types.Part.from_text(text=prompt)])
    )
    
    final_text = ""
    for event in events:
        if getattr(event, "message", None) and getattr(event.message, "parts", None):
            for part in event.message.parts:
                if getattr(part, "text", None):
                    final_text += part.text
                    
    return final_text.strip()
