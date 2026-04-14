"""
****************************************
CLI entry point for local dental agent testing.
****************************************
"""

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

# ****************************************
# Environment bootstrap keeps local runs simple.
# ****************************************
# Loads local environment values so the CLI works without extra shell setup.
load_dotenv(override=True)

import json

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage

_WORKFLOW_GRAPH = None

# ****************************************
# Terminal banner shows sample prompts for demos.
# ****************************************
BANNER = """
╔══════════════════════════════════════════════════════════╗
║         Dental Appointment Management System             ║
║         Powered by LangGraph + Gemini                    ║
╚══════════════════════════════════════════════════════════╝
Examples:
  • Show available slots for an orthodontist
  • Book patient 1000082 with Emily Johnson on 5/10/2026 9:00
  • Cancel appointment for patient 1000082 at 5/10/2026 9:00
  • Reschedule patient 1000082 from 5/10/2026 9:00 to 5/12/2026 10:00
  • What appointments does patient 1000048 have?

Type 'quit' to exit.
"""

# ****************************************
# Content helpers normalize streamed model output.
# ****************************************
def _content_to_text(content) -> str:
    """Normalize model payloads so CLI output stays readable."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "".join(parts)

    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]

    return str(content) if content is not None else ""


def _shorten_trace_value(value, limit: int = 180) -> str:
    """Keep trace output compact enough for the side panel."""
    text = _content_to_text(value).strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _format_tool_args(args) -> str:
    """Render tool arguments in a compact, readable trace format."""
    if args in (None, "", {}, []):
        return ""

    try:
        return json.dumps(args, ensure_ascii=True, default=str)
    except TypeError:
        return str(args)

# ****************************************
# Shared message processing powers both CLI and UI.
# ****************************************
def _get_workflow_graph():
    """Build the supervisor-driven workflow only when a chat turn actually needs it."""
    global _WORKFLOW_GRAPH

    if _WORKFLOW_GRAPH is None:
        from dental_agent.workflows.graph import dental_graph

        _WORKFLOW_GRAPH = dental_graph

    return _WORKFLOW_GRAPH


def _is_503_unavailable_error(exc: Exception) -> bool:
    """Detect if an exception is a 503 UNAVAILABLE error from Gemini API."""
    error_msg = str(exc).lower()
    return "503" in error_msg and "unavailable" in error_msg


def _emit_stream_trace(
    chunk,
    meta,
    seen_nodes: set[str],
    seen_tool_calls: set[str],
    seen_streaming_nodes: set[str],
    emit_trace,
) -> tuple[bool, str | None]:
    """Capture streamed node, tool-call, and response events from LangGraph."""
    node_name = meta.get("langgraph_node") if isinstance(meta, dict) else None
    if node_name and node_name not in seen_nodes:
        seen_nodes.add(node_name)
        emit_trace("Backend step entered", node_name)

    if isinstance(chunk, AIMessageChunk) and getattr(chunk, "tool_calls", None):
        for tool_call in chunk.tool_calls:
            tool_name = tool_call.get("name", "tool")
            tool_id = tool_call.get("id") or f"{tool_name}:{tool_call.get('args')}"
            if tool_id in seen_tool_calls:
                continue
            seen_tool_calls.add(tool_id)
            emit_trace(
                "Tool requested",
                f"{tool_name}({_format_tool_args(tool_call.get('args'))})",
            )

    if (
        isinstance(chunk, AIMessageChunk)
        and chunk.content
        and not getattr(chunk, "tool_calls", None)
    ):
        stream_node = node_name or "agent"
        if stream_node not in seen_streaming_nodes:
            seen_streaming_nodes.add(stream_node)
            emit_trace("LLM response streaming", stream_node)
        return True, node_name

    return False, node_name


def _emit_value_trace(
    final_messages,
    previous_message_count: int,
    emit_trace,
    include_tool_messages: bool = True,
) -> int:
    """Capture tool results and finalized assistant replies from the accumulated state."""
    new_messages = final_messages[previous_message_count:]

    for message in new_messages:
        if include_tool_messages and isinstance(message, ToolMessage):
            tool_name = getattr(message, "name", None) or "tool"
            emit_trace("Tool result received", f"{tool_name}: {_shorten_trace_value(message.content)}")
        elif isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            content = _shorten_trace_value(message.content)
            if content:
                emit_trace("Assistant response finalized", content)

    return len(final_messages)


def _emit_workflow_update_trace(node_name: str, node_update: dict, emit_trace) -> None:
    """Summarize node-level updates from the supervisor workflow."""
    if node_name == "supervisor":
        next_agent = node_update.get("next_agent", "unknown")
        intent = node_update.get("intent", "unknown")
        emit_trace("Supervisor routed request", f"intent={intent}, next={next_agent}")
        return

    if node_name.endswith("_agent"):
        final_response = _shorten_trace_value(node_update.get("final_response"))
        if final_response:
            emit_trace("Specialist replied", f"{node_name}: {final_response}")
        else:
            emit_trace("Specialist agent ran", node_name)
        return

    if node_name.endswith("_tools"):
        messages = node_update.get("messages", [])
        if messages:
            for message in messages:
                if isinstance(message, ToolMessage):
                    tool_name = getattr(message, "name", None) or node_name
                    emit_trace("Tool node completed", f"{tool_name}: {_shorten_trace_value(message.content)}")
        else:
            emit_trace("Tool node completed", node_name)


def process_user_message(
    history,
    user_input: str,
    trace_callback=None,
    return_trace: bool = False,
):
    """Run one user turn through the supervisor-driven workflow for both CLI and UI.
    
    Automatically falls back to gemini-1.5-flash if gemini-2.5-flash returns 503.
    """
    working_history = list(history)
    working_history.append(HumanMessage(content=user_input))

    final_messages = None
    response_chunks = []
    trace_entries = []
    seen_nodes = set()
    seen_tool_calls = set()
    seen_streaming_nodes = set()
    previous_message_count = len(working_history)

    def emit_trace(step: str, details: str = "") -> None:
        message = step if not details else f"{step}: {details}"
        trace_entries.append(message)
        if trace_callback is not None:
            trace_callback(message)

    emit_trace("User request received", _shorten_trace_value(user_input, limit=120))
    emit_trace("LangGraph run started", "Streaming the supervisor-driven multi-agent workflow")
    
    # Try with the configured model first, fall back to gemini-1.5-flash on 503
    graph = _get_workflow_graph()
    stream_modes = ["updates", "messages", "values"]

    try:
        for event_type, data in graph.stream(
            {"messages": working_history},
            stream_mode=stream_modes,
            config={"recursion_limit": 20},
        ):
            if event_type == "messages":
                chunk, meta = data
                # Keep the console response clean by skipping tool payloads.
                should_append, node_name = _emit_stream_trace(
                    chunk,
                    meta,
                    seen_nodes,
                    seen_tool_calls,
                    seen_streaming_nodes,
                    emit_trace,
                )
                if should_append and node_name != "supervisor":
                    response_chunks.append(_content_to_text(chunk.content))
            elif event_type == "updates" and isinstance(data, dict):
                for node_name, node_update in data.items():
                    if isinstance(node_update, dict):
                        _emit_workflow_update_trace(node_name, node_update, emit_trace)
            elif event_type == "values" and isinstance(data, dict):
                final_messages = data.get("messages", [])
                previous_message_count = _emit_value_trace(
                    final_messages,
                    previous_message_count,
                    emit_trace,
                    include_tool_messages=False,
                )
    except Exception as exc:
        # If 503 error, switch to fallback model and retry once
        if _is_503_unavailable_error(exc):
            emit_trace("Model overloaded", "Retrying with gemini-1.5-pro")
            from dental_agent.config.settings import set_model_name
            from dental_agent.agent import get_dental_graph
            
            # Reset state for retry
            response_chunks = []
            seen_nodes = set()
            seen_tool_calls = set()
            seen_streaming_nodes = set()
            previous_message_count = len(working_history)
            
            # Switch model and rebuild workflow graph
            set_model_name("gemini-1.5-pro")
            graph = get_dental_graph()
            
            # Retry with fallback model
            try:
                for event_type, data in graph.stream(
                    {"messages": working_history},
                    stream_mode=stream_modes,
                    config={"recursion_limit": 20},
                ):
                    if event_type == "messages":
                        chunk, meta = data
                        should_append, node_name = _emit_stream_trace(
                            chunk,
                            meta,
                            seen_nodes,
                            seen_tool_calls,
                            seen_streaming_nodes,
                            emit_trace,
                        )
                        if should_append and node_name != "supervisor":
                            response_chunks.append(_content_to_text(chunk.content))
                    elif event_type == "updates" and isinstance(data, dict):
                        for node_name, node_update in data.items():
                            if isinstance(node_update, dict):
                                _emit_workflow_update_trace(node_name, node_update, emit_trace)
                    elif event_type == "values" and isinstance(data, dict):
                        final_messages = data.get("messages", [])
                        previous_message_count = _emit_value_trace(
                            final_messages,
                            previous_message_count,
                            emit_trace,
                            include_tool_messages=False,
                        )
                    emit_trace("Retry succeeded", "Using gemini-1.5-pro due to high demand on 2.5-flash")
            except Exception as fallback_exc:
                # Log the fallback failure but raise the original error
                emit_trace("Fallback failed", str(fallback_exc)[:120])
                raise exc  # Re-raise original 503 error
        else:
            # Re-raise if not a 503 error
            raise

    response_text = "".join(response_chunks).strip()
    updated_history = final_messages if final_messages else working_history

    if not response_text and final_messages:
        for msg in reversed(final_messages):
            content = _content_to_text(getattr(msg, "content", "")).strip()
            if content:
                response_text = content
                break

    final_response = response_text or "I wasn't able to generate a response."
    emit_trace("Run completed", _shorten_trace_value(final_response))

    if return_trace:
        return final_response, updated_history, trace_entries
    return final_response, updated_history

# ****************************************
# Interactive CLI loop supports quick manual testing.
# ****************************************
def run():
    """Provide a simple terminal loop for manual checks and demos."""
    print(BANNER)
    history = []

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "bye"}:
            print("Goodbye!")
            break

        print("\nAgent: ", end="", flush=True)

        try:
            response_text, history = process_user_message(history, user_input)
            print(response_text)
        except Exception as exc:
            print(f"\nError: {exc}")
            continue


if __name__ == "__main__":
    run()
