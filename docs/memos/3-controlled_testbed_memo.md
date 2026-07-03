# A controlled testbed for coordination failures

I ran a known plan under different concurrency and state-sharing conditions and measured correctness and cost. It runs on constructed plans with no LLMs, so each condition gives a fixed, reproducible result.

## What it runs

A known DAG with known parallelism: one source, N independent workers each adding 1, one sink that reads the total. The correct result is N. Two knobs:

- Topology: sequential / parallel / over-parallel. Over-parallel starts every task at once, ignoring dependencies.
- Discipline: synchronized (each worker writes its own key, a reducer sums them) / free-for-all (all workers read-modify-write one shared key).

Execution is deterministic, via two-phase rounds with no real threads. The grid below is produced by a script with offline tests.

## What it shows (width 5)

| topology × discipline | correct | result | failure | cost |
|---|---|---|---|---|
| sequential, either discipline | yes | 5 | none | 7 |
| parallel, disciplined | yes | 5 | none | 3 |
| parallel, free-for-all | no | 1 | write-race (4 updates lost) | 3 |
| over-parallel, either discipline | no | 0 | stale-read (sink read before workers wrote) | 1 |

## Finding

Disciplined parallel execution is correct and cheaper than sequential. Free-for-all makes concurrent writes collide and lose updates. Over-parallelizing past the dependencies makes consumers read stale state. The two coordination failures, write-race and stale-read, are reproduced and distinguished deterministically.

## Can't parallelize vs. decided not to

Sequentiality has three possible sources: the task, the framework, or the agent's own plan. MAD settles only the framework case, and only for ChatDev: the ChatChain hard-codes the phase sequence, so its sequential plans are a framework decision, not a task constraint. Whether a task could have been parallelized, or whether a plan-generating agent would choose to, is unrecoverable from execution logs. Both are resolvable on constructed tasks, where available parallelism is known by construction.

The procedure: give the agent a task whose plan DAG has known width *w* greater than 1, let it produce its own plan, and extract that plan's width with the same Dilworth routine used throughout. Three outcomes per task: width *w* (parallelism found and taken), between 1 and *w* (partially taken), width 1 (a decision, not a constraint, since *w* exceeds 1 by construction). A sequential control task, true width 1, separates correctly-sequential from defaulted-to-sequential.

This slots into the real-agent study as a sub-study on the same task set: the imposed-topology grid answers what parallelization does to correctness and cost; this answers what parallelization the agent chooses when it is available. I would recommend we report both, since the gap between chosen and available width is the plan-vs-execution gap measured at the planning end.

## Next step

Plug real LLM agents via LangGraph.
