import streamlit as st
from pawpal_system import Owner, Scheduler, save_owner, load_owner

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# ── Load persisted data once per session ──────────────────────────────────────
if "owner" not in st.session_state:
    saved = load_owner()
    if saved:
        st.session_state.owner = saved

st.title("🐾 PawPal+")
st.markdown("Plan your pet's day — add a pet, add tasks, and generate a schedule.")
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
    start_time = st.text_input("Fixed time (HH:MM)", value="", placeholder="e.g. 09:00")

if st.button("Add task"):
    if "current_pet" not in st.session_state:
        st.warning("Set an owner and pet first.")
    else:
        pinned = start_time.strip() or None
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
    day_start = st.text_input("Day starts at (HH:MM)", value="09:00")
with col_end:
    day_end = st.text_input("Day ends at (HH:MM)", value="21:00")

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
        scheduler = Scheduler(tasks, day_start=day_start.strip(), day_end=day_end.strip())
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
        scheduler = Scheduler(tasks, day_start=day_start.strip(), day_end=day_end.strip())
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
                    "Frequency": t.frequency,
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
                        "- Shorten the **duration** to fit within the available gap."
                    )
            else:
                st.success("Schedule looks great — no conflicts detected!")
