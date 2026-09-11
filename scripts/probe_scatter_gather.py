"""Scratch probe: smoke-run the scatter-gather graph against a mocked LLM.

Stubs GOOGLE_API_KEY and swaps ``profile_plans.llm`` for a MagicMock so the
graph can be invoked offline. Prints a success line; asserts nothing.

Requires the ``llm`` extra. Run from the repo root:
    python scripts/probe_scatter_gather.py
"""
import os
os.environ["GOOGLE_API_KEY"] = "dummy"
import sys
from agent_guarantees.llm_lab.profile_plans import build_scatter_gather_graph
import agent_guarantees.llm_lab.profile_plans as pp

from unittest.mock import MagicMock
mock_llm = MagicMock()
class MockResponse:
    content = [{"type": "text", "text": "mocked code"}]
    usage_metadata = {"total_tokens": 10}
mock_llm.invoke.return_value = MockResponse()
pp.llm = mock_llm

sg = build_scatter_gather_graph()
result = sg.invoke({"task_goal": "goal", "plan": ["task1", "task2"]})
print("Result is OK!")
