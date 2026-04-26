"""
tools.py — FinServe Problem Management Agent Tools
====================================================
13 tools total | 5 read from CSV files at runtime | 2 write output files
All tools use Pydantic input models and return structured JSON-serializable output.
"""

from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta
import pandas as pd
import json
import os
import hashlib

# ============================================================================
# PATH RESOLUTION — reads from env vars, falls back to relative path
# ============================================================================

def _data_path(filename: str) -> str:
    env_key = "FINSERVE_DATA_DIR"
    data_dir = os.environ.get(env_key, os.path.join(os.path.dirname(__file__), "..", "data"))
    return os.path.join(data_dir, filename)

def _output_path(filename: str) -> str:
    env_key = "FINSERVE_OUTPUT_DIR"
    out_dir = os.environ.get(env_key, os.path.join(os.path.dirname(__file__), "..", "output"))
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, filename)

# ============================================================================
# PYDANTIC INPUT MODELS
# ============================================================================

class ParseIncidentsInput(BaseModel):
    service: Optional[str] = Field(None, description="Filter by service name (e.g. 'payment-gateway')")
    priority: Optional[str] = Field(None, description="Filter by priority (e.g. 'P1-Critical')")
    error_code: Optional[str] = Field(None, description="Filter by error code (e.g. 'ERR-5012')")
    start_date: Optional[str] = Field(None, description="Start date YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="End date YYYY-MM-DD")
    max_rows: Optional[int] = Field(100, description="Max rows to return")

class FindPatternsInput(BaseModel):
    frequency_threshold: int = Field(4, description="Minimum incident count to qualify as a pattern cluster")
    group_by_change: bool = Field(True, description="Whether to also group by related_change field")

class TimeDistributionInput(BaseModel):
    service: str = Field(..., description="Service name to analyze")
    error_code: Optional[str] = Field(None, description="Optional error code filter")

class QueryCMDBInput(BaseModel):
    ci_id: str = Field(..., description="Configuration Item ID (e.g. CI-1042)")

class QueryChangesInput(BaseModel):
    ci_id: Optional[str] = Field(None, description="Filter changes by CI ID")
    start_date: Optional[str] = Field(None, description="Start date YYYY-MM-DD")
    end_date: Optional[str] = Field(None, description="End date YYYY-MM-DD")
    change_id: Optional[str] = Field(None, description="Look up a specific change ID")

class MapDependenciesInput(BaseModel):
    ci_id: str = Field(..., description="CI ID to map dependencies for")

class CorrelateIncChangesInput(BaseModel):
    service: str = Field(..., description="Service name for the incident cluster")
    error_code: Optional[str] = Field(None, description="Error code to filter incidents")
    window_hours: int = Field(72, description="Look-back window in hours before each incident")

class FiveWhysInput(BaseModel):
    pattern_summary: str = Field(..., description="Text summary of the pattern to investigate")
    cmdb_data: str = Field(..., description="CMDB record data as string")
    change_data: str = Field(..., description="Relevant change records as string")

class BuildTimelineInput(BaseModel):
    service: str = Field(..., description="Service or CI to build timeline for")
    error_code: Optional[str] = Field(None, description="Optional error code filter")

class CreateProblemRecordInput(BaseModel):
    title: str = Field(..., description="Short title describing the problem")
    severity: str = Field(..., description="P1-Critical / P2-High / P3-Medium")
    affected_ci_ids: str = Field(..., description="Comma-separated CI IDs")
    linked_incident_ids: str = Field(..., description="Comma-separated incident IDs")
    pattern_summary: str = Field(..., description="Description of the recurring pattern")

class CreateKnownErrorInput(BaseModel):
    problem_id: str = Field(..., description="Parent problem record ID")
    title: str = Field(..., description="Known Error title")
    root_cause: str = Field(..., description="Confirmed root cause description")
    workaround: str = Field(..., description="Immediate workaround for the Service Desk")
    permanent_fix: str = Field(..., description="Description of the permanent fix required")
    affected_ci: str = Field(..., description="Primary affected CI ID")
    linked_incidents: str = Field(..., description="Comma-separated linked incident IDs")

class CreateRFCInput(BaseModel):
    known_error_id: str = Field(..., description="Parent Known Error ID")
    title: str = Field(..., description="Change title")
    description: str = Field(..., description="Detailed description of the change")
    affected_ci: str = Field(..., description="CI ID to be changed")
    risk: str = Field(..., description="Risk rating: Low / Medium / High")
    change_type: str = Field(..., description="Normal / Standard / Emergency")
    test_plan: str = Field(..., description="How the change will be tested")
    rollback_plan: str = Field(..., description="How to undo the change if it fails")
    proposed_schedule: str = Field(..., description="Proposed implementation window")

class CalculateImpactInput(BaseModel):
    service: str = Field(..., description="Service name")
    error_code: Optional[str] = Field(None, description="Error code to filter")
    include_downtime: bool = Field(True, description="Calculate total downtime hours")

# ============================================================================
# TOOL 1: parse_incidents — reads incident CSV at runtime
# ============================================================================

class ParseIncidentsTool(BaseTool):
    name: str = "parse_incidents"
    description: str = (
        "Reads the FinServe incident CSV and returns structured incident records. "
        "Supports filtering by service, priority, error_code, and date range. "
        "Returns JSON with incident details including timestamps, categories, error codes, and change links."
    )
    args_schema: type[BaseModel] = ParseIncidentsInput

    def _run(self, service: Optional[str] = None, priority: Optional[str] = None,
             error_code: Optional[str] = None, start_date: Optional[str] = None,
             end_date: Optional[str] = None, max_rows: Optional[int] = 100) -> str:
        df = pd.read_csv(_data_path("finserve_incidents_q1_2026.csv"))
        df["opened_at"] = pd.to_datetime(df["opened_at"])
        df["resolved_at"] = pd.to_datetime(df["resolved_at"])

        if service:
            df = df[df["service"].str.lower() == service.lower()]
        if priority:
            df = df[df["priority"].str.lower() == priority.lower()]
        if error_code:
            df = df[df["error_code"].str.lower() == error_code.lower()]
        if start_date:
            df = df[df["opened_at"] >= start_date]
        if end_date:
            df = df[df["opened_at"] <= end_date]

        df = df.head(max_rows)
        df["opened_at"] = df["opened_at"].astype(str)
        df["resolved_at"] = df["resolved_at"].astype(str)

        result = {
            "total_returned": len(df),
            "filters_applied": {
                "service": service, "priority": priority,
                "error_code": error_code, "start_date": start_date, "end_date": end_date
            },
            "incidents": df.to_dict(orient="records")
        }
        return json.dumps(result, default=str)

parse_incidents = ParseIncidentsTool()


# ============================================================================
# TOOL 2: find_patterns — reads incident CSV, groups by service+subcategory+error_code
# ============================================================================

class FindPatternsTool(BaseTool):
    name: str = "find_patterns"
    description: str = (
        "Reads the incident CSV and clusters incidents by service + subcategory + error_code. "
        "Returns only clusters that exceed the frequency threshold — these are candidate Problem patterns. "
        "Also optionally groups by related_change to surface change-correlated clusters."
    )
    args_schema: type[BaseModel] = FindPatternsInput

    def _run(self, frequency_threshold: int = 4, group_by_change: bool = True) -> str:
        df = pd.read_csv(_data_path("finserve_incidents_q1_2026.csv"))
        df["opened_at"] = pd.to_datetime(df["opened_at"])

        # Primary grouping
        grouped = (
            df.groupby(["service", "subcategory", "error_code"])
            .agg(
                count=("incident_id", "count"),
                incident_ids=("incident_id", lambda x: list(x)),
                priorities=("priority", lambda x: list(x.unique())),
                first_seen=("opened_at", "min"),
                last_seen=("opened_at", "max"),
                related_changes=("related_change", lambda x: list(x.dropna().unique())),
                assigned_teams=("assigned_team", lambda x: list(x.unique())),
                ci_ids=("ci_id", lambda x: list(x.unique())),
            )
            .reset_index()
        )
        patterns = grouped[grouped["count"] >= frequency_threshold].copy()
        patterns["first_seen"] = patterns["first_seen"].astype(str)
        patterns["last_seen"] = patterns["last_seen"].astype(str)
        patterns = patterns.sort_values("count", ascending=False)

        result = {
            "total_incidents_analyzed": len(df),
            "frequency_threshold": frequency_threshold,
            "candidate_patterns_found": len(patterns),
            "patterns": patterns.to_dict(orient="records")
        }
        return json.dumps(result, default=str)

find_patterns = FindPatternsTool()


# ============================================================================
# TOOL 3: get_time_distribution — temporal analysis of incident clusters
# ============================================================================

class TimeDistributionTool(BaseTool):
    name: str = "get_time_distribution"
    description: str = (
        "For a given service (and optional error_code), analyzes the temporal distribution "
        "of incidents: day of week, hour of day, and monthly distribution. "
        "Reveals weekly, nightly, or month-end recurrence patterns."
    )
    args_schema: type[BaseModel] = TimeDistributionInput

    def _run(self, service: str, error_code: Optional[str] = None) -> str:
        df = pd.read_csv(_data_path("finserve_incidents_q1_2026.csv"))
        df["opened_at"] = pd.to_datetime(df["opened_at"])
        df = df[df["service"].str.lower() == service.lower()]
        if error_code:
            df = df[df["error_code"].str.lower() == error_code.lower()]

        if df.empty:
            return json.dumps({"error": f"No incidents found for service={service} error_code={error_code}"})

        df["day_of_week"] = df["opened_at"].dt.day_name()
        df["hour_of_day"] = df["opened_at"].dt.hour
        df["month"] = df["opened_at"].dt.month_name()
        df["day_of_month"] = df["opened_at"].dt.day

        result = {
            "service": service,
            "error_code": error_code,
            "total_incidents": len(df),
            "day_of_week_distribution": df["day_of_week"].value_counts().to_dict(),
            "hour_of_day_distribution": df["hour_of_day"].value_counts().to_dict(),
            "month_distribution": df["month"].value_counts().to_dict(),
            "day_of_month_distribution": df["day_of_month"].value_counts().to_dict(),
            "incident_timestamps": sorted(df["opened_at"].astype(str).tolist())
        }
        return json.dumps(result, default=str)

get_time_distribution = TimeDistributionTool()


# ============================================================================
# TOOL 4: query_cmdb — reads CMDB CSV at runtime
# ============================================================================

class QueryCMDBTool(BaseTool):
    name: str = "query_cmdb"
    description: str = (
        "Looks up a Configuration Item (CI) in the CMDB by its CI ID and returns its full record: "
        "tier, owner, version, infrastructure, upstream/downstream dependencies, last change, and notes."
    )
    args_schema: type[BaseModel] = QueryCMDBInput

    def _run(self, ci_id: str) -> str:
        df = pd.read_csv(_data_path("finserve_cmdb.csv"))
        row = df[df["ci_id"].str.upper() == ci_id.upper()]
        if row.empty:
            return json.dumps({"error": f"CI not found: {ci_id}", "available_ci_ids": df["ci_id"].tolist()})
        record = row.iloc[0].to_dict()
        return json.dumps(record, default=str)

query_cmdb = QueryCMDBTool()


# ============================================================================
# TOOL 5: query_changes — reads change log CSV at runtime
# ============================================================================

class QueryChangesTool(BaseTool):
    name: str = "query_changes"
    description: str = (
        "Returns change records from the FinServe change log CSV. "
        "Can filter by CI ID, date range, or specific change ID. "
        "Use this to correlate incidents with infrastructure changes."
    )
    args_schema: type[BaseModel] = QueryChangesInput

    def _run(self, ci_id: Optional[str] = None, start_date: Optional[str] = None,
             end_date: Optional[str] = None, change_id: Optional[str] = None) -> str:
        df = pd.read_csv(_data_path("finserve_changes.csv"))
        df["implemented_at"] = pd.to_datetime(df["implemented_at"])

        if change_id:
            df = df[df["change_id"].str.upper() == change_id.upper()]
        if ci_id:
            df = df[df["ci_id"].str.upper() == ci_id.upper()]
        if start_date:
            df = df[df["implemented_at"] >= start_date]
        if end_date:
            df = df[df["implemented_at"] <= end_date]

        df["implemented_at"] = df["implemented_at"].astype(str)
        result = {
            "total_changes_returned": len(df),
            "changes": df.to_dict(orient="records")
        }
        return json.dumps(result, default=str)

query_changes = QueryChangesTool()


# ============================================================================
# TOOL 6: map_dependencies — walks CMDB dependency graph
# ============================================================================

class MapDependenciesTool(BaseTool):
    name: str = "map_dependencies"
    description: str = (
        "Given a CI ID, reads the CMDB and returns its full upstream and downstream dependency graph. "
        "Use this to understand shared infrastructure that might explain cross-service patterns."
    )
    args_schema: type[BaseModel] = MapDependenciesInput

    def _run(self, ci_id: str) -> str:
        df = pd.read_csv(_data_path("finserve_cmdb.csv"))
        row = df[df["ci_id"].str.upper() == ci_id.upper()]
        if row.empty:
            return json.dumps({"error": f"CI not found: {ci_id}"})

        r = row.iloc[0]
        upstream_ids = [x.strip() for x in str(r.get("upstream_deps", "") or "").split(",") if x.strip() and x.strip() != "nan"]
        downstream_ids = [x.strip() for x in str(r.get("downstream_deps", "") or "").split(",") if x.strip() and x.strip() != "nan"]

        def enrich(ids):
            out = []
            for cid in ids:
                match = df[df["ci_id"].str.upper() == cid.upper()]
                if not match.empty:
                    m = match.iloc[0]
                    out.append({"ci_id": cid, "ci_name": m["ci_name"], "tier": m["tier"], "ci_type": m["ci_type"]})
                else:
                    out.append({"ci_id": cid, "ci_name": "Unknown", "tier": "Unknown", "ci_type": "Unknown"})
            return out

        result = {
            "ci_id": ci_id,
            "ci_name": r["ci_name"],
            "tier": r["tier"],
            "upstream_dependencies": enrich(upstream_ids),
            "downstream_dependencies": enrich(downstream_ids),
            "notes": r.get("notes", "")
        }
        return json.dumps(result, default=str)

map_dependencies = MapDependenciesTool()


# ============================================================================
# TOOL 7: correlate_incidents_changes — cross-references incidents with recent changes
# ============================================================================

class CorrelateIncChangesTool(BaseTool):
    name: str = "correlate_incidents_changes"
    description: str = (
        "For a given service and error code, finds all changes that occurred within a configurable "
        "time window BEFORE each incident. Surfaces the strongest change-to-incident correlations. "
        "Critical for establishing causal links between changes and recurring failures."
    )
    args_schema: type[BaseModel] = CorrelateIncChangesInput

    def _run(self, service: str, error_code: Optional[str] = None, window_hours: int = 72) -> str:
        incidents = pd.read_csv(_data_path("finserve_incidents_q1_2026.csv"))
        changes = pd.read_csv(_data_path("finserve_changes.csv"))

        incidents["opened_at"] = pd.to_datetime(incidents["opened_at"])
        changes["implemented_at"] = pd.to_datetime(changes["implemented_at"])

        inc_filtered = incidents[incidents["service"].str.lower() == service.lower()]
        if error_code:
            inc_filtered = inc_filtered[inc_filtered["error_code"].str.lower() == error_code.lower()]

        correlations = []
        change_counts: Dict[str, int] = {}

        for _, inc in inc_filtered.iterrows():
            window_start = inc["opened_at"] - timedelta(hours=window_hours)
            nearby = changes[
                (changes["implemented_at"] >= window_start) &
                (changes["implemented_at"] <= inc["opened_at"])
            ]
            for _, chg in nearby.iterrows():
                cid = chg["change_id"]
                change_counts[cid] = change_counts.get(cid, 0) + 1
                correlations.append({
                    "incident_id": inc["incident_id"],
                    "incident_opened": str(inc["opened_at"]),
                    "change_id": cid,
                    "change_title": chg["title"],
                    "change_implemented": str(chg["implemented_at"]),
                    "hours_before_incident": round(
                        (inc["opened_at"] - chg["implemented_at"]).total_seconds() / 3600, 1
                    )
                })

        sorted_changes = sorted(change_counts.items(), key=lambda x: x[1], reverse=True)

        return json.dumps({
            "service": service,
            "error_code": error_code,
            "window_hours": window_hours,
            "incidents_analyzed": len(inc_filtered),
            "change_correlation_counts": [{"change_id": k, "correlated_incidents": v} for k, v in sorted_changes],
            "detailed_correlations": correlations
        }, default=str)

correlate_incidents_changes = CorrelateIncChangesTool()


# ============================================================================
# TOOL 8: five_whys_analysis — structured root cause reasoning template
# ============================================================================

class FiveWhysTool(BaseTool):
    name: str = "five_whys_analysis"
    description: str = (
        "Generates a structured Five Whys root cause analysis framework for a pattern. "
        "Given a pattern summary, CMDB data, and change data, returns a structured template "
        "with pre-populated context that the investigating agent should complete."
    )
    args_schema: type[BaseModel] = FiveWhysInput

    def _run(self, pattern_summary: str, cmdb_data: str, change_data: str) -> str:
        template = {
            "analysis_method": "ITIL 4 Five Whys (Sakichi Toyoda methodology)",
            "pattern_under_investigation": pattern_summary,
            "context": {
                "cmdb_data_provided": cmdb_data[:500] + "..." if len(cmdb_data) > 500 else cmdb_data,
                "change_data_provided": change_data[:500] + "..." if len(change_data) > 500 else change_data,
            },
            "five_whys_chain": [
                {"level": 1, "question": "Why did the failure occur?", "answer": "[Agent: fill from incident short_description and resolution_notes]"},
                {"level": 2, "question": "Why did that condition exist?", "answer": "[Agent: cross-reference CMDB notes and infrastructure details]"},
                {"level": 3, "question": "Why was that the underlying state?", "answer": "[Agent: examine related changes and their descriptions]"},
                {"level": 4, "question": "Why was that change/condition introduced?", "answer": "[Agent: examine change type, risk rating, and testing notes]"},
                {"level": 5, "question": "Why did the process allow that?", "answer": "[Agent: identify process gap — missing test plan, wrong risk rating, no load test, etc.]"}
            ],
            "root_cause_statement": "[Agent: synthesize the five whys chain into a single root cause statement]",
            "contributing_factors": ["[Agent: list secondary factors from CMDB/change data]"],
            "instructions": (
                "Complete each 'answer' field using the provided CMDB and change data. "
                "The root_cause_statement must be a single specific sentence identifying the underlying cause. "
                "Reference specific change IDs, CI IDs, configuration values, and error codes in your answers."
            )
        }
        return json.dumps(template, indent=2)

five_whys_analysis = FiveWhysTool()


# ============================================================================
# TOOL 9: build_timeline — chronological incident + change timeline
# ============================================================================

class BuildTimelineTool(BaseTool):
    name: str = "build_timeline"
    description: str = (
        "Constructs a chronological timeline of all incidents AND changes for a given service. "
        "Interleaves both datasets sorted by timestamp, making temporal patterns and "
        "change-triggered incidents immediately visible."
    )
    args_schema: type[BaseModel] = BuildTimelineInput

    def _run(self, service: str, error_code: Optional[str] = None) -> str:
        incidents = pd.read_csv(_data_path("finserve_incidents_q1_2026.csv"))
        changes = pd.read_csv(_data_path("finserve_changes.csv"))

        incidents["opened_at"] = pd.to_datetime(incidents["opened_at"])
        changes["implemented_at"] = pd.to_datetime(changes["implemented_at"])

        inc_filtered = incidents[incidents["service"].str.lower() == service.lower()].copy()
        if error_code:
            inc_filtered = inc_filtered[inc_filtered["error_code"].str.lower() == error_code.lower()]

        # Get CI IDs for this service to match changes
        ci_ids = inc_filtered["ci_id"].unique().tolist()
        chg_filtered = changes[changes["ci_id"].isin(ci_ids)].copy()

        timeline = []
        for _, inc in inc_filtered.iterrows():
            timeline.append({
                "timestamp": str(inc["opened_at"]),
                "type": "INCIDENT",
                "id": inc["incident_id"],
                "priority": inc["priority"],
                "description": inc["short_description"],
                "error_code": inc["error_code"],
                "resolution": inc["resolution_notes"],
                "related_change": str(inc.get("related_change", ""))
            })

        for _, chg in chg_filtered.iterrows():
            timeline.append({
                "timestamp": str(chg["implemented_at"]),
                "type": "CHANGE",
                "id": chg["change_id"],
                "risk": chg["risk"],
                "description": chg["title"],
                "detail": chg["description"]
            })

        timeline.sort(key=lambda x: x["timestamp"])

        return json.dumps({
            "service": service,
            "error_code": error_code,
            "total_events": len(timeline),
            "incident_count": len(inc_filtered),
            "change_count": len(chg_filtered),
            "timeline": timeline
        }, default=str)

build_timeline = BuildTimelineTool()


# ============================================================================
# TOOL 10: create_problem_record — generates a formal Problem Record
# ============================================================================

class CreateProblemRecordTool(BaseTool):
    name: str = "create_problem_record"
    description: str = (
        "Creates a formal ITIL 4 Problem Record with a unique Problem ID, severity classification, "
        "affected CIs, linked incidents, and current status. Returns the structured Problem Record."
    )
    args_schema: type[BaseModel] = CreateProblemRecordInput

    def _run(self, title: str, severity: str, affected_ci_ids: str,
             linked_incident_ids: str, pattern_summary: str) -> str:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        h = hashlib.md5(title.encode()).hexdigest()[:4].upper()
        problem_id = f"PRB-{ts[:8]}-{h}"

        ci_list = [c.strip() for c in affected_ci_ids.split(",") if c.strip()]
        inc_list = [i.strip() for i in linked_incident_ids.split(",") if i.strip()]

        record = {
            "problem_id": problem_id,
            "title": title,
            "severity": severity,
            "status": "Under Investigation",
            "opened_at": datetime.utcnow().isoformat() + "Z",
            "affected_cis": ci_list,
            "linked_incidents": inc_list,
            "incident_count": len(inc_list),
            "pattern_summary": pattern_summary,
            "itil_phase": "Problem Control",
            "assigned_team": "Problem Management",
            "sla_target_days": 30 if severity == "P3-Medium" else (14 if severity == "P2-High" else 7)
        }
        return json.dumps(record, indent=2)

create_problem_record = CreateProblemRecordTool()


# ============================================================================
# TOOL 11: create_known_error — produces Known Error Record and WRITES to file
# ============================================================================

class CreateKnownErrorTool(BaseTool):
    name: str = "create_known_error"
    description: str = (
        "Produces a formal Known Error Record with root cause, workaround, and permanent fix. "
        "WRITES the record to the output/ directory as JSON. "
        "Returns the Known Error ID and full record content."
    )
    args_schema: type[BaseModel] = CreateKnownErrorInput

    def _run(self, problem_id: str, title: str, root_cause: str, workaround: str,
             permanent_fix: str, affected_ci: str, linked_incidents: str) -> str:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        h = hashlib.md5(title.encode()).hexdigest()[:4].upper()
        ke_id = f"KE-{ts[:8]}-{h}"

        inc_list = [i.strip() for i in linked_incidents.split(",") if i.strip()]

        record = {
            "ke_id": ke_id,
            "parent_problem_id": problem_id,
            "title": title,
            "status": "Known Error — Permanent Fix Pending",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "affected_ci": affected_ci,
            "linked_incidents": inc_list,
            "root_cause": root_cause,
            "workaround": {
                "description": workaround,
                "audience": "Service Desk / First Responders",
                "estimated_resolution_time_minutes": 30
            },
            "permanent_fix": permanent_fix,
            "kedb_category": "Application",
            "itil_practice": "ITIL 4 Problem Management — Error Control",
            "knowledge_management_note": "Add to KEDB for Service Desk use. Link to incident template for fast triage."
        }

        filename = f"{ke_id}.json"
        filepath = _output_path(filename)
        with open(filepath, "w") as f:
            json.dump(record, f, indent=2)

        return json.dumps({
            "ke_id": ke_id,
            "written_to": filepath,
            "record": record
        }, indent=2)

create_known_error = CreateKnownErrorTool()


# ============================================================================
# TOOL 12: create_rfc — generates RFC and WRITES to file
# ============================================================================

class CreateRFCTool(BaseTool):
    name: str = "create_rfc"
    description: str = (
        "Generates a formal ITIL 4 Request for Change (RFC) with description, risk rating, "
        "test plan, rollback plan, and proposed schedule. WRITES the RFC to the output/ directory. "
        "Returns the RFC ID and full record."
    )
    args_schema: type[BaseModel] = CreateRFCInput

    def _run(self, known_error_id: str, title: str, description: str, affected_ci: str,
             risk: str, change_type: str, test_plan: str, rollback_plan: str,
             proposed_schedule: str) -> str:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        h = hashlib.md5(title.encode()).hexdigest()[:4].upper()
        rfc_id = f"RFC-{ts[:8]}-{h}"

        risk_scores = {"Low": 1, "Medium": 2, "High": 3}
        risk_score = risk_scores.get(risk, 2)

        record = {
            "rfc_id": rfc_id,
            "parent_known_error_id": known_error_id,
            "title": title,
            "status": "Pending CAB Review",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "affected_ci": affected_ci,
            "change_type": change_type,
            "risk_rating": risk,
            "risk_score": risk_score,
            "description": description,
            "test_plan": test_plan,
            "rollback_plan": rollback_plan,
            "proposed_schedule": proposed_schedule,
            "approval_required": "CAB" if risk_score >= 2 else "Standard Approval",
            "itil_practice": "ITIL 4 Change Enablement",
            "change_enablement_note": (
                "RFC derived from Problem Management investigation. "
                "Implement only after Known Error workaround is confirmed stable in production."
            )
        }

        filename = f"{rfc_id}.json"
        filepath = _output_path(filename)
        with open(filepath, "w") as f:
            json.dump(record, f, indent=2)

        return json.dumps({
            "rfc_id": rfc_id,
            "written_to": filepath,
            "record": record
        }, indent=2)

create_rfc = CreateRFCTool()


# ============================================================================
# TOOL 13: calculate_impact — computes business impact metrics from incident data
# ============================================================================

class CalculateImpactTool(BaseTool):
    name: str = "calculate_impact"
    description: str = (
        "Reads the incident CSV and computes business impact metrics for a service pattern: "
        "total incidents, P1/P2 counts, total downtime hours, average resolution time, "
        "and priority breakdown. Returns a structured impact summary."
    )
    args_schema: type[BaseModel] = CalculateImpactInput

    def _run(self, service: str, error_code: Optional[str] = None, include_downtime: bool = True) -> str:
        df = pd.read_csv(_data_path("finserve_incidents_q1_2026.csv"))
        df["opened_at"] = pd.to_datetime(df["opened_at"])
        df["resolved_at"] = pd.to_datetime(df["resolved_at"])
        df = df[df["service"].str.lower() == service.lower()]
        if error_code:
            df = df[df["error_code"].str.lower() == error_code.lower()]

        if df.empty:
            return json.dumps({"error": f"No incidents for service={service} error_code={error_code}"})

        df["duration_hours"] = (df["resolved_at"] - df["opened_at"]).dt.total_seconds() / 3600
        priority_counts = df["priority"].value_counts().to_dict()

        result = {
            "service": service,
            "error_code": error_code,
            "total_incidents": len(df),
            "priority_breakdown": priority_counts,
            "p1_critical_count": priority_counts.get("P1-Critical", 0),
            "p2_high_count": priority_counts.get("P2-High", 0),
            "date_range": {
                "first_incident": str(df["opened_at"].min()),
                "last_incident": str(df["opened_at"].max()),
                "span_days": (df["opened_at"].max() - df["opened_at"].min()).days
            },
            "resolution_time_hours": {
                "mean": round(df["duration_hours"].mean(), 2),
                "max": round(df["duration_hours"].max(), 2),
                "total": round(df["duration_hours"].sum(), 2)
            },
            "recurrence_rate": f"~{round(len(df) / max((df['opened_at'].max() - df['opened_at'].min()).days / 7, 1), 1)} incidents/week"
        }
        return json.dumps(result, default=str)

calculate_impact = CalculateImpactTool()
