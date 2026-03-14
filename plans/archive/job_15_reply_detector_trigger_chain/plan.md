# Job 15 — Reply Detector → Response Generator Trigger Chain

**Status:** ⬜ Not started
**Goal:** (1) Change reply detector from 15-min to 5-min poll interval. (2) Instead of response generator running on its own 5-min background poll, trigger it directly at the end of each reply detector run that found new replies — so the end-to-end latency is one 5-min cycle, not two independent polls that could be offset by up to 5+5=10 min.

---

## Background

Current architecture:
- Reply detector: polls every 15 min, detects replies + classifies, sets `draft_queued=False`
- Response generator: polls every 5 min independently, finds `draft_queued=False` rows, generates drafts

Problems:
- 15-min reply detection is too slow for real conversations
- The two independent polls mean a reply could wait up to 20 min before a draft is queued (15 min to detect + 5 min to generate)
- Running response generator every 5 min even when there's nothing to do wastes resources

Desired:
- Reply detector: polls every 5 min
- Response generator: called inline at the end of reply_detector.run() when new replies were found; does NOT run on its own background poll

---

## Deliverables

1. `api/app.py` — Change `REPLY_DETECTOR_POLL_SECONDS` from 900 (15 min) to 300 (5 min)
2. `api/app.py` — In `_reply_detector_loop()`: after `reply_detector.run()` returns, if `new_replies > 0`, immediately call `response_generator.run(operator_id)` inline (synchronous, same thread)
3. `api/app.py` — Disable the independent `_response_generator_loop()` background thread / APScheduler job (it's no longer needed)
4. `api/app.py` — Update `_agent_last_run["response_generator"]` timestamp when response generator runs inline (so agents page still shows last run time)
5. `agents/reply_detector.py` — Ensure `run()` returns the count of new replies detected (it probably already does — verify)
6. `templates/agents.html` — Update description text: "Runs every 5 min. Response generator runs automatically after each detection pass with new replies."

---

## Tasks

- [ ] Read current api/app.py scheduler setup — find REPLY_DETECTOR_POLL_SECONDS, _reply_detector_loop, _response_generator_loop, _start_response_generator
- [ ] Change poll interval constant
- [ ] Modify _reply_detector_loop to call response_generator inline when new_replies > 0
- [ ] Disable/remove _response_generator_loop and _start_response_generator (or leave stub that does nothing)
- [ ] Verify reply_detector.run() return value is the reply count
- [ ] Update agents.html description

---

## Files to Attach

```
api/app.py              (search: REPLY_DETECTOR_POLL_SECONDS, _reply_detector_loop, _response_generator_loop, _start_response_generator, _agent_last_run)
agents/reply_detector.py
templates/agents.html
```
