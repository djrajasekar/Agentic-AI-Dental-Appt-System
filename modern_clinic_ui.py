"""
****************************************
Modern Clinic Streamlit experience.
****************************************
"""

from html import escape
import sqlite3
from datetime import date

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

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
        st.session_state.ui_messages = []
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = None
    if "trace_events" not in st.session_state:
        st.session_state.trace_events = []


def queue_prompt(prompt_text: str) -> None:
    """Store a sidebar shortcut until the next rerun sends it through the chat flow."""
    st.session_state.pending_prompt = prompt_text


def clear_chat() -> None:
    """Reset only the visible conversation while leaving appointment data unchanged in SQLite."""
    st.session_state.agent_history = []
    st.session_state.ui_messages = []
    st.session_state.pending_prompt = None
    st.session_state.trace_events = []


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
            COALESCE(patient_to_attend, '') AS patient_id,
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
    st.caption("Search `doctor_availability.db` by date, specialization, doctor, status, and assigned patient ID.")

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
    display_results = results.rename(
        columns={
            "date_slot": "Date/Time",
            "specialization": "Specialization",
            "doctor_name": "Doctor",
            "patient_id": "Patient ID",
            "availability": "Status",
        }
    )
    st.table(display_results)


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

        st.caption("The right-side panel shows the full workflow trace for each request.")

        st.button("🧹 Clear chat", use_container_width=True, on_click=clear_chat)


def _build_trace_markup() -> str:
    """Render the live backend trace as HTML so a placeholder can refresh it during streaming."""
    mode_title = "Full Workflow Trace"
    mode_description = "Supervisor, specialist agent, tool calls, and final response flow."

    if not st.session_state.trace_events:
        entries_html = '<div class="trace-empty">Run a prompt to see the backend steps appear here.</div>'
    else:
        entries_html = "".join(
            (
                f'<div class="trace-entry">'
                f'<span class="trace-index">{index:02d}</span>'
                f'<span class="trace-text">{escape(entry)}</span>'
                f"</div>"
            )
            for index, entry in enumerate(st.session_state.trace_events, start=1)
        )

    return f"""
        <div class="panel trace-panel">
            <h3>🧭 {mode_title}</h3>
            <p>{mode_description}</p>
            <div class="trace-log">{entries_html}</div>
        </div>
    """


def render_trace_panel(trace_placeholder) -> None:
    """Refresh the side-panel trace without rerendering the rest of the page."""
    trace_placeholder.markdown(_build_trace_markup(), unsafe_allow_html=True)


def render_welcome_panel() -> None:
    """Keep the onboarding welcome message in a stable spot below the command center."""
    st.markdown(
        """
        <div class="panel">
            <h3>👋 Welcome to the Dental Agentic AI Assistant</h3>
            <p>I can help you <strong>check slots</strong>, <strong>book appointments</strong>, <strong>cancel bookings</strong>, and <strong>reschedule visits</strong>.</p>
            <p>Ask a question below or use quick actions from the left panel.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_post_trace_controls() -> None:
    """Render search and runtime controls after trace so mobile order matches clinic workflow."""
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

    with st.expander("⚙️ Assistant runtime details", expanded=True):
        metric1, metric2, metric3, metric4 = st.columns(4)
        metric1.metric("🤖 AI Status", "Ready")
        metric2.metric("🧠 Model", "Gemini")
        metric3.metric("📂 Data Source", "SQLite")
        metric4.metric("⚡ UI Mode", "Modern")

    # A single expander stays in sync with viewport: open on desktop, closed on mobile.
    components.html(
        """
        <script>
        const applyRuntimeDefault = () => {
            const root = window.parent.document;
            const detailsNodes = root.querySelectorAll('details');
            let runtimeDetails = null;

            detailsNodes.forEach((node) => {
                const summary = node.querySelector('summary');
                if (summary && summary.textContent && summary.textContent.includes('Assistant runtime details')) {
                    runtimeDetails = node;
                }
            });

            if (!runtimeDetails) {
                return;
            }

            const isMobile = window.parent.matchMedia('(max-width: 768px)').matches;
            runtimeDetails.open = !isMobile;
        };

        applyRuntimeDefault();
        window.parent.addEventListener('resize', applyRuntimeDefault);
        </script>
        """,
        height=0,
    )


def render_chat_area(trace_placeholder, placeholder: str, spinner_text: str = "Thinking with Gemini...") -> None:
    """Replay the visible transcript, then send each new prompt through the shared agent flow."""
    for msg in st.session_state.ui_messages:
        avatar = "🤖" if msg["role"] == "assistant" else "🙂"
        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "assistant":
                st.markdown(msg["content"])
            else:
                st.markdown(msg["content"])

    prompt = st.chat_input(placeholder)
    if not prompt and st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None

    if prompt:
        st.session_state.trace_events = []
        render_trace_panel(trace_placeholder)
        st.session_state.ui_messages.append({"role": "user", "content": prompt})

        def update_trace(event_text: str) -> None:
            st.session_state.trace_events.append(event_text)
            render_trace_panel(trace_placeholder)

        with st.spinner(spinner_text):
            try:
                reply, updated_history, trace_events = process_user_message(
                    st.session_state.agent_history,
                    prompt,
                    trace_callback=update_trace,
                    return_trace=True,
                )
                st.session_state.agent_history = updated_history
                st.session_state.trace_events = trace_events
                render_trace_panel(trace_placeholder)
            except Exception as exc:
                reply = f"⚠️ Error: {exc}"
                st.session_state.trace_events.append(f"Run failed: {exc}")
                render_trace_panel(trace_placeholder)

        st.session_state.ui_messages.append({"role": "assistant", "content": reply})
        st.rerun()


# ****************************************
# Page setup and styling must load before the layout.
# ****************************************
st.set_page_config(
    page_title="Dental Care Command Center",
    page_icon="✨",
    layout="wide",
)

init_ui_state()

# Centralizes the glass-style theme so visual changes stay easy to maintain.
MODERN_CSS = """
<style>
    .stApp {
        background: linear-gradient(145deg, #f4f7fb 0%, #ddeaf4 42%, #c7e3dc 100%);
        color: #10233a;
    }
    div[data-testid="stDialog"] div[role="dialog"] {
        width: min(1180px, 96vw);
        max-width: min(1180px, 96vw);
    }
    div[data-testid="stDialog"] table {
        width: 100%;
    }
    div[data-testid="stDialog"] th,
    div[data-testid="stDialog"] td {
        white-space: nowrap;
    }
    .panel {
        border-radius: 18px;
        padding: 1rem 1.2rem;
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid rgba(148, 163, 184, 0.28);
        box-shadow: 0 12px 30px rgba(15, 23, 42, 0.10);
        backdrop-filter: blur(10px);
        margin-bottom: 1rem;
    }
    .trace-panel {
        height: 760px;
        display: flex;
        flex-direction: column;
    }
    .trace-log {
        height: 100%;
        min-height: 0;
        overflow-y: auto;
        margin-top: 0.8rem;
        padding-right: 0.2rem;
        border-top: 1px solid rgba(148, 163, 184, 0.18);
    }
    .trace-entry {
        display: grid;
        grid-template-columns: 2.4rem 1fr;
        gap: 0.55rem;
        align-items: start;
        padding: 0.55rem 0;
        border-bottom: 1px solid rgba(148, 163, 184, 0.22);
        font-size: 0.94rem;
    }
    .trace-index {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 1.7rem;
        border-radius: 999px;
        background: #103b66;
        color: #f8fafc;
        font-weight: 700;
        font-size: 0.78rem;
    }
    .trace-text {
        color: #10233a;
        white-space: pre-wrap;
        word-break: break-word;
    }
    .trace-empty {
        padding: 1rem 0;
        color: rgba(16, 35, 58, 0.72);
    }
    .panel h1, .panel h3, .panel p, .panel li {
        color: #10233a;
        margin-top: 0;
    }
    .agent-chip {
        display: inline-block;
        margin: 0.2rem 0.35rem 0.2rem 0;
        padding: 0.35rem 0.7rem;
        border-radius: 999px;
        background: #103b66;
        color: #f8fafc;
        font-size: 0.9rem;
    }
    div[data-testid="stSidebar"] {
        background: rgba(16, 35, 58, 0.94);
    }
    div[data-testid="stSidebar"] * {
        color: #e6eef8;
    }
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.72);
        border: 1px solid rgba(148, 163, 184, 0.25);
        border-radius: 16px;
        padding: 0.8rem 1rem;
    }
    div[data-testid="stAlert"] {
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.94);
        border: 1px solid rgba(148, 163, 184, 0.35);
        color: #10233a;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
    }
    div[data-testid="stAlert"] * {
        color: #10233a !important;
    }
    div[data-testid="stChatMessage"] {
        background: rgba(255, 255, 255, 0.55);
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 18px;
        padding: 0.25rem 0.5rem;
        margin-bottom: 0.6rem;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
    }
    div[data-testid="stChatMessage"] p,
    div[data-testid="stChatMessage"] li,
    div[data-testid="stChatMessage"] span,
    div[data-testid="stChatMessage"] label {
        color: #10233a;
    }
    div[data-testid="stChatInput"] textarea {
        background: rgba(255, 255, 255, 0.96);
        color: #10233a;
    }
</style>
"""

st.markdown(MODERN_CSS, unsafe_allow_html=True)
render_sidebar("✨ Dental Care Command Center")

# ****************************************
# Main layout guides first-time staff through the app.
# ****************************************
st.markdown(
    """
    <div class="panel">
        <h1>✨ Dental Care Command Center</h1>
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

# ****************************************
# Mobile-first order keeps chat before trace on narrow screens.
# ****************************************
render_welcome_panel()

chat_column, trace_column = st.columns([1.45, 1], gap="large")
trace_placeholder = trace_column.empty()
with chat_column:
    render_chat_area(trace_placeholder, "Ask the modern clinic assistant anything about appointments...")

with trace_column:
    render_trace_panel(trace_placeholder)

render_post_trace_controls()

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
