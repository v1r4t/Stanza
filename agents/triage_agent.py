"""Specialist agents — typed request/response via uAgents messaging.

Orchestrator is the only public ACP entry. These run as separate agents
(local or Agentverse) and exchange structured Models, giving real
multi-agent orchestration (not just LLM personas).
"""
from __future__ import annotations
import os
from uagents import Agent, Context, Model, Protocol

from core.resolution import triage_text, policy_for, build_pack
from core.schemas import TriageResult
from core.security import redact


class TriageRequest(Model):
    text: str


class TriageResponse(Model):
    transaction_type: str
    debited: bool
    utr: str | None
    amount: float | None
    missing_fields: list[str]
    urgency: str


triage_agent = Agent(
    name="payresolve-triage",
    seed=os.getenv("TRIBUTE_SEED", "payresolve-triage-v1"),
    port=8002,
    mailbox=True,
)

triage_proto = Protocol("payresolve-triage")


@triage_proto.on_message(model=TriageRequest, replies={TriageResponse})
async def handle_triage(ctx: Context, sender: str, msg: TriageRequest):
    r = triage_text(redact(msg.text))
    await ctx.send(sender, TriageResponse(
        transaction_type=r.transaction_type.value,
        debited=r.debited,
        utr=r.utr,
        amount=r.amount,
        missing_fields=r.missing_fields,
        urgency=r.urgency,
    ))


triage_agent.include(triage_proto)

if __name__ == "__main__":
    triage_agent.run()
