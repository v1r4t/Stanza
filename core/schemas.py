from __future__ import annotations
from enum import Enum
from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    FAILED = "failed"
    PENDING = "pending"
    UNAUTHORISED = "unauthorised"
    UNKNOWN = "unknown"


class TriageResult(BaseModel):
    transaction_type: TransactionType = TransactionType.UNKNOWN
    debited: bool = False
    occurred_at: str | None = None
    merchant_status: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    urgency: str = "normal"  # low | normal | high
    utr: str | None = None
    amount: float | None = None
    raw_text: str = ""


class PolicyFinding(BaseModel):
    track: str
    source_ids: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    timelines: list[str] = Field(default_factory=list)
    escalation: list[str] = Field(default_factory=list)
    refund_guaranteed: bool = False
    uncertainty: list[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    timeline: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    official_sources: list[str] = Field(default_factory=list)
    complaint_draft: str = ""
    verified_facts: list[str] = Field(default_factory=list)
    user_reported: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
