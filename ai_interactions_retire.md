# AI Interactions Log

---

## Agent Workflow (SF7)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

Multiple multi-step tasks across the project lifecycle:

1. Write a full test suite for `tests/test_pawpal.py` covering four behaviors (add pets, add tasks with time, schedule tasks, explain schedule) with happy paths and edge cases.
2. Upgrade `app.py` to use `Scheduler` methods for sorted display, `st.table` output, and conflict warnings with actionable revision tips.
3. Update `diagrams/uml_final.mmd` to reflect the fully implemented system and highlight every difference from the original skeleton UML.
4. Replace the placeholder Demo Walkthrough section in `README.md` with a text walkthrough, example workflow, scheduler behavior explanations, and real CLI output from `main.py`.
5. Implement JSON file persistence — add `save_owner` / `load_owner` to `pawpal_system.py` and wire them into `app.py`.
6. Add a third algorithmic capability to `Scheduler` — "next available slot" — so a user who has a task of a given duration (e.g. 30 min) can hit a button and see which open blocks of time in the day (e.g. "16:00–17:00") are free, based on tasks already pinned/scheduled, without actually assigning the new task.

**What did the agent do?**

- Read existing source files (`pawpal_system.py`, `app.py`, `main.py`, `diagrams/uml.mmd`) before writing anything, to avoid guessing at the API.
- Created `tests/test_pawpal.py` with 21 new tests organized into four classes, preserving the two pre-existing tests — 23 total, all passing.
- Rewrote the task-display and schedule sections of `app.py` to use `Scheduler.schedule()`, `st.table`, `st.success`, and `st.warning` with per-conflict tips.
- Added a `Fixed time (HH:MM)` input column so users can pin anchor tasks from the UI.
- Diffed the original `uml.mmd` against the real implementation and rewrote `uml_final.mmd` with all fields, method signatures, return types, and `[NEW]` / `[EXPANDED]` markers on every addition.
- Ran `python main.py` to capture live CLI output, then embedded that exact output into the README demo section.
- Added `save_owner` and `load_owner` to `pawpal_system.py` using `dataclasses.asdict()` and `json` / `pathlib` (stdlib only, no new dependencies).
- Wired load-on-startup and save-on-mutation into `app.py`; smoke-tested the round-trip with a Python one-liner.
- Deleted the incorrectly placed root-level `test_pawpal.py` after realizing the correct path was `tests/test_pawpal.py`.
- Added `Scheduler.find_available_slots(duration_minutes)` in `pawpal_system.py`: finds open gaps (`>= duration_minutes`) between already-scheduled tasks, `day_start`, and `day_end`. Read-only, doesn't mutate tasks.
- Added a "Find Available Time" section to `app.py` (duration input + "Check available slots" button), and shared the `day_start`/`day_end` inputs with the "Build Schedule" section instead of duplicating them.
- Added `TestFindAvailableSlots` (6 tests) to `tests/test_pawpal.py` — all 29 tests pass.

**What did you have to verify or fix manually?**
- Fix the time when the user add it manually and so that we can prioritize user reference
- Confirmed that Pylance "Type unknown" errors on `st.*` calls are false positives caused by missing Streamlit type stubs — not real bugs. The app runs correctly.
- Verified that `save_owner` / `load_owner` correctly round-trips `start_time=None` (floating tasks) and `start_time="HH:MM"` (anchor tasks) by inspecting the smoke-test output.
- Reviewed the UML diff to confirm that the `<<utility>>` stereotype on the `Persistence` block accurately represents module-level functions in Mermaid's classDiagram syntax.
- Confirmed `find_available_slots` only considers tasks with an existing `start_time` (anchors or already-scheduled tasks) rather than running the full `assign_times()` placement — this matches the requested flow of checking availability *before* deciding where to put a new task.
- Verified overlapping anchor intervals are merged before computing gaps, so a small overlap between two busy tasks doesn't get miscounted as free time.
- Reran the full test suite (`pytest tests/test_pawpal.py -q`) after moving the day-window inputs in `app.py` to confirm no regressions from the reorder.

---

## CLI Output Formatting

**Task:** Add user-friendly CLI output — color-coded status, emojis per task type, structured tables (e.g. `tabulate`) — and document it in `README.md`.

**What the agent did:**
- Added `tabulate` to `requirements.txt` and used it in `main.py` to render the schedule as a bordered table (`tablefmt="rounded_outline"`) instead of manually padded `print()` lines.
- Added `task_emoji(title)`: keyword-matches the title (walk/feed/vet/medic/groom/play) to an emoji, default 🐾.
- Added `colored_priority(priority)`: wraps HIGH/MEDIUM/LOW in ANSI red/yellow/green — plain `\033[...m` codes, no new dependency.
- Colored the conflicts summary (`✅` green / `⚠️` red).
- Documented all of this in a new "🎨 CLI Output Formatting" section in `README.md` and refreshed the CLI sample output block.

**Verified manually:**
- `python main.py` initially crashed with `UnicodeEncodeError` on Windows (`cp1252` can't encode emoji/box-drawing chars) — fixed with `sys.stdout.reconfigure(encoding="utf-8")` at the top of `main.py`.
- Reran `python main.py` to confirm clean output, and `pytest -q` (36 passed) to confirm no regressions.

---

## Prompt Comparison (SF11)

> Compare two different prompts on the same task: writing the conflict-warning UI message in `app.py`.

| | Option A (vague prompt) | Option B (specific prompt) |
|-|-------------------------|----------------------------|
| **Prompt** | 
"Show a warning if there's a conflict" | "If the Scheduler flags a task conflict, show a `st.warning` that recommends the user revise the plan — adjust priority or time" 

| **Response summary** | 
Produced `st.warning(conflict_string)` — just echoed the raw conflict string from `detect_conflicts()` | 
Produced a formatted `st.warning` with the conflict string on the first line and a bulleted tip list (change fixed time / lower priority / shorten duration) 

| **What was useful** | 
Simple, fast | 
Actionable — tells *what needs to be fixed*, not just *that something is wrong* 

| **Problems noticed** | 
Raw conflict string like `WARNING [SAME PET: Mochi] 'Vet visit' (10:00) overlaps 'Feeding' (10:00)` is hard to read without context 
| Slightly more code, but all within a single `st.warning(f"...")` call 

| **Decision** | 
Not used | Used in final `app.py` 

**Which approach did you use in your final implementation and why?**

Option B. The raw conflict string from `detect_conflicts()` is written for programmatic use — it's precise but terse. I see it in a UI has no idea what action to take. Adding the tip list ("change the fixed time / lower the priority / shorten the duration") turns the warning from a diagnostic into a next-step guide, which is the point of a UI over a CLI.

