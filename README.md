# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors 

what does it mean "the most important scheduling behaviors"?

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## 🖥️ Sample Output

Paste a sample of your app's CLI or Streamlit output here so a reader can see what a generated plan looks like:

```
# e.g.:
# Daily plan for Biscuit (Golden Retriever):
#   08:00 — Morning walk (30 min) [priority: high]
#   09:00 — Feeding (10 min) [priority: high]
#   ...
```

## 🧪 Testing PawPal+

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```

  1. [HIGH  ] Feeding              10 min  |  daily
  2. [HIGH  ] Morning walk         30 min  |  daily
  3. [HIGH  ] Medication           5 min  |  daily
  4. [MEDIUM] Fetch                15 min  |  as_needed
  5. [LOW   ] Grooming             20 min  |  weekly

Schedule (high → low priority):
- Feeding (high priority, 10 min)
- Morning walk (high priority, 30 min)
- Medication (high priority, 5 min)
- Fetch (medium priority, 15 min)
- Grooming (low priority, 20 min)
```

## 📐 Smarter Scheduling

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Time sorting | `Scheduler.sort_by_time()` | Sorts tasks by HH:MM string; unscheduled tasks go last (sentinel "99:99") |
| Auto time assignment | `Scheduler.assign_times()` | Window-filling: anchors divide the day into gaps; floating tasks fill each gap priority-first |
| Filtering by pet / status | `Owner.get_all_tasks(pet_name, status)` | Keyword filters; omit either to return all pets or all statuses |
| Recurring task filter | `Scheduler.filter_recurring(day_of_week)` | daily always included; weekly only on Monday; as_needed excluded |
| Conflict detection | `Scheduler.detect_conflicts()` | Interval overlap (same-pet vs cross-pet labels) + budget overflow check |
| Recurring auto-renewal | `Pet.complete_task(title)` | Marks task complete and appends next occurrence using `timedelta(days=1)` or `timedelta(weeks=1)` |
| Duplicate guard | `Owner.add_pet()`, `Pet.add_task()` | Silently returns the existing object instead of creating a duplicate |

### Sorting — `Scheduler.sort_by_time()`

Tasks carry a `start_time` string in `"HH:MM"` format. Python's `sorted()` with a lambda key sorts these lexicographically, which works correctly because the format is zero-padded and fixed-width (`"09:00" < "10:00"`). Tasks with no time yet receive the sentinel `"99:99"` so they sort to the end without crashing.

### Auto time assignment — `Scheduler.assign_times()`

The scheduler separates tasks into two groups:

- **Anchors** — tasks the owner pinned to a fixed time (e.g. a vet appointment at 10:00). These are immovable.
- **Floating** — tasks with no preset time. These are sorted by priority (high → medium → low), then by shortest-first within each priority tier.

Anchors divide the day into time windows (e.g. `[09:00–10:00]` and `[11:00–21:00]`). Each floating task is placed in the **first window where it fits**. This ensures gaps before anchor tasks are used before spilling tasks to later slots.

### Filtering — `Owner.get_all_tasks(pet_name=None, status=None)`

Returns tasks from all pets by default. Pass `pet_name="Mochi"` to see only one pet's tasks, `status="pending"` to exclude completed tasks, or both to combine the filters. Used by `app.py` to build the task table and by `Scheduler` to get a fresh task list before scheduling.

### Conflict detection — `Scheduler.detect_conflicts()`

Runs two checks after times are assigned:

1. **Interval overlap**: for every pair of timed tasks, checks `a_start < b_end and b_start < a_end`. Labels the warning `[SAME PET]` or `[CROSS PET]` so the owner can tell at a glance whether one pet has a double-booking or two pets need attention at the same time.
2. **Budget overflow**: sums all pending task durations and compares to `day_end − day_start`. Reports how many minutes over budget the day is.

Returns an empty list when the schedule is clean.

### Recurring tasks — `Pet.complete_task(title)` + `Task.next_occurrence()`

When the owner marks a task complete, `complete_task()` calls `next_occurrence()` on it. That method uses Python's `timedelta` to compute the next due date:

```python
timedelta(days=1)   # for frequency="daily"  → tomorrow
timedelta(weeks=1)  # for frequency="weekly" → same day next week
```

`timedelta` handles month and year boundaries automatically (e.g. January 31 + 1 day = February 1). The new task is appended to the pet's task list with `completion_status="pending"` so it shows up in the next schedule automatically.

## 💾 Persistence — Save Workflow

PawPal+ automatically saves state to a local JSON file (`pawpal_save.json`) so an owner's pets and tasks survive a page reload or app restart.

**How it works:**

1. **On startup**, `app.py` checks if `owner` is already in `st.session_state`. If not, it calls `load_owner()`, which reads `pawpal_save.json` and rebuilds the `Owner` → `Pet` → `Task` objects. If the file doesn't exist yet (first run), `load_owner()` returns `None` and the app starts fresh.
2. **On every mutation** — clicking "Set Owner & Pet" or "Add task" — `app.py` calls `save_owner(st.session_state.owner)` right after the change. `save_owner()` converts the whole object tree to a dict with `dataclasses.asdict()` and writes it to `pawpal_save.json` with `json.dumps(..., indent=2)`.
3. Both functions use only the Python standard library (`json`, `pathlib`) — no new dependencies.

**Files modified:**

| File | Change |
|---|---|
| `pawpal_system.py` | Added `save_owner(owner, path="pawpal_save.json")` and `load_owner(path="pawpal_save.json")` at module level. |
| `app.py` | Imports `save_owner`/`load_owner`; calls `load_owner()` once at startup, and `save_owner(...)` after "Set Owner & Pet" and "Add task". |

Read-only actions like "Check available slots" and "Generate schedule" don't call `save_owner` — they don't change any task data, so there's nothing new to persist.

## 🧪 Testing PawPal+
```PowerShell:

# Run the full test suite:
python -m pytest

```
Sample test output:

```
======================================================================= test session starts ========================================================================
platform win32 -- Python 3.14.5, pytest-9.1.1, pluggy-1.6.0
rootdir: G:\My Drive\Self_Study\AI110\ai110-module2show-pawpal-starter-main
collected 23 items                                                                                                                                                  

tests\test_pawpal.py .......................                                                                                                                  [100%]

======================================================================== 23 passed in 0.32s ========================================================================
```
Confident Level: 5 stars
## 📸 Demo Walkthrough

### UI Features

The Streamlit app (`app.py`) exposes four interaction areas:

| Area | What the user can do |
|---|---|
| **Owner & Pet Setup** | Enter an owner name, pet name, and species, then click "Set Owner & Pet" to register them. Adding the same pet name twice returns the existing pet — no duplicates. |
| **Add Tasks** | Enter a task title, duration (minutes), priority (low / medium / high), and an optional fixed time (`HH:MM`). Tasks with a fixed time become anchors the scheduler will not move; tasks without one are placed automatically. |
| **Task Table** | Displays all current tasks across all pets with their pet name, duration, priority, fixed time (or "auto"), and completion status. |
| **Build Schedule** | Set a day-start and day-end window (default 09:00–21:00), then click "Generate schedule". The app shows a sorted schedule table and either a green success banner or amber conflict warnings with revision tips. |

---

### Example Workflow

1. Enter owner name **Jordan**, pet name **Mochi** (cat), click **Set Owner & Pet**.
2. Add a second pet: **Biscuit** (dog), click **Set Owner & Pet** again.
3. Add tasks for Mochi:
   - "Vet visit" — 60 min, high, fixed time **10:00** *(anchor)*
   - "Feeding" — 10 min, high, no fixed time *(floating)*
   - "Grooming" — 20 min, low, no fixed time *(floating)*
4. Add tasks for Biscuit:
   - "Medication" — 5 min, high, no fixed time
   - "Morning walk" — 30 min, high, no fixed time
   - "Play session" — 20 min, low, no fixed time
5. Click **Generate schedule** (window 09:00–21:00).

The scheduler pins Vet visit at 10:00, creating two windows: `[09:00–10:00]` and `[11:00–21:00]`. It fills the first window with the shortest high-priority tasks (Medication → Feeding → Morning walk), then places the low-priority tasks after 11:00. The schedule table shows all six tasks sorted by start time with no conflicts.

---

### Key Scheduler Behaviors Shown

**Anchor + window-filling (`assign_times`)**
The 60-min Vet visit at 10:00 splits the day into two gaps. Floating tasks are placed gap-by-gap, priority-first, so the 09:00–10:00 gap fills up before anything spills to 11:00+.

**Priority + shortest-first ordering**
Within the same priority tier, the shortest task goes first. That is why 5-min Medication (`09:00`) precedes 10-min Feeding (`09:05`) and 30-min Morning walk (`09:15`) — all are `high`, placed shortest-first.

**Sorting by time (`sort_by_time`)**
The final table is always returned sorted by `HH:MM` string. Because the format is zero-padded, lexicographic order is the same as chronological order.

**Conflict detection (`detect_conflicts`)**
After times are assigned, every task pair is checked with `a_start < b_end and b_start < a_end`. Warnings are labelled `[SAME PET]` or `[CROSS PET]`. A second check sums all pending durations; if the total exceeds `day_end − day_start`, a budget-overflow warning is added.

**Conflict warning tip (UI)**
When a conflict is flagged, the app displays: *"Try changing a task's fixed time so it doesn't overlap, lower its priority, or shorten its duration."*

---

### CLI Output — `python main.py`

```
=== Window-filling schedule ===
  Anchor: Vet visit pinned at 10:00 (ends 11:00)
  Windows: [09:00-10:00] and [11:00-21:00]

╭────────┬──────────────────────┬────────────┬────────────┬─────────────╮
│ Time   │ Task                 │ Priority   │ Duration   │ Frequency   │
├────────┼──────────────────────┼────────────┼────────────┼─────────────┤
│ 09:00  │ 💊 Medication        │ HIGH       │ 5 min      │ daily       │
│ 09:05  │ 🍽️ Feeding           │ HIGH       │ 10 min     │ daily       │
│ 09:15  │ 🚶 Morning walk      │ HIGH       │ 30 min     │ daily       │
│ 10:00  │ 🩺 Vet visit (anchor)│ HIGH       │ 60 min     │ as_needed   │
│ 11:00  │ 🧼 Grooming          │ LOW        │ 20 min     │ weekly      │
│ 11:20  │ 🎾 Play session      │ LOW        │ 20 min     │ as_needed   │
╰────────┴──────────────────────┴────────────┴────────────┴─────────────╯

✅ No conflicts detected.
```

*(HIGH renders red, LOW renders green in a real terminal — flattened to plain text here.)*

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or Streamlit Cloud link here -->

## 🎨 CLI Output Formatting

`main.py` formats the schedule with three readability features:

| Feature | How it's done |
|---|---|
| **Structured table** | [`tabulate`](https://pypi.org/project/tabulate/) (`tablefmt="rounded_outline"`) renders the schedule as a bordered table instead of manually padded `print()` lines. Added to `requirements.txt`. |
| **Task emojis** | `task_emoji(title)` keyword-matches the task title (`walk`, `feed`, `vet`, `medic`, `groom`, `play`/`fetch`) against an emoji dict, defaulting to 🐾 for anything unmatched. |
| **Color-coded priority** | `colored_priority(priority)` wraps the priority text in ANSI escape codes — red for `high`, yellow for `medium`, green for `low` — using plain `\033[...m` sequences (no extra dependency needed since modern terminals support ANSI natively). |

The conflicts summary also gets a colored/emoji treatment: `✅ No conflicts detected.` in green, or `⚠️ Conflicts:` in red with each line prefixed by a red `!`.

`sys.stdout.reconfigure(encoding="utf-8")` is set at the top of `main.py` so emojis and box-drawing characters render correctly on Windows terminals, which otherwise default to `cp1252`.
