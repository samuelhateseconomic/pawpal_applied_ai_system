"""Tool layer for the PawPal+ AI agent.

Each function here is a thin, JSON-in/JSON-out wrapper around a
pawpal_system.py method — these are the literal tool definitions the
Gemini agent will call. No LLM code lives in this file: every wrapper
takes the loaded Owner explicitly (never a hidden global), so it can
be called and tested directly with plain Python, no AI involved.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from pawpal_system import Owner, Pet, Scheduler, save_owner

_OMITTED = object()  # sentinel: "caller did not supply this optional field"


def _find_pet(owner: Owner, pet_name: str) -> Pet | None:
    return next((p for p in owner.get_pets() if p.pet_name == pet_name), None)


def tool_add_pet(owner: Owner, pet_name: str, species: str, notes: str = "") -> dict:
    """
    Register a new pet under the owner.

    Returns {"status": "created", "pet": {...}} on success, or
    {"status": "exists", "pet": {...}} if a pet with that name is
    already registered — add_pet() itself returns the existing pet
    rather than erroring, so this wrapper surfaces that distinctly
    instead of reporting a false "created".
    """
    existing = _find_pet(owner, pet_name)
    pet = owner.add_pet(pet_name, species)
    if existing is not None:
        return {"status": "exists", "pet": asdict(pet)}
    if notes:
        pet.notes = notes
    save_owner(owner)
    return {"status": "created", "pet": asdict(pet)}


def tool_edit_pet(owner: Owner, pet_name: str, new_name: str | None = None,
                   species: str | None = None, notes: str | None = None) -> dict:
    """
    Rename and/or update the species/notes of an existing pet.
    Omit (leave as None) new_name/species to keep them unchanged.
    notes: pass "" to clear existing notes, omit to keep them unchanged.

    Returns {"status": "updated", "pet": {...}}, {"status": "not_found"},
    or {"status": "name_collision"} if new_name matches another pet.
    """
    pet = _find_pet(owner, pet_name)
    if pet is None:
        return {"status": "not_found", "pet_name": pet_name}
    if new_name is not None and new_name != pet_name and _find_pet(owner, new_name) is not None:
        return {"status": "name_collision", "new_name": new_name}
    updated = owner.edit_pet(pet_name, new_name=new_name, species=species, notes=notes)
    save_owner(owner)
    return {"status": "updated", "pet": asdict(updated)}


def tool_remove_pet(owner: Owner, pet_name: str, confirm: bool = False) -> dict:
    """
    Delete a pet and every task belonging to it. Destructive and
    irreversible — nothing is deleted unless confirm=True.

    Call this first with confirm left as False: it deletes nothing and
    instead reports how many tasks would be deleted with the pet, so
    the agent can show the user the impact and get their explicit
    yes/confirmation before calling again with confirm=True.

    Returns {"status": "confirm_required", "deleted_task_count": N} (no
    change made), {"status": "removed", "deleted_task_count": N} once
    confirmed, or {"status": "not_found"}.
    """
    pet = _find_pet(owner, pet_name)
    if pet is None:
        return {"status": "not_found", "pet_name": pet_name}
    deleted_task_count = len(pet.tasks)
    if not confirm:
        return {"status": "confirm_required", "pet_name": pet_name, "deleted_task_count": deleted_task_count}
    owner.remove_pet(pet_name)
    save_owner(owner)
    return {"status": "removed", "pet_name": pet_name, "deleted_task_count": deleted_task_count}


def tool_add_task(owner: Owner, pet_name: str, title: str, duration_minutes: int,
                   priority: str, description: str = "", frequency_count: int = 1,
                   frequency_unit: str = "day", start_time: str | None = None) -> dict:
    """
    Add a task to an existing pet.

    duration_minutes and priority are required — never guess these; ask
    the user if a command didn't supply them. frequency_unit is one of
    "day"/"week"/"month"/"as_needed". start_time is "HH:MM" to pin a
    fixed time, or omit to let the scheduler place it automatically.

    Returns {"status": "created", "task": {...}}, {"status": "duplicate_title"},
    or {"status": "pet_not_found"}.
    """
    pet = _find_pet(owner, pet_name)
    if pet is None:
        return {"status": "pet_not_found", "pet_name": pet_name}
    task = pet.add_task(title, duration_minutes, priority, description,
                        frequency_count, frequency_unit, start_time)
    if task is None:
        return {"status": "duplicate_title", "title": title}
    save_owner(owner)
    return {"status": "created", "task": asdict(task)}


def tool_edit_task(owner: Owner, pet_name: str, title: str, *,
                    new_title: str = _OMITTED, duration_minutes: int = _OMITTED,
                    priority: str = _OMITTED, description: str = _OMITTED,
                    frequency_count: int = _OMITTED, frequency_unit: str = _OMITTED,
                    start_time: Any = _OMITTED) -> dict:
    """
    Update fields on an existing task. Omit any field to leave it
    unchanged; pass start_time=None explicitly to unpin a fixed time.

    Returns {"status": "updated", "task": {...}}, {"status": "task_not_found"},
    {"status": "pet_not_found"}, or {"status": "title_collision"} if
    new_title matches another existing task for this pet.
    """
    pet = _find_pet(owner, pet_name)
    if pet is None:
        return {"status": "pet_not_found", "pet_name": pet_name}
    if not any(t.title == title for t in pet.tasks):
        return {"status": "task_not_found", "title": title}

    fields = {
        "new_title": new_title, "duration_minutes": duration_minutes,
        "priority": priority, "description": description,
        "frequency_count": frequency_count, "frequency_unit": frequency_unit,
        "start_time": start_time,
    }
    kwargs = {k: v for k, v in fields.items() if v is not _OMITTED}

    if "new_title" in kwargs and kwargs["new_title"] != title and \
            any(t.title == kwargs["new_title"] for t in pet.tasks):
        return {"status": "title_collision", "new_title": kwargs["new_title"]}

    task = pet.edit_task(title, **kwargs)
    save_owner(owner)
    return {"status": "updated", "task": asdict(task)}


def tool_delete_task(owner: Owner, pet_name: str, title: str, confirm: bool = False) -> dict:
    """
    Remove a task by title. Destructive and irreversible — nothing is
    deleted unless confirm=True.

    Call this first with confirm left as False: it deletes nothing and
    just confirms the task exists, so the agent can ask the user to
    confirm before calling again with confirm=True.

    Returns {"status": "confirm_required"} (no change made),
    {"status": "deleted"} once confirmed, {"status": "task_not_found"},
    or {"status": "pet_not_found"}.
    """
    pet = _find_pet(owner, pet_name)
    if pet is None:
        return {"status": "pet_not_found", "pet_name": pet_name}
    if not any(t.title == title for t in pet.tasks):
        return {"status": "task_not_found", "title": title}
    if not confirm:
        return {"status": "confirm_required", "pet_name": pet_name, "title": title}
    pet.delete_task(title)
    save_owner(owner)
    return {"status": "deleted", "pet_name": pet_name, "title": title}


def tool_generate_schedule(owner: Owner, day_start: str = "09:00",
                            day_end: str = "21:00", pet_name: str | None = None) -> dict:
    """
    Build the day's schedule: assigns start times to pending tasks and
    reports conflicts. day_start/day_end are "HH:MM" — use the user's
    own day window if they gave one, otherwise the defaults apply.
    pet_name limits this to one pet's tasks; omit it for every pet.

    Preview only — matches the existing app.py behavior of not persisting
    scheduler-assigned times, so this never calls save_owner().

    Returned "conflicts" strings must be relayed to the user verbatim,
    not summarized away. Returns {"status": "ok", "tasks": [...],
    "conflicts": [...]}, or {"status": "pet_not_found"}.
    """
    if pet_name is not None and _find_pet(owner, pet_name) is None:
        return {"status": "pet_not_found", "pet_name": pet_name}
    tasks = owner.get_all_tasks(pet_name)
    result = Scheduler(tasks, day_start=day_start, day_end=day_end).schedule()
    return {
        "status": "ok",
        "tasks": [asdict(t) for t in result.tasks],
        "conflicts": result.conflicts,
    }


def tool_check_slots(owner: Owner, duration_minutes: int, day_start: str = "09:00",
                      day_end: str = "21:00", pet_name: str | None = None) -> dict:
    """
    Find open time blocks of at least duration_minutes within the day
    window, based on tasks that already have a start_time. Read-only —
    does not assign or modify any task.

    Returns {"status": "ok", "slots": [["09:00", "10:00"], ...]},
    or {"status": "pet_not_found"}.
    """
    if pet_name is not None and _find_pet(owner, pet_name) is None:
        return {"status": "pet_not_found", "pet_name": pet_name}
    tasks = owner.get_all_tasks(pet_name)
    slots = Scheduler(tasks, day_start=day_start, day_end=day_end).find_available_slots(duration_minutes)
    return {"status": "ok", "slots": [list(s) for s in slots]}
