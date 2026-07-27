from pathlib import Path

import pytest
from pawpal_system import Owner, load_owner

from agent_tools import (
    tool_add_pet, tool_edit_pet, tool_remove_pet,
    tool_add_task, tool_edit_task, tool_delete_task,
    tool_generate_schedule, tool_check_slots,
)


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Every tool call under test saves to the default 'pawpal_save.json'
    path; chdir into a temp dir so tests never touch the real project's
    save file."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def owner():
    return Owner("Alice")


@pytest.fixture
def pet_with_task(owner):
    tool_add_pet(owner, "Buddy", "dog")
    tool_add_task(owner, "Buddy", "Morning Walk", 30, "high")
    return owner


# ── 1. tool_add_pet ─────────────────────────────────────────────────────────

class TestToolAddPet:
    def test_happy_creates_pet_and_persists(self, owner):
        result = tool_add_pet(owner, "Buddy", "dog", notes="loves the park")
        assert result == {
            "status": "created",
            "pet": {"pet_name": "Buddy", "species": "dog", "notes": "loves the park", "tasks": []},
        }
        assert Path("pawpal_save.json").exists()
        assert load_owner().get_pets()[0].pet_name == "Buddy"

    def test_edge_duplicate_name_reports_exists_without_overwriting(self, owner):
        tool_add_pet(owner, "Buddy", "dog", notes="original")
        result = tool_add_pet(owner, "Buddy", "cat", notes="ignored")
        assert result["status"] == "exists"
        assert result["pet"]["species"] == "dog"
        assert result["pet"]["notes"] == "original"


# ── 2. tool_edit_pet ─────────────────────────────────────────────────────────

class TestToolEditPet:
    def test_happy_renames_and_updates_species(self, owner):
        tool_add_pet(owner, "Buddy", "dog")
        result = tool_edit_pet(owner, "Buddy", new_name="Max", species="puppy")
        assert result["status"] == "updated"
        assert result["pet"]["pet_name"] == "Max"
        assert result["pet"]["species"] == "puppy"

    def test_edge_not_found(self, owner):
        result = tool_edit_pet(owner, "Ghost", new_name="Nope")
        assert result == {"status": "not_found", "pet_name": "Ghost"}

    def test_edge_name_collision_leaves_pet_unmodified(self, owner):
        tool_add_pet(owner, "Buddy", "dog")
        tool_add_pet(owner, "Whiskers", "cat")
        result = tool_edit_pet(owner, "Buddy", new_name="Whiskers")
        assert result == {"status": "name_collision", "new_name": "Whiskers"}
        assert owner.get_pets()[0].pet_name == "Buddy"


# ── 3. tool_remove_pet ───────────────────────────────────────────────────────

class TestToolRemovePet:
    def test_happy_removes_pet_and_reports_task_count(self, pet_with_task):
        result = tool_remove_pet(pet_with_task, "Buddy")
        assert result == {"status": "removed", "pet_name": "Buddy", "deleted_task_count": 1}
        assert pet_with_task.get_pets() == []

    def test_edge_not_found(self, owner):
        result = tool_remove_pet(owner, "Ghost")
        assert result == {"status": "not_found", "pet_name": "Ghost"}


# ── 4. tool_add_task ─────────────────────────────────────────────────────────

class TestToolAddTask:
    def test_happy_adds_task(self, owner):
        tool_add_pet(owner, "Buddy", "dog")
        result = tool_add_task(owner, "Buddy", "Feeding", 10, "high", start_time="08:00")
        assert result["status"] == "created"
        assert result["task"]["title"] == "Feeding"
        assert result["task"]["pet_name"] == "Buddy"
        assert result["task"]["start_time"] == "08:00"

    def test_edge_pet_not_found(self, owner):
        result = tool_add_task(owner, "Ghost", "Feeding", 10, "high")
        assert result == {"status": "pet_not_found", "pet_name": "Ghost"}

    def test_edge_duplicate_title(self, pet_with_task):
        result = tool_add_task(pet_with_task, "Buddy", "Morning Walk", 20, "low")
        assert result == {"status": "duplicate_title", "title": "Morning Walk"}


# ── 5. tool_edit_task ────────────────────────────────────────────────────────

class TestToolEditTask:
    def test_happy_updates_only_given_fields(self, pet_with_task):
        result = tool_edit_task(pet_with_task, "Buddy", "Morning Walk", priority="low")
        assert result["status"] == "updated"
        assert result["task"]["priority"] == "low"
        assert result["task"]["duration_minutes"] == 30  # untouched

    def test_happy_explicit_none_unpins_start_time(self, owner):
        tool_add_pet(owner, "Buddy", "dog")
        tool_add_task(owner, "Buddy", "Vet visit", 60, "high", start_time="10:00")
        result = tool_edit_task(owner, "Buddy", "Vet visit", start_time=None)
        assert result["task"]["start_time"] is None

    def test_edge_pet_not_found(self, owner):
        result = tool_edit_task(owner, "Ghost", "Anything", priority="low")
        assert result == {"status": "pet_not_found", "pet_name": "Ghost"}

    def test_edge_task_not_found(self, pet_with_task):
        result = tool_edit_task(pet_with_task, "Buddy", "Ghost Task", priority="low")
        assert result == {"status": "task_not_found", "title": "Ghost Task"}

    def test_edge_title_collision_leaves_task_unmodified(self, owner):
        tool_add_pet(owner, "Buddy", "dog")
        tool_add_task(owner, "Buddy", "Feeding", 10, "high")
        tool_add_task(owner, "Buddy", "Walk", 30, "high")
        result = tool_edit_task(owner, "Buddy", "Feeding", new_title="Walk")
        assert result == {"status": "title_collision", "new_title": "Walk"}


# ── 6. tool_delete_task ──────────────────────────────────────────────────────

class TestToolDeleteTask:
    def test_happy_deletes_task(self, pet_with_task):
        result = tool_delete_task(pet_with_task, "Buddy", "Morning Walk")
        assert result == {"status": "deleted", "pet_name": "Buddy", "title": "Morning Walk"}
        assert pet_with_task.get_all_tasks() == []

    def test_edge_pet_not_found(self, owner):
        result = tool_delete_task(owner, "Ghost", "Anything")
        assert result == {"status": "pet_not_found", "pet_name": "Ghost"}

    def test_edge_task_not_found(self, pet_with_task):
        result = tool_delete_task(pet_with_task, "Buddy", "Ghost Task")
        assert result == {"status": "task_not_found", "title": "Ghost Task"}


# ── 7. tool_generate_schedule ────────────────────────────────────────────────

class TestToolGenerateSchedule:
    def test_happy_schedules_pending_tasks(self, pet_with_task):
        result = tool_generate_schedule(pet_with_task)
        assert result["status"] == "ok"
        assert result["tasks"][0]["title"] == "Morning Walk"
        assert result["conflicts"] == []

    def test_happy_relays_conflicts_verbatim(self, owner):
        tool_add_pet(owner, "Buddy", "dog")
        tool_add_task(owner, "Buddy", "Walk", 30, "high", start_time="09:00")
        tool_add_task(owner, "Buddy", "Grooming", 20, "low", start_time="09:00")
        result = tool_generate_schedule(owner)
        assert result["conflicts"] != []
        assert "Walk" in result["conflicts"][0]

    def test_happy_does_not_persist(self, pet_with_task):
        tool_generate_schedule(pet_with_task, day_start="10:00")
        reloaded = load_owner()
        # assigned start_time from the preview must not have been saved
        assert reloaded.get_all_tasks()[0].start_time is None

    def test_edge_pet_not_found(self, owner):
        result = tool_generate_schedule(owner, pet_name="Ghost")
        assert result == {"status": "pet_not_found", "pet_name": "Ghost"}


# ── 8. tool_check_slots ──────────────────────────────────────────────────────

class TestToolCheckSlots:
    def test_happy_finds_open_block(self, pet_with_task):
        result = tool_check_slots(pet_with_task, 30)
        assert result["status"] == "ok"
        assert result["slots"] == [["09:00", "21:00"]]  # no anchored task yet -> whole day is open

        tool_add_task(pet_with_task, "Buddy", "Vet visit", 60, "high", start_time="12:00")
        result = tool_check_slots(pet_with_task, 30)
        assert ["09:00", "12:00"] in result["slots"]

    def test_edge_pet_not_found(self, owner):
        result = tool_check_slots(owner, 30, pet_name="Ghost")
        assert result == {"status": "pet_not_found", "pet_name": "Ghost"}
