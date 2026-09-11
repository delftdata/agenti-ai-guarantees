"""Scratch probe: does LangGraph's ``add_conditional_edges`` accept a list map?

Compares the list form against the dict form and prints the compiled mermaid
diagram for visual inspection. Prints results; asserts nothing.

Requires the ``llm`` extra. Run from the repo root:
    python scripts/probe_conditional_edges.py
"""
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

class State(TypedDict):
    pass

def dummy(state): pass
def router(state): pass

builder = StateGraph(State)
builder.add_node("parallel_worker", dummy)
try:
    builder.add_conditional_edges(START, router, ["parallel_worker"])
    print("List map worked!")
except Exception as e:
    print("List map failed:", e)

builder2 = StateGraph(State)
builder2.add_node("parallel_worker", dummy)
try:
    builder2.add_conditional_edges(START, router, {"parallel_worker": "parallel_worker"})
    print("Dict map worked!")
except Exception as e:
    print("Dict map failed:", e)

print(builder.compile().get_graph().draw_mermaid())
