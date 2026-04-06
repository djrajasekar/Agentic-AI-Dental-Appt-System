"""
****************************************
Workflow builder for the multi-agent flow.
****************************************
"""

from langgraph.graph import StateGraph, START, END
from langchain_core.messages import AIMessage

from dental_agent.models.state import AppointmentState
from dental_agent.agents.supervisor import supervisor_node
from dental_agent.agents.info_agent import info_agent_node, info_tool_node
from dental_agent.agents.booking_agent import booking_agent_node, booking_tool_node
from dental_agent.agents.cancellation_agent import cancellation_agent_node, cancellation_tool_node
from dental_agent.agents.rescheduling_agent import rescheduling_agent_node, rescheduling_tool_node

# ****************************************
# Routing helpers for graph transitions.
# ****************************************
def route_from_supervisor(state: AppointmentState) -> str:
    """Keep routing safe when the supervisor returns an unexpected value."""
    target = state.get("next_agent", "info_agent")
    valid = {"info_agent", "booking_agent", "cancellation_agent", "rescheduling_agent", "end"}
    return target if target in valid else "info_agent"


def _should_continue(state: AppointmentState) -> str:
    """Skip extra routing once an agent has finished its reply."""
    messages = state.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage) and messages[-1].tool_calls:
        return "tools"
    return "end"


def build_graph():
    """Wire the supervisor and specialist agents into a single request-to-reply workflow."""
    graph = StateGraph(AppointmentState)

    # ****************************************
    # Register each node so the workflow stays explicit.
    # ****************************************
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("info_agent", info_agent_node)
    graph.add_node("info_tools", info_tool_node)
    graph.add_node("booking_agent", booking_agent_node)
    graph.add_node("booking_tools", booking_tool_node)
    graph.add_node("cancellation_agent", cancellation_agent_node)
    graph.add_node("cancellation_tools", cancellation_tool_node)
    graph.add_node("rescheduling_agent", rescheduling_agent_node)
    graph.add_node("rescheduling_tools", rescheduling_tool_node)

    # ****************************************
    # Start at the supervisor for intent detection.
    # ****************************************
    graph.add_edge(START, "supervisor")

    # ****************************************
    # Let the supervisor pick the specialist route.
    # ****************************************
    graph.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {
            "info_agent": "info_agent",
            "booking_agent": "booking_agent",
            "cancellation_agent": "cancellation_agent",
            "rescheduling_agent": "rescheduling_agent",
            "end": END,
        },
    )

    # ****************************************
    # Info loop keeps answering until no more tools are needed.
    # ****************************************
    graph.add_conditional_edges(
        "info_agent",
        _should_continue,
        {"tools": "info_tools", "end": END},
    )
    graph.add_edge("info_tools", "info_agent")

    # ****************************************
    # Booking loop keeps collecting and confirming details.
    # ****************************************
    graph.add_conditional_edges(
        "booking_agent",
        _should_continue,
        {"tools": "booking_tools", "end": END},
    )
    graph.add_edge("booking_tools", "booking_agent")

    # ****************************************
    # Cancellation loop protects the confirmation flow.
    # ****************************************
    graph.add_conditional_edges(
        "cancellation_agent",
        _should_continue,
        {"tools": "cancellation_tools", "end": END},
    )
    graph.add_edge("cancellation_tools", "cancellation_agent")

    # ****************************************
    # Rescheduling loop keeps the move process explicit.
    # ****************************************
    graph.add_conditional_edges(
        "rescheduling_agent",
        _should_continue,
        {"tools": "rescheduling_tools", "end": END},
    )
    graph.add_edge("rescheduling_tools", "rescheduling_agent")

    return graph.compile()

# ****************************************
# Compile the shared workflow once for app entrypoints.
# ****************************************
dental_graph = build_graph()
