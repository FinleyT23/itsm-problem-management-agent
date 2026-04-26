"""
tasks.py — FinServe Problem Management Sequential Tasks
========================================================
Five tasks mapping to the ITIL 4 Problem Management lifecycle.
Each task passes context forward to the next via CrewAI's context chaining.

Pipeline:
  Task 1 (Trend Analyst)          → Pattern clusters + impact metrics
  Task 2 (CMDB Correlator)        → Enriched patterns + Problem Records       [context: task1]
  Task 3 (Root Cause Investigator)→ Five Whys + root cause statements          [context: task1, task2]
  Task 4 (Known Error Author)     → KEDB records with workarounds               [context: task1, task2, task3]
  Task 5 (Change Proposer)        → RFCs + executive summary                   [context: task1, task2, task3, task4]
"""

from crewai import Task
from src.agents import create_agents

agents = create_agents()

trend_analyst          = agents[0]
cmdb_correlator        = agents[1]
root_cause_investigator = agents[2]
known_error_author     = agents[3]
change_proposer        = agents[4]


# ============================================================================
# TASK 1: Pattern Detection & Statistical Analysis (Trend Analyst)
# ITIL Phase: Problem Identification
# ============================================================================

task1 = Task(
    description=(
        "ITIL 4 PROBLEM IDENTIFICATION — PATTERN DETECTION & STATISTICAL ANALYSIS\n\n"
        "You are analyzing FinServe Digital Bank's Q1 2026 incident data (141 records). "
        "Your goal is to surface all statistically significant recurring incident patterns "
        "that indicate underlying Problems requiring formal investigation.\n\n"
        "REQUIRED STEPS — execute in order:\n"
        "1. Call find_patterns with frequency_threshold=4 to identify all incident clusters "
        "   where the same service + subcategory + error_code combination appears 4 or more times. "
        "   Record every cluster returned — do not filter any out at this stage.\n\n"
        "2. For EACH cluster returned by find_patterns, call get_time_distribution "
        "   to reveal temporal patterns. Look for: weekly recurrence (same day of week), "
        "   nightly patterns (incidents cluster at night), month-end patterns (day 1-3 of month).\n\n"
        "3. For EACH cluster, call calculate_impact to quantify business impact: "
        "   total incidents, priority breakdown (P1/P2/P3), total downtime hours, and recurrence rate.\n\n"
        "4. For each of the top clusters, call parse_incidents with the service and error_code "
        "   to retrieve the raw incident records. Read the resolution_notes field carefully — "
        "   responders leave root cause clues there (e.g., 'killed batch job', 'heap exhaustion', "
        "   'rolled back to v2.13.9', 'cleared Redis session cache').\n\n"
        "DELIVERABLES — your output MUST include for each pattern:\n"
        "  - Pattern key: service / subcategory / error_code\n"
        "  - Incident count and linked incident IDs\n"
        "  - Temporal distribution: day-of-week peak, hour-of-day peak, monthly distribution\n"
        "  - Priority breakdown and total downtime hours\n"
        "  - Recurrence rate (incidents per week)\n"
        "  - Preliminary hypothesis about the underlying cause (based on resolution_notes)\n"
        "  - Whether a related_change ID appears consistently across the cluster\n\n"
        "Format your output as a structured JSON pattern report with a 'patterns' array."
    ),
    agent=trend_analyst,
    expected_output=(
        "A structured JSON pattern report containing a 'patterns' array. "
        "Each pattern object must include: "
        "pattern_id (P1, P2, etc.), service, subcategory, error_code, incident_count, "
        "incident_ids (list), temporal_distribution (day_of_week, hour_of_day peaks), "
        "priority_breakdown (dict), total_downtime_hours (float), recurrence_rate (string), "
        "related_change_ids (list), preliminary_hypothesis (string), "
        "and resolution_notes_summary (key themes from responder notes). "
        "Minimum 4 patterns if data supports it. No pattern claimed without statistical evidence."
    )
)


# ============================================================================
# TASK 2: CMDB Enrichment & Problem Record Creation (CMDB Correlator)
# ITIL Phase: Problem Logging & Classification
# ============================================================================

task2 = Task(
    description=(
        "ITIL 4 PROBLEM LOGGING & CLASSIFICATION — CMDB ENRICHMENT & PROBLEM RECORDS\n\n"
        "You have received the pattern report from the Trend Analyst. "
        "Your goal is to enrich each candidate pattern with CMDB and change log intelligence, "
        "then create a formal Problem Record for each confirmed pattern.\n\n"
        "REQUIRED STEPS — for EACH pattern from Task 1:\n"
        "1. Call query_cmdb with the CI ID from the pattern cluster. "
        "   Focus on: tier classification, infrastructure notes (e.g., shared databases, "
        "   max_pool_size), last_change_date, and CMDB notes field. "
        "   Note any notes about known limitations or configurations.\n\n"
        "2. Call map_dependencies to understand the full upstream/downstream graph. "
        "   Shared infrastructure (e.g., shared database) is often the hidden link "
        "   between patterns that appear to be separate services.\n\n"
        "3. Call query_changes for the CI to retrieve all change records. "
        "   Read each change description carefully — look for: batch job schedule changes, "
        "   query parallelism increases, connection pool resizes, JWT/token handling changes, "
        "   deployment of new versions, configuration updates.\n\n"
        "4. Call correlate_incidents_changes (window_hours=72) to rank which change IDs "
        "   most frequently precede incidents in each cluster. A change that precedes 8 out of "
        "   8 incidents in a cluster is almost certainly causal.\n\n"
        "5. Call build_timeline to produce a chronological interleaving of incidents and changes. "
        "   This makes the before-and-after relationship visually clear.\n\n"
        "6. Call create_problem_record with the confirmed pattern data to generate a formal "
        "   Problem Record with ITIL 4 structure.\n\n"
        "DELIVERABLES — for each pattern:\n"
        "  - Problem Record (ID, title, severity, affected CIs, linked incidents, status)\n"
        "  - CI profile from CMDB (tier, infra, notes, last change)\n"
        "  - Dependency map (upstream/downstream CIs)\n"
        "  - Ranked change correlations (which change IDs precede incidents, how many times)\n"
        "  - Timeline summary (key events in chronological order)\n"
        "  - Enhanced hypothesis: update the Trend Analyst's preliminary hypothesis "
        "    with specific change IDs and CMDB evidence"
    ),
    agent=cmdb_correlator,
    expected_output=(
        "For each pattern: a Problem Record JSON object (problem_id, title, severity, affected_cis, "
        "linked_incidents, status), plus enrichment data: ci_profile (from CMDB), "
        "dependency_map, change_correlations (ranked by frequency with change descriptions), "
        "timeline_events (chronological list), and enhanced_hypothesis (updated with specific "
        "change IDs and CMDB evidence). All problem_ids must start with 'PRB-'."
    ),
    context=[task1]
)


# ============================================================================
# TASK 3: Root Cause Analysis (Root Cause Investigator)
# ITIL Phase: Problem Control — Root Cause Analysis
# ============================================================================

task3 = Task(
    description=(
        "ITIL 4 PROBLEM CONTROL — ROOT CAUSE ANALYSIS (FIVE WHYS METHOD)\n\n"
        "You have the pattern clusters from the Trend Analyst and the enriched Problem Records "
        "from the CMDB Correlator. Your goal is to determine the precise root cause of each Problem "
        "using the Five Whys methodology, cross-referenced with CMDB and change log evidence.\n\n"
        "REQUIRED STEPS — for EACH Problem Record:\n"
        "1. Call five_whys_analysis with the pattern_summary (from Task 1), cmdb_data (from Task 2), "
        "   and change_data (from Task 2) to generate the Five Whys framework. "
        "   Then COMPLETE each 'Why' level with specific evidence from the data — "
        "   do not leave any level as '[Agent: fill...]'. Each answer must cite a specific "
        "   CI ID, change ID, configuration value, or error message.\n\n"
        "2. Call build_timeline for the service to verify that your causal chain is consistent "
        "   with the chronological sequence of events.\n\n"
        "3. Call query_changes for the specific correlated change IDs identified in Task 2. "
        "   Read the full change description to confirm the causal mechanism: "
        "   - Does the change introduce a batch job? → Memory exhaustion risk\n"
        "   - Does it increase query parallelism? → Connection pool competition risk\n"
        "   - Does it change JWT signing logic? → Token validation regression risk\n"
        "   - Does it change AZ routing? → AZ-specific infrastructure fault risk\n\n"
        "4. Call query_cmdb to confirm that the CI's infrastructure notes corroborate the "
        "   failure mode (e.g., max_pool_size limit, shared database, AZ configuration).\n\n"
        "DELIVERABLES — for each Problem:\n"
        "  - Completed Five Whys chain (all 5 levels answered with specific evidence)\n"
        "  - Root cause statement: ONE specific sentence identifying the underlying cause\n"
        "    (format: 'The root cause is [specific condition] introduced by [specific change/config] "
        "    because [process gap].')\n"
        "  - Contributing factors (2-3 secondary factors)\n"
        "  - Process gap: what allowed the root cause to exist "
        "    (e.g., change was risk-rated Low and skipped load testing)\n"
        "  - Evidence summary: list of specific data points (CI IDs, change IDs, config values, "
        "    error codes) that support the root cause determination\n\n"
        "KNOWN PATTERNS TO INVESTIGATE (based on data):\n"
        "  - Pattern involving payment-gateway, Memory, ERR-5012, CHG0042 (Tuesday night recurrence)\n"
        "  - Pattern involving auth-service, Authentication, ERR-4401 (post-deployment clustering)\n"
        "  - Pattern involving account-ledger, Connection Pool, ERR-3200 (month-start recurrence)\n"
        "  - Pattern involving mobile-api, Timeout, ERR-5040 (AZ-specific: us-west-2 AZ-c)"
    ),
    agent=root_cause_investigator,
    expected_output=(
        "For each Problem Record: a complete Root Cause Analysis containing: "
        "five_whys_chain (array of 5 objects with question, answer, and evidence_cited), "
        "root_cause_statement (single specific sentence), "
        "contributing_factors (list of 2-3 items), "
        "process_gap (description of the process failure that allowed the root cause), "
        "evidence_summary (list of specific CI IDs, change IDs, config values, error codes "
        "supporting the determination), and confidence_level (High/Medium/Low with justification)."
    ),
    context=[task1, task2]
)


# ============================================================================
# TASK 4: Known Error Documentation (Known Error Author)
# ITIL Phase: Error Control — KEDB Documentation
# ============================================================================

task4 = Task(
    description=(
        "ITIL 4 ERROR CONTROL — KNOWN ERROR DATABASE (KEDB) DOCUMENTATION\n\n"
        "You have confirmed root causes for each Problem from the Root Cause Investigator. "
        "Your goal is to create a formal Known Error Record for each Problem and write it to "
        "the output directory. These records will be used by the Service Desk to resolve "
        "future occurrences of these incidents 60% faster.\n\n"
        "REQUIRED STEPS — for EACH Problem/Root Cause pair:\n"
        "1. Call create_known_error with ALL required fields:\n"
        "   - problem_id: the PRB- ID from Task 2\n"
        "   - title: clear descriptive title\n"
        "   - root_cause: the exact root cause statement from Task 3\n"
        "   - workaround: a SPECIFIC, ACTIONABLE procedure for the Service Desk — "
        "     write this as numbered steps an on-call engineer can execute at 3am. "
        "     Include: what to check first, specific threshold values, exact actions, "
        "     and how to confirm the workaround worked. "
        "     BAD: 'Restart the service.' "
        "     GOOD: '1. Check JVM heap in Datadog — if >85%, proceed. "
        "            2. Identify the batch reconciliation job PID. "
        "            3. Kill the process: kill -9 <PID>. "
        "            4. Restart the payment-gateway pod. "
        "            5. Confirm heap returns to <50% within 5 minutes.'\n"
        "   - permanent_fix: description of the permanent fix required "
        "     (specific enough for the Change Proposer to write an RFC from)\n"
        "   - affected_ci: primary CI ID\n"
        "   - linked_incidents: comma-separated incident IDs from Task 1\n\n"
        "2. Record the KE ID returned by create_known_error — this will be passed to the "
        "   Change Proposer.\n\n"
        "DELIVERABLES:\n"
        "  - One Known Error Record per Problem (written to output/ as JSON files)\n"
        "  - A KEDB Summary Table:\n"
        "    | KE ID | Problem ID | Service | Root Cause Summary | Workaround Key Steps |\n"
        "  - For each record: confirm it includes ke_id, parent_problem_id, root_cause, "
        "    workaround (with steps), permanent_fix, affected_ci, linked_incidents\n\n"
        "IMPORTANT: Your workarounds will be read by engineers under pressure. "
        "Be specific. Cite exact metrics, thresholds, commands, and validation steps. "
        "If the workaround for an auth pattern is 'clear Redis session cache', specify "
        "which cache, which command (redis-cli FLUSHDB on auth-cache namespace), and "
        "what success looks like."
    ),
    agent=known_error_author,
    expected_output=(
        "For each Problem: a Known Error Record (ke_id starting with 'KE-', parent_problem_id, "
        "title, root_cause, workaround with numbered steps, permanent_fix, affected_ci, "
        "linked_incidents, status='Known Error — Permanent Fix Pending'). "
        "All records must be written to the output/ directory. "
        "Plus a KEDB Summary Table in markdown format listing all KE IDs with their "
        "parent Problem IDs, services, root cause summaries, and key workaround steps."
    ),
    context=[task1, task2, task3]
)


# ============================================================================
# TASK 5: Change Proposals & Executive Summary (Change Proposer)
# ITIL Phase: Resolution via Change Enablement
# ============================================================================

task5 = Task(
    description=(
        "ITIL 4 CHANGE ENABLEMENT — REQUEST FOR CHANGE (RFC) GENERATION & EXECUTIVE SUMMARY\n\n"
        "You have Known Error Records for each confirmed Problem. "
        "Your goal is to create a formal RFC for each Known Error that permanently resolves "
        "the underlying problem, and to produce an executive summary of the Problem Management cycle.\n\n"
        "REQUIRED STEPS — for EACH Known Error:\n"
        "1. Call query_cmdb to confirm the current state of the affected CI before proposing changes. "
        "   Note the current version, infrastructure, and any relevant configuration values.\n\n"
        "2. Call create_rfc with ALL required fields:\n"
        "   - known_error_id: the KE- ID from Task 4\n"
        "   - title: clear action-oriented title (e.g., 'Configure payment-gateway batch job with memory limits')\n"
        "   - description: SPECIFIC technical description of what will change. "
        "     Reference exact config parameters, values, and files where applicable. "
        "     Example: 'Set JVM_MAX_HEAP=-Xmx2g on payment-gateway and configure batch "
        "     reconciliation job with streaming pagination (page_size=1000) to prevent "
        "     full dataset load into memory.'\n"
        "   - affected_ci: CI ID\n"
        "   - risk: Low / Medium / High (justify your rating)\n"
        "   - change_type: Normal / Standard / Emergency — apply ITIL 4 definitions\n"
        "   - test_plan: specific pre-implementation and post-implementation tests. "
        "     Include: load test parameters, what metrics to monitor, pass/fail criteria\n"
        "   - rollback_plan: exact steps to undo the change if it fails. "
        "     Include: how to detect failure, how to revert, validation steps\n"
        "   - proposed_schedule: realistic maintenance window (consider Tier-0/Tier-1 requirements)\n\n"
        "CHANGE TYPE CLASSIFICATION GUIDE:\n"
        "  - Standard: low-risk, pre-approved category, well-tested procedure, no CAB required\n"
        "  - Normal: moderate/high risk, requires CAB approval before implementation\n"
        "  - Emergency: immediate P1 risk, requires emergency CAB, implement within 24h\n\n"
        "DELIVERABLES:\n"
        "  - One RFC per Known Error (written to output/ as JSON files)\n"
        "  - RFC Summary Table:\n"
        "    | RFC ID | KE ID | Title | CI | Risk | Type | Proposed Schedule |\n"
        "  - EXECUTIVE SUMMARY (1-2 pages equivalent) covering:\n"
        "    * Problem Management Cycle Overview: how many incidents analyzed, patterns found\n"
        "    * Pattern Summaries: each pattern with incident count and root cause (1 sentence each)\n"
        "    * Business Impact Quantification: total incidents prevented if fixes implemented, "
        "      total downtime hours avoided, P1/P2 incidents eliminated\n"
        "    * ITIL 4 Framework Alignment: how this cycle implemented Problem Identification, "
        "      Problem Control, and Error Control\n"
        "    * Recommended Priority Order for RFC implementation\n"
        "    * Process Improvement Recommendations: gaps in change risk rating, load testing, "
        "      and AZ resilience testing that allowed these Problems to persist"
    ),
    agent=change_proposer,
    expected_output=(
        "For each Known Error: an RFC record (rfc_id starting with 'RFC-', parent_known_error_id, "
        "title, description, affected_ci, change_type, risk_rating, test_plan, rollback_plan, "
        "proposed_schedule, approval_required). All RFCs written to output/ directory. "
        "Plus: RFC Summary Table in markdown, and a full Executive Summary covering all patterns, "
        "business impact quantification, ITIL 4 alignment, implementation priority order, "
        "and process improvement recommendations. The Executive Summary must be written in "
        "language suitable for a CIO or VP of Technology briefing."
    ),
    context=[task1, task2, task3, task4]
)
