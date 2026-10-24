"""Shared typed messages for PayResolve multi-agent orchestration.

Defined once in core/ so the orchestrator can import request/response types
without importing (and instantiating) the specialist agent modules.
"""
from __future__ import annotations
from uagents import Model


class TriageRequest(Model):
    text: str


class TriageResponse(Model):
    transaction_type: str
    debited: bool
    utr: str | None
    amount: float | None
    missing_fields: list[str]
    urgency: str
    occurred_on: str | None = None
    days_elapsed: int | None = None


class PolicyRequest(Model):
    transaction_type: str
    utr: str | None = None
    occurred_on: str | None = None
    days_elapsed: int | None = None


class PolicyResponse(Model):
    track: str
    timelines: list[str]
    escalation: list[str]
    refund_guaranteed: bool
    uncertainty: list[str]
    source_ids: list[str] = []
    conditions: list[str] = []
    escalate_now: bool = False
    evidence: list[str] = []


class EvidenceRequest(Model):
    transaction_type: str
    utr: str | None = None
    amount: float | None = None
    report: str = ""
    occurred_on: str | None = None
    days_elapsed: int | None = None


class EvidenceResponse(Model):
    complaint_draft: str
    missing_evidence: list[str]
    timeline: list[str]
