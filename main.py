import sys
from tabulate import tabulate
from pawpal_system import Owner, Scheduler

sys.stdout.reconfigure(encoding="utf-8")  # emojis/box-drawing chars need utf-8, not the default cp1252 on Windows

# ── ANSI colors (no extra dependency — supported by modern terminals) ──────────
RED, YELLOW, GREEN, BOLD, RESET = "\033[91m", "\033[93m", "\033[92m", "\033[1m", "\033[0m"

_PRIORITY_COLOR = {"high": RED, "medium": YELLOW, "low": GREEN}

_TASK_EMOJI = {
    "walk": "🚶", "feed": "🍽️", "vet": "🩺", "medic": "💊",
    "groom": "🧼", "play": "🎾", "fetch": "🎾",
}


def task_emoji(title: str) -> str:
    """Look up a task emoji by keyword match on the title, default to a paw."""
    lowered = title.lower()
    for keyword, emoji in _TASK_EMOJI.items():
        if keyword in lowered:
            return emoji
    return "🐾"


def colored_priority(priority: str) -> str:
    color = _PRIORITY_COLOR.get(priority, "")
    return f"{color}{priority.upper()}{RESET}"


owner = Owner("Jordan")

mochi = owner.add_pet("Mochi", "cat")
biscuit = owner.add_pet("Biscuit", "dog")

# Anchor: Vet visit pinned to 10:00 (60 min) -> ends 11:00
# Floating tasks should fill 09:00-10:00 first, then spill to 11:00+
mochi.add_task("Vet visit",     60, "high",   frequency="as_needed", start_time="10:00")
mochi.add_task("Feeding",       10, "high",   frequency="daily")       # should fill 09:00 window
mochi.add_task("Grooming",      20, "low",    frequency="weekly")      # low — goes after 11:00

biscuit.add_task("Medication",   5, "high",   frequency="daily")       # should fill 09:00 window
biscuit.add_task("Morning walk", 30, "high",  frequency="daily")       # should fill 09:00 window
biscuit.add_task("Play session", 20, "low",   frequency="as_needed")   # low — goes after 11:00

print(f"{BOLD}=== Window-filling schedule ==={RESET}")
print("  Anchor: Vet visit pinned at 10:00 (ends 11:00)")
print("  Windows: [09:00-10:00] and [11:00-21:00]\n")

result = Scheduler(owner.get_all_tasks()).schedule()

rows = [
    [
        t.start_time,
        f"{task_emoji(t.title)} {t.title}" + (" (anchor)" if t.title == "Vet visit" else ""),
        colored_priority(t.priority),
        f"{t.duration_minutes} min",
        t.frequency,
    ]
    for t in result.tasks
]
print(tabulate(rows, headers=["Time", "Task", "Priority", "Duration", "Frequency"], tablefmt="rounded_outline"))

if result.conflicts:
    print(f"\n{RED}⚠️  Conflicts:{RESET}")
    for c in result.conflicts:
        print(f"  {RED}!{RESET} {c}")
else:
    print(f"\n{GREEN}✅ No conflicts detected.{RESET}")
