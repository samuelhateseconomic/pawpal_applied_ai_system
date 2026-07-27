import streamlit as st

from pawpal_system import save_owner

st.title("🐕 Pets")

if "owner" not in st.session_state:
    st.warning("Set up an owner on the Home page first.")
    st.stop()

owner = st.session_state.owner
SPECIES_OPTIONS = ["dog", "cat", "other"]

# ── Current pets ───────────────────────────────────────────────────────────────

pets = owner.get_pets()
if pets:
    st.table([
        {"Name": p.pet_name, "Species": p.species, "Notes": p.notes or "—", "Tasks": len(p.tasks)}
        for p in pets
    ])
else:
    st.info("No pets yet. Add one below.")

st.divider()

# ── Add a pet ──────────────────────────────────────────────────────────────────

st.subheader("Add a Pet")
col1, col2 = st.columns(2)
with col1:
    new_pet_name = st.text_input("Pet name", key="new_pet_name")
with col2:
    new_species = st.selectbox("Species", SPECIES_OPTIONS, key="new_species")
new_notes = st.text_area("Notes", key="new_pet_notes")

if st.button("Add pet", key="add_pet_btn"):
    if not new_pet_name:
        st.warning("Enter a pet name.")
    elif any(p.pet_name == new_pet_name for p in owner.get_pets()):
        st.warning(f"A pet named '{new_pet_name}' already exists.")
    else:
        pet = owner.add_pet(new_pet_name, new_species)
        pet.notes = new_notes
        save_owner(owner)
        st.success(f"Added '{new_pet_name}'.")
        st.rerun()

st.divider()

# ── Edit a pet ─────────────────────────────────────────────────────────────────

st.subheader("Edit a Pet")
if not pets:
    st.info("Add a pet first.")
else:
    names = [p.pet_name for p in pets]
    selected_name = st.selectbox("Pet to edit", names, key="edit_pet_select")
    selected_pet = next(p for p in pets if p.pet_name == selected_name)

    edit_name = st.text_input("Name", value=selected_pet.pet_name, key="edit_pet_name")
    edit_species = st.selectbox(
        "Species", SPECIES_OPTIONS,
        index=SPECIES_OPTIONS.index(selected_pet.species) if selected_pet.species in SPECIES_OPTIONS else 0,
        key="edit_pet_species",
    )
    edit_notes = st.text_area("Notes", value=selected_pet.notes, key="edit_pet_notes")

    if st.button("Save changes", key="save_pet_changes_btn"):
        updated = owner.edit_pet(selected_name, new_name=edit_name, species=edit_species, notes=edit_notes)
        if updated is None:
            st.warning(f"Couldn't rename to '{edit_name}' — that name is already taken by another pet.")
        else:
            save_owner(owner)
            st.success("Pet updated.")
            st.rerun()

st.divider()

# ── Delete a pet ───────────────────────────────────────────────────────────────

st.subheader("Delete a Pet")
if not pets:
    st.info("No pets to delete.")
else:
    delete_name = st.selectbox("Pet to delete", [p.pet_name for p in pets], key="delete_pet_select")
    delete_pet = next(p for p in pets if p.pet_name == delete_name)
    task_count = len(delete_pet.tasks)

    if task_count:
        st.warning(
            f"⚠️ Deleting '{delete_name}' will also delete all {task_count} of its "
            f"task(s). This cannot be undone."
        )
    else:
        st.info(f"'{delete_name}' has no tasks.")

    confirm_key = f"confirm_delete_pet_{delete_name}"
    if st.session_state.get(confirm_key):
        st.error(f"Click again to confirm deleting '{delete_name}' and its {task_count} task(s).")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, delete permanently", type="primary", key="confirm_delete_pet_btn"):
                owner.remove_pet(delete_name)
                save_owner(owner)
                st.session_state.pop(confirm_key, None)
                st.success(f"Deleted '{delete_name}'.")
                st.rerun()
        with col_no:
            if st.button("Cancel", key="cancel_delete_pet_btn"):
                st.session_state.pop(confirm_key, None)
                st.rerun()
    else:
        if st.button("Delete pet", key="delete_pet_btn"):
            st.session_state[confirm_key] = True
            st.rerun()
