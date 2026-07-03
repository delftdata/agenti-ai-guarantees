# MAD analysis

I had the full MAD corpus analysed (1242 traces, 7 systems, 7 benchmarks, 2 LLMs) before building the graph extractor. Extracting plan-graphs and showing that graph shape correlates with failure mode is **not extractable from MAD**, for structural reasons in how the dataset was built.

## What I did, step by step

**1. Worked example (ChatDev / ProgramDev) - structure does not predict failure.**
ChatDev runs a fixed 12-phase chain on every task. Across 130 traces the structure is constant, and identical for failed vs clean runs:

| ChatDev/ProgramDev (n=130) | failed (93) | clean (37) |
|---|---|---|
| avg exchanges | 12.3 | 12.2 |
| avg code-writes | 5.4 | 6.1 |
| avg runs | 8.4 | 8.3 |

71% of runs fail at least one mode, but graph shape carries no signal, the topology is hard-coded, so failures occur *within* a fixed structure, not because of structural variation.

**2. Cross-system - failure profile varies.**

| System | n | fail% | spec (1) | coord (2) | verif (3) |
|---|---|---|---|---|---|
| AG2 | 597 | 83% | 61% | 60% | 50% |
| Magentic | 195 | 78% | 58% | 53% | 45% |
| MetaGPT | 230 | 75% | 56% | 43% | 46% |
| ChatDev | 130 | 72% | 54% | 41% | 45% |
| OpenManus / AppWorld / HyperAgent | 30 each | 47% | 40% | 20% | 33% |

But the variation is confounded by construction. Only ProgramDev is shared across systems; the other six benchmarks are each run by a single system. Within ProgramDev the two structured pipelines are statistically indistinguishable (ChatDev 72% / 41% coord ≈ MetaGPT 75% / 43%). Failure tracks benchmark *difficulty* (ProgramDev 72% → Olympiad 86%), and the LLM is confounded as well - ChatDev/ProgramDev is 100% GPT-4o, with the Claude traces sitting in other systems. System, benchmark, and LLM are entangled; no single factor is isolable from observation alone.

**3. The labels are reliable.**
On the 19 human-labelled traces, 316 annotator judgments show **95% unanimous agreement** (97% mean pairwise) across three annotators. MAST's taxonomy produces consistent labels.

## What MAD supports

**Supports:** coordination failures are pervasive and reliably labelled. Category 2 appears in **51% of all 1242 traces**, and mode 2.6 is the single most common failure corpus-wide (495 traces).

**Does not support:** isolating the causal effect of topology or coordination discipline on failure. The dataset bundles each system with its own benchmark and LLM, so any observational correlation is uninterpretable.

## Conclusion

Claim 1 (uncoordinated execution fails) is now backed at scale by MAD. Claim 2 (principled primitives prevent it) would require a controlled study.
