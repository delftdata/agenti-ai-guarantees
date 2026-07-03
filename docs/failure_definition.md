# Failure definition

Operational definitions for the real-agent study. Every detector in the study implements one row of this document.

## Two levels, recorded independently

**Task-level failure**: the run's final result does not verify against the task's reference. Every task in the study's task set ships with a ground-truth check.

**Coordination-level failure**: a state-access anomaly during execution, independent of the final outcome. A lost update can be masked and the run still passes; a run can fail with clean coordination. I would recommend we record the two levels independently per run; otherwise the failure-count-vs-cost analysis conflates mechanism with outcome.

## Setting

A constructed plan DAG executed by LangGraph. LangGraph nodes receive the whole state, so reads are not observable at runtime: **read-sets are declared** at task construction, **write-sets are observed** from state updates. Exact for constructed tasks; dynamic read/write discovery is out of scope for this phase.

## Definitions, detection, localization

| Failure | Definition | Detection | Localization |
|---|---|---|---|
| Wrong result | final result differs from the reference | ground-truth check at the sink | run level |
| Lost update (write-race) | two or more nodes write the same key concurrently under free-for-all state access; all but one write is discarded | more than one write to key *k* in superstep *s* in the write log, surviving value is not the reduction of all writes | overwritten writers, surviving writer, key, superstep |
| Stale read | a node executes before some dependency parent's write has committed | a parent of the node is absent from the write log of all earlier supersteps, for a key in the node's read-set | reading node, missed parent, key, superstep |

## Constructing the free-for-all condition

Stock LangGraph with proper reducers cannot lose updates: concurrent unreduced writes raise an error, reduced writes merge. Channel discipline is the disciplined condition by definition, so the free-for-all baseline has to be constructed. Two constructions:

- **Last-write-wins reducer** on a shared key. Superstep semantics guarantee the loss (all workers read the step's start snapshot, one write survives). Deterministic; observed in LangGraph's own update stream.
- **External shared store** mutated through tool calls, outside the channels. Real interleaving on a side-effect surface, matching the mechanism in the MAD traces. Timing-dependent, so it needs repeated runs; observed in the store's write log, which we instrument.

I would recommend both, in sequence: the last-write-wins reducer as the validation rung, reproducing the deterministic rig inside LangGraph one-to-one to confirm the detectors, and the external store for the headline grid, since it is the condition the paper's claim is about.

## Observation points

Per superstep: index, nodes executed, per-node keys written, value hashes - from LangGraph's update stream and checkpointer, plus the store's write log under the external-store construction. Plan DAG and read-sets come from construction. Detectors run offline over this log; nothing is instrumented inside the agents. Event naming follows llmmas-otel conventions, reimplemented.

## Classification and recovery

Mechanism first: {wrong-result, lost-update, stale-read}, with count and location per run. MAST 2.x remains the corpus vocabulary; assigning a mechanism to a MAST mode stays per-exemplar and qualitative. A correction counts as **genuine recovery** only if the post-correction result verifies against ground truth; otherwise it is logged as attempted.

## Out of scope

Single-agent reasoning errors (they surface at task level only). Injected faults (parked for a later phase).
