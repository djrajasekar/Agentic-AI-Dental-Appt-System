"""
****************************************
CLI entry point for local dental agent testing.
****************************************
"""

from dotenv import load_dotenv

# ****************************************
# Environment bootstrap keeps local runs simple.
# ****************************************
# Loads local environment values so the CLI works without extra shell setup.
load_dotenv()

from langchain_core.messages import HumanMessage, AIMessageChunk
from dental_agent.agent import dental_graph

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

# ****************************************
# Shared message processing powers both CLI and UI.
# ****************************************
def process_user_message(history, user_input: str):
    """Run one user turn through the shared graph so the CLI and Streamlit UI behave the same way."""
    working_history = list(history)
    working_history.append(HumanMessage(content=user_input))

    final_messages = None
    response_chunks = []

    # Stream both partial text and the final state so the next turn keeps full context.
    for event_type, data in dental_graph.stream(
        {"messages": working_history},
        stream_mode=["messages", "values"],
        config={"recursion_limit": 20},
    ):
        if event_type == "messages":
            chunk, meta = data
            # Keep the console response clean by skipping tool payloads.
            if (
                isinstance(chunk, AIMessageChunk)
                and chunk.content
                and not getattr(chunk, "tool_calls", None)
            ):
                response_chunks.append(_content_to_text(chunk.content))
        elif event_type == "values" and isinstance(data, dict):
            final_messages = data.get("messages", [])

    response_text = "".join(response_chunks).strip()
    updated_history = final_messages if final_messages else working_history

    if not response_text and final_messages:
        for msg in reversed(final_messages):
            content = _content_to_text(getattr(msg, "content", "")).strip()
            if content:
                response_text = content
                break

    return response_text or "I wasn't able to generate a response.", updated_history

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
