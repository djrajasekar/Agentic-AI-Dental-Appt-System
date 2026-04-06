"""
****************************************
Modern Clinic Streamlit experience.
****************************************
"""

import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

from dental_agent.config.settings import BASE_DIR, GOOGLE_API_KEY, MODEL_NAME, VALID_SPECIALIZATIONS
from main import process_user_message

# ****************************************
# Static UI content shared across reruns.
# ****************************************
# Keeps the first assistant reply in one place so resets stay consistent.
WELCOME_MESSAGE = """
## 👋 Welcome to the Dental Agentic AI Assistant
I can help you **check slots**, **book appointments**, **cancel bookings**, and **reschedule visits**.
Ask a question or use the quick actions from the left panel.
"""

# These shortcuts double as a demo for staff who are new to the assistant.
QUICK_ACTIONS = [
    ("📅 Show orthodontist slots", "Show available slots for an orthodontist"),
    ("🦷 Book an appointment", "Book patient 1000082 with Emily Johnson on 5/10/2026 9:00"),
    ("❌ Cancel an appointment", "Cancel appointment for patient 1000082 at 5/10/2026 9:00"),
    ("🔄 Reschedule a visit", "Reschedule patient 1000082 from 5/10/2026 9:00 to 5/12/2026 10:00"),
]

DB_PATH = BASE_DIR / "doctor_availability.db"

# ****************************************
# Session-state helpers keep the chat stable.
# ****************************************
def init_ui_state() -> None:
    """Create the Streamlit session keys once so page reruns keep the chat context."""
    if "agent_history" not in st.session_state:
        st.session_state.agent_history = []
    if "ui_messages" not in st.session_state:
        st.session_state.ui_messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None


def queue_prompt(prompt_text: str) -> None:
    """Store a sidebar shortcut until the next rerun sends it through the chat flow."""
    st.session_state.pending_prompt = prompt_text


def clear_chat() -> None:
    """Reset only the visible conversation while leaving appointment data unchanged in SQLite."""
    st.session_state.agent_history = []
    st.session_state.ui_messages = [{"role": "assistant", "content": WELCOME_MESSAGE}]
    st.session_state.pending_prompt = None


def query_availability_records(
    date_text: str = "",
    specialization: str = "All",
    doctor_name: str = "",
    availability: str = "All",
    limit: int = 25,
) -> pd.DataFrame:
    """Build the popup search results from SQLite so the UI and agent read the same live data."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. Run scripts/import_doctor_availability_to_sqlite.py first."
        )

    # Start with today-or-future rows so the popup does not surface expired appointments.
    filters = ["date(date_slot) >= ?"]
    params: list[str | int] = [date.today().isoformat()]

    if date_text.strip():
        # Prefer an exact date match when the input parses cleanly; otherwise fall back to a text search.
        parsed_date = pd.to_datetime(date_text.strip(), format="mixed", dayfirst=False, errors="coerce")
        if pd.notna(parsed_date):
            filters.append("date(date_slot) = ?")
            params.append(parsed_date.date().isoformat())
        else:
            filters.append("date_slot LIKE ?")
            params.append(f"%{date_text.strip()}%")
    if specialization != "All":
        filters.append("specialization = ?")
        params.append(specialization)
    if doctor_name.strip():
        filters.append("lower(doctor_name) LIKE lower(?)")
        params.append(f"%{doctor_name.strip()}%")
    if availability != "All":
        filters.append("is_available = ?")
        params.append(1 if availability == "Available" else 0)

    where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
    params.append(limit)

    query = f"""
        SELECT
            date_slot,
            specialization,
            doctor_name,
            CASE WHEN is_available = 1 THEN 'Available' ELSE 'Booked' END AS availability
        FROM doctor_availability
        {where_clause}
        ORDER BY date_slot, doctor_name
        LIMIT ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn, params=params)


# ****************************************
# SQLite lookup tools support the front-desk popup.
# ****************************************
@st.dialog("🔎 Search doctor availability")
def show_availability_search_dialog() -> None:
    """Give reception staff a quick live lookup window without leaving the main dashboard."""
    st.caption("Search `doctor_availability.db` by date, specialization, doctor, or status.")

    date_value = st.date_input(
        "Date filter",
        value=None,
        format="MM/DD/YYYY",
        help="Pick a date from the calendar to narrow the availability list.",
    )
    left, middle, right = st.columns(3)
    with left:
        specialization = st.selectbox("Specialization", ["All", *VALID_SPECIALIZATIONS])
    with middle:
        availability = st.selectbox("Availability", ["All", "Available", "Booked"])
    with right:
        limit = st.number_input("Max rows", min_value=5, max_value=200, value=25, step=5)

    doctor_name = st.text_input("Doctor name", placeholder="john doe")

    try:
        results = query_availability_records(
            date_text=date_value.isoformat() if date_value else "",
            specialization=specialization,
            doctor_name=doctor_name,
            availability=availability,
            limit=int(limit),
        )
    except FileNotFoundError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error(f"Unable to load availability data: {exc}")
        return

    st.write(f"**Matches:** {len(results)}")
    st.dataframe(results, use_container_width=True, hide_index=True)


def render_availability_lookup_button() -> None:
    """Open the SQLite search popup from the Modern UI."""
    if st.button("🔎 Search doctor availability", use_container_width=True, type="primary"):
        show_availability_search_dialog()


def render_sidebar(title: str) -> None:
    """Keep health checks, shortcuts, and the reset action in one predictable place."""
    with st.sidebar:
        st.markdown(f"## {title}")
        st.markdown(f"**Model:** `{MODEL_NAME}`")

        if GOOGLE_API_KEY:
            st.success("✅ Gemini API key detected")
        else:
            st.warning("⚠️ Add `GOOGLE_API_KEY` in `.env` before asking the agent questions.")

        st.markdown("### ⚡ Quick actions")
        for label, prompt_text in QUICK_ACTIONS:
            st.button(
                label,
                use_container_width=True,
                on_click=queue_prompt,
                args=(prompt_text,),
            )

        st.button("🧹 Clear chat", use_container_width=True, on_click=clear_chat)


def render_chat_area(placeholder: str, spinner_text: str = "Thinking with Gemini...") -> None:
    """Replay the visible transcript, then send each new prompt through the shared agent flow."""
    for msg in st.session_state.ui_messages:
        avatar = "🤖" if msg["role"] == "assistant" else "🙂"
        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "assistant":
                st.info(msg["content"], icon="✨")
            else:
                st.markdown(msg["content"])

    prompt = st.chat_input(placeholder)
    if not prompt and st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    if prompt:
        st.session_state.ui_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🙂"):
            st.markdown(prompt)

        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner(spinner_text):
                try:
                    reply, updated_history = process_user_message(st.session_state.agent_history, prompt)
                    st.session_state.agent_history = updated_history
                    st.info(reply, icon="✨")
                except Exception as exc:
                    reply = f"⚠️ Error: {exc}"
                    st.error(reply)

        st.session_state.ui_messages.append({"role": "assistant", "content": reply})


# ****************************************
# Page setup and styling must load before the layout.
# ****************************************
st.set_page_config(
    page_title="Dental Agentic AI Modern Clinic",
    page_icon="✨",
    layout="wide",
)

init_ui_state()

# Centralizes the glass-style theme so visual changes stay easy to maintain.
MODERN_CSS = """
<style>
    .stApp {
        background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 45%, #0f766e 100%);
        color: #e2e8f0;
    }
    .panel {
        border-radius: 18px;
        padding: 1rem 1.2rem;
        background: rgba(255, 255, 255, 0.10);
        border: 1px solid rgba(255, 255, 255, 0.18);
        box-shadow: 0 8px 30px rgba(15, 23, 42, 0.24);
        backdrop-filter: blur(10px);
        margin-bottom: 1rem;
    }
    .panel h1, .panel h3 {
        color: #ffffff;
        margin-top: 0;
    }
    .agent-chip {
        display: inline-block;
        margin: 0.2rem 0.35rem 0.2rem 0;
        padding: 0.35rem 0.7rem;
        border-radius: 999px;
        background: rgba(255,255,255,0.14);
        color: #f8fafc;
        font-size: 0.9rem;
    }
    div[data-testid="stAlert"] {
        border-radius: 14px;
    }
</style>
"""

st.markdown(MODERN_CSS, unsafe_allow_html=True)
render_sidebar("✨ Modern Clinic Control")

# ****************************************
# Main layout guides first-time staff through the app.
# ****************************************
header_left, header_right = st.columns([3.2, 1.2])
with header_left:
    st.markdown(
        """
        <div class="panel">
            <h1>✨ Modern Clinic Dashboard UI</h1>
            <p>A premium clinic experience for appointments, schedules, and patient support.</p>
            <div>
                <span class="agent-chip">🤖 Supervisor Agent</span>
                <span class="agent-chip">📅 Booking Agent</span>
                <span class="agent-chip">❌ Cancellation Agent</span>
                <span class="agent-chip">🔄 Reschedule Agent</span>
                <span class="agent-chip">🦷 Dental Support</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with header_right:
    st.markdown(
        """
        <div class="panel">
            <h3>🔎 Quick search</h3>
            <p>Open the popup to search live appointment availability from SQLite.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_availability_lookup_button()

metric1, metric2, metric3, metric4 = st.columns(4)
metric1.metric("🤖 AI Status", "Ready")
metric2.metric("🧠 Model", "Gemini")
metric3.metric("📂 Data Source", "SQLite")
metric4.metric("⚡ UI Mode", "Modern")

# This middle section helps first-time users understand what the assistant can do.
info_left, info_middle, info_right = st.columns([1.15, 1.45, 1])
with info_left:
    st.markdown(
        """
        <div class="panel">
            <h3>💡 Suggested asks</h3>
            <ul>
                <li>Show open orthodontist slots this week</li>
                <li>Book or cancel a patient appointment</li>
                <li>Reschedule a visit to a new time</li>
                <li>Look up existing patient appointments</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

with info_middle:
    st.markdown(
        """
        <div class="panel">
            <h3>📋 Example prompts</h3>
            <ul>
                <li>Show available slots for an orthodontist</li>
                <li>Book patient 1000082 with Emily Johnson on 5/10/2026 9:00</li>
                <li>Cancel appointment for patient 1000082 at 5/10/2026 9:00</li>
                <li>Reschedule patient 1000082 from 5/10/2026 9:00 to 5/12/2026 10:00</li>
                <li>What appointments does patient 1000048 have?</li>
            </ul>
        </div>
        """,
        unsafe_allow_html=True,
    )

with info_right:
    st.markdown(
        """
        <div class="panel">
            <h3>📌 Live lookup</h3>
            <p>Use the top-right search button anytime to filter slot availability by date, doctor, specialization, or booking status.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

render_chat_area("Ask the modern clinic assistant anything about appointments...")
