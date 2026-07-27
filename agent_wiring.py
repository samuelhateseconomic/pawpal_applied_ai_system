"""Standalone Gemini agent wiring for PawPal+ (Phase 3).

Takes a user command string, lets Gemini pick a tool from agent_tools.py
and call it, then prints which tool ran and the agent's reply. No
Streamlit involved yet — run this directly to test the agent loop:

    python agent_wiring.py
"""
import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from pawpal_system import Owner, load_owner, save_owner
import agent_tools as tools

PRIMARY_MODEL = "gemini-3.1-flash-lite"    # 15 RPM free tier
FALLBACK_MODEL = "gemini-3.5-flash-lite"   # used if PRIMARY_MODEL's quota runs out

SYSTEM_INSTRUCTION = """\
You are the PawPal+ assistant. You help an owner manage their pets' \
tasks and daily schedule by calling the tools available to you.

Strict rules:
1. Never invent or guess a missing required parameter (e.g. a task's \
duration, priority, or start time). If the user's command doesn't give \
you something a tool needs, stop and ask them for it instead of calling \
the tool with a made-up value.
2. If a tool result includes a "conflicts" list, relay every entry to \
the user in plain language, unaltered — do not summarize conflicts away \
or drop any of them.
3. Report tool results honestly, including statuses like "not_found" or \
"duplicate_title" — tell the user plainly what happened rather than \
glossing over it.
4. After adding or editing a task that has a fixed start_time, call \
generate_schedule for that pet to check for conflicts, and tell the user \
about any conflicts it finds before moving on.
"""


def bind_tools(owner: Owner) -> list:
    """Return agent_tools.py's tool functions bound to this owner, with
    clean signatures/docstrings (no `owner` param) for Gemini to introspect."""

    def add_pet(pet_name: str, species: str, notes: str = "") -> dict:
        """Register a new pet for the owner."""
        return tools.tool_add_pet(owner, pet_name, species, notes)

    def edit_pet(pet_name: str, new_name: str = None, species: str = None,
                 notes: str = None) -> dict:
        """Rename a pet and/or change its species or notes."""
        return tools.tool_edit_pet(owner, pet_name, new_name, species, notes)

    def remove_pet(pet_name: str) -> dict:
        """Delete a pet and all of its tasks."""
        return tools.tool_remove_pet(owner, pet_name)

    def add_task(pet_name: str, title: str, duration_minutes: int, priority: str,
                 description: str = "", frequency_count: int = 1,
                 frequency_unit: str = "day", start_time: str = None) -> dict:
        """Add a task to an existing pet. duration_minutes and priority are
        required. frequency_unit is one of day/week/month/as_needed.
        start_time, if given, is a fixed "HH:MM" time."""
        return tools.tool_add_task(owner, pet_name, title, duration_minutes, priority,
                                    description, frequency_count, frequency_unit, start_time)

    def edit_task(pet_name: str, title: str, new_title: str = None,
                  duration_minutes: int = None, priority: str = None,
                  description: str = None, frequency_count: int = None,
                  frequency_unit: str = None, start_time: str = None) -> dict:
        """Update fields on an existing task. Only pass the fields that
        should change; leave the rest as None."""
        kwargs = {k: v for k, v in {
            "new_title": new_title, "duration_minutes": duration_minutes,
            "priority": priority, "description": description,
            "frequency_count": frequency_count, "frequency_unit": frequency_unit,
            "start_time": start_time,
        }.items() if v is not None}
        return tools.tool_edit_task(owner, pet_name, title, **kwargs)

    def delete_task(pet_name: str, title: str) -> dict:
        """Remove a task from a pet by title."""
        return tools.tool_delete_task(owner, pet_name, title)

    def generate_schedule(day_start: str = "09:00", day_end: str = "21:00",
                           pet_name: str = None) -> dict:
        """Build today's schedule, assigning start times and reporting
        conflicts. Omit pet_name to schedule every pet's tasks together."""
        return tools.tool_generate_schedule(owner, day_start, day_end, pet_name)

    def check_slots(duration_minutes: int, day_start: str = "09:00",
                     day_end: str = "21:00", pet_name: str = None) -> dict:
        """Find open time blocks of at least duration_minutes in the day window."""
        return tools.tool_check_slots(owner, duration_minutes, day_start, day_end, pet_name)

    return [add_pet, edit_pet, remove_pet, add_task, edit_task, delete_task,
            generate_schedule, check_slots]


def describe_call(part) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in dict(part.function_call.args or {}).items())
    return f"{part.function_call.name}({args})"


class Agent:
    """Wraps a Gemini chat session on PRIMARY_MODEL. If a message hits a
    429 (quota exhausted), rebuilds the chat on FALLBACK_MODEL with the
    same conversation history and retries once."""

    def __init__(self, client: genai.Client, config: types.GenerateContentConfig):
        self._client = client
        self._config = config
        self.model = PRIMARY_MODEL
        self._chat = client.chats.create(model=self.model, config=config)

    def ask(self, message: str):
        try:
            return self._chat.send_message(message)
        except errors.ClientError as e:
            if e.code != 429 or self.model == FALLBACK_MODEL:
                raise
            print(f"  [info] {self.model} quota exhausted — switching to {FALLBACK_MODEL}")
            self.model = FALLBACK_MODEL
            self._chat = self._client.chats.create(
                model=self.model, config=self._config, history=self._chat.get_history(),
            )
            return self._chat.send_message(message)


def build_agent(client: genai.Client, owner: Owner) -> Agent:
    """Construct an Agent wired to this owner's tools and guardrail
    system instruction — shared by the CLI loop below and the Streamlit
    chat UI in app.py."""
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        tools=bind_tools(owner),
    )
    return Agent(client, config)


def run_command(agent: Agent, command: str) -> None:
    resp = agent.ask(command)
    history = resp.automatic_function_calling_history or []
    for content in history:
        for part in content.parts:
            if part.function_call:
                print(f"  [tool] {describe_call(part)}")
            elif part.function_response:
                print(f"  [result] {part.function_response.response}")
    print(f"\n{resp.text}\n")


def main() -> None:
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY not set — add it to .env first.")

    owner = load_owner()
    if owner is None:
        name = input("No saved owner found. Enter an owner name to create one: ").strip()
        owner = Owner(name)
        save_owner(owner)

    client = genai.Client(api_key=api_key)
    agent = build_agent(client, owner)

    print(f"PawPal+ agent ready for {owner.owner_name}. Type 'quit' to exit.\n")
    while True:
        command = input("> ").strip()
        if command.lower() in ("quit", "exit"):
            break
        if command:
            run_command(agent, command)


if __name__ == "__main__":
    main()
