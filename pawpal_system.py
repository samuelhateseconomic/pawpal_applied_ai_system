from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path
from typing import NamedTuple

_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class ScheduleResult(NamedTuple):
    tasks: list[Task]
    conflicts: list[str]


def _parse_hhmm(hhmm: str) -> int:
    """'HH:MM' -> minutes from midnight."""
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _format_hhmm(minutes: int) -> str:
    """Minutes from midnight -> 'HH:MM'."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass
class Task:
    title: str
    duration_minutes: int
    priority: str               # "high", "medium", "low"
    description: str = ""
    frequency: str = "daily"    # "daily", "weekly", "as_needed"
    completion_status: str = "pending"  # "pending", "complete"
    start_time: str | None = None  # "HH:MM" format, e.g. "09:00"
    due_date: str | None = None    # "YYYY-MM-DD" format
    pet_name: str | None = None    # set automatically by Pet.add_task()

    def mark_complete(self) -> None:
        self.completion_status = "complete"

    def mark_incomplete(self) -> None:
        self.completion_status = "pending"

    def next_occurrence(self) -> Task | None:
        """
        Return a new pending Task for the next scheduled occurrence, or None
        if the task is 'as_needed' (no fixed recurrence).

        timedelta(days=1) adds exactly 1 day to today's date, handling
        month and year boundaries automatically (e.g. Jan 31 + 1 = Feb 1).
        timedelta(weeks=1) is shorthand for timedelta(days=7).
        """
        if self.frequency == "daily":
            next_due = date.today() + timedelta(days=1)
        elif self.frequency == "weekly":
            next_due = date.today() + timedelta(weeks=1)
        else:
            return None
        return Task(
            title=self.title,
            duration_minutes=self.duration_minutes,
            priority=self.priority,
            description=self.description,
            frequency=self.frequency,
            due_date=str(next_due),
            pet_name=self.pet_name,
        )


@dataclass
class Pet:
    pet_name: str
    species: str
    tasks: list[Task] = field(default_factory=list)

    def add_task(self, title: str, duration_minutes: int, priority: str,
                 description: str = "", frequency: str = "daily",
                 start_time: str | None = None) -> Task | None:
        """Create and append a Task. Returns None if a task with that title already exists.
        Pass start_time='HH:MM' to pin the task to a fixed slot; assign_times() will skip it."""
        if any(t.title == title for t in self.tasks):
            return None
        task = Task(title, duration_minutes, priority, description, frequency,
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


class Owner:
    def __init__(self, owner_name: str):
        self.owner_name = owner_name
        self.pets: list[Pet] = []

    def add_pet(self, pet_name: str, species: str) -> Pet:
        """Return the existing pet if the name already exists, otherwise create and add one."""
        existing = next((p for p in self.pets if p.pet_name == pet_name), None)
        if existing:
            return existing
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

    def filter_recurring(self, day_of_week: int = 0) -> list[Task]:
        """
        Return the subset of tasks that should run on the given weekday.

        day_of_week follows Python's weekday() convention: 0 = Monday, 6 = Sunday.

        - ``daily``     tasks are always included regardless of the day.
        - ``weekly``    tasks are included only on Monday (day_of_week == 0),
                        so they appear exactly once per week.
        - ``as_needed`` tasks are excluded entirely; they are meant to be
                        scheduled manually when the owner decides they are needed.

        Use this before passing tasks to Scheduler to get a day-appropriate
        task list instead of the full unfiltered set.
        """
        result = []
        for t in self.tasks:
            if t.frequency == "daily":
                result.append(t)
            elif t.frequency == "weekly" and day_of_week == 0:
                result.append(t)
        return result

    def assign_times(self) -> list[Task]:
        """
        Fill time windows created by anchor (pre-set) tasks with floating tasks,
        in priority+shortest-first order. Each floating task is placed in the
        first window where it fits, so gaps before anchors are used before spilling
        past them. Tasks that fit nowhere are placed sequentially after day_end.
        """
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

        1. **Time overlap** — any two tasks whose intervals intersect.
           Overlap is detected with the standard interval test:
           ``a_start < b_end and b_start < a_end``.
           Each warning is labelled either:
           - ``[SAME PET: <name>]``  when both tasks belong to the same pet, or
           - ``[CROSS PET: <A> / <B>]`` when they belong to different pets.
           This distinction helps the owner see whether they need to reschedule
           one pet's activity or coordinate between two pets at the same time.

        2. **Budget overflow** — total pending task duration exceeds the
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
                if a_start < b_end and b_start < a_end:
                    if a.pet_name and b.pet_name and a.pet_name == b.pet_name:
                        kind = f"[SAME PET: {a.pet_name}]"
                        label = f"'{a.title}' ({a.start_time}) overlaps '{b.title}' ({b.start_time})"
                    else:
                        pa = a.pet_name or "unknown"
                        pb = b.pet_name or "unknown"
                        kind = f"[CROSS PET: {pa} / {pb}]"
                        label = f"'{a.title}' ({a.start_time}) overlaps '{b.title}' ({b.start_time})"
                    messages.append(f"WARNING {kind} {label}")

        pending = [t for t in self.tasks if t.completion_status == "pending"]
        total = sum(t.duration_minutes for t in pending)
        available = _parse_hhmm(self.day_end) - _parse_hhmm(self.day_start)
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
                f"{t.title:<20} {t.duration_minutes} min  |  {t.frequency}"
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
    """Load an Owner from a JSON file. Returns None if the file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    owner = Owner(data["owner_name"])
    for pet_data in data["pets"]:
        pet = owner.add_pet(pet_data["pet_name"], pet_data["species"])
        for t in pet_data["tasks"]:
            pet.tasks.append(Task(**t))
    return owner
