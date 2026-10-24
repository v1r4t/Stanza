from __future__ import annotations
import os
from dotenv import load_dotenv
from uagents import Agent, Context, Model, Protocol
from uagents.setup import fund_agent_if_low

load_dotenv()
from core.schemas import TriageResult, TransactionType
from core.resolution import policy_for, build_pack
from core.messages import EvidenceRequest, EvidenceResponse


evidence_agent = Agent(
    name="payresolve-evidence",
    seed=os.getenv("EVIDENCE_SEED", "payresolve-evidence-v1"),
    port=8004,
    mailbox=True,
    network="testnet",
)

fund_agent_if_low(str(evidence_agent.wallet.address()))


@evidence_agent.on_event("startup")
async def _log_address(ctx: Context):
    ctx.logger.info(f"[startup] {evidence_agent.name} ADDRESS={evidence_agent.address}")
evidence_proto = Protocol("payresolve-evidence")


@evidence_proto.on_message(model=EvidenceRequest, replies={EvidenceResponse})
async def handle_evidence(ctx: Context, sender: str, msg: EvidenceRequest):
    try:
        ttype = TransactionType(msg.transaction_type)
    except Exception:
        ttype = TransactionType.UNKNOWN
    triage = TriageResult(
        transaction_type=ttype, utr=msg.utr, amount=msg.amount, raw_text=msg.report,
        occurred_on=msg.occurred_on, days_elapsed=msg.days_elapsed,
    )
    pack = build_pack(triage, policy_for(triage))
    await ctx.send(sender, EvidenceResponse(
        complaint_draft=pack.complaint_draft,
        missing_evidence=pack.missing_evidence,
        timeline=pack.timeline,
    ))


evidence_agent.include(evidence_proto)

if __name__ == "__main__":
    evidence_agent.run()
