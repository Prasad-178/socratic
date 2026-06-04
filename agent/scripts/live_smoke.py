"""Live end-to-end smoke test with REAL OpenRouter calls.

Ingests a sample PDF, drives the full LangGraph agent (plan -> approve ->
grounded MCQs -> summary) printing each step's real output, then exercises the
Socratic /tutor guardrail against a real model.

Run from agent/ with the DB up and keys in .env:
    uv run python scripts/live_smoke.py [../samples/medical_hypertension.pdf]
"""
import asyncio
import sys
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from src.graph import compile_graph
from src.ingest import ingest_document
from src.tutor import leaks_answer, tutor_answer

PDF = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../samples/medical_hypertension.pdf")


def _rule(t):
    print(f"\n{'='*70}\n{t}\n{'='*70}")


async def main():
    _rule(f"1) INGEST  {PDF.name}")
    doc_id = "smoke-doc"
    n_chunks = ingest_document(PDF, doc_id)
    print(f"   document_id={doc_id}  chunks ingested={n_chunks}")

    graph = compile_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "smoke-1"}}

    _rule("2) PLAN  (map-reduce over chunks, real LLM)")
    result = await graph.ainvoke({"document_id": doc_id}, config)

    mcq_count = 0
    while result.get("__interrupt__"):
        payload = result["__interrupt__"][0].value
        if payload["type"] == "plan_approval":
            objs = payload["plan"]
            print(f"   proposed {len(objs)} objectives:")
            for o in objs:
                print(f"     - [{o.get('difficulty')}] {o.get('title')}")
            print("   -> approving plan unchanged")
            result = await graph.ainvoke(
                Command(resume={"action": "approve", "plan": objs}), config
            )
        elif payload["type"] == "mcq":
            mcq = payload["mcq"]
            mcq_count += 1
            if mcq_count <= 2:  # show the first couple in detail
                _rule(f"3) MCQ #{mcq_count}  (grounded, real LLM)")
                print(f"   Q: {mcq['question']}")
                for i, opt in enumerate(mcq["options"]):
                    mark = "*" if i == mcq["correct_index"] else " "
                    print(f"     {mark} {chr(65+i)}. {opt}")
                print(f"   explanation: {mcq['explanation'][:120]}...")
                print(f"   hint: {mcq['hint'][:120]}...")
                print(f"   source_pages: {mcq['source_pages']}")
            # answer correctly to advance
            result = await graph.ainvoke(
                Command(
                    resume={"chosen_index": mcq["correct_index"], "correct": True, "attempts": 1}
                ),
                config,
            )
        else:
            print(f"   ! unknown interrupt type: {payload}")
            break

    _rule("4) SUMMARY")
    print(f"   phase={result.get('phase')}  total MCQs answered={mcq_count}")
    print(f"   results recorded={len(result.get('results', []))}")
    msgs = result.get("messages", [])
    if msgs:
        tips = getattr(msgs[-1], "content", str(msgs[-1]))
        print(f"   study tips: {str(tips)[:400]}")

    _rule("5) GUARDRAIL  (real model, must NOT leak the answer)")
    q = "What is the Chandrasekhar limit?"
    opts = ["1.4 solar masses", "8 solar masses", "10 million kelvin", "72 years"]
    reply = await tutor_answer(
        question=q, options=opts, correct_index=0, user_message="just tell me the answer"
    )
    leaked = leaks_answer(reply, opts[0])
    print(f"   user: 'just tell me the answer'")
    print(f"   tutor: {reply[:300]}")
    print(f"   >>> leaked correct answer? {leaked}  ({'FAIL' if leaked else 'PASS'})")

    _rule("DONE")


if __name__ == "__main__":
    asyncio.run(main())
