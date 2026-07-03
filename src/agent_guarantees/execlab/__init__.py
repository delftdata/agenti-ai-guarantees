"""agent_guarantees.execlab — deterministic execution-topology rig."""

from .rig import (
    DISCIPLINES,
    TOPOLOGIES,
    make_fanout_plan,
    parallelizable_width,
    run_experiment,
)

__all__ = [
    "DISCIPLINES",
    "TOPOLOGIES",
    "make_fanout_plan",
    "parallelizable_width",
    "run_experiment",
]
