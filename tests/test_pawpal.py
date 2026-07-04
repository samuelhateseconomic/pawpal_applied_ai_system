import pytest
from pawpal_system import Owner, Pet, Task, Scheduler


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
