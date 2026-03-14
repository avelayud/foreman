# Job 11 — Fix Agent Run Timeout

**Status:** ✅ Complete
**Goal:** The "Run All Agents" button on the agents page times out after 5 minutes because the HTTP request waits synchronously for all agents to finish. Fix it so the button fires agents in the background and returns immediately, with the page polling for completion.

---

## Background

`POST /api/agent/run-all` currently runs each agent in sequence inside the request handler. On Railway, HTTP requests time out after ~30s by default. Running 4–5 agents sequentially (each doing LLM calls) easily exceeds this.

The individual "Run Now" buttons per-agent work fine because each agent runs in a background thread and the endpoint returns immediately. Run All needs the same pattern.

---

## Deliverables

1. `api/app.py` — Refactor `/api/agent/run-all` to fire each agent as a background thread and return `{"status": "started", "agents": [...]}` immediately
2. `api/app.py` — Ensure `_agent_last_run` timestamps update when background runs complete (already exists per-agent, just needs to be wired for run-all)
3. `templates/agents.html` — Update "Run All Agents" button JS to handle `status: started` response and show "Agents running in background…" feedback instead of waiting for completion

---

## Tasks

- [ ] Read current `/api/agent/run-all` implementation
- [ ] Refactor to background thread pattern (match how individual run-now endpoints work)
- [ ] Update agents.html JS callback for run-all
- [ ] Test: click Run All, verify immediate response, verify `_agent_last_run` timestamps update after completion

---

## Files to Attach

```
api/app.py          (search: run-all, _agent_last_run, run_reply_detector)
templates/agents.html
```
