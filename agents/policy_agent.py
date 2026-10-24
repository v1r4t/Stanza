from __future__ import annotations
import os
from dotenv import load_dotenv
from uagents import Agent, Context, Model, Protocol
from uagents.setup import fund_agent_if_low

load_dotenv()
from core.schemas import TransactionType
from core.resolution import policy_for
from core.schemas import TriageResult
from core.messages import PolicyRequest, PolicyResponse


policy_agent = Agent(
    name="payresolve-policy",
    seed=os.getenv("POLICY_SEED", "payresolve-policy-v1"),
    port=8003,
    mailbox=True,
    network="testnet",
)

fund_agent_if_low(str(policy_agent.wallet.address()))


@policy_agent.on_event("startup")
async def _log_address(ctx: Context):
    ctx.logger.info(f"[startup] {policy_agent.name} ADDRESS={policy_agent.address}")
policy_proto = Protocol("payresolve-policy")


@policy_proto.on_message(model=PolicyRequest, replies={PolicyResponse})
async def handle_policy(ctx: Context, sender: str, msg: PolicyRequest):
    try:
        ttype = TransactionType(msg.transaction_type)
    except Exception:
        ttype = TransactionType.UNKNOWN
    triage = TriageResult(
        transaction_type=ttype,
        utr=msg.utr,
        raw_text="",
        occurred_on=msg.occurred_on,
        days_elapsed=msg.days_elapsed,
    )
    p = policy_for(triage)
    await ctx.send(sender, PolicyResponse(
        track=p.track, timelines=p.timelines, escalation=p.escalation,
        refund_guaranteed=False, uncertainty=p.uncertainty,
        source_ids=p.source_ids, conditions=p.conditions,
        escalate_now=p.escalate_now, evidence=p.evidence,
    ))


policy_agent.include(policy_proto)

if __name__ == "__main__":
    policy_agent.run()
