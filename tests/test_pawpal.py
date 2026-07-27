import json
from datetime import date, timedelta

import pytest
from pawpal_system import Owner, Pet, Task, Scheduler, save_owner, load_owner, _active_days


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def owner():
    return Owner("Alice")


@pytest.fixture
def pet_with_tasks(owner):
    pet = owner.add_pet("Buddy", "dog")
    pet.add_task("Morning Walk", 30, "high", start_time="08:00")
    pet.add_task("Feeding", 15, "high")
    pet.add_task("Playtime", 20, "medium")
    return pet


# ── Original tests ────────────────────────────────────────────────────────────

def test_mark_complete_changes_status():
    task = Task(title="Morning walk", duration_minutes=30, priority="high")
    task.mark_complete()
    assert task.completion_status == "complete"


def test_add_task_increases_pet_task_count():
    pet = Pet(pet_name="Mochi", species="cat")
    pet.add_task("Feeding", 10, "high")
    assert len(pet.get_tasks()) == 1


# ── 1. Add Pets ───────────────────────────────────────────────────────────────

class TestAddPets:
    def test_happy_add_single_pet(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        assert pet.pet_name == "Buddy"
        assert pet.species == "dog"
        assert len(owner.get_pets()) == 1

    def test_happy_add_multiple_pets(self, owner):
        owner.add_pet("Buddy", "dog")
        owner.add_pet("Whiskers", "cat")
        names = [p.pet_name for p in owner.get_pets()]
        assert names == ["Buddy", "Whiskers"]

    def test_edge_duplicate_name_returns_existing(self, owner):
        first = owner.add_pet("Buddy", "dog")
        second = owner.add_pet("Buddy", "cat")  # different species, same name
        assert first is second                   # same object returned
        assert len(owner.get_pets()) == 1        # not added twice
        assert first.species == "dog"            # original species unchanged

    def test_edge_new_pet_has_no_tasks(self, owner):
        pet = owner.add_pet("Goldie", "fish")
        assert pet.get_tasks() == []


# ── 2. Add Tasks With Time ────────────────────────────────────────────────────

class TestAddTasksWithTime:
    def test_happy_add_task_with_start_time(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        task = pet.add_task("Morning Walk", 30, "high", start_time="08:00")
        assert task is not None
        assert task.start_time == "08:00"
        assert task.duration_minutes == 30
        assert task.priority == "high"
        assert task.pet_name == "Buddy"

    def test_happy_add_task_without_time(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        task = pet.add_task("Feeding", 15, "medium")
        assert task is not None
        assert task.start_time is None  # floating; Scheduler will assign it

    def test_happy_multiple_tasks_stored(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Morning Walk", 30, "high", start_time="08:00")
        pet.add_task("Feeding", 15, "medium")
        assert len(pet.get_tasks()) == 2

    def test_edge_duplicate_title_returns_none(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Morning Walk", 30, "high")
        result = pet.add_task("Morning Walk", 45, "low")  # same title
        assert result is None
        assert len(pet.get_tasks()) == 1  # not added twice

    def test_edge_pet_name_set_automatically(self, owner):
        pet = owner.add_pet("Whiskers", "cat")
        task = pet.add_task("Grooming", 20, "low")
        assert task.pet_name == "Whiskers"


# ── 3. Schedule Tasks ─────────────────────────────────────────────────────────

class TestScheduleTasks:
    def test_happy_floating_tasks_get_times(self, pet_with_tasks):
        tasks = [t for t in pet_with_tasks.get_tasks() if t.start_time is None]
        scheduler = Scheduler(tasks)
        result = scheduler.schedule()
        assert all(t.start_time is not None for t in result.tasks)

    def test_happy_anchor_task_keeps_its_time(self, pet_with_tasks):
        scheduler = Scheduler(pet_with_tasks.get_tasks())
        result = scheduler.schedule()
        walk = next(t for t in result.tasks if t.title == "Morning Walk")
        assert walk.start_time == "08:00"

    def test_happy_tasks_sorted_by_time(self, pet_with_tasks):
        scheduler = Scheduler(pet_with_tasks.get_tasks())
        result = scheduler.schedule()
        times = [t.start_time for t in result.tasks]
        assert times == sorted(times)

    def test_happy_no_conflicts_when_tasks_fit(self):
        tasks = [
            Task("Walk", 30, "high",   start_time="09:00", pet_name="Buddy"),
            Task("Feed", 15, "medium", start_time="10:00", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks)
        result = scheduler.schedule()
        assert result.conflicts == []

    def test_edge_no_tasks_returns_empty(self):
        scheduler = Scheduler([])
        result = scheduler.schedule()
        assert result.tasks == []
        assert result.conflicts == []

    def test_edge_two_tasks_exact_same_time_conflict(self):
        tasks = [
            Task("Walk", 30, "high",   start_time="09:00", pet_name="Buddy"),
            Task("Bath", 30, "medium", start_time="09:00", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks)
        result = scheduler.schedule()
        assert any("Walk" in c and "Bath" in c for c in result.conflicts)

    def test_happy_different_pets_same_time_not_a_conflict(self):
        # Two pets doing an activity together (e.g. a joint walk) is allowed
        # on purpose — only the same pet double-booked should be flagged.
        tasks = [
            Task("Walk", 30, "high", start_time="09:00", pet_name="Buddy"),
            Task("Walk", 30, "high", start_time="09:00", pet_name="Whiskers"),
        ]
        scheduler = Scheduler(tasks)
        result = scheduler.schedule()
        assert result.conflicts == []

    def test_edge_overflow_reported_when_tasks_exceed_window(self):
        tasks = [Task(f"Task{i}", 120, "low") for i in range(6)]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="10:00")
        result = scheduler.schedule()
        assert any("exceed" in c for c in result.conflicts)


# ── 4. Find Available Slots ───────────────────────────────────────────────────

class TestFindAvailableSlots:
    def test_happy_gap_between_anchors_found(self):
        tasks = [
            Task("Walk", 60, "high", start_time="09:00", pet_name="Buddy"),
            Task("Vet",  60, "high", start_time="16:00", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(30)
        assert ("10:00", "16:00") in slots

    def test_happy_empty_day_returns_full_window(self):
        scheduler = Scheduler([], day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(30)
        assert slots == [("09:00", "21:00")]

    def test_edge_slot_too_small_is_excluded(self):
        tasks = [
            Task("Walk", 60, "high", start_time="09:00", pet_name="Buddy"),
            Task("Vet",  60, "high", start_time="09:20", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(30)
        assert all(s[0] != "09:00" for s in slots)  # the tiny overlap gap isn't offered

    def test_edge_overlapping_anchors_merged_before_gap_check(self):
        tasks = [
            Task("Walk", 60, "high", start_time="09:00", pet_name="Buddy"),
            Task("Bath", 60, "high", start_time="09:30", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="12:00")
        slots = scheduler.find_available_slots(30)
        assert slots == [("10:30", "12:00")]

    def test_edge_floating_tasks_without_time_are_ignored(self):
        tasks = [Task("Feeding", 15, "medium", pet_name="Buddy")]  # no start_time yet
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(30)
        assert slots == [("09:00", "21:00")]

    def test_edge_no_slot_big_enough_returns_empty(self):
        tasks = [Task("Busy", 700, "high", start_time="09:00", pet_name="Buddy")]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(60)
        assert slots == []

    def test_edge_slot_exactly_matching_duration_is_included(self):
        tasks = [
            Task("Walk", 60, "high", start_time="09:00", pet_name="Buddy"),
            Task("Vet",  60, "high", start_time="10:30", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(30)  # gap is exactly 30 min
        assert ("10:00", "10:30") in slots

    def test_edge_completed_tasks_are_ignored(self):
        tasks = [
            Task("Old Walk", 60, "high", start_time="09:00", pet_name="Buddy",
                 completion_status="complete"),
        ]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(30)
        assert slots == [("09:00", "21:00")]  # completed task's time is freed up

    def test_edge_anchor_at_day_start_has_no_leading_gap(self):
        tasks = [Task("Walk", 60, "high", start_time="09:00", pet_name="Buddy")]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="10:30")
        slots = scheduler.find_available_slots(30)
        assert slots == [("10:00", "10:30")]  # nothing before day_start

    def test_edge_anchor_ending_exactly_at_day_end_has_no_trailing_gap(self):
        tasks = [Task("Walk", 60, "high", start_time="20:00", pet_name="Buddy")]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(30)
        assert all(end != "21:00" for _, end in slots) or slots == [("09:00", "20:00")]

    def test_happy_multiple_separate_gaps_all_returned(self):
        tasks = [
            Task("Walk", 30, "high", start_time="10:00", pet_name="Buddy"),
            Task("Vet",  30, "high", start_time="14:00", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="16:00")
        slots = scheduler.find_available_slots(30)
        assert slots == [("09:00", "10:00"), ("10:30", "14:00"), ("14:30", "16:00")]

    def test_edge_input_order_does_not_affect_result(self):
        tasks = [
            Task("Vet",  60, "high", start_time="16:00", pet_name="Buddy"),
            Task("Walk", 60, "high", start_time="09:00", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        slots = scheduler.find_available_slots(30)
        assert ("10:00", "16:00") in slots

    def test_happy_default_day_window_used_when_not_specified(self):
        tasks = [Task("Walk", 30, "high", start_time="10:00", pet_name="Buddy")]
        scheduler = Scheduler(tasks)  # default day_start=09:00, day_end=21:00
        slots = scheduler.find_available_slots(30)
        assert ("09:00", "10:00") in slots
        assert ("10:30", "21:00") in slots


# ── 5. Explain the Schedule ───────────────────────────────────────────────────

class TestExplainSchedule:
    def test_happy_output_contains_task_titles(self, pet_with_tasks):
        scheduler = Scheduler(pet_with_tasks.get_tasks())
        output = scheduler.explain_reasoning()
        assert "Morning Walk" in output
        assert "Feeding" in output
        assert "Playtime" in output

    def test_happy_no_conflicts_message_when_clean(self):
        tasks = [
            Task("Walk", 30, "high",   start_time="09:00", pet_name="Buddy"),
            Task("Feed", 15, "medium", start_time="10:00", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks)
        output = scheduler.explain_reasoning()
        assert "No conflicts detected." in output

    def test_happy_conflict_section_shown_when_overlap(self):
        tasks = [
            Task("Walk", 60, "high",   start_time="09:00", pet_name="Buddy"),
            Task("Bath", 60, "medium", start_time="09:00", pet_name="Buddy"),
        ]
        scheduler = Scheduler(tasks)
        output = scheduler.explain_reasoning()
        assert "Conflicts detected:" in output

    def test_edge_no_tasks_returns_no_pending_message(self):
        scheduler = Scheduler([])
        output = scheduler.explain_reasoning()
        assert output == "No pending tasks to schedule."

    def test_edge_pet_with_only_completed_tasks_not_scheduled(self):
        task = Task("Old Walk", 30, "high", start_time="09:00", pet_name="Buddy",
                    completion_status="complete")
        scheduler = Scheduler([task])
        output = scheduler.explain_reasoning()
        assert output == "No pending tasks to schedule."


# ── 6. Pet Notes ──────────────────────────────────────────────────────────────

class TestPetNotes:
    def test_happy_default_notes_is_empty(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        assert pet.notes == ""

    def test_happy_edit_pet_sets_notes(self, owner):
        owner.add_pet("Buddy", "dog")
        pet = owner.edit_pet("Buddy", notes="Loves other dogs, good with cats")
        assert pet.notes == "Loves other dogs, good with cats"

    def test_happy_notes_round_trip_through_save_and_load(self, owner, tmp_path):
        owner.add_pet("Buddy", "dog")
        owner.edit_pet("Buddy", notes="Needs a friend for walks")
        path = str(tmp_path / "save.json")
        save_owner(owner, path)
        loaded = load_owner(path)
        assert loaded.get_pets()[0].notes == "Needs a friend for walks"


# ── 7. Edit Pet ───────────────────────────────────────────────────────────────

class TestEditPet:
    def test_happy_rename_cascades_to_tasks(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Walk", 30, "high")
        owner.edit_pet("Buddy", new_name="Max")
        assert owner.get_pets()[0].pet_name == "Max"
        assert all(t.pet_name == "Max" for t in pet.get_tasks())

    def test_edge_rename_collision_rejected(self, owner):
        owner.add_pet("Buddy", "dog")
        owner.add_pet("Whiskers", "cat")
        result = owner.edit_pet("Buddy", new_name="Whiskers")
        assert result is None
        assert owner.get_pets()[0].pet_name == "Buddy"  # unmodified

    def test_happy_species_only_edit(self, owner):
        owner.add_pet("Goldie", "fish")
        pet = owner.edit_pet("Goldie", species="axolotl")
        assert pet.species == "axolotl"
        assert pet.pet_name == "Goldie"  # unchanged

    def test_happy_notes_only_edit_leaves_other_fields(self, owner):
        owner.add_pet("Buddy", "dog")
        pet = owner.edit_pet("Buddy", notes="Shy around strangers")
        assert pet.notes == "Shy around strangers"
        assert pet.pet_name == "Buddy"
        assert pet.species == "dog"

    def test_edge_edit_nonexistent_pet_returns_none(self, owner):
        assert owner.edit_pet("Ghost", species="cat") is None


# ── 8. Edit Task ──────────────────────────────────────────────────────────────

class TestEditTask:
    def test_happy_edit_multiple_fields(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Walk", 30, "high")
        task = pet.edit_task("Walk", duration_minutes=45, priority="low", description="slower pace")
        assert task.duration_minutes == 45
        assert task.priority == "low"
        assert task.description == "slower pace"

    def test_happy_rename_task(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Walk", 30, "high")
        task = pet.edit_task("Walk", new_title="Evening Walk")
        assert task.title == "Evening Walk"

    def test_edge_rename_collision_rejected(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Walk", 30, "high")
        pet.add_task("Feed", 15, "medium")
        result = pet.edit_task("Walk", new_title="Feed")
        assert result is None
        assert any(t.title == "Walk" for t in pet.get_tasks())  # unmodified

    def test_happy_explicit_none_unpins_anchor(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Walk", 30, "high", start_time="08:00")
        task = pet.edit_task("Walk", start_time=None)
        assert task.start_time is None

    def test_edge_no_fields_supplied_leaves_task_unchanged(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Walk", 30, "high", start_time="08:00")
        before = pet.get_tasks()[0]
        task = pet.edit_task("Walk")
        assert task.duration_minutes == before.duration_minutes
        assert task.start_time == "08:00"

    def test_edge_edit_nonexistent_task_returns_none(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        assert pet.edit_task("Ghost", priority="low") is None


# ── 9. Delete Task ────────────────────────────────────────────────────────────

class TestDeleteTask:
    def test_happy_delete_removes_task(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Walk", 30, "high")
        result = pet.delete_task("Walk")
        assert result is True
        assert pet.get_tasks() == []

    def test_edge_delete_nonexistent_returns_false(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        assert pet.delete_task("Ghost") is False

    def test_edge_title_freed_after_delete(self, owner):
        pet = owner.add_pet("Buddy", "dog")
        pet.add_task("Walk", 30, "high")
        pet.delete_task("Walk")
        result = pet.add_task("Walk", 20, "medium")
        assert result is not None
        assert len(pet.get_tasks()) == 1


# ── 10. Frequency Defaults & Recurrence ──────────────────────────────────────

class TestFrequencyDefaults:
    def test_happy_default_is_once_per_day(self):
        task = Task("Feed", 10, "high")
        assert task.frequency_count == 1
        assert task.frequency_unit == "day"

    def test_happy_frequency_label_formats(self):
        assert Task("Feed", 10, "high", frequency_count=2, frequency_unit="day").frequency_label() == "2x/day"
        assert Task("Vet", 60, "high", frequency_unit="as_needed").frequency_label() == "as needed"

    def test_happy_next_occurrence_day(self):
        task = Task("Feed", 10, "high", frequency_unit="day")
        nxt = task.next_occurrence()
        expected = date.today() + timedelta(days=1)
        assert nxt.due_date == str(expected)
        assert nxt.frequency_unit == "day"

    def test_happy_next_occurrence_week(self):
        task = Task("Groom", 20, "low", frequency_count=1, frequency_unit="week")
        nxt = task.next_occurrence()
        expected = date.today() + timedelta(weeks=1)
        assert nxt.due_date == str(expected)

    def test_happy_next_occurrence_month(self):
        task = Task("Nail trim", 15, "low", frequency_unit="month")
        nxt = task.next_occurrence()
        expected = date.today() + timedelta(days=30)
        assert nxt.due_date == str(expected)

    def test_edge_next_occurrence_as_needed_returns_none(self):
        task = Task("Vet visit", 60, "high", frequency_unit="as_needed")
        assert task.next_occurrence() is None

    def test_happy_next_occurrence_carries_frequency_forward(self):
        task = Task("Groom", 20, "low", frequency_count=3, frequency_unit="week")
        nxt = task.next_occurrence()
        assert nxt.frequency_count == 3
        assert nxt.frequency_unit == "week"


# ── 11. Legacy Save-File Migration ───────────────────────────────────────────

class TestLegacyLoadMigration:
    def _write(self, tmp_path, data):
        path = tmp_path / "legacy.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_happy_legacy_daily_migrates(self, tmp_path):
        path = self._write(tmp_path, {
            "owner_name": "Jordan",
            "pets": [{
                "pet_name": "Mochi", "species": "cat",
                "tasks": [{
                    "title": "Feed", "duration_minutes": 10, "priority": "high",
                    "description": "", "frequency": "daily",
                    "completion_status": "pending", "start_time": None,
                    "due_date": None, "pet_name": "Mochi",
                }],
            }],
        })
        owner = load_owner(path)
        task = owner.get_all_tasks()[0]
        assert task.frequency_count == 1
        assert task.frequency_unit == "day"

    def test_happy_legacy_weekly_and_as_needed_migrate(self, tmp_path):
        path = self._write(tmp_path, {
            "owner_name": "Jordan",
            "pets": [{
                "pet_name": "Mochi", "species": "cat", "tasks": [
                    {"title": "Groom", "duration_minutes": 20, "priority": "low",
                     "description": "", "frequency": "weekly",
                     "completion_status": "pending", "start_time": None,
                     "due_date": None, "pet_name": "Mochi"},
                    {"title": "Vet", "duration_minutes": 60, "priority": "high",
                     "description": "", "frequency": "as_needed",
                     "completion_status": "pending", "start_time": None,
                     "due_date": None, "pet_name": "Mochi"},
                ],
            }],
        })
        owner = load_owner(path)
        groom, vet = owner.get_all_tasks()
        assert (groom.frequency_count, groom.frequency_unit) == (1, "week")
        assert vet.frequency_unit == "as_needed"

    def test_happy_legacy_pet_defaults_notes_to_empty(self, tmp_path):
        path = self._write(tmp_path, {
            "owner_name": "Jordan",
            "pets": [{"pet_name": "Mochi", "species": "cat", "tasks": []}],
        })
        owner = load_owner(path)
        assert owner.get_pets()[0].notes == ""

    def test_happy_new_format_file_passes_through_unchanged(self, tmp_path):
        path = self._write(tmp_path, {
            "owner_name": "Jordan",
            "pets": [{
                "pet_name": "Mochi", "species": "cat", "notes": "friendly",
                "tasks": [{
                    "title": "Feed", "duration_minutes": 10, "priority": "high",
                    "description": "", "frequency_count": 2, "frequency_unit": "day",
                    "completion_status": "pending", "start_time": None,
                    "due_date": None, "pet_name": "Mochi",
                }],
            }],
        })
        owner = load_owner(path)
        pet = owner.get_pets()[0]
        assert pet.notes == "friendly"
        task = pet.get_tasks()[0]
        assert task.frequency_count == 2
        assert task.frequency_unit == "day"

    def test_happy_save_then_load_round_trip_preserves_new_fields(self, owner, tmp_path):
        pet = owner.add_pet("Mochi", "cat")
        owner.edit_pet("Mochi", notes="Loves company")
        pet.add_task("Feed", 10, "high", frequency_count=2, frequency_unit="day")
        path = str(tmp_path / "save.json")
        save_owner(owner, path)
        loaded = load_owner(path)
        loaded_pet = loaded.get_pets()[0]
        assert loaded_pet.notes == "Loves company"
        task = loaded_pet.get_tasks()[0]
        assert task.frequency_count == 2
        assert task.frequency_unit == "day"


# ── 12. Same-Day Multiplicity ─────────────────────────────────────────────────

class TestSameDayMultiplicity:
    def test_happy_two_per_day_gets_two_distinct_times(self, owner):
        pet = owner.add_pet("Mochi", "cat")
        pet.add_task("Feed", 10, "high", frequency_count=2, frequency_unit="day")
        scheduler = Scheduler(pet.get_tasks())
        result = scheduler.schedule()
        feed_occurrences = [t for t in result.tasks if t.title.startswith("Feed")]
        assert len(feed_occurrences) == 2
        times = {t.start_time for t in feed_occurrences}
        assert len(times) == 2  # distinct, non-overlapping start times

    def test_happy_original_task_not_mutated_by_expansion(self, owner):
        pet = owner.add_pet("Mochi", "cat")
        pet.add_task("Feed", 10, "high", frequency_count=2, frequency_unit="day")
        scheduler = Scheduler(pet.get_tasks())
        scheduler.schedule()
        original = pet.get_tasks()[0]
        assert original.frequency_count == 2
        assert original.start_time is None

    def test_happy_pinned_multi_count_keeps_first_occurrence_time(self, owner):
        pet = owner.add_pet("Mochi", "cat")
        pet.add_task("Feed", 10, "high", frequency_count=2, frequency_unit="day", start_time="09:00")
        scheduler = Scheduler(pet.get_tasks())
        result = scheduler.schedule()
        first = next(t for t in result.tasks if t.title == "Feed (1/2)")
        assert first.start_time == "09:00"

    def test_edge_double_schedule_call_is_idempotent(self, owner):
        pet = owner.add_pet("Mochi", "cat")
        pet.add_task("Feed", 10, "high", frequency_count=2, frequency_unit="day")
        scheduler = Scheduler(pet.get_tasks())
        first_result = scheduler.schedule()
        second_result = scheduler.schedule()
        assert (sorted(t.title for t in first_result.tasks)
                == sorted(t.title for t in second_result.tasks))


# ── 13. Week/Month Day Selection ──────────────────────────────────────────────

class TestWeekMonthDaySelection:
    def test_happy_distinct_indices_for_count(self):
        days = _active_days(7, 3)
        assert len(days) == 3
        assert all(0 <= d < 7 for d in days)

    def test_edge_count_one_returns_day_zero(self):
        assert _active_days(7, 1) == {0}

    def test_edge_count_at_least_period_length_returns_all_days(self):
        assert _active_days(7, 10) == set(range(7))

    def test_edge_count_zero_returns_empty(self):
        assert _active_days(7, 0) == set()

    def test_happy_week_task_appears_on_exactly_count_days(self):
        task = Task("Groom", 20, "low", frequency_count=3, frequency_unit="week")
        scheduler = Scheduler([task])
        appearances = sum(
            1 for d in range(7) if scheduler.filter_recurring(day_of_week=d)
        )
        assert appearances == 3

    def test_happy_month_task_uses_day_of_month(self):
        task = Task("Nail trim", 15, "low", frequency_count=2, frequency_unit="month")
        scheduler = Scheduler([task])
        appearances = sum(
            1 for d in range(1, 31) if scheduler.filter_recurring(day_of_month=d)
        )
        assert appearances == 2

    def test_edge_as_needed_never_appears(self):
        task = Task("Vet visit", 60, "high", frequency_unit="as_needed")
        scheduler = Scheduler([task])
        assert all(
            not scheduler.filter_recurring(day_of_week=d) for d in range(7)
        )


# ── 14. Out-of-Window Detection ───────────────────────────────────────────────

class TestOutOfWindowDetection:
    def test_happy_anchor_ending_after_day_end_flagged(self):
        tasks = [Task("Late walk", 20, "high", start_time="21:00", pet_name="Mochi")]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        result = scheduler.schedule()
        assert any("Late walk" in c and "runs past" in c for c in result.conflicts)

    def test_happy_anchor_starting_before_day_start_flagged(self):
        tasks = [Task("Early walk", 25, "high", start_time="08:00", pet_name="Moch")]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        result = scheduler.schedule()
        assert any("Early walk" in c and "starts before" in c for c in result.conflicts)

    def test_happy_task_fully_inside_window_not_flagged(self):
        tasks = [Task("Walk", 20, "high", start_time="10:00", pet_name="Buddy")]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        result = scheduler.schedule()
        assert not any("OUT OF WINDOW" in c for c in result.conflicts)

    def test_edge_task_ending_exactly_at_day_end_not_flagged(self):
        tasks = [Task("Walk", 60, "high", start_time="20:00", pet_name="Buddy")]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        result = scheduler.schedule()
        assert not any("OUT OF WINDOW" in c for c in result.conflicts)

    def test_edge_task_starting_exactly_at_day_start_not_flagged(self):
        tasks = [Task("Walk", 60, "high", start_time="09:00", pet_name="Buddy")]
        scheduler = Scheduler(tasks, day_start="09:00", day_end="21:00")
        result = scheduler.schedule()
        assert not any("OUT OF WINDOW" in c for c in result.conflicts)
