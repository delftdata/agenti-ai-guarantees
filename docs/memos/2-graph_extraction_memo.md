# Plan-graph extraction from execution logs: a methodological boundary

I ran the plan-graph step on the MAD traces and gathered statistics (fan-out, input nodes, task count). Executing this step surfaced a boundary: the structural statistics are either non-discriminative or not recoverable from execution logs.

## The steps

For each ChatDev trace I build a plan-graph: nodes are agent exchanges plus code writes and runs; edges are execution sequence plus state-access (each write to the shared code, and the steps that depend on it). On that graph I compute the statistics: node count, fan-out, dependency depth, and parallelizable width.

## Finding: parallelizable width

The key parallelism statistic cannot be extracted from an execution log at all. Two defensible graph models bracket the truth and sit at opposite degenerate extremes:

| Model | dependency edges | width (n=130) |
|---|---|---|
| spine | consecutive execution order | exactly 1, every trace (depth = n−1) |
| state-only | code read/write only | 32–55, median 34 |

The spine model encodes *execution order* as dependency, so the graph is necessarily a single chain. The state-only model encodes only code dependencies, so the agent exchanges appear mutually independent and width inflates to ~34. The true width requires message-level data-flow analysis that is not recoverable from the log.

Separately, ChatDev is a sequential pipeline by architecture, the ChatChain is a fixed phase sequence, and every run executes the same 12 phases, so the true width is low regardless.

## What this implies

The boundary it reveals is structural, and it generalises: the plan → graph → statistics step *and* the subsequent run-versus-plan step both presuppose a clean, recoverable plan, and an execution log does not contain one.

The same steps become clean and meaningful on a **constructed** plan, where the dependency structure, and therefore the width, is known by definition rather than inferred. Plan structure for this study must be constructed, not extracted.

## Conclusion

The boundary - plan structure is not recoverable from execution logs. Together with the confound finding (observation cannot isolate topology causally), I would recommend we construct controlled plans rather than mine existing traces.
