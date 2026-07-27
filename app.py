import os
from datetime import time

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import errors

from pawpal_system import Owner, Scheduler, save_owner, load_owner
from agent_wiring import build_agent

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
load_dotenv()

# ── Load persisted data once per session ──────────────────────────────────────
if "owner" not in st.session_state:
    saved = load_owner()
    if saved:
        st.session_state.owner = saved

st.title("🐾 PawPal+")
st.markdown("Plan your pet's day — add a pet, add tasks, and generate a schedule.")
st.divider()

# ── AI Assistant ───────────────────────────────────────────────────────────────

st.subheader("🐾 AI Assistant")

if "owner" not in st.session_state:
    st.info("Set an owner and pet below, then come back here to chat.")
elif not os.environ.get("GEMINI_API_KEY"):
    st.warning("GEMINI_API_KEY not set — add it to .env to enable the chat assistant.")
else:
    # Rebuild the agent whenever the owner object itself is swapped out
    # (e.g. the "Set Owner & Pet" button below creates a new Owner) so
    # the agent's tools never operate on a stale owner.
    if st.session_state.get("agent_owner_id") != id(st.session_state.owner):
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        st.session_state.agent = build_agent(client, st.session_state.owner)
        st.session_state.agent_owner_id = id(st.session_state.owner)
        st.session_state.chat_transcript = []

    for role, text, tool_log in st.session_state.chat_transcript:
        with st.chat_message(role):
            for line in tool_log or []:
                st.caption(line)
            st.write(text)

    command = st.chat_input("Tell PawPal+ what to do...")
    if command:
        st.session_state.chat_transcript.append(("user", command, None))
        with st.spinner("Thinking..."):
            try:
                resp = st.session_state.agent.ask(command)
            except errors.ClientError as e:
                reply_text, tool_log = f"Sorry, the AI service returned an error: {e}", []
            else:
                tool_log = []
                for content in resp.automatic_function_calling_history or []:
                    for part in content.parts or []:
                        if part.function_call:
                            args = ", ".join(f"{k}={v!r}" for k, v in dict(part.function_call.args or {}).items())
                            tool_log.append(f"🔧 ran `{part.function_call.name}({args})`")
                        elif part.function_response:
                            tool_log.append(f"↳ {part.function_response.response}")
                reply_text = resp.text
        st.session_state.chat_transcript.append(("assistant", reply_text, tool_log))
        st.rerun()

st.divider()

# ── Owner & Pet Setup ─────────────────────────────────────────────────────────

st.subheader("Owner & Pet Setup")

owner_name = st.text_input("Owner name", value="Jordan")
pet_name   = st.text_input("Pet name",   value="Mochi")
species    = st.selectbox("Species", ["dog", "cat", "other"])

if st.button("Set Owner & Pet"):
    if "owner" not in st.session_state or st.session_state.owner.owner_name != owner_name:
        st.session_state.owner = Owner(owner_name)
    pet = st.session_state.owner.add_pet(pet_name, species)
    st.session_state.current_pet = pet
    save_owner(st.session_state.owner)
    st.success(f"Owner '{owner_name}' and pet '{pet_name}' are ready!")

# ── Add Tasks ─────────────────────────────────────────────────────────────────

st.markdown("### Tasks")

col1, col2, col3, col4 = st.columns(4)
with col1:
    task_title = st.text_input("Task title", value="Morning walk")
with col2:
    duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20)
with col3:
    priority = st.selectbox("Priority", ["low", "medium", "high"], index=2)
with col4:
    pin_time = st.checkbox("Fixed time?")
    fixed_time = st.time_input("Time", value=time(9, 0), disabled=not pin_time, label_visibility="collapsed")

if st.button("Add task"):
    if "current_pet" not in st.session_state:
        st.warning("Set an owner and pet first.")
    else:
        pinned = fixed_time.strftime("%H:%M") if pin_time else None
        result = st.session_state.current_pet.add_task(
            task_title, int(duration), priority, start_time=pinned
        )
        if result is None:
            st.warning(f"A task named '{task_title}' already exists for this pet.")
        else:
            save_owner(st.session_state.owner)
            st.success(f"Task '{task_title}' added!")

# ── Current Task Table ────────────────────────────────────────────────────────

if "owner" in st.session_state:
    all_tasks = st.session_state.owner.get_all_tasks()
    if all_tasks:
        st.markdown("**Current tasks:**")
        st.table([
            {
                "Pet":      t.pet_name or "—",
                "Task":     t.title,
                "Duration": f"{t.duration_minutes} min",
                "Priority": t.priority.capitalize(),
                "Fixed at": t.start_time or "auto",
                "Status":   t.completion_status,
            }
            for t in all_tasks
        ])
    else:
        st.info("No tasks yet. Add one above.")

st.divider()

# ── Day Window ────────────────────────────────────────────────────────────────

col_start, col_end = st.columns(2)
with col_start:
    day_start = st.time_input("Day starts at", value=time(9, 0)).strftime("%H:%M")
with col_end:
    day_end = st.time_input("Day ends at", value=time(21, 0)).strftime("%H:%M")

# ── Find Available Time ──────────────────────────────────────────────────────

st.subheader("Find Available Time")

col_dur, col_check = st.columns([3, 1])
with col_dur:
    check_duration = st.number_input(
        "New task duration (min)", min_value=1, max_value=240, value=30, key="check_duration"
    )
with col_check:
    st.write("")
    st.write("")
    check_clicked = st.button("Check available slots")

if check_clicked:
    if "owner" not in st.session_state or not st.session_state.owner.get_all_tasks():
        st.warning("Add an owner, pet, and at least one task first.")
    else:
        tasks = st.session_state.owner.get_all_tasks()
        scheduler = Scheduler(tasks, day_start=day_start, day_end=day_end)
        slots = scheduler.find_available_slots(int(check_duration))
        if slots:
            st.success(f"Open blocks of at least {int(check_duration)} min:")
            for start, end in slots:
                st.write(f"- {start}–{end}")
        else:
            st.info(f"No open block of at least {int(check_duration)} min found in the day.")

st.divider()

# ── Build Schedule ────────────────────────────────────────────────────────────

st.subheader("Build Schedule")

if st.button("Generate schedule"):
    if "owner" not in st.session_state or not st.session_state.owner.get_all_tasks():
        st.warning("Add an owner, pet, and at least one task first.")
    else:
        tasks = st.session_state.owner.get_all_tasks()
        scheduler = Scheduler(tasks, day_start=day_start, day_end=day_end)
        result = scheduler.schedule()

        if not result.tasks:
            st.info("No pending tasks to schedule.")
        else:
            st.markdown("#### Scheduled Tasks")
            st.table([
                {
                    "Time":     t.start_time or "—",
                    "Pet":      t.pet_name or "—",
                    "Task":     t.title,
                    "Duration": f"{t.duration_minutes} min",
                    "Priority": t.priority.capitalize(),
                    "Frequency": t.frequency_label(),
                }
                for t in result.tasks
            ])

            if result.conflicts:
                for conflict in result.conflicts:
                    st.warning(
                        f"⚠️ **Conflict detected:** {conflict}\n\n"
                        "**Tip:** To resolve this, try one of the following:\n"
                        "- Change a task's **Fixed time** so it doesn't overlap.\n"
                        "- Lower its **priority** so the scheduler places it later.\n"
                        "- Shorten the **duration** to fit within the available gap.\n"
                        "- If a task falls outside the day window, move its **Fixed time** "
                        "inside **Day starts at / Day ends at**, or widen that window."
                    )
            else:
                st.success("Schedule looks great — no conflicts detected!")
