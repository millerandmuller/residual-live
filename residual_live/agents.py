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
from typing import Optional

from .config import settings

logger = logging.getLogger("residual_live.agents")

class ClauseAnalysis(BaseModel):
    is_applicable: bool = Field(description="Whether the clause triggers a milestone bonus based on streams.")
    threshold_value: int = Field(description="The stream minutes threshold required.")
    bonus_amount: float = Field(description="The fixed bonus amount in USD.")


class ExtractedContractRule(BaseModel):
    rule_id: str = Field(description="Unique identifier for the rule, e.g. RULE-SVOD-BASE or RULE-STREAM-HERO-BONUS")
    rule_name: str = Field(description="Short human-readable rule name")
    rule_type: str = Field(description="One of: per_stream_minute, threshold_trigger, flat_fee_per_play")
    clause_reference: str = Field(description="Exact clause reference in the agreement, e.g. Section 4.1 or Section 4.2")
    channel: str = Field(default="svod", description="Usage channel, e.g. svod, avod, tvod")
    territory: str = Field(default="US", description="Geographic territory, e.g. US, GLOBAL")
    unit_rate_amount: Optional[float] = Field(default=None, description="Per-minute rate in USD if per_stream_minute (e.g. 0.0015)")
    threshold_value: Optional[float] = Field(default=None, description="Threshold metric level required, e.g. 5000000")
    threshold_metric: Optional[str] = Field(default="stream_minutes", description="stream_minutes or play_count")
    bonus_amount: Optional[float] = Field(default=None, description="Fixed bonus amount in USD when threshold is breached, e.g. 25000.00")
    notes: Optional[str] = Field(default="", description="Brief legal summary of clause terms")


class ContractIntakeOutput(BaseModel):
    contract_id: str = Field(description="Agreement identifier, e.g. AGR-SAG-DGA-2026-088")
    title_name: str = Field(description="Title or property governed by the agreement, e.g. Echoes of Eternity")
    licensor: str = Field(description="Licensor entity, e.g. Sovereign Media Rights LLC")
    licensee: str = Field(description="Licensee / distributor entity, e.g. Global Cinema Distribution Corp")
    governing_guild: str = Field(default="SAG-AFTRA", description="Union standard agreement")
    extracted_rules: list[ExtractedContractRule] = Field(description="List of all extracted operative royalty and milestone rules")


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

contract_intake_agent = LlmAgent(
    name="contract_intake_agent",
    model=settings.GEMINI_MODEL,
    instruction="""
    You are an expert legal contract analyst specializing in SAG-AFTRA, WGA, and DGA entertainment licensing agreements.
    Analyze the provided license agreement or schedule extract.
    Extract:
    1. Contract metadata: contract_id, title_name, licensor, licensee, governing_guild.
    2. All operative royalty rules:
       - Base streaming rates (rule_type: 'per_stream_minute', unit_rate_amount, clause_reference).
       - Milestone bonuses / threshold triggers (rule_type: 'threshold_trigger', threshold_value, bonus_amount, clause_reference).
    Be precise with dollar amounts, thresholds, and clause citations.
    """,
    output_schema=ContractIntakeOutput
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


def intake_contract_document(contract_text: str) -> ContractIntakeOutput:
    """Agent 3: Contract-Intake-Agent zur automatischen Regelerstellung aus Verträgen"""
    logger.info(f"Agent 3 (Contract-Intake-Agent) ist aktiv... Modell: {contract_intake_agent.model.name if hasattr(contract_intake_agent.model, 'name') else contract_intake_agent.model}")
    runner = Runner(
        agent=contract_intake_agent,
        app_name="residual_live_app",
        session_service=session_service,
        auto_create_session=True
    )
    
    prompt = f"Please analyze and extract all operative royalty and threshold rules from this agreement text:\n\n{contract_text}"
    
    events = runner.run(
        user_id="system",
        session_id=f"contract_intake_session_{uuid.uuid4().hex[:8]}",
        new_message=types.Content(parts=[types.Part.from_text(text=prompt)])
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
    return ContractIntakeOutput.model_validate(data)


def build_contract_rules_from_intake(intake: ContractIntakeOutput):
    """Convert extracted intake output into validated ContractRule domain objects."""
    from datetime import datetime, timezone
    from .schemas import ContractRule, RuleType, ThresholdBasis, ThresholdOperator, UsageChannel, RightsTerritory, Money
    
    now = datetime.now(timezone.utc)
    rules = []
    for r in intake.extracted_rules:
        is_threshold = "threshold" in r.rule_type.lower() or (r.threshold_value is not None and r.threshold_value > 0)
        
        if is_threshold:
            bonus = Decimal(str(r.bonus_amount or "25000.00"))
            thresh = Decimal(str(r.threshold_value or "5000000"))
            rate_amount = (bonus / thresh) if thresh > 0 else Decimal("0.0050")
            rule = ContractRule(
                rule_id=r.rule_id if r.rule_id.startswith("RULE-") else f"RULE-{r.rule_id}",
                contract_id=intake.contract_id,
                clause_reference=r.clause_reference,
                rule_type=RuleType.THRESHOLD_TRIGGER,
                channels=[UsageChannel.SVOD],
                territories=[RightsTerritory.US],
                threshold_basis=ThresholdBasis.STREAM_MINUTES,
                threshold_operator=ThresholdOperator.GREATER_THAN_OR_EQUAL,
                threshold_value=thresh,
                unit_rate=Money(amount=rate_amount, currency="USD"),
                apply_rate_to_full_accumulation=True,
                effective_from=now,
            )
        else:
            rate_amount = Decimal(str(r.unit_rate_amount or "0.0015"))
            rule = ContractRule(
                rule_id=r.rule_id if r.rule_id.startswith("RULE-") else f"RULE-{r.rule_id}",
                contract_id=intake.contract_id,
                clause_reference=r.clause_reference,
                rule_type=RuleType.PER_STREAM_MINUTE,
                channels=[UsageChannel.SVOD],
                territories=[RightsTerritory.US],
                unit_rate=Money(amount=rate_amount, currency="USD"),
                effective_from=now,
            )
        rules.append(rule)
        
    return rules

