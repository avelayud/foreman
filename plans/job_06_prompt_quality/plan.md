# Job 06 — Prompt Quality Sprint

**Phase:** 8
**Status:** ⬜ Not started
**Depends on:** Job 05 (operator config must be wired before prompts use config values)
**Goal:** Rewrite the core agent prompts so every draft sounds like it came from a skilled, professional trade operator — not AI-generated outreach. Blue-collar competence: direct, specific, no corporate filler, confident on pricing.

---

## Background

The reactivation emails and conversation replies are functional, but they can read as AI-polished in ways that experienced HVAC operators would immediately recognize. The target voice is a 10–15 year trade veteran running a tight owner-operated shop: someone who writes short emails, is direct about pricing, doesn't hedge, and treats customers like adults.

This job rewrites prompts in `reactivation.py`, `conversation_agent.py`, and `follow_up.py` — and wires in the operator config values from Job 05 as dynamic prompt inputs.

---

## Voice & Tone Target

**This operator:**
- Has been doing HVAC for 12 years, runs a crew of 4
- Writes emails on their phone between jobs
- Doesn't say "I wanted to reach out" or "I hope this finds you well"
- Gives real price ranges without hedging ("tune-ups run $89–149 depending on the system")
- Is busy — follow-ups are short, not guilt-trippy
- Respects the customer's time and expects the same

**Not this:** "I hope you're doing well! I wanted to take a moment to reach out and check in about your HVAC system. As we approach the warmer months, it might be a great time to consider scheduling a tune-up to ensure everything is running optimally."

**This:** "Hey [first name] — it's been about a year since we serviced your unit. Tune-ups run $89–149 and usually take about an hour. Want to get something on the calendar before the summer rush?"

---

## Prompt Targets by Agent

### `agents/reactivation.py` — Cold Outreach (REACTIVATION_PROMPT)

**Problems to fix:**
- Generic subject lines ("Checking in on your HVAC system")
- Corporate opener language
- Doesn't feel like it's from the specific operator

**Rewrite goals:**
- Subject line references the actual last job or job type ("Your AC tune-up — checking in")
- First sentence gets to the point in 10 words or less
- Body is 2–3 short paragraphs max, often less
- No "I hope this email finds you well" or equivalent
- Close with a soft but direct CTA ("Want me to get something on the calendar?")
- Inject: operator tone level, salesy level, estimate range for job type, business context

### `agents/conversation_agent.py` — Reply Drafts

**AGENT_SYSTEM (base system prompt):**
- Stronger voice definition: "You are a professional HVAC contractor..."
- Remind the agent it's busy — responses are concise, not exhaustive
- Inject operator config context block at top

**NOT_INTERESTED_PROMPT:**
- Answer the customer's actual question with real trade knowledge
- Don't hedge on pricing — give a specific range if they ask
- Keep it to 2–3 sentences
- Don't re-pitch in the same message

**BOOKING_INTENT_PROMPT:**
- Propose slots the way a busy contractor would: "I have Tuesday morning or Thursday after 2"
- Not: "I would be happy to find a time that works for both of our schedules"
- Keep it short — they said yes, don't oversell it

**PRICE_RESPONSE_PROMPT:**
- Pull from operator config estimate ranges
- Give a real range with brief context on what drives variability
- ("Repairs vary a lot — a capacitor swap is $150, a compressor is another story. Happy to give you a better number once I see the system.")
- Offer a next step

**FOLLOW_UP_PROMPT (if exists in conversation_agent):**
- Short. Warmer. Acknowledge they're busy.

### `agents/follow_up.py` — Follow-up Sequence

**Follow-up 1 (first bump):**
- 1–2 sentences
- Softer tone: "Just wanted to make sure this didn't get buried"
- Reference the original email topic
- One clear CTA

**Follow-up 2 (final):**
- Close the loop gracefully: "No worries if the timing isn't right — happy to reconnect whenever you need us"
- Not guilt-trippy, not desperate
- Leave the door open

---

## Operator Config Injection

Every prompt should include the config block from `core/operator_config.get_agent_context()` at the top of the system prompt. Example:

```python
system_prompt = get_agent_context(operator_id, db) + "\n\n" + REACTIVATION_PROMPT
```

The config block tells the agent:
- How direct/consultative to be (tone dial)
- How hard to push for a booking (salesy dial)
- What price ranges to use for this job type
- Any operator-specific context ("We specialize in Carrier systems", "Family-owned since 2011")

---

## Test Protocol

After each prompt rewrite, test against these scenario types from the seed data:

1. Customer with 1 maintenance job, 18 months dormant, high score
2. Customer with 3 repair jobs, 2 years dormant, medium score
3. Customer who replied "not right now" to last outreach
4. Customer who asked about pricing
5. Customer who said "yes, when can you come?"

Review the draft for:
- [ ] Does it sound like a real contractor wrote it?
- [ ] Does the subject line reference the actual history?
- [ ] Is the length appropriate (short for SMS parity, not a wall of text)?
- [ ] Is pricing confident, not hedged?
- [ ] Does it actually answer what the customer asked?

---

## Tasks

- [ ] task_01_reactivation_prompt.md — rewrite REACTIVATION_PROMPT + config injection
- [ ] task_02_conversation_system_prompt.md — rewrite AGENT_SYSTEM
- [ ] task_03_not_interested_prompt.md — rewrite NOT_INTERESTED_PROMPT
- [ ] task_04_booking_intent_prompt.md — rewrite BOOKING_INTENT_PROMPT
- [ ] task_05_price_response_prompt.md — rewrite PRICE_RESPONSE_PROMPT with config ranges
- [ ] task_06_follow_up_prompts.md — rewrite follow-up 1 + 2 in follow_up.py
- [ ] task_07_test_and_iterate.md — run against 5 scenarios, document issues, iterate

---

## Files to Attach in Claude Code

```
PROJECT_PLAN.md
agents/reactivation.py
agents/conversation_agent.py
agents/follow_up.py
core/operator_config.py   ← from Job 05
```
