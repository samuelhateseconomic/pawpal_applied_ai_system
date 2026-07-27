from datetime import time

import streamlit as st

from pawpal_system import save_owner

st.title("📋 Tasks")

if "owner" not in st.session_state:
    st.warning("Set up an owner on the Home page first.")
    st.stop()

owner = st.session_state.owner
pets = owner.get_pets()

if not pets:
    st.warning("Add a pet on the Pets page first.")
    st.stop()

PRIORITY_OPTIONS = ["low", "medium", "high"]
FREQUENCY_OPTIONS = ["day", "week", "month", "as_needed"]

pet_names = [p.pet_name for p in pets]
selected_name = st.selectbox("Pet", pet_names, key="tasks_pet_select")
pet = next(p for p in pets if p.pet_name == selected_name)

# ── Current tasks ──────────────────────────────────────────────────────────────

if pet.tasks:
    st.table([
        {
            "Task": t.title, "Duration": f"{t.duration_minutes} min",
            "Priority": t.priority.capitalize(), "Frequency": t.frequency_label(),
            "Fixed at": t.start_time or "auto", "Note": t.description or "—",
            "Status": t.completion_status,
        }
        for t in pet.tasks
    ])
else:
    st.info(f"No tasks yet for {selected_name}. Add one below.")

st.divider()

# ── Add a task ─────────────────────────────────────────────────────────────────

st.subheader("Add a Task")
col1, col2, col3 = st.columns(3)
with col1:
    title = st.text_input("Task title", key="new_task_title")
with col2:
    duration = st.number_input("Duration (min)", min_value=1, max_value=240, value=20, key="new_task_duration")
with col3:
    priority = st.selectbox("Priority", PRIORITY_OPTIONS, index=2, key="new_task_priority")

col4, col5, col6 = st.columns(3)
with col4:
    freq_count = st.number_input("Occurrences", min_value=1, value=1, key="new_task_freq_count")
with col5:
    freq_unit = st.selectbox("Per", FREQUENCY_OPTIONS, key="new_task_freq_unit")
with col6:
    pin_time = st.checkbox("Fixed time?", key="new_task_pin")
    fixed_time = st.time_input("Time", value=time(9, 0), disabled=not pin_time,
                                label_visibility="collapsed", key="new_task_time")

note = st.text_area("Note", key="new_task_note")

if st.button("Add task", key="add_task_btn"):
    if not title:
        st.warning("Enter a task title.")
    else:
        pinned = fixed_time.strftime("%H:%M") if pin_time else None
        result = pet.add_task(title, int(duration), priority, note,
                               int(freq_count), freq_unit, start_time=pinned)
        if result is None:
            st.warning(f"A task named '{title}' already exists for {selected_name}.")
        else:
            save_owner(owner)
            st.success(f"Task '{title}' added.")
            st.rerun()

st.divider()

# ── Edit a task ────────────────────────────────────────────────────────────────

st.subheader("Edit a Task")
if not pet.tasks:
    st.info("Add a task first.")
else:
    task_titles = [t.title for t in pet.tasks]
    edit_title = st.selectbox("Task to edit", task_titles, key="edit_task_select")
    task = next(t for t in pet.tasks if t.title == edit_title)

    e_title = st.text_input("Title", value=task.title, key="edit_task_title")
    e_duration = st.number_input("Duration (min)", min_value=1, max_value=240,
                                  value=task.duration_minutes, key="edit_task_duration")
    e_priority = st.selectbox("Priority", PRIORITY_OPTIONS,
                               index=PRIORITY_OPTIONS.index(task.priority), key="edit_task_priority")
    e_freq_count = st.number_input("Occurrences", min_value=1, value=task.frequency_count,
                                    key="edit_task_freq_count")
    e_freq_unit = st.selectbox("Per", FREQUENCY_OPTIONS,
                                index=FREQUENCY_OPTIONS.index(task.frequency_unit), key="edit_task_freq_unit")
    e_pin_time = st.checkbox("Fixed time?", value=task.start_time is not None, key="edit_task_pin")
    e_fixed_time = st.time_input(
        "Time",
        value=time(*map(int, task.start_time.split(":"))) if task.start_time else time(9, 0),
        disabled=not e_pin_time, label_visibility="collapsed", key="edit_task_time",
    )
    e_note = st.text_area("Note", value=task.description, key="edit_task_note")

    if st.button("Save task changes", key="save_task_changes_btn"):
        new_start = e_fixed_time.strftime("%H:%M") if e_pin_time else None
        updated = pet.edit_task(
            edit_title, new_title=e_title, duration_minutes=int(e_duration),
            priority=e_priority, description=e_note, frequency_count=int(e_freq_count),
            frequency_unit=e_freq_unit, start_time=new_start,
        )
        if updated is None:
            st.warning(f"Couldn't rename to '{e_title}' — that title is already taken for this pet.")
        else:
            save_owner(owner)
            st.success("Task updated.")
            st.rerun()

st.divider()

# ── Delete a task ──────────────────────────────────────────────────────────────

st.subheader("Delete a Task")
if not pet.tasks:
    st.info("No tasks to delete.")
else:
    delete_title = st.selectbox("Task to delete", [t.title for t in pet.tasks], key="delete_task_select")
    confirm_key = f"confirm_delete_task_{selected_name}_{delete_title}"
    if st.session_state.get(confirm_key):
        st.error(f"Click again to confirm deleting '{delete_title}'.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, delete permanently", type="primary", key="confirm_task_delete_btn"):
                pet.delete_task(delete_title)
                save_owner(owner)
                st.session_state.pop(confirm_key, None)
                st.success(f"Deleted '{delete_title}'.")
                st.rerun()
        with col_no:
            if st.button("Cancel", key="cancel_task_delete_btn"):
                st.session_state.pop(confirm_key, None)
                st.rerun()
    else:
        if st.button("Delete task", key="delete_task_btn"):
            st.session_state[confirm_key] = True
            st.rerun()
