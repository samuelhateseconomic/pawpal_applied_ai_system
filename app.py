import streamlit as st
from dotenv import load_dotenv

from pawpal_system import load_owner

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")
load_dotenv()

# ── Load persisted data once per session ──────────────────────────────────────
if "owner" not in st.session_state:
    saved = load_owner()
    if saved:
        st.session_state.owner = saved

pg = st.navigation([
    st.Page("views/home.py", title="Home & Chat", icon="🐾", default=True),
    st.Page("views/pets.py", title="Pets", icon="🐕"),
    st.Page("views/tasks.py", title="Tasks", icon="📋"),
    st.Page("views/schedule.py", title="Schedule", icon="📅"),
])
pg.run()
