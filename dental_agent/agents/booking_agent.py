"""
****************************************
Booking specialist for new appointments.
****************************************
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import ToolNode
from dental_agent.config.settings import GOOGLE_API_KEY, MODEL_NAME, TEMPERATURE
from dental_agent.models.state import AppointmentState
from dental_agent.tools.sqllite_reader import get_available_slots, check_slot_availability
from dental_agent.tools.sqllite_writer import book_appointment
from dental_agent.utils import sanitize_messages

# ****************************************
# Booking-only tools keep this agent narrowly focused.
# ****************************************
# Keep this agent limited to booking-safe tools so its behavior stays predictable.
BOOKING_TOOLS = [get_available_slots, check_slot_availability, book_appointment]

BOOKING_SYSTEM = """You are the Booking Agent for a dental appointment management system.

Your ONLY job is to book NEW appointments for patients.

## Workflow
1. Collect REQUIRED information (ask if missing):
   - patient_id       : numeric patient ID (e.g., 1000082)
   - specialization   : the type of dentist needed
   - doctor_name      : specific doctor (or help user choose from available)
   - date_slot        : desired date/time in M/D/YYYY H:MM format

2. Call check_slot_availability first to confirm the slot is free.
   - If the slot is taken, call get_available_slots to show alternatives.

3. Once confirmed available, call book_appointment with all parameters.

4. Confirm the booking to the user with all details.

## Rules
- NEVER book without first verifying availability via check_slot_availability.
- If a slot is taken, proactively offer alternatives using get_available_slots.
- Be explicit about what was booked: doctor, date, time, patient ID.
- Ask for ONE missing piece of information at a time.

## Date Format
M/D/YYYY H:MM (e.g., 5/10/2026 9:00)
"""

BOOKING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", BOOKING_SYSTEM),
    ("placeholder", "{messages}"),
])

booking_tool_node = ToolNode(tools=BOOKING_TOOLS)

# ****************************************
# Agent entrypoint returns either tool calls or the reply.
# ****************************************
def booking_agent_node(state: AppointmentState) -> dict:
    """Run the booking specialist and return either tool calls or the final reply."""
    llm = ChatGoogleGenerativeAI(
        google_api_key=GOOGLE_API_KEY,
        model=MODEL_NAME,
        temperature=TEMPERATURE,
    ).bind_tools(BOOKING_TOOLS)

    chain = BOOKING_PROMPT | llm
    response = chain.invoke({"messages": sanitize_messages(state["messages"])})
    return {
        "messages": [response],
        "final_response": response.content if not response.tool_calls else None,
    }
