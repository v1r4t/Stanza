from __future__ import annotations
import os
from dotenv import load_dotenv
from uagents import Agent, Context, Model, Protocol
from uagents.setup import fund_agent_if_low

load_dotenv()
from core.schemas import TransactionType
from core.resolution import policy_for
from core.schemas import TriageResult


class PolicyRequest(Model):
    transaction_type: str
    utr: str | None = None


class PolicyResponse(Model):
    track: str
    timelines: list[str]
    escalation: list[str]
    refund_guaranteed: bool
    uncertainty: list[str]


policy_agent = Agent(
    name="payresolve-policy",
    seed=os.getenv("POLICY_SEED", "payresolve-policy-v1"),
    port=8003,
    mailbox=True,
    network="testnet",
)

fund_agent_if_low(str(policy_agent.wallet.address()))
policy_proto = Protocol("payresolve-policy")


@policy_proto.on_message(model=PolicyRequest, replies={PolicyResponse})
async def handle_policy(ctx: Context, sender: str, msg: PolicyRequest):
    try:
        ttype = TransactionType(msg.transaction_type)
    except Exception:
        ttype = TransactionType.UNKNOWN
    triage = TriageResult(transaction_type=ttype, utr=msg.utr, raw_text="")
    p = policy_for(triage)
    await ctx.send(sender, PolicyResponse(
        track=p.track, timelines=p.timelines, escalation=p.escalation,
        refund_guaranteed=False, uncertainty=p.uncertainty,
    ))


policy_agent.include(policy_proto)

if __name__ == "__main__":
    policy_agent.run()
