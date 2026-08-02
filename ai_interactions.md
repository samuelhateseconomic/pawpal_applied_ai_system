## Agentic Workflow Enhancement
**already implemented in the plan - restate**

**What task did you give the agent?**
    1. Across Phase 3 (wire the agent) and the later delete-confirmation fix, asked for an agent that doesn't just call one tool per command but reasons over multiple steps: figuring out what's missing, chaining follow-up tool calls on its own, and pausing for human input before anything destructive.

**What did the agent do?**
    1. **Multi-step reasoning over a single command:** the agent decides intent, checks whether every required parameter for the matching tool is present, and only proceeds once satisfied — no assumption-filling on missing data.
    2. **Planning / self-chaining tool calls without being asked for each one:** a system-instruction rule ("After adding or editing a task that has a fixed start_time, call generate_schedule...") makes the agent plan a second tool call on its own initiative — e.g. `add_task` followed automatically by `generate_schedule` to check for conflicts, then relaying any conflict found, all from one user message.
    3. **Confirm-then-execute planning for destructive actions:** `tool_remove_pet`/`tool_delete_task` default to `confirm=False`, returning a `confirm_required` status (with the impact, e.g. how many tasks a pet-removal would take with it) instead of deleting. The agent is instructed to surface that impact, wait for the user's explicit yes in a follow-up message, and only then re-call the same tool with `confirm=True` — a genuine two-turn plan, not a single blind action.
    4. **Guardrails enforced at the code level, not just the prompt:** required tool parameters have no default (so the schema itself marks them required), and the confirm gate is a real code branch — so the multi-step behavior holds even when the model doesn't follow the system prompt perfectly.

**What did you have to verify or fix manually?**
    1. Live-tested each reasoning path against the real Gemini API rather than trusting it would work: an incomplete command → clarifying question with no tool call; a fixed-time task add → automatic follow-up `generate_schedule` call with the conflict relayed verbatim; and "delete Mochi" → confirmation question with zero data loss, only deleting after an explicit "yes" produced a second `confirm=True` call.
    2. Caught that the delete flow was originally only a soft prompt instruction ("ask before deleting") which the model wasn't reliably honoring, and hardened it into the code-level `confirm` gate described above.

## Test harness

**What task did you give the agent?**
    1. Asked whether the test suite included a real AI test (one that actually calls the live Gemini API, not just the deterministic tool layer) - and if not, to add one and document it.

**What did the agent do?**
    1. Checked honestly first rather than assuming: confirmed `test_agent_tools.py` deliberately tests tools with plain function calls only (by design, per the plan), and `test_views.py`'s chat-page tests actively avoid the AI path (delete the API key first, or never reach that code). No automated test called the real model.
    2. Added `tests/test_agent_live.py` — two tests against the real Gemini API: one asserting an incomplete command ("Add a walk for Mochi") creates no task, one asserting "delete Mochi" only removes the pet after an explicit follow-up confirmation. Both assert on observable state (was anything actually created/deleted), never the model's exact wording, since wording isn't deterministic but the guardrail holding is.
    3. Kept these out of the default `pytest` run — added `pytest.ini` with a `live_api` marker excluded by default (`addopts = -m "not live_api"`), run explicitly with `pytest -m live_api`. Live LLM calls cost real quota and depend on an external service, so they shouldn't make the everyday suite slower or flaky.
    4. **The first live run immediately caught a real bug**, which is exactly why this test earns its keep: `gemini-3.1-flash-lite` called `add_task` with `duration_minutes=0, priority=''` instead of asking the user for them — satisfying the function schema's "required" constraint with garbage values rather than real ones. The schema-level guardrail alone wasn't enough; the same class of gap as the delete-confirmation bug.
    5. Fixed it at the domain-model level (not just the tool layer) in `pawpal_system.py`: added `check_duration`/`check_priority`/`check_frequency_unit`, raising the existing `ValidationError` (already used for description/name word limits) from `Pet.add_task`/`Pet.edit_task`. `agent_tools.py` already catches `ValidationError` and returns `{"status": "invalid_input", ...}`, so no tool-layer change was needed — every caller is protected, not just the AI path.
    6. Backfilled deterministic coverage for the fix in `tests/test_pawpal.py` and `tests/test_agent_tools.py` (invalid duration/priority/frequency_unit rejected, task left unchanged) so this regression can be caught without spending API quota on every run, then re-ran the live test to confirm it now passes.
    7. **A follow-up live run caught a second, subtler violation of the same rule**: instead of garbage values, the model filled in *plausible* ones — `add_task(duration_minutes=30, priority="high", start_time="09:00")` for "add a walk for Mochi," with no duration/priority/time ever stated. This passed the new `ValidationError` checks fine, since 30/"high" are legitimately valid values; just not ones the user actually gave. A data-validation fix can't catch this in general, because the tool has no way to tell a real user-supplied value from a guessed-but-plausible one.
    8. Fixed this one at the prompt level instead, since it's a prompt-adherence gap, not a data gap: rewrote `SYSTEM_INSTRUCTION` rule 1 in `agent_wiring.py` to explicitly call out that a "reasonable default" is just as wrong as an invalid value, plus a concrete example of the exact mistake the model had just made and the question it should ask instead.

**What did you have to verify or fix manually?**
    1. Ran the live tests for real against the API (not just written and assumed passing) — the first run failed, which is what surfaced the `duration_minutes=0`/`priority=''` bug above.
    2. Re-ran the full default suite twice after the fix to separate a real regression from the pre-existing flaky `test_views.py` `AppTest` timeout (confirmed unrelated — reproduces even in isolation, on a different test each time, independent of this change).
    3. Since LLM behavior is probabilistic, one passing run after the prompt fix wasn't enough to trust, re-ran the same live test 3 more times to build actual confidence (all 3 passed, versus failing on both attempts before the fix) rather than declaring it fixed off a single lucky pass.