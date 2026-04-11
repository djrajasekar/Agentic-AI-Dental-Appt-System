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
from dental_agent.tools.sqllite_writer import book_appointment, book_first_available_appointment
from dental_agent.utils import sanitize_messages

# ****************************************
# Booking-only tools keep this agent narrowly focused.
# ****************************************
# Keep this agent limited to booking-safe tools so its behavior stays predictable.
BOOKING_TOOLS = [
    get_available_slots,
    check_slot_availability,
    book_appointment,
    book_first_available_appointment,
]

BOOKING_SYSTEM = """You are the Booking Agent for a dental appointment management system.

Your ONLY job is to book NEW appointments for patients.

## Workflow
1. Collect REQUIRED information (ask if missing):
   - patient_id       : numeric patient ID (e.g., 1000082)
    - specialization   : the type of dentist needed when the doctor is not already given
    - doctor_name      : specific doctor when the user names one
    - date_slot        : desired date/time in M/D/YYYY H:MM format when the user wants an exact slot
    - date_filter / part_of_day : use these when the user gives a day and a flexible window like morning

2. For an exact requested time, call check_slot_availability first to confirm the slot is free.
   - If the slot is taken, call get_available_slots to show alternatives.

3. For flexible requests such as "morning", "afternoon", "evening", "first available", or "if available book it":
    - Call get_available_slots or book_first_available_appointment instead of asking for an exact time immediately.
    - If the user has already authorized booking and the request is flexible, prefer book_first_available_appointment.

4. Once confirmed available, call book_appointment with all parameters, or use book_first_available_appointment when the user asked for the first matching flexible slot.

5. Confirm the booking to the user with all details.

## Rules
- NEVER book without first verifying availability via check_slot_availability.
- For flexible time-window requests, you may use book_first_available_appointment because it checks and books the earliest matching open slot in one step.
- If a slot is taken, proactively offer alternatives using get_available_slots.
- Be explicit about what was booked: doctor, date, time, patient ID.
- Ask for ONE missing piece of information at a time.
- If no matching slot exists on the requested day, say that clearly instead of asking for a more specific time.

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
