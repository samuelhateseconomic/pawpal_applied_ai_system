from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any, NamedTuple

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

_UNSET = object()  # sentinel: "argument not supplied" (distinct from None, which can be a real value)

_LEGACY_FREQUENCY_MAP = {
    "daily": (1, "day"),
    "weekly": (1, "week"),
    "as_needed": (1, "as_needed"),
}

# Light input bounds: not a defense against a determined bad actor, just a
# cheap cap on blast radius (spam-dumping, prompt-injection payloads hidden
# in a field, or an unbounded local JSON file) that doesn't require content
# moderation or an extra LLM call to enforce.
MAX_NAME_WORDS = 50   # owner_name / pet_name / species
MAX_TEXT_WORDS = 200  # task description / pet notes
MAX_PETS_PER_OWNER = 500

# Baseline companion-animal categories that are commonly legal to keep as a
# pet. Not exhaustive and not a legal ruling — species outside this list
# aren't blocked, they just get flagged so the agent can warn the user
# rather than silently treating them like a dog or cat.
RECOGNIZED_SPECIES = frozenset({
    "dog", "cat", "savannah cat",
    "guinea pig", "mouse", "rat", "chinchilla",
    "hamster", "golden hamster", "syrian hamster",
    "rabbit",
    "canary", "finch", "budgie", "budgerigar",
    "snake", "king snake", "corn snake",
    "fish", "freshwater fish",
})


class ValidationError(ValueError):
    """Raised when user-supplied text/counts exceed PawPal+'s input bounds."""


def word_count(text: str) -> int:
    return len(text.split())


def check_word_limit(field: str, text: str, limit: int) -> None:
    count = word_count(text)
    if count > limit:
        raise ValidationError(f"{field} must be under {limit} words (got {count}).")


def is_recognized_species(species: str) -> bool:
    """True if species matches PawPal+'s baseline list of commonly-legal companion animals."""
    return species.strip().lower() in RECOGNIZED_SPECIES


VALID_PRIORITIES = frozenset({"high", "medium", "low"})
VALID_FREQUENCY_UNITS = frozenset({"day", "week", "month", "as_needed"})


def check_duration(duration_minutes: Any) -> None:
    if not isinstance(duration_minutes, int) or duration_minutes <= 0:
        raise ValidationError(f"duration_minutes must be a positive integer (got {duration_minutes!r}).")


def check_priority(priority: Any) -> None:
    if priority not in VALID_PRIORITIES:
        raise ValidationError(f"priority must be one of {sorted(VALID_PRIORITIES)} (got {priority!r}).")


def check_frequency_unit(frequency_unit: Any) -> None:
    if frequency_unit not in VALID_FREQUENCY_UNITS:
        raise ValidationError(f"frequency_unit must be one of {sorted(VALID_FREQUENCY_UNITS)} (got {frequency_unit!r}).")


class ScheduleResult(NamedTuple):
    tasks: list[Task]
    conflicts: list[str]


def _parse_hhmm(hhmm: str) -> int:
    """'HH:MM' -> minutes from midnight."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _active_days(period_length: int, count: int) -> set[int]:
    """
    Return `count` evenly-spaced 0-based day indices within a period of
    `period_length` days (e.g. period_length=7 for a week). Used to
    auto-spread a week/month multi-count task across the period without a
    real calendar engine — self-contained day-of-period math only.
    """
    if count <= 0:
        return set()
    count = min(count, period_length)  # can't have more occurrences than days in the period
    step = period_length / count
    return {int(i * step) for i in range(count)}


def _format_hhmm(minutes: int) -> str:
    """Minutes from midnight -> 'HH:MM'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class Task:
    title: str
    duration_minutes: int
    priority: str               # "high", "medium", "low"
    description: str = ""
    frequency_count: int = 1       # occurrences per frequency_unit period; ignored when unit == "as_needed"
    frequency_unit: str = "day"    # "day", "week", "month", "as_needed"
    completion_status: str = "pending"  # "pending", "complete"
    start_time: str | None = None  # "HH:MM" format, e.g. "09:00"
    due_date: str | None = None    # "YYYY-MM-DD" format
    pet_name: str | None = None    # set automatically by Pet.add_task()

    def mark_complete(self) -> None:
        self.completion_status = "complete"

    def mark_incomplete(self) -> None:
        self.completion_status = "pending"

    def frequency_label(self) -> str:
        """Human-readable frequency string for display, e.g. '2x/day', 'as needed'."""
        if self.frequency_unit == "as_needed":
            return "as needed"
        return f"{self.frequency_count}x/{self.frequency_unit}"

    def next_occurrence(self) -> Task | None:
        """
        Return a new pending Task for the next scheduled occurrence, or None
        if the task is 'as_needed' (no fixed recurrence).

        timedelta(days=1) adds exactly 1 day to today's date, handling
        month and year boundaries automatically (e.g. Jan 31 + 1 = Feb 1).
        timedelta(weeks=1) is shorthand for timedelta(days=7). "month" uses a
        flat 30-day approximation rather than tracking calendar months.
        """
        if self.frequency_unit == "day":
            next_due = date.today() + timedelta(days=1)
        elif self.frequency_unit == "week":
            next_due = date.today() + timedelta(weeks=1)
        elif self.frequency_unit == "month":
            next_due = date.today() + timedelta(days=30)
        else:
            return None
        return Task(
            title=self.title,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            description=self.description,
            frequency_count=self.frequency_count,
            frequency_unit=self.frequency_unit,
            due_date=str(next_due),
            pet_name=self.pet_name,
        )


@dataclass
class Pet:
    pet_name: str
    species: str
    notes: str = ""
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, title: str, duration_minutes: int, priority: str,
                 description: str = "", frequency_count: int = 1,
                 frequency_unit: str = "day",
                 start_time: str | None = None) -> Task | None:
        """Create and append a Task. Returns None if a task with that title already exists.
        Pass start_time='HH:MM' to pin the task to a fixed slot; assign_times() will skip it.
        Raises ValidationError if description exceeds MAX_TEXT_WORDS words, duration_minutes
        isn't a positive integer, or priority/frequency_unit is unrecognized."""
        if any(t.title == title for t in self.tasks):
            return None
        check_word_limit("description", description, MAX_TEXT_WORDS)
        check_duration(duration_minutes)
        check_priority(priority)
        check_frequency_unit(frequency_unit)
        task = Task(title, duration_minutes, priority, description,
                    frequency_count, frequency_unit,
                    start_time=start_time, pet_name=self.pet_name)
        self.tasks.append(task)
        return task

    def get_tasks(self) -> list[Task]:
        return self.tasks

    def complete_task(self, title: str) -> Task | None:
        """
        Mark a task complete by title. If the task is daily or weekly,
        automatically append the next occurrence to this pet's task list.
        Returns the new occurrence Task, or None if not recurring or not found.
        """
        task = next((t for t in self.tasks if t.title == title), None)
        if task is None:
            return None
        task.mark_complete()
        next_task = task.next_occurrence()
        if next_task:
            self.tasks.append(next_task)
        return next_task

    def edit_task(self, title: str, *, new_title: Any = _UNSET, duration_minutes: Any = _UNSET,
                  priority: Any = _UNSET, description: Any = _UNSET, frequency_count: Any = _UNSET,
                  frequency_unit: Any = _UNSET, start_time: Any = _UNSET) -> Task | None:
        """
        Update fields on an existing task in place. Any field left as _UNSET
        (the default) is left unchanged. Pass start_time=None explicitly to
        unpin a fixed time. Returns the updated Task, or None if not found.
        Rename is rejected (returns None, task left unmodified) if new_title
        collides with another existing task's title. Raises ValidationError
        if description exceeds MAX_TEXT_WORDS words, duration_minutes isn't
        a positive integer, or priority/frequency_unit is unrecognized.
        """
        task = next((t for t in self.tasks if t.title == title), None)
        if task is None:
            return None
        if new_title is not _UNSET and new_title != title:
            if any(t.title == new_title for t in self.tasks):
                return None
            task.title = new_title
        if duration_minutes is not _UNSET:
            check_duration(duration_minutes)
            task.duration_minutes = duration_minutes
        if priority is not _UNSET:
            check_priority(priority)
            task.priority = priority
        if description is not _UNSET:
            check_word_limit("description", description, MAX_TEXT_WORDS)
            task.description = description
        if frequency_count is not _UNSET:
            task.frequency_count = frequency_count
        if frequency_unit is not _UNSET:
            check_frequency_unit(frequency_unit)
            task.frequency_unit = frequency_unit
        if start_time is not _UNSET:
            task.start_time = start_time
        return task

    def delete_task(self, title: str) -> bool:
        """Remove a task by title. Returns True if found and removed, False otherwise."""
        for i, t in enumerate(self.tasks):
            if t.title == title:
                self.tasks.pop(i)
                return True
        return False


class Owner:
    def __init__(self, owner_name: str):
        self.owner_name = owner_name
        self.pets: list[Pet] = []

    def add_pet(self, pet_name: str, species: str) -> Pet:
        """
        Return the existing pet if the name already exists, otherwise create and add one.
        Raises ValidationError if pet_name/species exceed MAX_NAME_WORDS words, or if the
        owner already has MAX_PETS_PER_OWNER pets.
        """
        existing = next((p for p in self.pets if p.pet_name == pet_name), None)
        if existing:
            return existing
        check_word_limit("pet_name", pet_name, MAX_NAME_WORDS)
        check_word_limit("species", species, MAX_NAME_WORDS)
        if len(self.pets) >= MAX_PETS_PER_OWNER:
            raise ValidationError(f"Cannot add more than {MAX_PETS_PER_OWNER} pets.")
        pet = Pet(pet_name, species)
        self.pets.append(pet)
        return pet

    def remove_pet(self, pet_name: str) -> bool:
        """Remove a pet by name. Returns True if found and removed, False otherwise."""
        for i, p in enumerate(self.pets):
            if p.pet_name == pet_name:
                self.pets.pop(i)
                return True
        return False

    def edit_pet(self, pet_name: str, *, new_name: str | None = None,
                 species: str | None = None, notes: str | None = None) -> Pet | None:
        """
        Update an existing pet's name/species/notes in place. None means
        "leave unchanged" for each param (pass notes="" to clear notes text).
        Returns the updated Pet, or None if not found. Rename is rejected
        (returns None, pet left unmodified) if new_name collides with another
        existing pet. Raises ValidationError if new_name/species exceed
        MAX_NAME_WORDS words, or notes exceeds MAX_TEXT_WORDS words.
        """
        pet = next((p for p in self.pets if p.pet_name == pet_name), None)
        if pet is None:
            return None
        if new_name is not None and new_name != pet_name:
            check_word_limit("new_name", new_name, MAX_NAME_WORDS)
            if any(p.pet_name == new_name for p in self.pets):
                return None
            pet.pet_name = new_name
            for t in pet.tasks:
                t.pet_name = new_name  # keep Task.pet_name in sync — read by Scheduler.detect_conflicts and app.py
        if species is not None:
            check_word_limit("species", species, MAX_NAME_WORDS)
            pet.species = species
        if notes is not None:
            check_word_limit("notes", notes, MAX_TEXT_WORDS)
            pet.notes = notes
        return pet

    def get_pets(self) -> list[Pet]:
        return self.pets

    def get_all_tasks(self, pet_name: str | None = None,
                      status: str | None = None) -> list[Task]:
        """Return tasks, optionally filtered by pet name and/or completion status."""
        return [
            task
            for pet in self.pets
            if pet_name is None or pet.pet_name == pet_name
            for task in pet.tasks
            if status is None or task.completion_status == status
        ]


class Scheduler:
    def __init__(self, tasks: list[Task], day_start: str = "09:00", day_end: str = "21:00"):
        """day_start / day_end: scheduling window in 'HH:MM' format."""
        self.tasks = tasks
        self.day_start = day_start
        self.day_end = day_end

    def filter_recurring(self, day_of_week: int = 0, day_of_month: int = 1) -> list[Task]:
        """
        Return the subset of tasks that should run on the given day.

        day_of_week follows Python's weekday() convention: 0 = Monday, 6 = Sunday.
        day_of_month is a 1-based day-of-period index used for "month" tasks.

        - ``day``       tasks are always included regardless of the day; same-day
                        multiplicity (frequency_count > 1) is expanded later, in
                        assign_times(), not here.
        - ``week``      tasks are included only on the frequency_count evenly-spaced
                        weekdays picked by _active_days(7, frequency_count).
        - ``month``     tasks are included only on the frequency_count evenly-spaced
                        days picked by _active_days(30, frequency_count) — a flat
                        30-day approximation, not a real calendar month.
        - ``as_needed`` tasks are excluded entirely; they are meant to be
                        scheduled manually when the owner decides they are needed.

        Use this before passing tasks to Scheduler to get a day-appropriate
        task list instead of the full unfiltered set.
        """
        result = []
        for t in self.tasks:
            if t.frequency_unit == "day":
                result.append(t)
            elif t.frequency_unit == "week":
                if day_of_week in _active_days(7, t.frequency_count):
                    result.append(t)
            elif t.frequency_unit == "month":
                if (day_of_month - 1) in _active_days(30, t.frequency_count):
                    result.append(t)
        return result

    def _expand_daily_multiplicity(self) -> None:
        """
        Replace self.tasks with an expanded list: any pending task with
        frequency_unit == "day" and frequency_count > 1 is split into N
        independent, ephemeral copies (via dataclasses.replace) — never
        written back to Pet.tasks, only used within this Scheduler run.
        If the original task had a pinned start_time, occurrence 1 keeps it
        (stays an anchor) and occurrences 2..N float, so assign_times() finds
        them their own slots. Each copy gets frequency_count=1 so re-running
        this method (e.g. via a second .schedule() call) is a no-op.
        """
        expanded: list[Task] = []
        for t in self.tasks:
            if t.frequency_unit == "day" and t.frequency_count > 1 and t.completion_status == "pending":
                for i in range(1, t.frequency_count + 1):
                    expanded.append(replace(
                        t,
                        title=f"{t.title} ({i}/{t.frequency_count})",
                        start_time=t.start_time if i == 1 else None,
                        frequency_count=1,
                    ))
            else:
                expanded.append(t)
        self.tasks = expanded

    def assign_times(self) -> list[Task]:
        """
        Fill time windows created by anchor (pre-set) tasks with floating tasks,
        in priority+shortest-first order. Each floating task is placed in the
        first window where it fits, so gaps before anchors are used before spilling
        past them. Tasks that fit nowhere are placed sequentially after day_end.
        """
        self._expand_daily_multiplicity()
        pending = [t for t in self.tasks if t.completion_status == "pending"]

        anchors: list[Task] = sorted(
            [t for t in pending if t.start_time is not None],
            key=lambda t: _parse_hhmm(t.start_time or "00:00"),
        )
        floating: list[Task] = sorted(
            [t for t in pending if t.start_time is None],
            key=lambda t: (_PRIORITY_ORDER.get(t.priority, 99), t.duration_minutes),
        )

        day_start_min = _parse_hhmm(self.day_start)
        day_end_min = _parse_hhmm(self.day_end)

        # Build windows: (start, end) gaps between day_start, anchors, and day_end.
        windows: list[tuple[int, int]] = []
        cursor = day_start_min
        for anchor in anchors:
            a_start = _parse_hhmm(anchor.start_time or "00:00")
            if a_start > cursor:
                windows.append((cursor, a_start))
            cursor = max(cursor, a_start + anchor.duration_minutes)
        windows.append((cursor, day_end_min))  # final window after last anchor

        win_cursors: list[int] = [w[0] for w in windows]

        for task in floating:
            assigned = False
            for i, (_, win_end) in enumerate(windows):
                if win_cursors[i] + task.duration_minutes <= win_end:
                    task.start_time = _format_hhmm(win_cursors[i])
                    win_cursors[i] += task.duration_minutes
                    assigned = True
                    break
            if not assigned:
                # Overflow: place sequentially past day_end
                task.start_time = _format_hhmm(win_cursors[-1])
                win_cursors[-1] += task.duration_minutes

        return sorted(floating + anchors, key=lambda t: _parse_hhmm(t.start_time or "00:00"))

    def find_available_slots(self, duration_minutes: int) -> list[tuple[str, str]]:
        """
        Return open (start, end) HH:MM blocks within the day window that are
        at least ``duration_minutes`` long, based on tasks that already have
        a start_time (anchors or previously assigned tasks).

        Use this to answer "what times are free for a new task of this length?"
        before adding/pinning it — it does not assign or modify any tasks.
        """
        day_start_min = _parse_hhmm(self.day_start)
        day_end_min = _parse_hhmm(self.day_end)

        busy = sorted(
            (_parse_hhmm(t.start_time), _parse_hhmm(t.start_time) + t.duration_minutes)
            for t in self.tasks
            if t.start_time is not None and t.completion_status == "pending"
        )

        merged: list[tuple[int, int]] = []
        for start, end in busy:
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))

        slots: list[tuple[str, str]] = []
        cursor = day_start_min
        for start, end in merged:
            if start - cursor >= duration_minutes:
                slots.append((_format_hhmm(cursor), _format_hhmm(start)))
            cursor = max(cursor, end)
        if day_end_min - cursor >= duration_minutes:
            slots.append((_format_hhmm(cursor), _format_hhmm(day_end_min)))

        return slots

    def sort_by_time(self) -> list[Task]:
        """
        Return all tasks sorted by their assigned start_time in ascending order.

        Sorting is done lexicographically on the 'HH:MM' string, which works
        correctly because the format is zero-padded and fixed-width
        (e.g. '09:00' < '10:00' < '21:00').

        Tasks that have no start_time yet (``None``) are sorted to the end by
        substituting the sentinel value '99:99', which is greater than any
        valid HH:MM time.  Call ``assign_times()`` first if you want all tasks
        to carry an actual time before sorting.
        """
        return sorted(
            self.tasks,
            key=lambda t: t.start_time if t.start_time is not None else "99:99",
        )

    def detect_conflicts(self) -> list[str]:
        """
        Return a list of human-readable warning strings describing scheduling conflicts.

        Two types of conflicts are checked:

        1. **Time overlap** — two tasks *for the same pet* whose intervals
           intersect. Overlap is detected with the standard interval test:
           ``a_start < b_end and b_start < a_end``. Labelled ``[SAME PET: <name>]``.
           Two different pets overlapping is intentionally allowed — e.g. two
           dogs going for a walk together — so cross-pet overlaps are not
           reported as conflicts at all.

        2. **Out-of-window scheduling** — a task's interval falls partly or
           fully outside ``[day_start, day_end]``. This can happen to a
           manually pinned anchor task (e.g. fixed at 21:00 when the day ends
           at 21:00, so it runs 20 min past close), or to a floating task
           pushed past ``day_end`` when there's no room left elsewhere (see
           ``assign_times()``'s overflow handling). Reported per-task, naming
           which boundary was missed, so the owner knows whether to change
           that task's fixed time or move the day's start/end instead.

        3. **Budget overflow** — total pending task duration exceeds the
           ``day_end - day_start`` window.  Reported as a single summary line
           so the owner knows the day is over-committed even if no two tasks
           happen to overlap after auto-scheduling.

        Returns an empty list when no conflicts are found.
        Call ``assign_times()`` before this method so tasks have start times.
        """
        messages: list[str] = []

        timed = [t for t in self.tasks if t.start_time is not None]
        for i, a in enumerate(timed):
            a_start = _parse_hhmm(a.start_time)
            a_end = a_start + a.duration_minutes
            for b in timed[i + 1:]:
                b_start = _parse_hhmm(b.start_time)
                b_end = b_start + b.duration_minutes
                # Two different pets overlapping is allowed on purpose — e.g. two dogs
                # going for a walk together — so only the same pet double-booked counts.
                if a_start < b_end and b_start < a_end and a.pet_name and a.pet_name == b.pet_name:
                    kind = f"[SAME PET: {a.pet_name}]"
                    label = f"'{a.title}' ({a.start_time}) overlaps '{b.title}' ({b.start_time})"
                    messages.append(f"WARNING {kind} {label}")

        day_start_min = _parse_hhmm(self.day_start)
        day_end_min = _parse_hhmm(self.day_end)
        for t in timed:
            t_start = _parse_hhmm(t.start_time or "00:00")
            t_end = t_start + t.duration_minutes
            if t_start < day_start_min:
                messages.append(
                    f"WARNING [OUT OF WINDOW] '{t.title}' ({t.start_time}) starts before the day "
                    f"begins at {self.day_start} — change its fixed time or move the day's start earlier."
                )
            elif t_end > day_end_min:
                messages.append(
                    f"WARNING [OUT OF WINDOW] '{t.title}' ({t.start_time}, ends {_format_hhmm(t_end)}) "
                    f"runs past the day's end at {self.day_end} — change its fixed time or move the day's end later."
                )

        pending = [t for t in self.tasks if t.completion_status == "pending"]
        total = sum(t.duration_minutes for t in pending)
        available = day_end_min - day_start_min
        if total > available:
            messages.append(
                f"Total tasks ({total} min) exceed the {available}-min window by {total - available} min"
            )

        return messages

    def schedule(self) -> ScheduleResult:
        """
        Build and return the full schedule.
        Assigns HH:MM start times to unscheduled pending tasks, then runs
        conflict detection. Returns a ScheduleResult(tasks, conflicts) so
        callers get structured data rather than a formatted string.
        """
        tasks = self.assign_times()
        conflicts = self.detect_conflicts()
        return ScheduleResult(tasks=tasks, conflicts=conflicts)

    def explain_reasoning(self) -> str:
        result = self.schedule()
        if not result.tasks:
            return "No pending tasks to schedule."

        lines = ["Schedule (high->low priority, shortest first within same tier):"]
        for t in result.tasks:
            lines.append(
                f"  {t.start_time} | [{t.priority.upper():6}] "
                f"{t.title:<20} {t.duration_minutes} min  |  {t.frequency_label()}"
            )

        if result.conflicts:
            lines.append("\nConflicts detected:")
            lines.extend(f"  ! {c}" for c in result.conflicts)
        else:
            lines.append("\nNo conflicts detected.")

        return "\n".join(lines)


def save_owner(owner: Owner, path: str = "pawpal_save.json") -> None:
    """Persist owner + all pets + all tasks to a JSON file."""
    data = {
        "owner_name": owner.owner_name,
        "pets": [
            {**asdict(pet)}
            for pet in owner.pets
        ],
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_owner(path: str = "pawpal_save.json") -> Owner | None:
    """
    Load an Owner from a JSON file. Returns None if the file doesn't exist.
    Migrates legacy saves (a "frequency": "daily"/"weekly"/"as_needed" string,
    no "notes" on pets) into the current frequency_count/frequency_unit schema.
    """
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    owner = Owner(data["owner_name"])
    for pet_data in data["pets"]:
        pet = owner.add_pet(pet_data["pet_name"], pet_data["species"])
        pet.notes = pet_data.get("notes", "")
        for t in pet_data["tasks"]:
            t = dict(t)  # copy — don't mutate the parsed JSON in place
            if "frequency" in t:
                count, unit = _LEGACY_FREQUENCY_MAP.get(t.pop("frequency"), (1, "day"))
                t.setdefault("frequency_count", count)
                t.setdefault("frequency_unit", unit)
            pet.tasks.append(Task(**t))
    return owner
