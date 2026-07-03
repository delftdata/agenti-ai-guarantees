"""Thin wrapper: run the ``agent_guarantees.llm_lab.profile_plans`` main block.

Requires the ``llm`` extra and a GOOGLE_API_KEY (see README, Track 2):
    pip install -e .[llm]
    python scripts/run_profile_plans.py
"""
import runpy

if __name__ == "__main__":
    runpy.run_module("agent_guarantees.llm_lab.profile_plans", run_name="__main__")
