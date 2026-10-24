# PayResolve — Stanza

![tag:innovationlab](https://img.shields.io/badge/innovationlab-3D8BD3)
![tag:hackathon](https://img.shields.io/badge/hackathon-5F43F1)

Fetch.ai-native multi-agent payment dispute resolver. Working ASI:One interface, real policy retrieval, clear outcome.

**Tracks (not interchangeable):** `failed` ≠ `pending` ≠ `unauthorised` (NPCI guidance).

## Agents
- `PayResolve` (agents/orchestrator.py, port 8001) — public ACP entry, Interactive Cards
  - dev address: `agent1qf5maaj2jw7z69qewwwat3p02kzfnx0lcnhzvnuq2v5w83mhwdhszhlgej8`
- `payresolve-triage` (port 8002) — dev address: `agent1qgxex2xv5834jh7hsec0e9xjcgmvhur8rz9fj9dcquvawdwn30q665cf45e`
- `payresolve-policy` (port 8003) — dev address: `agent1q099ulyv0l4wvlgztyl82qe927rtpc8cp56lm0klhawa7zk0entdy3u9767`
- `payresolve-evidence` (port 8004) — dev address: `agent1qwzmerm3xkwrkwscqynudmwjgg4ayzmhrmlknrhazgal9c6sttyaxztrq25`
- NOTE: dev-seed addresses; your `AGENT_SEED` / `TRIBUTE_SEED` / `POLICY_SEED` / `EVIDENCE_SEED` will change these.

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
