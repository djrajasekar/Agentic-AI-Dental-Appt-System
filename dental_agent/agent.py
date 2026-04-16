"""
****************************************
Primary dental assistant graph assembly.
****************************************
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from dental_agent.config.settings import GOOGLE_API_KEY, get_model_name, TEMPERATURE
from dental_agent.utils import sanitize_messages
from dental_agent.tools.sqllite_reader import (
    get_available_slots,
    get_patient_appointments,
    check_slot_availability,
    list_doctors_by_specialization,
)
from dental_agent.tools.sqllite_writer import (
    book_appointment,
    cancel_appointment,
    reschedule_appointment,
)

# ****************************************
# Shared tool registry keeps every entrypoint aligned.
# ****************************************
# One shared tool list keeps the UI and CLI on the same appointment rules.
TOOLS = [
    get_available_slots,
    get_patient_appointments,
    check_slot_availability,
    list_doctors_by_specialization,
    book_appointment,
    cancel_appointment,
    reschedule_appointment,
]

# ****************************************
# Core system instructions keep the assistant behavior consistent.
# ****************************************
SYSTEM_PROMPT = """You are a helpful dental appointment assistant. You help patients with:

1. Checking available appointment slots and doctor information
2. Booking new appointments
3. Cancelling existing appointments
4. Rescheduling appointments

## Available Specializations
general_dentist, oral_surgeon, orthodontist, cosmetic_dentist,
prosthodontist, pediatric_dentist, emergency_dentist

## Date Format
Always use M/D/YYYY H:MM format — e.g. 5/10/2026 9:00

## Booking Rules
- Always call check_slot_availability before booking to confirm the slot is free
- If a slot is taken, call get_available_slots to suggest alternatives
- Always confirm cancellations before executing them
- Ask for one missing detail at a time — don't overwhelm the user
"""

# ****************************************
# Prompt preparation cleans messages before each model call.
# ****************************************
def _pre_model_hook(state: dict) -> dict:
    """
    Runs as a dedicated graph node before every LLM call in the react loop.

    xAI (grok) API rejects any message with empty/null content.
    This hook sanitizes all message types and prepends the system prompt,
    returning them via `llm_input_messages` so the stored state is never mutated.
    """
    sanitized = sanitize_messages(state["messages"])
    return {"llm_input_messages": [SystemMessage(content=SYSTEM_PROMPT)] + sanitized}


# ****************************************
# Model and graph setup with fallback support for high-demand scenarios.
# ****************************************
_CACHED_GRAPH = None


def _create_llm():
    """Create LLM instance with the currently active model."""
    return ChatGoogleGenerativeAI(
        google_api_key=GOOGLE_API_KEY,
        model=get_model_name(),
        temperature=TEMPERATURE,
    )


def get_dental_graph():
    """Get the dental graph, rebuilt with the currently active model."""
    global _CACHED_GRAPH
    
    # Always create a fresh graph to pick up any model changes
    llm = _create_llm()
    _CACHED_GRAPH = create_react_agent(model=llm, tools=TOOLS, pre_model_hook=_pre_model_hook)
    
    return _CACHED_GRAPH


# Build the default graph
dental_graph = get_dental_graph()
