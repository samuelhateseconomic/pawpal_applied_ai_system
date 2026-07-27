from datetime import time

import streamlit as st

from pawpal_system import Scheduler

st.title("📅 Schedule")

if "owner" not in st.session_state:
    st.warning("Set up an owner on the Home page first.")
    st.stop()

owner = st.session_state.owner
if not owner.get_all_tasks():
    st.warning("Add a pet and at least one task first.")
    st.stop()

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
    check_clicked = st.button("Check available slots", key="check_slots_btn")

if check_clicked:
    tasks = owner.get_all_tasks()
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

if st.button("Generate schedule", key="generate_schedule_btn"):
    tasks = owner.get_all_tasks()
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
