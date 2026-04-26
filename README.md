# FinServe Problem Management Agent
### ITSM — Agent-Driven Problem Management | CrewAI + Ollama

---

## Overview

A five-agent CrewAI system implementing the full **ITIL 4 Problem Management lifecycle**
for FinServe Digital Bank's Q1 2026 incident data. Agents autonomously detect recurring
incident patterns, enrich findings with CMDB and change log data, perform Five Whys root
cause analysis, produce Known Error Records, and generate formal Requests for Change.

## Project Structure

```
finserve_problem_mgmt/
├── main.py                          # Entry point — run this
├── requirements.txt                 # Python dependencies
├── WRITTEN_SUMMARY.md               # Assignment written summary (patterns + tool design)
├── data/
│   ├── finserve_incidents_q1_2026.csv
│   ├── finserve_cmdb.csv
│   └── finserve_changes.csv
├── output/                          # Agent-generated artifacts (created at runtime)
│   ├── KE-*.json                    # Known Error Records
│   ├── RFC-*.json                   # Requests for Change
│   └── problem_management_report.md # Full crew output
└── src/
    ├── __init__.py
    ├── agents.py                    # 5 agents with Ollama LLM config
    ├── tasks.py                     # 5 sequential tasks with context chaining
    ├── tools.py                     # 13 tools (7 read CSV, 2 write JSON)
    └── problem_crew.py              # Crew assembly (sequential process)
```

## Agent Pipeline

| # | Agent | ITIL Phase | Key Tools |
|---|-------|-----------|-----------|
| 1 | **Trend Analyst** | Problem Identification | `find_patterns`, `get_time_distribution`, `calculate_impact`, `parse_incidents` |
| 2 | **CMDB Correlator** | Problem Logging & Classification | `query_cmdb`, `query_changes`, `map_dependencies`, `correlate_incidents_changes`, `build_timeline`, `create_problem_record` |
| 3 | **Root Cause Investigator** | Problem Control (RCA) | `five_whys_analysis`, `build_timeline`, `query_changes`, `query_cmdb` |
| 4 | **Known Error Author** | Error Control (KEDB) | `create_known_error` |
| 5 | **Change Proposer** | Change Enablement | `query_cmdb`, `create_rfc` |

## Setup

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com/) running locally with `qwen3:8b-q4_K_M` pulled
  ```bash
  ollama pull qwen3:8b-q4_K_M
  ```

### Installation

```bash
# Clone / extract the project
cd finserve_problem_mgmt

# Create virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
python main.py
```

The crew will run for approximately 10–30 minutes depending on your hardware.
Output artifacts (KE records, RFCs, full report) are written to `output/`.

### Custom Data Paths

```bash
export FINSERVE_DATA_DIR=/path/to/your/csvs
export FINSERVE_OUTPUT_DIR=/path/to/your/output
python main.py
```

## Tools Summary (13 total)

| Tool | File I/O | Description |
|------|----------|-------------|
| `parse_incidents` | READ | Load/filter incident CSV |
| `find_patterns` | READ | Frequency clustering by service+subcategory+error_code |
| `get_time_distribution` | READ | Day-of-week / hour-of-day temporal analysis |
| `query_cmdb` | READ | CI metadata lookup (tier, infra, dependencies, notes) |
| `query_changes` | READ | Change log lookup by CI, date, or change ID |
| `map_dependencies` | READ | Full upstream/downstream dependency graph |
| `correlate_incidents_changes` | READ | Score which changes precede incidents most often |
| `five_whys_analysis` | — | Generate structured Five Whys framework |
| `build_timeline` | READ | Chronological incident + change interleaved timeline |
| `create_problem_record` | — | Generate ITIL 4 Problem Record JSON |
| `create_known_error` | **WRITE** | Write Known Error Record to output/ |
| `create_rfc` | **WRITE** | Write RFC to output/ |
| `calculate_impact` | READ | Business impact metrics (downtime, priority breakdown) |

## Output Artifacts

After a successful run, `output/` will contain:
- **`KE-*.json`** — One Known Error Record per pattern (KEDB entries)
- **`RFC-*.json`** — One Request for Change per Known Error
- **`problem_management_report.md`** — Full executive report from the Change Proposer

## ITIL 4 Frameworks Referenced

- **Problem Management** — Problem Identification, Problem Control, Error Control
- **Change Enablement** — Normal / Standard / Emergency change classification
- **Knowledge Management** — Known Error Database (KEDB) documentation
- **Configuration Management** — CMDB-based dependency and CI analysis

## Rubric Alignment

| Dimension | Implementation |
|-----------|---------------|
| Pattern Detection | `find_patterns` + `get_time_distribution` + `calculate_impact` surface 4 patterns with statistical evidence |
| Root Cause Accuracy | `five_whys_analysis` + `correlate_incidents_changes` + `query_cmdb` cross-reference supports each RCA |
| Tool Quality | 13 tools, 7 read CSV at runtime, 2 write JSON output, all with Pydantic input models |
| Known Error Records | `create_known_error` writes structured JSON with specific numbered workaround steps |
| Change Proposals | `create_rfc` writes structured JSON with test plan, rollback plan, risk rating, schedule |
| Agent Design | 5 distinct roles, detailed backstories, appropriate tools, full context chaining |
