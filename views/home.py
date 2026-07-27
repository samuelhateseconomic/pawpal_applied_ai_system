import os

import streamlit as st
from google import genai
from google.genai import errors

from pawpal_system import Owner, save_owner
from agent_wiring import build_agent

st.title("🐾 PawPal+")
st.markdown("Chat with the AI assistant, or use the **Pets** / **Tasks** / **Schedule** pages directly.")
st.divider()

# ── Owner bootstrap ────────────────────────────────────────────────────────────

if "owner" not in st.session_state:
    st.subheader("Get Started")
    name = st.text_input("Your name", value="Jordan")
    if st.button("Create owner", key="create_owner_btn"):
        st.session_state.owner = Owner(name)
        save_owner(st.session_state.owner)
        st.rerun()
    st.stop()

st.success(f"Welcome back, {st.session_state.owner.owner_name}! Head to the **Pets** page to add a pet.")

with st.expander("✏️ Change your name"):
    new_owner_name = st.text_input(
        "Your name", value=st.session_state.owner.owner_name, key="rename_owner_input"
    )
    if st.button("Save name", key="save_owner_name_btn"):
        if not new_owner_name:
            st.warning("Enter a name.")
        else:
            st.session_state.owner.owner_name = new_owner_name
            save_owner(st.session_state.owner)
            st.success("Name updated.")
            st.rerun()

st.divider()

# ── AI Assistant ───────────────────────────────────────────────────────────────

st.subheader("🐾 AI Assistant")

if not os.environ.get("GEMINI_API_KEY"):
    st.warning("GEMINI_API_KEY not set — add it to .env to enable the chat assistant.")
else:
    # Rebuild the agent whenever the owner object itself is swapped out so
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
