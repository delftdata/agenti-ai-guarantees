# agenti-ai-guarantees

Guarantees for agentic AI workflows. One package, three parts:

- **`agent_guarantees.mad`** — corpus analysis of the MAD multi-agent failure
  dataset ([`mcemri/MAD`](https://huggingface.co/datasets/mcemri/MAD)),
  annotated with the 14-mode MAST failure taxonomy: loader, trace inspection,
  plan-graph extraction, structural stats.
- **`agent_guarantees.execlab`** — a deterministic execution-topology rig
  (no LLM, no API, no network, no real threads) that reproduces coordination
  failures reliably.
- **`agent_guarantees.llm_lab`** — real-agent LangGraph experiments profiling
  sequential vs distributed vs scatter-gather plans (needs an API key).

## Layout

```
pyproject.toml
src/agent_guarantees/
    mad/        loader.py, inspect_traces.py, graph.py, stats.py
    execlab/    rig.py
    llm_lab/    profile_plans.py
scripts/        01_explore.py ... 05_failed_vs_clean.py, run_profile_plans.py
tests/          offline tests + fixtures (no network needed)
docs/           findings, corpus profile, failure definition, memos
data/raw/       gitignored — the loader re-fetches from the HF Hub
```

## Track 1 — MAD analysis + deterministic rig (no API key)

Setup on Windows / PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[dev]
```

Setup on macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e '.[dev]'
```

Run the tests (fully offline, against `tests/fixtures/synthetic_mad.json`):

```
pytest
```

The analysis scripts (run from the repo root; 01–03 and 05 download the raw
MAD files into `data/raw/` on first run — no API key needed; set `MAD_DATA_DIR`
to point elsewhere):

| Script | What it does |
| --- | --- |
| `python scripts/01_explore.py` | Filter to ChatDev/ProgramDev, inspect the first 5 traces (phases, roles, role pairs) |
| `python scripts/02_corpus_profile.py` | Reproducible whole-corpus profile → `docs/corpus_profile.md` |
| `python scripts/03_extract_chatdev.py` | ChatDev trajectories → plan-graphs, per-trace structural metrics |
| `python scripts/04_topology_grid.py` | The `{topology} × {discipline}` grid on the deterministic rig — fully offline |
| `python scripts/05_failed_vs_clean.py` | Failed-vs-clean structural split → `docs/failed_vs_clean.md` |

The topology grid (`04`) reliably detects two distinct coordination failures —
a write-race (`ffa`) and a stale-read (`over_parallel`) — without any LLM.

Read more in `docs/`: [findings](docs/findings.md),
[corpus profile](docs/corpus_profile.md),
[failed vs clean](docs/failed_vs_clean.md), and the memos under
[docs/memos/](docs/memos/).

## Track 2 — LLM experiments (Gemini API key required)

Install the `llm` extra and set your key.

Windows / PowerShell:

```powershell
pip install -e .[llm]
$env:GOOGLE_API_KEY = '<YOUR API KEY HERE>'
```

macOS / Linux:

```bash
pip install -e '.[llm]'
export GOOGLE_API_KEY='<YOUR API KEY HERE>'
```

Then profile sequential vs distributed vs scatter-gather plans:

```
python scripts/run_profile_plans.py
```

The discipline axis and the operational failure detectors for the real-agent
study land in the next change — see
[docs/failure_definition.md](docs/failure_definition.md) and
[docs/parallelization_methodology.md](docs/parallelization_methodology.md).
