# Parallelization methodology

Operationalizes the team's requirement: impose parallelization level as the variable, measure correctness, cost, and failure type against it. Companion to `failure_definition.md`; together they specify the real-agent study.

## The variable

**Parallelization level k**: the maximum number of ready plan nodes admitted per superstep. k = 1 is sequential; k = W (the plan's parallelizable width) is full parallel; intermediate k gives the curve the team asked for (failure type by level, failure count vs cost), not three buckets.

**Dependency violation is a separate switch, not a larger k.** Admitting nodes whose parents have not committed is a different variable from admitting more ready nodes. The over-parallel condition from the deterministic rig becomes: admission ignores dependencies, full width. Grading k measures the cost of parallelism; the switch measures the cost of violating the plan.

## The grid

| Axis | Values |
|---|---|
| Parallelization level | k in {1, 2, ..., W}, dependencies respected |
| Dependency violation | off for the k-sweep; on as two extra cells at full width |
| Discipline | disciplined (channels + reducers) / free-for-all (per `failure_definition.md`: last-write-wins rung for validation, external shared store for the headline grid) |

Expected signatures, from the rig: cost falls with k while correctness holds under discipline; free-for-all loses updates once k exceeds 1; stale reads appear only with the violation switch on, either discipline.

## Task set

Constructed tasks with ground-truth checks and known width by construction:

1. **Fan-out** (source, W independent workers, sink) - the rig's plan with real agents; W = 5 to start.
2. **Mixed structure** (two fan-out stages with a synchronization point between them, diamond-shaped) - separates "parallelism within a stage" from "ordering across stages"; stale reads have a non-trivial place to occur mid-plan.
3. **Sequential control** (true W = 1) - anchors the agent-chosen-width sub-study and checks that k has no effect when no parallelism exists.
4. **One real task**, after the constructed grid is in, chosen so a ground-truth check still exists.

The agent-chosen-width sub-study (memo 3) runs on the same tasks: let the agent plan, extract the plan's width, compare to W.

## Runs and reporting

The external-store condition is timing-dependent, so cells are repeated. I would recommend 10 runs per cell to start, adjusted after the first cost numbers. Per run we record: task-level correct, coordination failures by type with localization, tokens, wall-clock, superstep count. Per cell we report correctness rate, failure counts by type, and mean cost with min-max range. Recovery classification (genuine vs claimed, per `failure_definition.md`) runs offline over the same per-run logs; it is the second cut and adds no instrumentation.

## Decisions needing sign-off

- Grading k, rather than keeping the rig's three levels. I would recommend the grading; the three rig levels remain as the k = 1, k = W, and violation-on points of the same grid, so nothing is lost.
- W = 5, the mixed-structure task shape, and 10 repeats per cell as starting values.
