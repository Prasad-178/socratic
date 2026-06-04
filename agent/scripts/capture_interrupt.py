"""Drive the real AG-UI bridge and print the interrupt event the frontend sees."""
import asyncio
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from copilotkit import LangGraphAGUIAgent

from src.graph import compile_graph
from src.ingest import ingest_document


async def main():
    ingest_document(Path("../samples/finance_time_value_money.pdf"), "cap-doc")
    agent = LangGraphAGUIAgent(
        name="socratic", description="x", graph=compile_graph(InMemorySaver())
    )

    # Build a RunAgentInput however the installed ag_ui exposes it.
    from ag_ui.core import RunAgentInput

    inp = RunAgentInput(
        thread_id="cap-1",
        run_id="run-1",
        state={"document_id": "cap-doc"},
        messages=[],
        tools=[],
        context=[],
        forwarded_props={},
    )

    print("--- events ---")
    async for ev in agent.run(inp):
        et = str(getattr(ev, "type", ""))
        name = getattr(ev, "name", None)
        if "INTERRUPT" in et.upper() or "CUSTOM" in et.upper() or name == "on_interrupt":
            val = getattr(ev, "value", None)
            print(f"EVENT type={et} name={name}")
            print(f"  value={val!r}")
    print("--- done ---")


if __name__ == "__main__":
    asyncio.run(main())
