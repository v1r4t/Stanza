# PayResolve — Stanza

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Fetch.ai-native multi-agent payment dispute resolver. Working ASI:One interface, real policy retrieval, clear outcome.

**Tracks (not interchangeable):** `failed` ≠ `pending` ≠ `unauthorised` (NPCI guidance).

## Agents

**Hosted (always-on — this is the submitted deployment):**
- `payresolve-hosted` — public ACP entry, Interactive Cards
  - address: `agent1qw2ex8clxmdawmj4sfjdjmpskhv7revadhx7dc6tu9k0967t3x8aggg6a28p`
- `payresolve-triage-hosted` — `agent1qwj64glvt2rdls3u7pyv5n6u5s72ugc0x0m8azvh33kg66u9ahuqvsr8f2m`
- `payresolve-policy-hosted` — `agent1qwc0h83ft85elyk8y782ltw0gmlsr7cxm92ggm466cdevdpmc0xa2mkdt8y`
- `payresolve-evidence-hosted` — `agent1qf47wyrenvewcn6sy7apz9ylgfakmwmnrrxguqchytrvxlr9cja8yddwu8v`

**Local (native runtime, full ACP multi-agent topology):**
- `PayResolve` :8001 — `agent1q0vj3x8sjdvvpv0elvd0rr60umhkeva8kd9w49pcdqh9zw67wxxrk6yvda6`
- `payresolve-triage` :8002 — `agent1qwd7l7jv9fzpkej7nq4c8wjxfs8vgw9unddst5q08076yn92k5uy5l043dq`
- `payresolve-policy` :8003 — `agent1qggnj3j4jvz9su2eefhf7l9rprjsccjphjxdan77wmahe9tgtmz5yxppwr7`
- `payresolve-evidence` :8004 — `agent1qvnrqea7eflv2my3szqtn2jdq82uu7dspuguzdgvmnpqf2c2nx70qxd5u79`

### Why hosted runs consolidated
Agentverse's hosted wrapper does not register custom message-model schemas
(`RuntimeError: Unable to determine message model`) and does not inject
environment variables. So the hosted build runs the full pipeline in-process
(`DELEGATE_ENABLED=False`, baked by `scripts/build_hosted.py`), while the
four-agent delegation (`ctx.send_and_receive` → triage/policy/evidence) runs on
the native uAgent runtime. Both paths share the same deterministic core.

## Run
```
py -3.12 -m venv .venv  # or: uv venv --python 3.12 .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env  # fill ASI1_API_KEY, AGENT_SEED
python -m py_compile agents/orchestrator.py
pytest -q
python -m agents.orchestrator
```
Connect via Agentverse mailbox inspector, then chat via ASI:One (@mention). Cards: intake form → carousel → review pack.

## Always-on hosting (no laptop needed)

Agentverse's Build tab takes a single script, so `scripts/build_hosted.py` flattens
`core/` + `agents/` into four paste-ready bundles:

```
python scripts/build_hosted.py   # writes hosted_{payresolve,triage,policy,evidence}.py
```

Rerun after **every** source change (tests fail if bundles go stale). Never hand-edit bundles.

Deploy order in Agentverse → Agents → Launch an Agent → Generate/blank agent → Build tab:

1. Paste `hosted_triage.py`, Start, copy its address. Repeat for `hosted_policy.py`, `hosted_evidence.py`.
2. Paste `hosted_payresolve.py`, Start it, then mention it in ASI:One.
3. **Do not rely on env vars on hosted agents** — Agentverse does not inject them.
   Hosted behaviour is baked in by `scripts/build_hosted.py` (e.g. `DELEGATE_ENABLED=False`).

Hosted agents stay up without your machine. SQLite cases fall back to a temp dir when the
filesystem is read-only, so drafting still works.

## LangChain for uAgents — yes
Two supported patterns (docs: `uagents-adapter-guide`):
1. Lightweight (implemented in `core/langchain_triage.py`): `ChatOpenAI(base_url="https://api.asi1.ai/v1", model="asi1-mini")` inside handler. Deterministic `core/policy_rules.py` remains guardrail so tests pass offline.
2. Full adapter publish: `pip install "uagents-adapter[langchain]"`, then `LangchainRegisterTool().invoke({"agent_obj": langchain_agent, ...})`.

## References
- https://github.com/fetchai/innovation-lab-examples (asi1-llm-example/ASI1_Langchain, dynamic-ui-on-asi1, fetch-hackathon-quickstarter, Crewai-agents)
- https://innovationlab.fetch.ai/resources/docs/intro
- https://innovationlab.fetch.ai/resources/docs/agent-creation/uagent-creation (mailbox, >=0.25.5, Python 3.10-13)
- https://innovationlab.fetch.ai/resources/docs/interactive-cards/asi-interactive-cards
- https://innovationlab.fetch.ai/resources/docs/asione/asi-one-quickstart
- https://innovationlab.fetch.ai/resources/docs/agent-creation/uagents-adapter-guide

## Submission
- Agentverse agent profile: `https://agentverse.ai/agents/profile?address=agent1qw2ex8clxmdawmj4sfjdjmpskhv7revadhx7dc6tu9k0967t3x8aggg6a28p`
- ASI:One shared chat URL: https://asi1.ai/chat/89c9d6ee-f1f9-4314-94e3-fc0d9597ba11
- Demo video (3-5 min): _
- Dashboard: ASI:One Fetch-A-Thon 3.0 → Project Submission Agent

## What PayResolve does (submission blurb)
UPI disputes fail in three legally distinct ways — `failed` (debited, beneficiary
not credited), `pending` (still processing), and `unauthorised` (denied by the
user) — and NPCI/RBI treat each differently. PayResolve takes a plain-language
report, classifies the track, extracts the UTR/amount/date, computes how many
days of the official TAT window have elapsed, decides whether to escalate now,
lists the exact evidence required, and drafts a ready-to-send complaint with
cited circulars. It never promises a refund — it recommends process.

**Target users:** UPI users in India dealing with a stuck or disputed payment.
**Outcome:** a decision (track, days remaining, who to contact, what to attach)
plus a complaint draft — inside a single ASI:One chat.
