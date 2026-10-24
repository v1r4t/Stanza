# PayResolve — Stanza

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Fetch.ai-native multi-agent payment dispute resolver. Working ASI:One interface, real policy retrieval, clear outcome.

**Tracks (not interchangeable):** `failed` ≠ `pending` ≠ `unauthorised` (NPCI guidance).

## Agents
- `PayResolve` (agents/orchestrator.py, port 8001) — public ACP entry, Interactive Cards
  - live address: `agent1q0vj3x8sjdvvpv0elvd0rr60umhkeva8kd9w49pcdqh9zw67wxxrk6yvda6` (your `AGENT_SEED`)
- `payresolve-triage` (port 8002) — live address: `agent1qwd7l7jv9fzpkej7nq4c8wjxfs8vgw9unddst5q08076yn92k5uy5l043dq`
- `payresolve-policy` (port 8003) — live address: `agent1qggnj3j4jvz9su2eefhf7l9rprjsccjphjxdan77wmahe9tgtmz5yxppwr7`
- `payresolve-evidence` (port 8004) — live address: `agent1qvnrqea7eflv2my3szqtn2jdq82uu7dspuguzdgvmnpqf2c2nx70qxd5u79`
- NOTE: live-seed addresses; keep agents running for ASI:One discovery.

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

## Submission (fill after deploy)
- Agentverse profile URL: _
- ASI:One shared chat URL: _
- Demo video (3-5 min): _
- Dashboard: ASI:One Fetch-A-Thon 3.0 → Project Submission Agent
