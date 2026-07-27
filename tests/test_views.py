from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from pawpal_system import Owner, load_owner

VIEWS_DIR = Path(__file__).resolve().parent.parent / "views"


def view(name: str) -> str:
    """Absolute path to a views/*.py file — AppTest.from_file() resolves
    relative paths against the current cwd, which the isolated_cwd fixture
    below deliberately chdirs away from the project root."""
    return str(VIEWS_DIR / name)


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Every page save_owner()'s to the default 'pawpal_save.json' path;
    chdir into a temp dir so tests never touch the real project's save file."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def owner():
    return Owner("Alice")


@pytest.fixture
def owner_with_pet(owner):
    owner.add_pet("Buddy", "dog")
    return owner


# ── views/home.py ────────────────────────────────────────────────────────────

class TestHomePage:
    def test_happy_creates_owner_when_none_saved(self):
        at = AppTest.from_file(view("home.py"))
        at.run()
        assert not at.exception

        at.text_input[0].set_value("Jordan")
        at.button(key="create_owner_btn").click().run()

        assert not at.exception
        assert at.session_state["owner"].owner_name == "Jordan"
        assert load_owner().owner_name == "Jordan"

    def test_edge_no_api_key_shows_warning_not_crash(self, owner, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        at = AppTest.from_file(view("home.py"))
        at.session_state["owner"] = owner
        at.run()
        assert not at.exception
        assert any("GEMINI_API_KEY" in w.value for w in at.warning)

    def test_happy_renames_owner_without_new_identity(self, owner, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        at = AppTest.from_file(view("home.py"))
        at.session_state["owner"] = owner
        at.run()

        at.text_input(key="rename_owner_input").set_value("Jordan Lee")
        at.button(key="save_owner_name_btn").click().run()

        assert not at.exception
        assert at.session_state["owner"] is owner  # renamed in place, not replaced
        assert owner.owner_name == "Jordan Lee"
        assert load_owner().owner_name == "Jordan Lee"


# ── views/pets.py ────────────────────────────────────────────────────────────

class TestPetsPage:
    def test_happy_add_pet(self, owner):
        at = AppTest.from_file(view("pets.py"))
        at.session_state["owner"] = owner
        at.run()
        assert not at.exception

        at.text_input(key="new_pet_name").set_value("Mochi")
        at.selectbox(key="new_species").set_value("cat")
        at.button(key="add_pet_btn").click().run()

        assert not at.exception
        assert [p.pet_name for p in owner.get_pets()] == ["Mochi"]

    def test_edge_duplicate_pet_name_warns(self, owner_with_pet):
        at = AppTest.from_file(view("pets.py"))
        at.session_state["owner"] = owner_with_pet
        at.run()

        at.text_input(key="new_pet_name").set_value("Buddy")
        at.button(key="add_pet_btn").click().run()

        assert not at.exception
        assert any("already exists" in w.value for w in at.warning)
        assert len(owner_with_pet.get_pets()) == 1

    def test_happy_edit_pet_rename(self, owner_with_pet):
        at = AppTest.from_file(view("pets.py"))
        at.session_state["owner"] = owner_with_pet
        at.run()

        at.text_input(key="edit_pet_name").set_value("Max")
        at.button(key="save_pet_changes_btn").click().run()

        assert not at.exception
        assert owner_with_pet.get_pets()[0].pet_name == "Max"

    def test_happy_delete_pet_requires_two_clicks(self, owner_with_pet):
        owner_with_pet.get_pets()[0].add_task("Walk", 20, "high")
        at = AppTest.from_file(view("pets.py"))
        at.session_state["owner"] = owner_with_pet
        at.run()

        # first click only asks for confirmation, doesn't delete yet
        at.button(key="delete_pet_btn").click().run()
        assert not at.exception
        assert len(owner_with_pet.get_pets()) == 1
        assert any("Click again to confirm" in e.value for e in at.error)

        # second click actually deletes
        at.button(key="confirm_delete_pet_btn").click().run()
        assert not at.exception
        assert owner_with_pet.get_pets() == []


# ── views/tasks.py ───────────────────────────────────────────────────────────

class TestTasksPage:
    def test_happy_add_task(self, owner_with_pet):
        at = AppTest.from_file(view("tasks.py"))
        at.session_state["owner"] = owner_with_pet
        at.run()
        assert not at.exception

        at.text_input(key="new_task_title").set_value("Feeding")
        at.number_input(key="new_task_duration").set_value(10)
        at.button(key="add_task_btn").click().run()

        assert not at.exception
        pet = owner_with_pet.get_pets()[0]
        assert [t.title for t in pet.tasks] == ["Feeding"]

    def test_happy_edit_task_updates_priority(self, owner_with_pet):
        pet = owner_with_pet.get_pets()[0]
        pet.add_task("Walk", 30, "high")
        at = AppTest.from_file(view("tasks.py"))
        at.session_state["owner"] = owner_with_pet
        at.run()

        at.selectbox(key="edit_task_priority").set_value("low")
        at.button(key="save_task_changes_btn").click().run()

        assert not at.exception
        assert pet.tasks[0].priority == "low"

    def test_happy_delete_task_requires_two_clicks(self, owner_with_pet):
        pet = owner_with_pet.get_pets()[0]
        pet.add_task("Walk", 30, "high")
        at = AppTest.from_file(view("tasks.py"))
        at.session_state["owner"] = owner_with_pet
        at.run()

        at.button(key="delete_task_btn").click().run()
        assert not at.exception
        assert len(pet.tasks) == 1

        at.button(key="confirm_task_delete_btn").click().run()
        assert not at.exception
        assert pet.tasks == []


# ── views/schedule.py ────────────────────────────────────────────────────────

class TestSchedulePage:
    def test_happy_generates_schedule(self, owner_with_pet):
        pet = owner_with_pet.get_pets()[0]
        pet.add_task("Walk", 30, "high")
        at = AppTest.from_file(view("schedule.py"))
        at.session_state["owner"] = owner_with_pet
        at.run()

        at.button(key="generate_schedule_btn").click().run()

        assert not at.exception
        assert any("Scheduled Tasks" in m.value for m in at.markdown)

    def test_edge_no_tasks_shows_warning_not_crash(self, owner_with_pet):
        at = AppTest.from_file(view("schedule.py"))
        at.session_state["owner"] = owner_with_pet
        at.run()
        assert not at.exception
        assert any("at least one task" in w.value for w in at.warning)
