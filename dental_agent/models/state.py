"""
****************************************
Shared conversation state for graph nodes.
****************************************
"""

from typing import TypedDict, Annotated, Literal, Optional, List
from langchain_core.messages import BaseMessage
import operator

# ****************************************
# Shared enums keep routing values predictable.
# ****************************************
IntentType = Literal[
    "get_info",
    "book",
    "cancel",
    "reschedule",
    "unknown",
    "end",
]

RouteTarget = Literal[
    "info_agent",
    "booking_agent",
    "cancellation_agent",
    "rescheduling_agent",
    "end",
]

# ****************************************
# Conversation state travels through every graph node.
# ****************************************
class AppointmentState(TypedDict):
    # Preserves the shared chat trail across node handoffs.
    messages: Annotated[List[BaseMessage], operator.add]

    # Stores the supervisor's latest routing choice.
    intent: Optional[IntentType]
    next_agent: Optional[RouteTarget]

    # Keeps captured booking details between turns.
    patient_id: Optional[str]
    requested_specialization: Optional[str]
    requested_doctor: Optional[str]
    requested_date_slot: Optional[str]

    # Tracks both slots so reschedules stay explicit.
    current_date_slot: Optional[str]
    new_date_slot: Optional[str]

    # Carries tool results into the next reply.
    available_slots: Optional[List[dict]]
    operation_success: Optional[bool]
    operation_message: Optional[str]

    # Holds the final reply for the active surface.
    final_response: Optional[str]
