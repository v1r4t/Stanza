"""Specialist agents — typed request/response via uAgents messaging.

Orchestrator is the only public ACP entry. These run as separate agents
(local or Agentverse) and exchange structured Models, giving real
multi-agent orchestration (not just LLM personas).
"""
from __future__ import annotations
import os
from dotenv import load_dotenv
from uagents import Agent, Context, Model, Protocol
from uagents.setup import fund_agent_if_low

load_dotenv()

from core.resolution import triage_text, policy_for, build_pack
from core.schemas import TriageResult
from core.security import redact
from core.messages import TriageRequest, TriageResponse


triage_agent = Agent(
    name="payresolve-triage",
    seed=os.getenv("TRIBUTE_SEED", "payresolve-triage-v1"),
    port=8002,
    mailbox=True,
    network="testnet",
)

fund_agent_if_low(str(triage_agent.wallet.address()))


@triage_agent.on_event("startup")
async def _log_address(ctx: Context):
    ctx.logger.info(f"[startup] {triage_agent.name} ADDRESS={triage_agent.address}")

triage_proto = Protocol("payresolve-triage")


@triage_proto.on_message(model=TriageRequest, replies={TriageResponse})
async def handle_triage(ctx: Context, sender: str, msg: TriageRequest):
    r = triage_text(msg.text or "")
    await ctx.send(sender, TriageResponse(
        transaction_type=r.transaction_type.value,
        debited=r.debited,
        utr=r.utr,
        amount=r.amount,
        missing_fields=r.missing_fields,
        urgency=r.urgency,
        occurred_on=r.occurred_on,
        days_elapsed=r.days_elapsed,
    ))


triage_agent.include(triage_proto)

if __name__ == "__main__":
    triage_agent.run()
