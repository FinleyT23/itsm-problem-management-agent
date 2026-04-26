# Written Summary — FinServe Problem Management Agent
## Pattern Discovery & Tool Design

---

### 1. Overview

This agent system implements the ITIL 4 Problem Management lifecycle across five sequential CrewAI
agents. The crew processes 141 Q1 2026 incident records, a 10-record CMDB, and 14 change log entries
to autonomously identify recurring incident patterns, determine root causes, and produce formal
Known Error Records and RFCs. The system discovered **four distinct patterns** embedded within
approximately 110 noise incidents.

---

### 2. Patterns Discovered

#### Pattern 1 — Payment Gateway Weekly Memory Exhaustion
- **Cluster:** `payment-gateway / Application / Memory / ERR-5012`
- **Incident Count:** 8 incidents (INC01001–INC01008)
- **Temporal Signal:** All 8 incidents occurred on **Tuesday nights** between 22:00–00:00 UTC
- **Change Correlation:** All 8 incidents link directly to `CHG0042` — "Payment gateway batch
  reconciliation schedule" — which configured a weekly batch job to run every Tuesday at 22:00 UTC
- **Root Cause:** CHG0042 introduced a weekly batch reconciliation job that loads the full
  transaction dataset into JVM heap without pagination or streaming, causing heap exhaustion
  (OutOfMemoryError) and 503 errors on every Tuesday night execution. The change was classified
  Standard/Low risk and skipped performance and load testing.
- **Workaround:** Identify and kill the batch reconciliation process; restart payment-gateway pods;
  confirm heap drops below 50%.
- **Permanent Fix:** Implement streaming pagination (page_size=1000) on the batch job and set JVM
  heap limits (-Xmx2g) with alerting at 80% threshold.

#### Pattern 2 — Auth Service Post-Deployment JWT Failures
- **Cluster:** `auth-service / Security / Authentication / ERR-4401`
- **Incident Count:** 10 incidents (INC01009–INC01018)
- **Temporal Signal:** Incidents cluster within 24–48 hours of auth-service deployments (CHG0078,
  CHG0079, CHG0091, CHG0095, CHG0102) spanning January–March 2026
- **Change Correlation:** Every incident links to an auth-service change; CHG0078 (v2.14.0
  JWT signing logic change) was the initiating change; subsequent incidents tracked each
  successive deployment and hotfix cycle
- **Root Cause:** The auth-service JWT signing and token cache handling introduced a regression
  in v2.14.0 (CHG0078) that was never fully resolved through the subsequent hotfix cycle. Each
  new auth-service deployment reintroduces token validation failures because the root JWT signing
  key rotation logic and Redis session cache TTL interaction were not regression-tested after
  the v2.14.0 PKCE flow changes.
- **Workaround:** Clear the Redis session cache on the auth-cache namespace; if failures persist,
  roll back auth-service to the last known-good version (v2.13.9).
- **Permanent Fix:** Implement mandatory JWT signing regression test suite that validates token
  issuance, validation, and refresh flows before any auth-service deployment proceeds to production.

#### Pattern 3 — Account Ledger Month-Start Connection Pool Exhaustion
- **Cluster:** `account-ledger / Database / Connection Pool / ERR-3200`
- **Incident Count:** 6 incidents (INC01019–INC01024), appearing on the 1st–3rd of each month
- **Temporal Signal:** All incidents occur on the **first 1–3 days of each month**, consistent
  with month-end/month-start batch reporting cycles
- **Root Cause:** The reporting-engine (CHG0048) was optimized to increase query parallelism from
  10 to 25 threads, sharing the `db-ledger-prod` database connection pool with account-ledger.
  At month-start, the reporting-engine's month-end report batch executes, consuming up to 25
  connections simultaneously and exhausting the 200-connection pool cap (`max_pool_size=200`)
  set in CHG0055. The CMDB explicitly notes this shared connection pool dependency, but the
  change risk assessment for CHG0048 did not account for it.
- **Workaround:** Identify and terminate the month-end reporting batch process consuming connections;
  connections will recover to normal within 2–5 minutes.
- **Permanent Fix:** Implement separate connection pool allocation for reporting-engine with a
  hard cap of 15 connections; add connection pool monitoring alerts at 80% utilization.

#### Pattern 4 — Mobile API AZ-Specific Infrastructure Fault
- **Cluster:** `mobile-api / Network / Timeout / ERR-5040`
- **Incident Count:** 7 incidents (INC01025–INC01031)
- **Temporal Signal:** No fixed day/time pattern; incidents distributed across all days
- **Infrastructure Signal:** All incident descriptions explicitly reference **us-west-2 AZ-c**;
  other availability zones are unaffected
- **Root Cause:** CHG0085 enabled multi-region deployment for mobile-api in us-west-2 across
  AZ-a, AZ-b, and AZ-c. AZ-c has a persistent infrastructure-layer issue (packet loss, elevated
  latency) that was not detected during pre-deployment testing. Traffic routed to AZ-c experiences
  504 gateway timeouts while AZ-a and AZ-b remain healthy, indicating an AZ-level infrastructure
  fault rather than an application bug.
- **Workaround:** Drain traffic from us-west-2 AZ-c by adjusting load balancer weights (set
  AZ-c weight to 0); confirm all mobile-api traffic routes through AZ-a and AZ-b.
- **Permanent Fix:** Engage AWS Support to investigate persistent packet loss in us-west-2 AZ-c;
  implement automated AZ health checks with automatic traffic drainage when AZ-level latency
  exceeds 200ms p99.

---

### 3. How Tool Design Enabled Pattern Discovery

#### Real File I/O (5 tools reading CSVs at runtime)
The core insight was that hardcoded tools cannot discover what you do not already know.
Five tools read the actual CSV files at runtime:
- `parse_incidents` — loads and filters the full 141-record incident dataset
- `find_patterns` — groups by service/subcategory/error_code and applies frequency thresholds
- `get_time_distribution` — reads timestamps to reveal day-of-week and hour-of-day clustering
- `query_cmdb` — reads CI records to surface shared infrastructure notes (e.g., `max_pool_size=200`,
  shared `db-ledger-prod`)
- `query_changes` — reads change descriptions to confirm causal mechanisms

#### Change Correlation as the Key Analytical Layer
The `correlate_incidents_changes` tool with a 72-hour window proved to be the decisive tool
for Patterns 1 and 2. By scoring how many times each change ID preceded an incident, the tool
surfaced CHG0042 appearing before all 8 payment-gateway incidents — a near-perfect correlation
that a frequency-only analysis would miss.

#### Temporal Analysis for Non-Change-Correlated Patterns
Patterns 3 and 4 lacked direct `related_change` links in the incident records.
`get_time_distribution` revealed Pattern 3's month-start clustering (days 1–3), and the
`build_timeline` tool interleaved changes and incidents chronologically to establish that
CHG0048's parallelism increase preceded the first connection pool exhaustion.
For Pattern 4, the temporal tool showed no day-of-week signal, which directed the investigation
to the `short_description` field — where every incident explicitly named `us-west-2 AZ-c`.

#### CMDB as the Bridge Between Patterns
The `map_dependencies` and `query_cmdb` tools were essential for Pattern 3. The CMDB notes field
explicitly documents: *"max_pool_size=200"* and that `db-ledger-prod` is shared between
account-ledger and reporting-engine. Without CMDB lookup, the connection pool exhaustion pattern
appears as a database problem; with it, the shared infrastructure dependency and the CHG0048
parallelism increase become the obvious causal chain.

#### Sequential Pipeline: Why It Matters
The sequential architecture ensured that each agent's output enriched the next:
- The Trend Analyst's pattern clusters (with incident IDs) gave the CMDB Correlator specific
  CI IDs to look up — eliminating trial-and-error CMDB queries
- The CMDB Correlator's change correlations gave the Root Cause Investigator specific CHG IDs
  to examine in detail — enabling precise Five Whys answers rather than speculation
- The Root Cause Investigator's root cause statements gave the Known Error Author the precise
  language needed for actionable KEDB records
- The Known Error Author's permanent_fix descriptions gave the Change Proposer a specific
  technical target for each RFC — no vagueness about what needs to change

---

### 4. Tool Summary

| # | Tool | File I/O | Purpose |
|---|------|----------|---------|
| 1 | `parse_incidents` | READ CSV | Load/filter incident records |
| 2 | `find_patterns` | READ CSV | Frequency clustering |
| 3 | `get_time_distribution` | READ CSV | Temporal pattern analysis |
| 4 | `query_cmdb` | READ CSV | CI metadata lookup |
| 5 | `query_changes` | READ CSV | Change record lookup |
| 6 | `map_dependencies` | READ CSV | Dependency graph walker |
| 7 | `correlate_incidents_changes` | READ CSV | Change-incident correlation scoring |
| 8 | `five_whys_analysis` | None | Five Whys framework generator |
| 9 | `build_timeline` | READ CSV | Chronological event timeline |
| 10 | `create_problem_record` | None | Formal Problem Record generator |
| 11 | `create_known_error` | **WRITE JSON** | KEDB record writer |
| 12 | `create_rfc` | **WRITE JSON** | RFC writer |
| 13 | `calculate_impact` | READ CSV | Business impact calculator |

**Total: 13 tools | 7 read CSVs at runtime | 2 write output files**
