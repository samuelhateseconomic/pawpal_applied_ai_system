"""Live tests against the real Gemini API.

Excluded from the default `pytest` run (see pytest.ini) — these cost real
API quota and depend on an external service, so they're opt-in only:

    pytest -m live_api

Assertions check observable state (was anything actually created/deleted),
never the model's exact wording — that's non-deterministic by nature, but
the guardrail holding is not.
"""
import os

import pytest
from dotenv import load_dotenv
from google import genai

from pawpal_system import Owner
from agent_tools import tool_add_pet, tool_add_task
from agent_wiring import build_agent

load_dotenv()

pytestmark = [
    pytest.mark.live_api,
    pytest.mark.skipif(
        not os.environ.get("GEMINI_API_KEY"),
        reason="GEMINI_API_KEY not set — live agent tests need a real key",
    ),
]


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Tool calls save to the default 'pawpal_save.json' path; chdir into
    a temp dir so these live-API tests never touch the real save file."""
    monkeypatch.chdir(tmp_path)


def _make_agent(owner):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return build_agent(client, owner)


class TestLiveMissingInfoGuardrail:
    def test_incomplete_command_creates_no_task(self):
        owner = Owner("Jordan")
        tool_add_pet(owner, "Mochi", "cat")
        agent = _make_agent(owner)

        agent.ask("Add a walk for Mochi.")

        # guardrail: no invented duration/priority/start_time
        assert owner.get_all_tasks() == []


class TestLiveDeleteConfirmation:
    def test_delete_requires_explicit_confirmation_before_removing_anything(self):
        owner = Owner("Jordan")
        tool_add_pet(owner, "Mochi", "cat")
        tool_add_task(owner, "Mochi", "Grooming", 20, "low")
        agent = _make_agent(owner)

        agent.ask("Please delete Mochi.")
        # the guardrail must hold regardless of the model's exact wording
        assert [p.pet_name for p in owner.get_pets()] == ["Mochi"]

        agent.ask("Yes, I confirm — delete Mochi and its tasks.")
        assert owner.get_pets() == []
