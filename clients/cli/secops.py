#!/usr/bin/env python3
"""SecOps Workflow Engine CLI Interface.

A clean command-line consumer of the workflow engine primitives.
"""

import argparse
import os
import signal
import sys
import time
from datetime import datetime, timedelta, timezone


# Ensure secops-lean root is in pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from engine import LifecycleState, SearchBatchResult, SearchRequest, SearchSession, SecOpsEngine


def main():
    parser = argparse.ArgumentParser(description="SecOps Workflow Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search command
    search_parser = subparsers.add_parser("search", help="Execute UDM Search workflow")
    search_parser.add_argument("--query", "-q", required=True, help="UDM Query expression")
    search_parser.add_argument("--start", help="Start timestamp ISO8601 (default: 24h ago)")
    search_parser.add_argument("--end", help="End timestamp ISO8601 (default: now)")
    search_parser.add_argument("--limit", type=int, default=10000, help="Max events limit")
    search_parser.add_argument("--batch-size", type=int, default=2000, help="Batch size per fetch")

    # UDM Stats Search command
    stats_parser = subparsers.add_parser(
        "search-stats",
        aliases=["stats-search"],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="Execute UDM Stats Search (Aggregation, Analytics & Metrics)",
        description="""Execute analytical UDM aggregation queries using match/outcome syntax.

Stats queries use match/outcome syntax (different from UDM search):
  - match:   defines grouping variables (e.g. match: $logType)
  - outcome: defines aggregation functions (count, sum, min, max, avg, count_distinct)
  - order:   (optional) sort outcome metric (e.g. order: $total desc)
  - limit:   (optional) group limit (e.g. limit: 10)

Canonical Examples:
  1. UDM Events by Log Type:
     secops.py search-stats -q 'metadata.base_labels.namespaces = "SDL" metadata.log_type = $logType match: $logType outcome: $total = count(metadata.id) order: $total desc limit: 10'

  2. UDM Entity Graph Distribution:
     secops.py search-stats -q 'graph.metadata.entity_type = $et match: $et outcome: $total = count(graph.metadata.product_entity_id) order: $total desc limit: 10'

  3. Detection Alerts by Rule Name:
     secops.py search-stats -q 'detection.detection.rule_name = $rn match: $rn outcome: $total = count(detection.id) order: $total desc limit: 10'

  4. Event Type Distribution (CSV format):
     secops.py search-stats -q 'metadata.event_type = $et match: $et outcome: $total = count(metadata.id)' --format csv

See docs/UDM_STATS_SYNTAX.md for the complete query language reference and documentation.""",
    )
    stats_parser.add_argument(
        "--query",
        "-q",
        required=True,
        help="UDM Stats query with match/outcome aggregation (e.g. 'metadata.event_type = $et match: $et outcome: $total = count(metadata.id)')",
    )
    stats_parser.add_argument("--start", help="Start timestamp ISO8601 (default: 24h ago)")
    stats_parser.add_argument("--end", help="End timestamp ISO8601 (default: now)")
    stats_parser.add_argument("--limit", type=int, default=10000, help="Max events limit (default: 10000)")
    stats_parser.add_argument("--format", "-f", choices=["table", "json", "csv"], default="table", help="Output format (default: table)")
    stats_parser.add_argument("--dedup", action="store_true", help="Deduplicate identical rows in the result set")
    stats_parser.add_argument("--case-sensitive", action="store_true", help="Perform case-sensitive matching")

    # Investigate command
    inv_parser = subparsers.add_parser("investigate", help="Investigate a specific SecOps event and view Raw Log")
    inv_parser.add_argument("--event-id", "-id", required=True, help="Event ID (Base64 string)")
    inv_parser.add_argument("--token", help="Optional Event Log Token for raw log lookup")
    inv_parser.add_argument("--raw-log", action="store_true", help="Fetch and display decoded verbatim Raw Log")

    # Entity Search command
    entity_parser = subparsers.add_parser("entity-search", help="Execute canonical entity pivot search")
    entity_parser.add_argument("--type", "-t", required=True, choices=["IP", "HOSTNAME", "USER", "SHA256", "DOMAIN"], help="Entity Type")
    entity_parser.add_argument("--value", "-v", required=True, help="Entity Value")
    entity_parser.add_argument("--start", help="Start timestamp ISO8601 (default: 24h ago)")
    entity_parser.add_argument("--end", help="End timestamp ISO8601 (default: now)")
    entity_parser.add_argument("--limit", type=int, default=1000, help="Max events limit")

    # Refine Search command
    refine_parser = subparsers.add_parser("refine", help="Refine an existing query with field filters")
    refine_parser.add_argument("--base-query", "-q", required=True, help="Base UDM Query")
    refine_parser.add_argument("--include", "-i", action="append", default=[], help="Include field filter in format: field=value")
    refine_parser.add_argument("--exclude", "-e", action="append", default=[], help="Exclude field filter in format: field=value")
    refine_parser.add_argument("--start", help="Start timestamp ISO8601 (default: 24h ago)")
    refine_parser.add_argument("--end", help="End timestamp ISO8601 (default: now)")
    refine_parser.add_argument("--limit", type=int, default=1000, help="Max events limit")

    # Case Investigate command
    case_parser = subparsers.add_parser("case", help="Search cases, investigate workspace, and manage comments")
    case_sub = case_parser.add_subparsers(dest="case_action", required=True)
    case_show = case_sub.add_parser("show", help="Show full composite case workspace")
    case_show.add_argument("case_id", help="Case ID (e.g. 104185)")

    case_comment = case_sub.add_parser("comment", help="Add a comment to a case")
    case_comment.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_comment.add_argument("text", help="Comment text")

    case_search_cmd = case_sub.add_parser("search", help="Search cases across text, priorities, stages, and tags")
    case_search_cmd.add_argument("query", nargs="?", default="", help="Search query text / keyword (default: '')")
    case_search_cmd.add_argument("--priority", "-p", action="append", default=[], help="Filter by priority (LOW, MEDIUM, HIGH, CRITICAL)")
    case_search_cmd.add_argument("--stage", "-s", action="append", default=[], help="Filter by stage (e.g. Triage, Investigation)")
    case_search_cmd.add_argument("--tag", "-t", action="append", default=[], help="Filter by tag")
    case_search_cmd.add_argument("--environment", "-env", action="append", default=[], help="Filter by environment")
    case_search_cmd.add_argument("--assignee", "-u", action="append", default=[], help="Filter by assignee user/role")
    case_search_cmd.add_argument("--important", action="store_true", default=None, help="Filter only important cases")
    case_search_cmd.add_argument("--limit", type=int, default=20, help="Results page size (default: 20)")
    case_search_cmd.add_argument("--page", type=int, default=0, help="Page number (default: 0)")

    case_triage_single_cmd = case_sub.add_parser(
        "triage",
        help="End-to-end single case triage: investigation, Gemini AI summary, title/entity precedents, novelty, and updates",
    )
    case_triage_single_cmd.add_argument("case_id", help="Case ID to triage (e.g. 104839)")
    case_triage_single_cmd.add_argument("--summary", action="store_true", default=True, help="Fetch and analyze Gemini AI summary (default: True)")
    case_triage_single_cmd.add_argument("--no-summary", action="store_false", dest="summary", help="Skip Gemini AI summary")
    case_triage_single_cmd.add_argument("--precedents", action="store_true", default=True, help="Search historical title and entity precedents (default: True)")
    case_triage_single_cmd.add_argument("--no-precedents", action="store_false", dest="precedents", help="Skip precedent search")
    case_triage_single_cmd.add_argument("--update-stage", action="store_true", default=False, help="Auto-apply suggested stage update in SecOps")
    case_triage_single_cmd.add_argument("--comment", action="store_true", default=False, help="Post structured triage report as a case comment")
    case_triage_single_cmd.add_argument("--generate-prompts", action="store_true", default=False, help="Output ready-to-use Antigravity subagent dispatch prompts")
    case_triage_single_cmd.add_argument("--format", "-f", choices=["table", "json", "markdown"], default="table", help="Output format (default: table)")

    case_timeline_cmd = case_sub.add_parser(
        "timeline",
        help="Synthesize and display a chronological event timeline for a case",
    )
    case_timeline_cmd.add_argument("case_id", help="Case ID (e.g. 104839)")
    case_timeline_cmd.add_argument("--format", "-f", choices=["table", "json", "markdown"], default="table", help="Output format (default: table)")

    case_comments_cmd = case_sub.add_parser(
        "comments",
        help="List analyst comments and AI assessment notes for a case",
    )
    case_comments_cmd.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_comments_cmd.add_argument("--format", "-f", choices=["table", "json", "markdown"], default="table", help="Output format (default: table)")

    case_wall_cmd = case_sub.add_parser(
        "wall",
        help="Retrieve the complete SOAR case activity wall records",
    )
    case_wall_cmd.add_argument("case_id", help="Case ID (e.g. 104839)")
    case_wall_cmd.add_argument("--limit", "-n", type=int, default=50, help="Number of records to retrieve (default: 50)")
    case_wall_cmd.add_argument("--type", choices=["CASE_STATUS_CHANGE", "CASE_ACTION", "CASE_COMMENT"], help="Filter by activity type")
    case_wall_cmd.add_argument("--page-token", help="Pagination token for subsequent pages")
    case_wall_cmd.add_argument("--format", "-f", choices=["table", "json", "markdown"], default="table", help="Output format (default: table)")

    case_triage_cmd = case_sub.add_parser(
        "orchestrate-triage",
        aliases=["triage-batch"],
        help="Batch retrieve latest SOAR cases, perform deep investigation, and derive triage verdicts",
    )
    case_triage_cmd.add_argument("--case-id", "-c", action="append", default=[], help="Specific Case ID(s) to triage (can be specified multiple times)")
    case_triage_cmd.add_argument("--limit", "-n", type=int, default=5, help="Number of cases to retrieve and triage (default: 5)")
    case_triage_cmd.add_argument("--all-statuses", action="store_true", default=False, help="Include closed cases (default: open only)")
    case_triage_cmd.add_argument("--query", "-q", default="", help="Optional search query filter")
    case_triage_cmd.add_argument("--priority", "-p", action="append", default=[], help="Filter by priority (LOW, MEDIUM, HIGH, CRITICAL)")
    case_triage_cmd.add_argument("--stage", "-s", action="append", default=[], help="Filter by stage")
    case_triage_cmd.add_argument("--tag", "-t", action="append", default=[], help="Filter by tag")
    case_triage_cmd.add_argument("--environment", "-env", action="append", default=[], help="Filter by environment")
    case_triage_cmd.add_argument("--assignee", "-u", action="append", default=[], help="Filter by assignee")
    case_triage_cmd.add_argument("--summary", action="store_true", default=False, help="Fetch Gemini AI case summaries for each candidate (default: False)")
    case_triage_cmd.add_argument("--precedents", action="store_true", default=True, help="Search historical title and entity precedents (default: True)")
    case_triage_cmd.add_argument("--no-precedents", action="store_false", dest="precedents", help="Skip precedent search")
    case_triage_cmd.add_argument("--format", "-f", choices=["table", "json", "markdown"], default="table", help="Output format (default: table)")
    case_triage_cmd.add_argument("--generate-prompts", action="store_true", default=False, help="Output ready-to-use Antigravity subagent dispatch prompts")

    case_update_cmd = case_sub.add_parser("update", help="Update case attributes (assignee, stage, incident, priority)")
    case_update_cmd.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_update_cmd.add_argument("--assignee", "-a", help="Assign to SOC role (@Tier1) or user GUID")
    case_update_cmd.add_argument("--stage", "-s", help="Set lifecycle stage (e.g. Assessment, Investigation, Incident)")
    case_update_cmd.add_argument("--incident", action="store_true", default=None, help="Mark case as incident")
    case_update_cmd.add_argument("--no-incident", action="store_false", dest="incident", help="Unmark case as incident")
    case_update_cmd.add_argument("--priority", "-p", help="Set priority (LOW, MEDIUM, HIGH, CRITICAL)")

    case_assign_cmd = case_sub.add_parser("assign", help="Assign case to SOC role (@Role) or user GUID/email")
    case_assign_cmd.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_assign_cmd.add_argument("--to", required=True, help="Target role (@Tier1) or user GUID / email")

    case_stage_cmd = case_sub.add_parser("set-stage", help="Update case lifecycle stage")
    case_stage_cmd.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_stage_cmd.add_argument("--stage", "-s", required=True, help="Target stage (e.g. Assessment, Investigation, Incident)")

    case_incident_cmd = case_sub.add_parser("set-incident", help="Mark or unmark case as incident")
    case_incident_cmd.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_incident_cmd.add_argument("--incident", action="store_true", default=True, help="Mark as incident (default)")
    case_incident_cmd.add_argument("--no-incident", action="store_false", dest="incident", help="Unmark as incident")

    case_alert_prio_cmd = case_sub.add_parser("alert-priority", help="Update priority level of a specific case alert")
    case_alert_prio_cmd.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_alert_prio_cmd.add_argument("alert_id", help="Alert ID or resource name")
    case_alert_prio_cmd.add_argument("--priority", "-p", required=True, help="Priority (LOW, MEDIUM, HIGH, CRITICAL, INFO)")

    case_rec_cmd = case_sub.add_parser("recommend-alert", help="Generate or retrieve Gemini AI recommendation for a case alert")
    case_rec_cmd.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_rec_cmd.add_argument("alert_id", help="Alert ID or resource name")
    case_rec_cmd.add_argument("--wait", action="store_true", default=True, help="Poll until completion (default: true)")
    case_rec_cmd.add_argument("--no-wait", action="store_false", dest="wait", help="Trigger asynchronously without waiting")
    case_rec_cmd.add_argument("--timeout", type=float, default=30.0, help="Polling timeout in seconds (default: 30)")

    case_rec_fetch_cmd = case_sub.add_parser("recommend-fetch", help="Fetch Gemini AI recommendation by recommendation ID")
    case_rec_fetch_cmd.add_argument("case_id", help="Case ID (e.g. 104185)")
    case_rec_fetch_cmd.add_argument("recommendation_id", help="Recommendation ID (UUID)")

    case_summary_cmd = case_sub.add_parser("summary", help="Retrieve or generate Gemini AI summary for a SOAR case")
    case_summary_cmd.add_argument("case_id", help="Case ID (e.g. 104655)")
    case_summary_cmd.add_argument("--wait", action="store_true", default=True, help="Poll until completion (default: true)")
    case_summary_cmd.add_argument("--no-wait", action="store_false", dest="wait", help="Fetch or initiate asynchronously without polling")
    case_summary_cmd.add_argument("--timeout", type=float, default=45.0, help="Polling timeout in seconds (default: 45)")

    # Alert Investigate command
    alert_parser = subparsers.add_parser("alert", help="Investigate specific SecOps alert")
    alert_sub = alert_parser.add_subparsers(dest="alert_action", required=True)
    alert_show = alert_sub.add_parser("show", help="Show alert deep-dive details")
    alert_show.add_argument("alert_name", help="Alert resource name or identifier")

    # Playbook command
    playbook_parser = subparsers.add_parser("playbook", help="Search playbooks, view steps, and list categories")
    playbook_sub = playbook_parser.add_subparsers(dest="playbook_action", required=True)

    pb_search = playbook_sub.add_parser("search", help="Search and filter SOAR playbooks")
    pb_search.add_argument("query", nargs="?", default="", help="Keyword query (matches name, creator, ID)")
    pb_search.add_argument("--category", "-c", help="Filter by category (e.g. GSA, Blocks, Cymbal)")
    pb_search.add_argument("--type", "-t", choices=["REGULAR", "NESTED"], help="Filter by playbook type")
    pb_search.add_argument("--enabled", action="store_true", default=None, help="Filter only enabled playbooks")
    pb_search.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    pb_list = playbook_sub.add_parser("list", help="List all SOAR playbooks")
    pb_list.add_argument("--category", "-c", help="Filter by category")
    pb_list.add_argument("--type", "-t", choices=["REGULAR", "NESTED"], help="Filter by playbook type")
    pb_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    pb_get = playbook_sub.add_parser("get", help="Get full playbook details, trigger, and step DAG")
    pb_get.add_argument("identifier", help="Playbook UUID identifier or numeric ID (e.g. 2277)")

    pb_audit = playbook_sub.add_parser("audit", help="Audit all playbooks & blocks, priorities, enabled status, and environment mappings")
    pb_audit.add_argument("--type", "-t", choices=["REGULAR", "NESTED"], help="Filter by playbook type (REGULAR or NESTED)")
    pb_audit.add_argument("--environment", "-e", help="Filter by SOC environment name")
    pb_audit.add_argument("--category", "-c", help="Filter by category folder")
    pb_audit.add_argument("--enabled", action="store_true", help="Filter for enabled workflows only")
    pb_audit.add_argument("--disabled", action="store_true", help="Filter for disabled workflows only")
    pb_audit.add_argument("--limit", type=int, default=500, help="Maximum workflows to retrieve (default: 500)")
    pb_audit.add_argument("--out", "-o", help="Optional path to output JSON report file")
    pb_audit.add_argument("--json", action="store_true", help="Print raw JSON output")

    pb_health = playbook_sub.add_parser("audit-health", help="Comprehensive SOAR Playbook Health Check, failure triage, faulted action hotspots, and queue latency using native Playbook Dashboard telemetry")
    pb_health.add_argument("--days", "-d", type=int, default=7, help="Evaluation lookback period in days (default: 7)")
    pb_health.add_argument("--no-deep-scan", action="store_true", help="Skip deep query analytics and run inventory-only audit")
    pb_health.add_argument("--fail-threshold", type=float, default=15.0, help="Failure percentage threshold for high risk findings (default: 15.0)")
    pb_health.add_argument("--slow-threshold", type=float, default=3.0, help="Runtime duration threshold in minutes for slow playbooks (default: 3.0)")
    pb_health.add_argument("--out", "-o", help="Optional path to output JSON report file")
    pb_health.add_argument("--json", action="store_true", help="Print raw JSON output")

    pb_cats = playbook_sub.add_parser("categories", help="List all SOAR playbook categories/folders")

    # Integration command
    int_parser = subparsers.add_parser("integration", help="Search integrations, view instances, and inspect remote agents")
    int_sub = int_parser.add_subparsers(dest="integration_action", required=True)

    int_search = int_sub.add_parser("search", help="Search and filter SOAR integrations")
    int_search.add_argument("query", nargs="?", default="", help="Keyword query (matches identifier, name, description)")
    int_search.add_argument("--env", help="Filter integrations configured for a specific environment (or '*' for global)")
    int_search.add_argument("--configured", action="store_true", default=None, help="Filter only configured integrations")
    int_search.add_argument("--certified", action="store_true", default=None, help="Filter only certified integrations")
    int_search.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    int_list = int_sub.add_parser("list", help="List all SOAR integrations")
    int_list.add_argument("--env", help="Filter integrations configured for a specific environment")
    int_list.add_argument("--configured", action="store_true", default=None, help="Filter only configured integrations")
    int_list.add_argument("--certified", action="store_true", default=None, help="Filter only certified integrations")
    int_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    int_get = int_sub.add_parser("get", help="Get full integration details, instances, remote agents, and docs")
    int_get.add_argument("identifier", help="Integration identifier (e.g. CrowdStrikeFalcon, GoogleSecOpsAiAgents)")

    int_inst = int_sub.add_parser("instances", help="List configured integration instances across environments")
    int_inst.add_argument("--integration", "-i", help="Filter by integration identifier")
    int_inst.add_argument("--env", "-e", help="Filter by environment (e.g. 'Default Environment', 'Cymbal', '*')")

    int_agents = int_sub.add_parser("agents", help="List remote execution proxy agents")
    int_agents.add_argument("--active-only", action="store_true", default=False, help="Filter only active agents")

    # Job command
    job_parser = subparsers.add_parser("job", help="Search scheduled jobs, inspect instances, and view execution logs")
    job_sub = job_parser.add_subparsers(dest="job_action", required=True)

    job_search = job_sub.add_parser("search", help="Search and filter SOAR scheduled jobs")
    job_search.add_argument("query", nargs="?", default="", help="Keyword query (matches display name, description, integration)")
    job_search.add_argument("--integration", "-i", help="Filter by integration name (e.g. Demoverse, Splunk)")
    job_search.add_argument("--enabled", action="store_true", default=None, help="Filter only enabled jobs")
    job_search.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    job_list = job_sub.add_parser("list", help="List all SOAR scheduled jobs")
    job_list.add_argument("--integration", "-i", help="Filter by integration name")
    job_list.add_argument("--enabled", action="store_true", default=None, help="Filter only enabled jobs")
    job_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    job_get = job_sub.add_parser("get", help="Get full details for a job including runtime instances and logs")
    job_get.add_argument("integration", help="Integration identifier (e.g. Demoverse)")
    job_get.add_argument("job_id", help="Job numeric ID (e.g. 667)")

    job_inst = job_sub.add_parser("instances", help="List runtime job instances across environments")
    job_inst.add_argument("--integration", "-i", help="Filter by integration identifier")
    job_inst.add_argument("--job-id", "-j", help="Filter by job ID")

    job_logs = job_sub.add_parser("logs", help="Get execution run history and logs for a job instance")
    job_logs.add_argument("instance_id", help="Job instance numeric ID (e.g. 80)")
    job_logs.add_argument("--limit", type=int, default=10, help="Number of log runs to retrieve (default: 10)")

    # Content Pack command
    pack_parser = subparsers.add_parser("pack", help="Search Content Hub Marketplace packs, categories, and bundled playbooks/rulesets")
    pack_sub = pack_parser.add_subparsers(dest="pack_action", required=True)

    pack_search = pack_sub.add_parser("search", help="Search and filter Marketplace Content Packs")
    pack_search.add_argument("query", nargs="?", default="", help="Keyword query (matches title, description, categories, uploader)")
    pack_search.add_argument("--category", "-c", help="Filter by category (e.g. 'Threat Intelligence', 'Cloud')")
    pack_search.add_argument("--type", "-t", help="Filter by type (e.g. ONBOARDING, PRODUCT, EXTERNAL)")
    pack_search.add_argument("--deployed", action="store_true", default=None, help="Filter only installed/deployed packs")
    pack_search.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    pack_list = pack_sub.add_parser("list", help="List all Marketplace Content Packs")
    pack_list.add_argument("--category", "-c", help="Filter by category")
    pack_list.add_argument("--type", "-t", help="Filter by type")
    pack_list.add_argument("--deployed", action="store_true", default=None, help="Filter only installed/deployed packs")
    pack_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    pack_get = pack_sub.add_parser("get", help="Get full Content Pack details and bundled components")
    pack_get.add_argument("identifier", help="Content Pack UUID identifier, resource name, or title")

    pack_cats = pack_sub.add_parser("categories", help="List all Content Hub categories with pack counts")

    # Curated Detections command
    curated_parser = subparsers.add_parser("curated", help="Explore Google SecOps Curated Rule Sets, MITRE mappings, YARA-L logic, and detection telemetry")
    curated_sub = curated_parser.add_subparsers(dest="curated_action", required=True)

    cur_search = curated_sub.add_parser("rulesets", help="Search and filter Curated Rule Sets")
    cur_search.add_argument("query", nargs="?", default="", help="Keyword query (matches title, description, category, authors)")
    cur_search.add_argument("--category", "-c", help="Filter by category name or ID (e.g. 'Cloud Threats')")
    cur_search.add_argument("--tactic", help="Filter by MITRE ATT&CK tactic (e.g. 'TA0005' or 'Stealth')")
    cur_search.add_argument("--technique", help="Filter by MITRE ATT&CK technique (e.g. 'T1562')")
    cur_search.add_argument("--log-source", "-l", help="Filter by log source (e.g. 'Azure Activity')")
    cur_search.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    cur_get = curated_sub.add_parser("get", help="Deep-inspect a Curated Rule Set, its deployments, and member rules")
    cur_get.add_argument("identifier", help="Curated Rule Set UUID, resource name, or title")

    cur_rule = curated_sub.add_parser("rule", help="Inspect a Curated Rule and extract its executable YARA-L logic")
    cur_rule.add_argument("rule_id", help="Curated Rule ID (e.g. 'ur_025628f0-af2d-4a52-b899-4de31928edfc') or title")

    cur_metrics = curated_sub.add_parser("metrics", help="Show tenant-wide rule quotas and top firing Curated Rule Sets")
    cur_metrics.add_argument("--days", type=int, default=7, help="Time window in days (default: 7)")

    cur_set = curated_sub.add_parser("set-deployment", help="Enable/disable a Curated Rule Set deployment and toggle alerting")
    cur_set.add_argument("identifier", help="Curated Rule Set UUID, resource name, or title")
    cur_set.add_argument("--precision", choices=["PRECISE", "BROAD", "precise", "broad"], default="PRECISE", help="Precision profile (default: PRECISE)")
    cur_set_state = cur_set.add_mutually_exclusive_group()
    cur_set_state.add_argument("--enabled", dest="enabled", action="store_true", default=None, help="Enable deployment")
    cur_set_state.add_argument("--disabled", dest="enabled", action="store_false", default=None, help="Disable deployment")
    cur_set_alert = cur_set.add_mutually_exclusive_group()
    cur_set_alert.add_argument("--alerting", dest="alerting", action="store_true", default=None, help="Enable alerting")
    cur_set_alert.add_argument("--no-alerting", dest="alerting", action="store_false", default=None, help="Disable alerting (silent detection)")
    cur_set.add_argument("--no-sync-rules", dest="sync_rules", action="store_false", default=True, help="Do not cascade status to individual rules")

    cur_audit = curated_sub.add_parser("audit", help="Run comprehensive Curated Detections Health Check & Operational Audit")
    cur_audit.add_argument("--days", type=int, default=7, help="Evaluation timeframe in days (default: 7)")
    cur_audit.add_argument("--out", help="Optional output filepath to save JSON report")
    cur_audit.add_argument("--json", action="store_true", help="Output raw JSON instead of text tables")

    # Marketplace Response Integrations command
    mp_parser = subparsers.add_parser("marketplace", help="Search Content Hub Marketplace Response Integrations, compare version diffs, and inspect affected playbooks")
    mp_sub = mp_parser.add_subparsers(dest="mp_action", required=True)

    mp_search = mp_sub.add_parser("search", help="Search and filter Marketplace Response Integrations")
    mp_search.add_argument("query", nargs="?", default="", help="Keyword query (matches identifier, title, description, categories)")
    mp_search.add_argument("--category", "-c", help="Filter by category (e.g. 'Cloud', 'EDR', 'Email Security')")
    mp_search.add_argument("--installed", action="store_true", default=None, help="Filter only installed integrations")
    mp_search.add_argument("--updates", action="store_true", default=None, help="Filter integrations with updates available")
    mp_search.add_argument("--certified", action="store_true", default=None, help="Filter certified integrations")
    mp_search.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    mp_list = mp_sub.add_parser("list", help="List Marketplace Response Integrations")
    mp_list.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    mp_list.add_argument("--category", "-c", help="Filter by category")
    mp_list.add_argument("--installed", action="store_true", default=None, help="Filter only installed integrations")
    mp_list.add_argument("--updates", action="store_true", default=None, help="Filter integrations with updates available")
    mp_list.add_argument("--certified", action="store_true", default=None, help="Filter certified integrations")
    mp_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    mp_get = mp_sub.add_parser("get", help="Get full Marketplace Response Integration details, actions, managers, and changelogs")
    mp_get.add_argument("identifier", help="Integration identifier, resource name, or title (e.g. 'Wiz' or 'SentinelOneSingularityOperationsCenter')")

    mp_diff = mp_sub.add_parser("diff", help="Get commercial upgrade diff between installed and latest version")
    mp_diff.add_argument("identifier", help="Integration identifier or title (e.g. 'Wiz' or 'PubSub')")

    mp_affected = mp_sub.add_parser("affected", help="Get downstream environment instances and active playbooks affected by an integration")
    mp_affected.add_argument("identifier", help="Integration identifier or title (e.g. 'Wiz')")

    # Dashboards command
    dash_parser = subparsers.add_parser("dashboard", help="Explore native dashboards, inspect chart widgets, and execute statistical telemetry queries")
    dash_sub = dash_parser.add_subparsers(dest="dash_action", required=True)

    dash_list = dash_sub.add_parser("list", help="List and filter native dashboards")
    dash_list.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    dash_list.add_argument("--type", "-t", help="Filter by dashboard type (CUSTOM, DEFAULT)")
    dash_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    dash_search = dash_sub.add_parser("search", help="Search and filter native dashboards")
    dash_search.add_argument("query", nargs="?", default="", help="Keyword query")
    dash_search.add_argument("--type", "-t", help="Filter by dashboard type")
    dash_search.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    dash_get = dash_sub.add_parser("get", help="Get full dashboard details, charts, layout, and queries")
    dash_get.add_argument("identifier", help="Dashboard UUID or display name")
    dash_get.add_argument("--execute-queries", action="store_true", default=False, help="Execute chart queries and display live data tables")

    dash_query = dash_sub.add_parser("query", help="Execute a dashboard widget query against live telemetry")
    dash_query.add_argument("query_id", help="Dashboard Query UUID or resource name")
    dash_query.add_argument("--limit", type=int, default=20, help="Max rows to display (default: 20)")

    dash_val = dash_sub.add_parser("validate", help="Validate statistical / widget query syntax")
    dash_val.add_argument("query_text", help="Query text to validate")
    dash_val.add_argument("--dialect", default="DIALECT_STATS", help="Query dialect (default: DIALECT_STATS)")

    # Managed Domain Settings command
    domain_parser = subparsers.add_parser("domain", help="View approved managed email domains")
    domain_sub = domain_parser.add_subparsers(dest="domain_action", required=True)
    domain_list = domain_sub.add_parser("list", help="List approved email domains")

    # Feeds command
    feed_parser = subparsers.add_parser("feed", help="Explore ingestion feeds and source configurations")
    feed_sub = feed_parser.add_subparsers(dest="feed_action", required=True)
    feed_list = feed_sub.add_parser("list", help="List and filter ingestion feeds")
    feed_list.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    feed_list.add_argument("--source", "-s", help="Filter by feed source type (e.g. AMAZON_S3_V2)")
    feed_list.add_argument("--log-type", "-l", help="Filter by log type (e.g. CS_EDR)")
    feed_list.add_argument("--state", help="Filter by state (e.g. ACTIVE)")
    feed_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")
    feed_get = feed_sub.add_parser("get", help="Get full feed configuration and source settings")
    feed_get.add_argument("identifier", help="Feed UUID or display name")

    # Pipelines command
    pipeline_parser = subparsers.add_parser("pipeline", help="Explore Data Processing Pipelines and Bindplane SaaS integrations")
    pipeline_sub = pipeline_parser.add_subparsers(dest="pipeline_action", required=True)
    pipe_list = pipeline_sub.add_parser("list", help="List and filter Data Processing Pipelines")
    pipe_list.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    pipe_list.add_argument("--log-type", "-l", help="Filter by log type stream")
    pipe_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")
    pipe_get = pipeline_sub.add_parser("get", help="Get full pipeline transform rules and Bindplane URL")
    pipe_get.add_argument("identifier", help="Pipeline UUID or display name")

    # Feed Schemas command
    schema_parser = subparsers.add_parser("feed-schema", help="Inspect supported feed source types and log type schemas")
    schema_sub = schema_parser.add_subparsers(dest="schema_action", required=True)
    schema_sources = schema_sub.add_parser("sources", help="List supported feed source types")
    schema_sources.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")
    schema_logtypes = schema_sub.add_parser("log-types", help="List log type schemas for a feed source type")
    schema_logtypes.add_argument("source_type", help="Target feed source type (e.g. AMAZON_S3, GCS)")
    schema_logtypes.add_argument("--include-field-schemas", action="store_true", default=False, help="Include verbose details field schemas")
    schema_logtypes.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    # Parsers command
    parser_cmd = subparsers.add_parser("parser", help="Explore SIEM parsers, log types catalog, parser extensions, and settings")
    parser_sub = parser_cmd.add_subparsers(dest="parser_action", required=True)

    parser_list = parser_sub.add_parser("list", help="List and filter SIEM parsers across log types")
    parser_list.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    parser_list.add_argument("--log-type", "-l", default="-", help="Filter by log type (or '-' for all, default: '-')")
    parser_list.add_argument("--creator", "-c", choices=["GOOGLE", "CUSTOMER", "ALL"], default="ALL", help="Filter by creator (default: ALL)")
    parser_list.add_argument("--state", "-s", choices=["ACTIVE", "INACTIVE", "ALL"], default="ALL", help="Filter by parser state (default: ALL)")
    parser_list.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    parser_get = parser_sub.add_parser("get", help="Get full parser details and decoded Logstash CBN code")
    parser_get.add_argument("log_type", help="Target log type (e.g. AQUA_TRACEE_CUSTOM, GCP_IDS)")
    parser_get.add_argument("parser_id", nargs="?", default=None, help="Optional parser ID (defaults to active/latest)")
    parser_get.add_argument("--show-cbn", action="store_true", default=False, help="Display decoded Logstash CBN filter code")

    parser_logtypes = parser_sub.add_parser("log-types", help="List supported ingestion log types in the catalog")
    parser_logtypes.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    parser_logtypes.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    parser_exts = parser_sub.add_parser("extensions", help="List and filter parser extensions")
    parser_exts.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    parser_exts.add_argument("--log-type", "-l", default="-", help="Filter by log type (or '-' for all, default: '-')")
    parser_exts.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    parser_ext_get = parser_sub.add_parser("extension-get", help="Get full parser extension details, snippets, and test logs")
    parser_ext_get.add_argument("log_type", help="Target log type (e.g. CS_EDR)")
    parser_ext_get.add_argument("extension_id", help="Parser extension UUID")
    parser_ext_get.add_argument("--show-snippet", action="store_true", default=False, help="Display decoded Logstash CBN snippet")
    parser_ext_get.add_argument("--show-log", action="store_true", default=False, help="Display decoded sample test log")

    parser_setting = parser_sub.add_parser("setting", help="Get autonomous parsing settings for a log type")
    parser_setting.add_argument("log_type", help="Target log type (e.g. POWERSHELL)")

    # Preview Features command
    preview_cmd = subparsers.add_parser("preview", help="Discover customer preview features and enablement states")
    preview_sub = preview_cmd.add_subparsers(dest="preview_action", required=True)

    preview_list = preview_sub.add_parser("list", help="List and filter tenant preview features")
    preview_list.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    preview_list.add_argument("--enabled-only", "-e", action="store_true", default=False, help="Filter for only enabled features")
    preview_list.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    preview_get = preview_sub.add_parser("get", help="Get preview feature details and retirement date")
    preview_get.add_argument("feature_id", help="Preview feature ID")

    # Data RBAC command
    rbac_cmd = subparsers.add_parser("rbac", help="Inspect Data Access RBAC scopes, labels, and SOAR environments")
    rbac_sub = rbac_cmd.add_subparsers(dest="rbac_action", required=True)

    rbac_scopes = rbac_sub.add_parser("scopes", help="List and search Data Access Scopes")
    rbac_scopes.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    rbac_scopes.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    rbac_scope_get = rbac_sub.add_parser("scope-get", help="Get deep configuration of a Data Access Scope")
    rbac_scope_get.add_argument("scope_id", help="Data Access Scope ID (e.g. compliance-analyst)")

    rbac_labels = rbac_sub.add_parser("labels", help="List and search Data Access Labels and UDM queries")
    rbac_labels.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    rbac_labels.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    rbac_label_get = rbac_sub.add_parser("label-get", help="Get full configuration of a Data Access Label")
    rbac_label_get.add_argument("label_id", help="Data Access Label ID (e.g. pci)")

    rbac_envs = rbac_sub.add_parser("environments", help="List SOAR multi-tenant environments and bound Data RBAC Scopes")
    rbac_envs.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    rbac_envs.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    # Enrichment command
    enrichment_cmd = subparsers.add_parser("enrichment", help="Explore available enrichment combinations and deployed controls")
    enrichment_sub = enrichment_cmd.add_subparsers(dest="enrichment_action", required=True)

    enr_comb = enrichment_sub.add_parser("combinations", help="List available entity enrichment combinations")
    enr_comb.add_argument("enrichment_type", nargs="?", default="ALL", help="Enrichment type filter (USER_ENRICHMENT, ASSET_ENRICHMENT, GEO_IP_ENRICHMENT, GOOGLE_THREAT_INTEL_ENRICHMENT, or ALL)")
    enr_comb.add_argument("--target-log-type", "-t", default="", help="Filter by target log type")
    enr_comb.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    enr_ctrls = enrichment_sub.add_parser("controls", help="List and search deployed enrichment controls")
    enr_ctrls.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    enr_ctrls.add_argument("--type", "-t", default="ALL", help="Filter by enrichment type (e.g. GEO_IP_ENRICHMENT)")
    enr_ctrls.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    enr_get = enrichment_sub.add_parser("control-get", help="Get deep configuration of a deployed enrichment control")
    enr_get.add_argument("control_id", help="Enrichment control ID or resource name")

    # SIEM Settings command
    siem_cmd = subparsers.add_parser("siem", help="Inspect SIEM settings: agent settings, UEBA risk config, tenant instance")
    siem_sub = siem_cmd.add_subparsers(dest="siem_action", required=True)

    siem_agent = siem_sub.add_parser("agent-settings", help="Get Gemini Triage & Investigation Agent settings")
    siem_risk = siem_sub.add_parser("risk-config", help="Get UEBA Entity Risk Scoring configuration")
    siem_tenant = siem_sub.add_parser("tenant", help="Get root tenant instance details and configuration")

    # SOAR Users command
    soar_users_cmd = subparsers.add_parser("soar-users", help="Discover and filter SOAR users and external identity profiles")
    soar_users_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching user full name, email, or login identifier")
    soar_users_cmd.add_argument("--role", "-r", type=int, default=None, help="Filter by numeric SOC role ID")
    soar_users_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    # SOAR User Get command
    soar_user_get_cmd = subparsers.add_parser("soar-user-get", help="Get deep inspection of a single SOAR user profile")
    soar_user_get_cmd.add_argument("user_id", help="SOAR user numeric ID or resource name")

    # SOAR SOC Roles command
    soar_roles_cmd = subparsers.add_parser("soar-roles", help="List configured SOC roles and workflow assignment access hierarchy")
    soar_roles_cmd.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    # SOAR Company Settings command
    soar_company_cmd = subparsers.add_parser("soar-company-settings", help="Get tenant company rebranding and reporting settings")

    # SOAR Data Retention Settings command
    soar_retention_cmd = subparsers.add_parser("soar-data-retention", help="Get SOAR data retention configuration and environment policy settings")

    # SOAR Environments command
    soar_envs_cmd = subparsers.add_parser("soar-environments", help="Search and list SOAR multi-tenancy environments")
    soar_envs_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    soar_envs_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    # SOAR Environment Get command
    soar_env_get_cmd = subparsers.add_parser("soar-environment-get", help="Deep inspection of a single multi-tenancy environment")
    soar_env_get_cmd.add_argument("env_id", help="Numeric ID or resource name of the environment")

    # SOAR Environment Groups command
    soar_env_groups_cmd = subparsers.add_parser("soar-environment-groups", help="Search and list environment group collections")
    soar_env_groups_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    soar_env_groups_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    # SOAR Remote Agents command
    soar_ra_cmd = subparsers.add_parser("soar-remote-agents", help="Search and list remote SOAR execution agents and bindings")
    soar_ra_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching display name or identifier")
    soar_ra_cmd.add_argument("--env", "-e", default="", help="Filter by bound environment name")
    soar_ra_cmd.add_argument("--state", "-s", default="", help="Filter by agent state (e.g. ACTIVE, INACTIVE)")
    soar_ra_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    # SOAR Remote Agent Get command
    soar_ra_get_cmd = subparsers.add_parser("soar-remote-agent-get", help="Deep inspection of a single remote agent including certificates")
    soar_ra_get_cmd.add_argument("agent_id", help="Numeric ID or resource name of the remote agent")

    # SOAR Email Settings command
    soar_email_cmd = subparsers.add_parser("soar-email-settings", help="Get composite SOAR email transport and SMTP configuration")

    # SOAR Google Support Access Settings command
    soar_support_cmd = subparsers.add_parser("soar-support-settings", help="Get Google Support access delegation parameters")

    # SOAR Networks commands
    soar_net_cmd = subparsers.add_parser("soar-networks", help="Search and list customer CIDR network address ranges")
    soar_net_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching display name or IP range")
    soar_net_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_net_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_net_get_cmd = subparsers.add_parser("soar-network-get", help="Deep inspection of a single customer CIDR network")
    soar_net_get_cmd.add_argument("network_id", help="Numeric ID or resource name of the network")

    # SOAR Domains commands
    soar_dom_cmd = subparsers.add_parser("soar-domains", help="Search and list approved customer domain names")
    soar_dom_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching domain name")
    soar_dom_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_dom_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_dom_get_cmd = subparsers.add_parser("soar-domain-get", help="Deep inspection of a single approved customer domain")
    soar_dom_get_cmd.add_argument("domain_id", help="Numeric ID or resource name of the domain")

    # SOAR Custom Lists commands
    soar_cl_cmd = subparsers.add_parser("soar-custom-lists", help="Search and list SOAR custom key-value style retention lists")
    soar_cl_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching list name or description")
    soar_cl_cmd.add_argument("--category", "-c", default="", help="Filter by category (e.g., 'malicious_domains', 'High Value')")
    soar_cl_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_cl_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_cl_get_cmd = subparsers.add_parser("soar-custom-list-get", help="Deep inspection of a single SOAR custom list record")
    soar_cl_get_cmd.add_argument("list_id", help="Numeric ID or resource name of the custom list")

    # SOAR Email Templates commands
    soar_et_cmd = subparsers.add_parser("soar-email-templates", help="Search and list plain text and HTML email templates")
    soar_et_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching template name or description")
    soar_et_cmd.add_argument("--type", "-t", default="", help="Filter by template type (e.g. TEMPLATE, HTML_FORMAT)")
    soar_et_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_et_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_et_get_cmd = subparsers.add_parser("soar-email-template-get", help="Deep inspection of a single email template including body content")
    soar_et_get_cmd.add_argument("template_id", help="Numeric ID or resource name of the email template")

    # SOAR Entities Blocklist commands
    soar_eb_cmd = subparsers.add_parser("soar-entities-blocklists", help="Search and list entity extraction noise-reduction blocklists")
    soar_eb_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching entity value")
    soar_eb_cmd.add_argument("--entity-type", "-t", default="", help="Filter by entity type (e.g. FILENAME, USERUNIQNAME)")
    soar_eb_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_eb_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_eb_get_cmd = subparsers.add_parser("soar-entities-blocklist-get", help="Deep inspection of a single entity blocklist entry")
    soar_eb_get_cmd.add_argument("blocklist_id", help="Numeric ID or resource name of the blocklist entry")

    # SOAR SLA Definitions commands
    soar_sla_cmd = subparsers.add_parser("soar-sla-definitions", help="Search and list Service Level Agreement definitions")
    soar_sla_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching SLA name or type value")
    soar_sla_cmd.add_argument("--sla-type", "-t", default="", help="Filter by SLA type (CASE_STAGE, CASE_PRIORITY)")
    soar_sla_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_sla_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_sla_get_cmd = subparsers.add_parser("soar-sla-definition-get", help="Deep inspection of a single SLA definition")
    soar_sla_get_cmd.add_argument("sla_id", help="Numeric ID or resource name of the SLA definition")

    # SOAR Request Templates commands
    soar_rt_cmd = subparsers.add_parser("soar-request-templates", help="Search and list manual case request form templates")
    soar_rt_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching template name or description")
    soar_rt_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_rt_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_rt_get_cmd = subparsers.add_parser("soar-request-template-get", help="Deep inspection of a single request template and form field definitions")
    soar_rt_get_cmd.add_argument("template_id", help="Numeric ID or resource name of the request template")

    # SOAR Ingestion Connectors commands
    soar_ic_cmd = subparsers.add_parser("soar-ingestion-connectors", help="Search and list configured SOAR ingestion connector instances")
    soar_ic_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching connector name, identifier, or integration")
    soar_ic_cmd.add_argument("--integration", "-i", default="-", help="Filter by integration name (default: '-')")
    soar_ic_cmd.add_argument("--connector-id", "-c", default="-", help="Filter by connector ID (default: '-')")
    soar_ic_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_ic_cmd.add_argument("--enabled", action="store_true", help="Filter only enabled connector instances")
    soar_ic_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_ic_get_cmd = subparsers.add_parser("soar-ingestion-connector-get", help="Deep inspection of a single SOAR ingestion connector instance")
    soar_ic_get_cmd.add_argument("instance_id", help="Numeric ID or resource name of the connector instance")
    soar_ic_get_cmd.add_argument("--integration", "-i", default="-", help="Integration name (default: '-')")
    soar_ic_get_cmd.add_argument("--connector-id", "-c", default="-", help="Connector ID (default: '-')")

    # SOAR Ingestion Webhooks commands
    soar_wh_cmd = subparsers.add_parser("soar-webhooks", help="Search and list configured SOAR event ingestion webhooks")
    soar_wh_cmd.add_argument("query", nargs="?", default="", help="Optional keyword filter matching webhook display name or description")
    soar_wh_cmd.add_argument("--env", "-e", default="", help="Filter by environment name")
    soar_wh_cmd.add_argument("--enabled", action="store_true", help="Filter only enabled webhooks")
    soar_wh_cmd.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    soar_wh_get_cmd = subparsers.add_parser("soar-webhook-get", help="Deep inspection of a single SOAR event ingestion webhook and JSON schema mapping")
    soar_wh_get_cmd.add_argument("webhook_id", help="UUID identifier or resource name of the webhook")

    # Case Data Configuration command
    case_config_cmd = subparsers.add_parser("case-config", help="Explore case configuration data: views, custom fields, calculated fields, alert grouping, tags, stages, close reasons, dynamic parameters, title rules")
    case_config_sub = case_config_cmd.add_subparsers(dest="config_action", required=True)

    cc_tags = case_config_sub.add_parser("tags", help="List and search case tag classification rules")
    cc_tags.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    cc_tags.add_argument("--criteria", "-c", default="ALL", help="Filter by match criteria (DATA_DRIVEN, BY_VENDOR, BY_PRODUCT, etc.)")
    cc_tags.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    cc_stages = case_config_sub.add_parser("stages", help="List ordered SOC case lifecycle pipeline stages")
    cc_stages.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    cc_close = case_config_sub.add_parser("close-reasons", help="List predefined case close reasons and root causes")
    cc_close.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    cc_params = case_config_sub.add_parser("close-params", help="List dynamic form parameters and custom field schemas for case closure")
    cc_params.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    cc_title = case_config_sub.add_parser("title-rules", help="Get case title formatting priority rules")

    cc_views = case_config_sub.add_parser("views", help="Search and list Case, Alert, and Detection layout views")
    cc_views.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    cc_views.add_argument("--type", "-t", default="", help="Filter by view type (e.g., CASE_OVERVIEW_V2, ALERT_OVERVIEW_V2, DETECTION_OVERVIEW)")
    cc_views.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    cc_view_get = case_config_sub.add_parser("view-get", help="Deep inspection of a specific layout view template")
    cc_view_get.add_argument("view_id", help="Numeric ID or UUID identifier of the view template")

    cc_cfields = case_config_sub.add_parser("custom-fields", help="Search and list custom typed fields across Case and Alert scopes")
    cc_cfields.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    cc_cfields.add_argument("--type", "-t", default="", help="Filter by field type (e.g., LIST, MULTIPLE_CHOICE_LIST, DATE_TIME, FREE_TEXT)")
    cc_cfields.add_argument("--scope", "-s", default="", help="Filter by scope (e.g., Case, Alert)")
    cc_cfields.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    cc_cfield_get = case_config_sub.add_parser("custom-field-get", help="Deep inspection of a single custom field definition")
    cc_cfield_get.add_argument("field_id", help="Numeric ID or resource name of the custom field")

    cc_calc = case_config_sub.add_parser("calculated-fields", help="Search and list calculated field formula definitions")
    cc_calc.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    cc_calc.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    cc_calc_get = case_config_sub.add_parser("calculated-field-get", help="Deep inspection of a single calculated field definition")
    cc_calc_get.add_argument("definition_id", help="Numeric ID or resource name of the calculated field definition")

    cc_ag_rules = case_config_sub.add_parser("alert-grouping-rules", help="Search and list alert grouping rules determining case clustering")
    cc_ag_rules.add_argument("query", nargs="?", default="", help="Optional keyword filter")
    cc_ag_rules.add_argument("--category", "-c", default="", help="Filter by category (e.g., ALL, ALERT_TYPE, PRODUCT_NAME)")
    cc_ag_rules.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")

    cc_ag_rule_get = case_config_sub.add_parser("alert-grouping-rule-get", help="Deep inspection of a single alert grouping rule")
    cc_ag_rule_get.add_argument("rule_id", help="Numeric ID or resource name of the alert grouping rule")

    cc_ag_settings = case_config_sub.add_parser("alert-grouping-settings", help="Get global SOAR alert grouping configuration parameters")

    # Runbook command group
    runbook_parser = subparsers.add_parser("runbook", help="List and execute autonomous SecOps incident response and threat hunting runbooks")
    runbook_sub = runbook_parser.add_subparsers(dest="runbook_action", required=True)

    runbook_list = runbook_sub.add_parser("list", help="List available autonomous SecOps runbooks")

    runbook_run = runbook_sub.add_parser("run", help="Execute an autonomous SecOps runbook")
    runbook_run.add_argument(
        "name",
        choices=[
            "case-ai-triage",
            "autonomous_case_ai_triage",
            "tenant-settings-audit",
            "tenant_settings_audit",
            "data-table-inventory",
            "data_table_inventory",
            "yara-l-rules-audit",
            "yara_l_rules_audit",
            "soar-playbook-inventory",
            "playbook-inventory",
            "soar_playbook_inventory",
            "soar-playbook-health",
            "soar_playbook_health",
            "playbook-health",
            "curated-detections-health",
            "curated_detections_health",
        ],
        help="Name of the runbook to execute",
    )
    runbook_run.add_argument("--case-id", "-c", default="104655", help="Target SecOps case ID (default: 104655)")
    runbook_run.add_argument("--lookback-days", type=int, default=14, help="Threat hunt telemetry lookback days (default: 14)")
    runbook_run.add_argument("--limit", type=int, default=50, help="Per-query threat hunt event cap (default: 50)")
    runbook_run.add_argument("--timeout", type=float, default=90.0, help="Summary polling timeout in seconds (default: 90)")
    runbook_run.add_argument("--out", "-o", help="Filepath to save report output (for tenant-settings-audit)")
    runbook_run.add_argument("--dry-run", action="store_true", help="Execute in read-only preview mode")

    # Entity command group
    entity_grp = subparsers.add_parser("entity", help="Search UDM Entity Graph, summarize entities, and run composite investigations")
    entity_sub = entity_grp.add_subparsers(dest="entity_action", required=True)

    ent_search = entity_sub.add_parser("search", help="Search UDM entity graph (graph.entity.*)")
    ent_search.add_argument("indicator", help="Entity indicator or value (e.g. hash, IP, user)")
    ent_search.add_argument("--field", "-f", help="Explicit entity graph field (e.g. file.sha256, ip, hostname)")
    ent_search.add_argument("--start", help="Start timestamp ISO8601")
    ent_search.add_argument("--end", help="End timestamp ISO8601")
    ent_search.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")

    ent_summary = entity_sub.add_parser("summarize", help="Get entity summary, timeline intervals, and prevalence")
    ent_summary.add_argument("entity_id", help="Entity identifier or URI")
    ent_summary.add_argument("--start", help="Start timestamp ISO8601")
    ent_summary.add_argument("--end", help="End timestamp ISO8601")

    ent_inv = entity_sub.add_parser("investigate", help="Run multi-engine cross-correlation for an indicator")
    ent_inv.add_argument("indicator", help="Indicator (IP, hash, email, hostname, domain, user)")
    ent_inv.add_argument("--start", help="Start timestamp ISO8601")
    ent_inv.add_argument("--end", help="End timestamp ISO8601")
    ent_inv.add_argument("--limit", type=int, default=50, help="Max events per search")

    # IoC command group
    ioc_grp = subparsers.add_parser("ioc", help="Search enterprise-wide IoC matches and Mandiant threat intel")
    ioc_sub = ioc_grp.add_subparsers(dest="ioc_action", required=True)

    ioc_search = ioc_sub.add_parser("search", help="Search enterprise-wide IoCs")
    ioc_search.add_argument("value", help="IoC value (hash, IP, domain, etc.)")
    ioc_search.add_argument("--type", "-t", help="Explicit IoC valueType (e.g. HASH_SHA256, HASH_MD5, IP_ADDRESS, DOMAIN_NAME)")
    # Chronicle SIEM Data Tables command
    dt_parser = subparsers.add_parser("data-table", help="Manage Chronicle SIEM Data Tables and row entries")
    dt_sub = dt_parser.add_subparsers(dest="dt_action", required=True)

    dt_list = dt_sub.add_parser("list", help="List Chronicle SIEM Data Tables")
    dt_list.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")
    dt_list.add_argument("--json", action="store_true", help="Output raw JSON")

    dt_get = dt_sub.add_parser("get", help="Get Data Table schema and metadata")
    dt_get.add_argument("table", help="Name or ID of the Data Table")
    dt_get.add_argument("--json", action="store_true", help="Output raw JSON")

    dt_create = dt_sub.add_parser("create", help="Create a new Data Table")
    dt_create.add_argument("table_id", help="Unique ID for the new Data Table")
    dt_create.add_argument("--display-name", help="Display name for the Data Table")
    dt_create.add_argument("--description", help="Description of the Data Table")
    dt_create.add_argument("--columns", required=True, help="Comma-separated column defs: name:TYPE[:key] e.g. 'user:STRING:key,ip:CIDR'")
    dt_create.add_argument("--ttl", help="Optional row time to live e.g. '168h'")
    dt_create.add_argument("--json", action="store_true", help="Output raw JSON")

    dt_delete = dt_sub.add_parser("delete", help="Delete a Data Table")
    dt_delete.add_argument("table", help="Name or ID of the Data Table to delete")

    dt_rows = dt_sub.add_parser("rows", help="List rows inside a Data Table")
    dt_rows.add_argument("table", help="Name or ID of the Data Table")
    dt_rows.add_argument("--filter", "-f", help="Filter expression for rows")
    dt_rows.add_argument("--limit", type=int, default=50, help="Results limit (default: 50)")
    dt_rows.add_argument("--json", action="store_true", help="Output raw JSON")

    dt_add_row = dt_sub.add_parser("add-row", help="Add a row of values to a Data Table")
    dt_add_row.add_argument("table", help="Name or ID of the Data Table")
    dt_add_row.add_argument("--values", "-v", required=True, help="Comma-separated row values e.g. 'user@corp.com,192.168.1.1'")
    dt_add_row.add_argument("--json", action="store_true", help="Output raw JSON")

    dt_del_row = dt_sub.add_parser("delete-row", help="Delete a row from a Data Table")
    dt_del_row.add_argument("table", help="Name or ID of the Data Table")
    dt_del_row.add_argument("row_id", help="Row ID or resource path to delete")

    # Chronicle SIEM Detection Rules command
    rule_parser = subparsers.add_parser("rule", help="Manage custom Chronicle SIEM YARA-L detection rules")
    rule_sub = rule_parser.add_subparsers(dest="rule_action", required=True)

    rule_list = rule_sub.add_parser("list", help="List custom detection rules")
    rule_list.add_argument("--filter", "-f", help="Filter expression (e.g. 'display_name:\"my_rule\"')")
    rule_list.add_argument("--view", choices=["BASIC", "FULL"], default="BASIC", help="Rule view (default: BASIC)")
    rule_list.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")
    rule_list.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_get = rule_sub.add_parser("get", help="Get detection rule details and YARA-L logic")
    rule_get.add_argument("rule", help="Rule ID (ru_...) or resource name")
    rule_get.add_argument("--view", choices=["BASIC", "FULL"], default="FULL", help="Rule view (default: FULL)")
    rule_get.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_verify = rule_sub.add_parser("verify", help="Validate YARA-L 2.0 rule syntax against the Chronicle compiler")
    rule_verify.add_argument("rule_input", help="File path (.yaral / .yara) or raw YARA-L rule text string")
    rule_verify.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_create = rule_sub.add_parser("create", help="Create a new custom detection rule")
    rule_create.add_argument("rule_input", help="File path (.yaral / .yara) or raw YARA-L rule text string")
    rule_create.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_patch = rule_sub.add_parser("patch", help="Update the YARA-L logic of an existing detection rule")
    rule_patch.add_argument("rule", help="Rule ID (ru_...) or resource name")
    rule_patch.add_argument("rule_input", help="File path (.yaral / .yara) or raw YARA-L rule text string")
    rule_patch.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_delete = rule_sub.add_parser("delete", help="Delete a custom detection rule")
    rule_delete.add_argument("rule", help="Rule ID (ru_...) or resource name to delete")

    rule_revisions = rule_sub.add_parser("revisions", help="List version history and past revisions of a rule")
    rule_revisions.add_argument("rule", help="Rule ID (ru_...) or resource name")
    rule_revisions.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")
    rule_revisions.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_dep = rule_sub.add_parser("deployment", help="Get rule deployment, schedule, and alerting status")
    rule_dep.add_argument("rule", help="Rule ID (ru_...) or resource name")
    rule_dep.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_set_dep = rule_sub.add_parser("set-deployment", help="Update rule deployment configuration")
    rule_set_dep.add_argument("rule", help="Rule ID (ru_...) or resource name")
    rule_set_dep.add_argument("--enabled", action="store_true", help="Enable rule execution")
    rule_set_dep.add_argument("--disabled", action="store_true", help="Disable rule execution")
    rule_set_dep.add_argument("--alerting", action="store_true", help="Enable alerting for rule detections")
    rule_set_dep.add_argument("--no-alerting", action="store_true", help="Disable alerting for rule detections")
    rule_set_dep.add_argument("--frequency", choices=["LIVE", "HOURLY", "DAILY"], help="Execution run frequency")
    rule_set_dep.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_errors = rule_sub.add_parser("errors", help="List runtime / execution errors across detection rules")
    rule_errors.add_argument("--rule", "-r", help="Optional Rule ID to filter errors by")
    rule_errors.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")
    rule_errors.add_argument("--json", action="store_true", help="Output raw JSON")

    rule_audit = rule_sub.add_parser("audit", help="Audit all rules, deployment status, and cross-correlate errors")
    rule_audit.add_argument("--filter", "-f", help="Optional filter expression for listing rules")
    rule_audit.add_argument("--limit", type=int, default=100, help="Results limit (default: 100)")
    rule_audit.add_argument("--out", "-o", help="Optional path to output JSON report file")
    rule_audit.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()

    if args.command == "search":
        run_search_cli(args)
    elif args.command in ("search-stats", "stats-search"):
        run_search_stats_cli(args)
    elif args.command == "investigate":
        run_investigate_cli(args)
    elif args.command == "entity-search":
        run_entity_search_cli(args)
    elif args.command == "entity":
        run_entity_cli(args)
    elif args.command == "ioc":
        run_ioc_cli(args)
    elif args.command == "refine":
        run_refine_cli(args)
    elif args.command == "case":
        run_case_cli(args)
    elif args.command == "alert":
        run_alert_cli(args)
    elif args.command == "playbook":
        run_playbook_cli(args)
    elif args.command == "integration":
        run_integration_cli(args)
    elif args.command == "job":
        run_job_cli(args)
    elif args.command == "pack":
        run_content_pack_cli(args)
    elif args.command == "curated":
        run_curated_cli(args)
    elif args.command == "marketplace":
        run_marketplace_cli(args)
    elif args.command == "dashboard":
        run_dashboard_cli(args)
    elif args.command == "domain":
        run_domain_cli(args)
    elif args.command == "feed":
        run_feed_cli(args)
    elif args.command == "pipeline":
        run_pipeline_cli(args)
    elif args.command == "feed-schema":
        run_feed_schema_cli(args)
    elif args.command == "parser":
        run_parser_cli(args)
    elif args.command == "preview":
        run_preview_cli(args)
    elif args.command == "rbac":
        run_rbac_cli(args)
    elif args.command == "enrichment":
        run_enrichment_cli(args)
    elif args.command == "siem":
        run_siem_cli(args)
    elif args.command == "soar-users":
        run_soar_users_cli(args)
    elif args.command == "soar-user-get":
        run_soar_user_get_cli(args)
    elif args.command == "soar-roles":
        run_soar_roles_cli(args)
    elif args.command == "soar-company-settings":
        run_soar_company_cli(args)
    elif args.command == "soar-data-retention":
        run_soar_retention_cli(args)
    elif args.command == "soar-environments":
        run_soar_environments_cli(args)
    elif args.command == "soar-environment-get":
        run_soar_environment_get_cli(args)
    elif args.command == "soar-environment-groups":
        run_soar_environment_groups_cli(args)
    elif args.command == "soar-remote-agents":
        run_soar_remote_agents_cli(args)
    elif args.command == "soar-remote-agent-get":
        run_soar_remote_agent_get_cli(args)
    elif args.command == "soar-email-settings":
        run_soar_email_settings_cli(args)
    elif args.command == "soar-support-settings":
        run_soar_support_settings_cli(args)
    elif args.command == "soar-networks":
        run_soar_networks_cli(args)
    elif args.command == "soar-network-get":
        run_soar_network_get_cli(args)
    elif args.command == "soar-domains":
        run_soar_domains_cli(args)
    elif args.command == "soar-domain-get":
        run_soar_domain_get_cli(args)
    elif args.command == "soar-custom-lists":
        run_soar_custom_lists_cli(args)
    elif args.command == "soar-custom-list-get":
        run_soar_custom_list_get_cli(args)
    elif args.command == "soar-email-templates":
        run_soar_email_templates_cli(args)
    elif args.command == "soar-email-template-get":
        run_soar_email_template_get_cli(args)
    elif args.command == "soar-entities-blocklists":
        run_soar_entities_blocklists_cli(args)
    elif args.command == "soar-entities-blocklist-get":
        run_soar_entities_blocklist_get_cli(args)
    elif args.command == "soar-sla-definitions":
        run_soar_sla_definitions_cli(args)
    elif args.command == "soar-sla-definition-get":
        run_soar_sla_definition_get_cli(args)
    elif args.command == "soar-request-templates":
        run_soar_request_templates_cli(args)
    elif args.command == "soar-request-template-get":
        run_soar_request_template_get_cli(args)
    elif args.command == "soar-ingestion-connectors":
        run_soar_ingestion_connectors_cli(args)
    elif args.command == "soar-ingestion-connector-get":
        run_soar_ingestion_connector_get_cli(args)
    elif args.command == "soar-webhooks":
        run_soar_webhooks_cli(args)
    elif args.command == "soar-webhook-get":
        run_soar_webhook_get_cli(args)
    elif args.command == "case-config":
        run_case_config_cli(args)
    elif args.command == "data-table":
        run_data_table_cli(args)
    elif args.command == "rule":
        run_rule_cli(args)
    elif args.command == "runbook":
        run_runbook_cli(args)


def run_runbook_cli(args):
    if args.runbook_action == "list":
        print("\n=== Available Autonomous SecOps Runbooks ===")
        print("  1. case-ai-triage (autonomous_case_ai_triage)")
        print("     Category : Incident Response")
        print("     Summary  : 4-stage loop: Gemini AI Summary -> Indicator Extraction -> UDM Threat Hunt -> Incident Escalation & Audit Comment")
        print("     Usage    : secops runbook run case-ai-triage --case-id <ID> [--dry-run]")
        print()
        print("  2. tenant-settings-audit (tenant_settings_audit)")
        print("     Category : Operations & Governance")
        print("     Summary  : Complete audit of Root Instance, Gemini AI/UEBA, Pipelines, SOAR Settings, and Topography")
        print("     Usage    : secops runbook run tenant-settings-audit [--out <FILE>]")
        print()
        print("  3. data-table-inventory (data_table_inventory)")
        print("     Category : Operations & Governance")
        print("     Summary  : Comprehensive audit of Chronicle SIEM Data Tables: schemas, columns, types, owners, TTL, and timestamps")
        print("     Usage    : secops runbook run data-table-inventory [--out <FILE>]")
        print()
        print("  4. yara-l-rules-audit (yara_l_rules_audit)")
        print("     Category : Operations & Detection Engineering")
        print("     Summary  : Audit all custom YARA-L detection rules: deployment status, authoring, compilation, and error cross-correlation")
        print("     Usage    : secops runbook run yara-l-rules-audit [--out <FILE>]")
        print()
        print("  5. soar-playbook-inventory (soar_playbook_inventory / playbook-inventory)")
        print("     Category : Operations & SOAR Automation")
        print("     Summary  : Comprehensive audit of SOAR Playbooks & Blocks: types (REGULAR/NESTED), enabled status, priority, and environment mappings")
        print("     Usage    : secops runbook run soar-playbook-inventory [--out <FILE>]")
        print()
        print("  6. curated-detections-health (curated_detections_health)")
        print("     Category : Operations & Detection Engineering")
        print("     Summary  : Health check & hygiene audit across Curated Rule Sets: misconfiguration risks (BROAD alerting), top firing rules, newest/oldest intelligence")
        print("     Usage    : secops runbook run curated-detections-health [--days <N>] [--out <FILE>]")
        print()
        print("  7. soar-playbook-health (soar_playbook_health / playbook-health)")
        print("     Category : Operations & SOAR Automation")
        print("     Summary  : Comprehensive SOAR Playbook Health Check: failure rates, faulted connector actions, queue latency, and Playbook Dashboard (SOAR) telemetry")
        print("     Usage    : secops runbook run soar-playbook-health [--lookback-days <N>] [--out <FILE>]")
        print()
    elif args.runbook_action == "run":
        if args.name in ("case-ai-triage", "autonomous_case_ai_triage"):
            from runbooks.incident_response.autonomous_case_ai_triage import run_autonomous_case_ai_triage
            run_autonomous_case_ai_triage(
                case_id=args.case_id,
                hunt_lookback_days=args.lookback_days,
                hunt_receive_limit=args.limit,
                summary_timeout_sec=args.timeout,
                dry_run=args.dry_run,
            )
        elif args.name in ("tenant-settings-audit", "tenant_settings_audit"):
            import json
            from runbooks.operations.tenant_settings_audit import generate_tenant_settings_report
            report = generate_tenant_settings_report()
            rendered = json.dumps(report, indent=2)
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as f:
                    f.write(rendered)
                print(f"[+] Audit report written to {args.out}")
            else:
                print(rendered)
        elif args.name in ("data-table-inventory", "data_table_inventory"):
            import json
            from runbooks.operations.data_table_inventory import (
                generate_data_table_inventory_report,
                print_data_table_inventory_console,
            )
            report = generate_data_table_inventory_report()
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2)
                print(f"[+] Data table inventory written to {args.out}")
            else:
                print_data_table_inventory_console(report)
        elif args.name in ("yara-l-rules-audit", "yara_l_rules_audit"):
            import json
            from runbooks.operations.yara_l_rules_audit import (
                generate_yara_l_rules_audit_report,
                print_yara_l_rules_audit_console,
            )
            report = generate_yara_l_rules_audit_report()
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2)
                print(f"[+] YARA-L rules audit written to {args.out}")
            else:
                print_yara_l_rules_audit_console(report)
        elif args.name in ("soar-playbook-inventory", "playbook-inventory", "soar_playbook_inventory"):
            import json
            from runbooks.operations.soar_playbook_inventory import (
                generate_playbook_inventory_report,
                print_playbook_inventory_console,
            )
            report = generate_playbook_inventory_report()
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2)
                print(f"[+] SOAR Playbook inventory written to {args.out}")
            else:
                print_playbook_inventory_console(report)
        elif args.name in ("curated-detections-health", "curated_detections_health"):
            import json
            from runbooks.operations.curated_detections_health import (
                generate_curated_detections_health_report,
                print_curated_detections_health_console,
            )
            days = getattr(args, "lookback_days", 7) or 7
            report = generate_curated_detections_health_report(days=days)
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2)
                print(f"[+] Curated Detections health audit written to {args.out}")
            else:
                print_curated_detections_health_console(report)
        elif args.name in ("soar-playbook-health", "soar_playbook_health", "playbook-health"):
            import json
            from runbooks.operations.soar_playbook_health import (
                generate_soar_playbook_health_report,
                print_soar_playbook_health_console,
            )
            days = getattr(args, "lookback_days", 7) or 7
            report = generate_soar_playbook_health_report(days=days)
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2)
                print(f"[+] SOAR Playbook health audit written to {args.out}")
            else:
                print_soar_playbook_health_console(report)


def run_entity_search_cli(args):
    now = datetime.now(timezone.utc)
    end_time = args.end or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_time = args.start or (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    from engine import EntityType
    entity_type = EntityType(args.type)
    engine = SecOpsEngine()

    print(f"\n[CLI] Starting Canonical Entity Search for {entity_type.value}: '{args.value}'...")

    def on_batch(batch, session):
        print(f" [➜] Batch received: {batch.batch_count} events (Total: {session.received_count})")

    session = engine.search_from_entity(
        entity_type=entity_type,
        entity_value=args.value,
        start_time=start_time,
        end_time=end_time,
        receive_limit=args.limit,
        on_batch=on_batch,
    )

    print("\n--- Entity Search Summary ---")
    print(f"Session ID    : {session.session_id}")
    print(f"Query Run     : {session.request.query}")
    print(f"Total Matches : {session.received_count}")
    print(f"Lifecycle     : {session.lifecycle.value}")


def run_entity_cli(args):
    now = datetime.now(timezone.utc)
    end_time = args.end or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_time = args.start or (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    engine = SecOpsEngine()

    if args.entity_action == "search":
        print(f"\n[CLI] Searching UDM Entity Graph for '{args.indicator}'...")
        def on_batch(batch, session):
            print(f" [➜] Batch: {batch.batch_count} entity records (Total: {session.received_count})")

        session = engine.search_entity_graph(
            indicator_or_field=args.field or args.indicator,
            value=args.indicator if args.field else None,
            start_time=start_time,
            end_time=end_time,
            receive_limit=args.limit,
            on_batch=on_batch,
        )
        print("\n--- Entity Graph Search Summary ---")
        print(f"Session ID    : {session.session_id}")
        print(f"Query Run     : {session.request.query}")
        print(f"Total Matches : {session.received_count}")
        print(f"Lifecycle     : {session.lifecycle.value}")

    elif args.entity_action == "summarize":
        print(f"\n[CLI] Retrieving Entity Profile Summary for: {args.entity_id}")
        summary = engine.summarize_entity(
            entity_id=args.entity_id,
            start_time=args.start,
            end_time=args.end,
        )
        print("\n--- Entity Profile Summary ---")
        print(f"Entity ID     : {summary.entity_id}")
        print(f"Entity Type   : {summary.entity_type}")
        print(f"Timeline Span : {len(summary.timeline)} intervals")
        if summary.prevalence:
            print(f"Prevalence    : {summary.prevalence}")
        if summary.file_metadata:
            print(f"File Metadata : {summary.file_metadata}")

    elif args.entity_action == "investigate":
        print(f"\n[CLI] Initiating Multi-Engine Investigation for indicator: '{args.indicator}'...")
        report = engine.investigate_entity(
            indicator=args.indicator,
            start_time=start_time,
            end_time=end_time,
            max_events=args.limit,
        )
        print("\n--- Unified Entity Investigation Report ---")
        print(f"Indicator     : {report.indicator}")
        print(f"Detected Type : {report.detected_type} (Category: {report.category})")
        print(f"Entity Graph  : {report.entity_graph_events_count} matches")
        print(f"UDM Events    : {report.udm_events_count} events")
        print(f"IoC Matches   : {report.enterprise_iocs_count} threat intel hits")
        print(f"SOAR Cases    : {report.related_cases_count} correlated cases")
        if report.ioc_matches:
            print("\nThreat Intel Sources:")
            for m in report.ioc_matches[:5]:
                print(f"  - Sources: {', '.join(m.sources)} | Categories: {', '.join(m.categories)}")


def run_ioc_cli(args):
    now = datetime.now(timezone.utc)
    end_time = args.end or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_time = args.start or (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    engine = SecOpsEngine()

    if args.ioc_action == "search":
        print(f"\n[CLI] Searching Enterprise IoCs for: '{args.value}'...")
        batch = engine.search_enterprise_iocs(
            value=args.value,
            value_type=args.type,
            start_time=start_time,
            end_time=end_time,
            max_matches=args.limit,
        )
        print("\n--- Enterprise IoC Results ---")
        print(f"Searched Value : {batch.searched_value}")
        print(f"Value Type     : {batch.value_type}")
        print(f"Total Matches  : {batch.total_count}")
        for idx, m in enumerate(batch.matches[:10], 1):
            print(f"\nMatch #{idx}:")
            print(f"  Sources      : {', '.join(m.sources)}")
            print(f"  Categories   : {', '.join(m.categories)}")
            if m.artifact_indicator:
                print(f"  Artifact     : {m.artifact_indicator}")
            if m.asset_indicators:
                print(f"  Asset Count  : {len(m.asset_indicators)}")


def run_refine_cli(args):
    now = datetime.now(timezone.utc)
    end_time = args.end or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_time = args.start or (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    from engine import FieldFilter, FilterOperator
    filters = []
    for inc in args.include:
        if "=" in inc:
            k, v = inc.split("=", 1)
            filters.append(FieldFilter(field_path=k.strip(), operator=FilterOperator.EQUALS, value=v.strip()))
    for exc in args.exclude:
        if "=" in exc:
            k, v = exc.split("=", 1)
            filters.append(FieldFilter(field_path=k.strip(), operator=FilterOperator.NOT_EQUALS, value=v.strip()))

    engine = SecOpsEngine()
    print(f"\n[CLI] Executing Refined Search based on: '{args.base_query}' with {len(filters)} filter(s)...")

    def on_batch(batch, session):
        print(f" [➜] Batch received: {batch.batch_count} events (Total: {session.received_count})")

    session = engine.refine_search(
        base=args.base_query,
        filters=filters,
        start_time=start_time,
        end_time=end_time,
        receive_limit=args.limit,
        on_batch=on_batch,
    )

    print("\n--- Refined Search Summary ---")
    print(f"Session ID    : {session.session_id}")
    print(f"Query Run     : {session.request.query}")
    print(f"Total Matches : {session.received_count}")
    print(f"Lifecycle     : {session.lifecycle.value}")



def run_case_cli(args):
    engine = SecOpsEngine()
    if args.case_action == "show":
        print(f"\n[CLI] Loading Case Workspace: {args.case_id}...")
        inv = engine.investigate_case(args.case_id)
        print(f"\n=======================================================")
        print(f" CASE {inv.case_id}: {inv.display_name}")
        print(f" Status: {inv.status.value} | Priority: {inv.priority.value} | Stage: {inv.stage}")
        print(f" Assignee: {inv.assignee or 'Unassigned'} | Created: {inv.create_time}")
        print(f"=======================================================")

        print(f"\n--- ALERTS ({len(inv.alerts)}) ---")
        for idx, a in enumerate(inv.alerts, 1):
            print(f" [{idx}] {a.display_name}")
            print(f"     ID: {a.identifier} | Priority: {a.priority} | Status: {a.status} | Events: {a.event_count}")
            print(f"     Name: {a.name}")

        print(f"\n--- INVOLVED ENTITIES ({len(inv.entities)}) ---")
        for idx, e in enumerate(inv.entities, 1):
            susp_flag = " [SUSPICIOUS]" if e.is_suspicious else ""
            print(f" [{idx}] ({e.entity_type or 'ENTITY'}) {e.identifier}{susp_flag}")
            if e.role:
                print(f"     Role: {e.role}")

        print(f"\n--- COMMENTS ({len(inv.comments)}) ---")
        for idx, c in enumerate(inv.comments, 1):
            print(f" [{idx}] {c.author_name or c.author or 'Unknown'} @ {c.create_time}:")
            print(f"     \"{c.comment}\"")

    elif args.case_action == "comment":
        print(f"\n[CLI] Adding comment to Case {args.case_id}...")
        res = engine.add_case_comment(args.case_id, args.text)
        print(f" [✓] Comment posted successfully.")
        print(f"     Resource: {res.name}")
        print(f"     Author  : {res.author_name or res.author}")
        print(f"     Time    : {res.create_time}")
        print(f"     Text    : \"{res.comment}\"")

    elif args.case_action == "search":
        print(f"\n[CLI] Searching Cases (query='{args.query}', limit={args.limit}, page={args.page})...")
        batch = engine.search_cases(
            query=args.query,
            priorities=args.priority,
            stages=args.stage,
            tags=args.tag,
            environments=args.environment,
            assigned_users=args.assignee,
            is_important=True if args.important else None,
            page_size=args.limit,
            page_number=args.page,
        )
        print(f"\n==========================================================================================")
        print(f" SOAR CASE SEARCH RESULTS (Total: {batch.total_count:,} | Returned: {len(batch.results)} | Page: {batch.page_number})")
        print(f"==========================================================================================")
        if not batch.results:
            print(" No cases found matching criteria.")
            return

        for idx, c in enumerate(batch.results, 1):
            prio_badge = f"[{c.priority.value}]"
            imp_badge = "★ " if c.is_important else ""
            time_str = c.create_time.strftime("%Y-%m-%d %H:%M:%S") if c.create_time else "N/A"
            print(f" {idx:2d}. {imp_badge}ID: {c.case_id:<8s} | {prio_badge:10s} | Stage: {c.stage:<14s} | Alerts: {c.alerts_count:2d} | Created: {time_str}")
            print(f"     Title   : {c.title}")
            if c.tags:
                print(f"     Tags    : {', '.join(c.tags)}")
            if c.user_assigned:
                print(f"     Assignee: {c.user_assigned}")
            print()

    elif args.case_action == "triage":
        print(f"\n[CLI] Triaging Case #{args.case_id} (summary={args.summary}, precedents={args.precedents})...")
        assessment = engine.triage_case(
            case_id=args.case_id,
            fetch_summary=args.summary,
            search_precedents=args.precedents,
            apply_stage_update=args.update_stage,
            post_comment=args.comment,
        )

        if getattr(args, "format", "table") == "json":
            import json
            out = {
                "case_id": assessment.case_id,
                "title": assessment.title,
                "priority": assessment.priority.value if hasattr(assessment.priority, "value") else str(assessment.priority),
                "status": assessment.status.value if hasattr(assessment.status, "value") else str(assessment.status),
                "stage": assessment.stage,
                "is_closed": assessment.is_closed,
                "is_novel": assessment.is_novel,
                "is_repeat": assessment.is_repeat,
                "prior_case_count": assessment.prior_case_count,
                "suggested_stage_transition": assessment.suggested_stage_transition,
                "alert_count": assessment.alert_count,
                "highest_alert_priority": assessment.highest_alert_priority,
                "suspicious_entities": assessment.suspicious_entities,
                "comment_count": assessment.comment_count,
                "latest_comment": assessment.latest_comment,
                "triage_verdict": assessment.triage_verdict.value,
                "triage_summary": assessment.triage_summary,
                "recommended_actions": assessment.recommended_actions,
                "suggested_agent_prompt": assessment.suggested_agent_prompt,
                "gemini_summary": assessment.gemini_summary.summary if assessment.gemini_summary else None,
                "precedent_notes": assessment.precedent_summary.precedent_notes if assessment.precedent_summary else [],
                "playbooks": [
                    {
                        "alert_id": pb.alert_id,
                        "alert_display_name": pb.alert_display_name,
                        "attached_playbook_name": pb.attached_playbook_name,
                        "status": pb.status,
                        "run_count": pb.run_count,
                    }
                    for pb in assessment.alert_playbook_statuses
                ],
                "timeline_events": [
                    {
                        "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                        "event_type": ev.event_type,
                        "title": ev.title,
                        "description": ev.description,
                        "severity": ev.severity,
                    }
                    for ev in (assessment.timeline.events if assessment.timeline else [])
                ],
            }
            print(json.dumps(out, indent=2))
            return

        print(f"\n==========================================================================================")
        print(f" SOAR SINGLE CASE TRIAGE ASSESSMENT: Case #{assessment.case_id}")
        print(f"==========================================================================================")
        verdict_badge = f"[{assessment.triage_verdict.value}]"
        prio_badge = f"[{assessment.priority.value if hasattr(assessment.priority, 'value') else assessment.priority}]"
        status_badge = "[CLOSED]" if assessment.is_closed else "[OPEN]"
        print(f" Case ID     : #{assessment.case_id} | {status_badge} | Priority: {prio_badge} | Stage: {assessment.stage}")
        print(f" Title       : {assessment.title}")
        print(f" Verdict     : {verdict_badge} {assessment.triage_summary}")
        if assessment.suggested_stage_transition and assessment.suggested_stage_transition != assessment.stage:
            print(f" Stage Suggestion: Transition to '{assessment.suggested_stage_transition}'")

        if assessment.gemini_summary and assessment.gemini_summary.summary:
            print(f"\n Gemini AI Case Summary:")
            print(f"   {assessment.gemini_summary.summary}")

        if assessment.precedent_summary:
            print(f"\n Precedent & Pattern Analysis:")
            if assessment.precedent_summary.is_novel:
                print(f"   - Novel Detection: 0 prior occurrences with this title or entities.")
            else:
                for pnote in assessment.precedent_summary.precedent_notes:
                    print(f"   - {pnote}")

        if assessment.alert_playbook_statuses:
            print(f"\n Key Alerts & SOAR Playbook Status ({len(assessment.alert_playbook_statuses)}):")
            for idx, pb in enumerate(assessment.alert_playbook_statuses, 1):
                aname = pb.alert_display_name or pb.alert_id or "Alert"
                if pb.attached_playbook_name:
                    status_str = f"[{pb.status or 'PENDING'}]"
                    runs_str = f"({pb.run_count} runs)"
                    print(f"   {idx}. {aname} -> Playbook: '{pb.attached_playbook_name}' {status_str} {runs_str}")
                else:
                    print(f"   {idx}. {aname} -> Playbook: [NO PLAYBOOK ATTACHED]")

        if assessment.timeline and assessment.timeline.events:
            print(f"\n Incident & Case Timeline ({len(assessment.timeline.events)} events):")
            for idx, ev in enumerate(assessment.timeline.events, 1):
                t_str = ev.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if ev.timestamp else "N/A"
                print(f"   [{t_str}] [{ev.event_type:<12s}] {ev.title} - {ev.description}")

        if assessment.suspicious_entities:
            print(f"\n Flagged Entities: {', '.join(assessment.suspicious_entities)}")

        if assessment.recommended_actions:
            print(f"\n Recommended Analyst Actions:")
            for act in assessment.recommended_actions:
                print(f"   - {act}")

        if assessment.latest_comment:
            clean_note = assessment.latest_comment.splitlines()[0] if assessment.latest_comment else ""
            print(f"\n Latest Note : {clean_note}")

        if getattr(args, "generate_prompts", False):
            print(f"\n --- Suggested Antigravity Subagent Dispatch Prompt ---")
            for pline in assessment.suggested_agent_prompt.splitlines():
                print(f" | {pline}")
            print(f" ------------------------------------------------------")
        print()

    elif args.case_action == "timeline":
        print(f"\n[CLI] Generating Chronological Timeline for Case #{args.case_id}...")
        timeline = engine.get_case_timeline(case_id=args.case_id)

        if getattr(args, "format", "table") == "json":
            import json
            out = {
                "case_id": timeline.case_id,
                "event_count": len(timeline.events),
                "earliest_time": timeline.earliest_time.isoformat() if timeline.earliest_time else None,
                "latest_time": timeline.latest_time.isoformat() if timeline.latest_time else None,
                "events": [
                    {
                        "timestamp": ev.timestamp.isoformat() if ev.timestamp else None,
                        "event_type": ev.event_type,
                        "title": ev.title,
                        "description": ev.description,
                        "source_id": ev.source_id,
                        "severity": ev.severity,
                        "metadata": ev.metadata,
                    }
                    for ev in timeline.events
                ],
                "provenance": timeline.provenance,
            }
            print(json.dumps(out, indent=2))
            return

        print(f"\n==========================================================================================")
        print(f" CHRONOLOGICAL TIMELINE: Case #{timeline.case_id} ({len(timeline.events)} events)")
        print(f"==========================================================================================")
        if not timeline.events:
            print(" No timeline events recorded for this case.")
        else:
            for idx, ev in enumerate(timeline.events, 1):
                t_str = ev.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC") if ev.timestamp else "N/A"
                print(f" {idx:2d}. [{t_str}] [{ev.event_type:<12s}] {ev.title}")
                print(f"     {ev.description}")
                print()

    elif args.case_action == "comments":
        print(f"\n[CLI] Retrieving Case Comments for Case #{args.case_id}...")
        comments = engine.list_case_comments(case_id=args.case_id)

        if getattr(args, "format", "table") == "json":
            import json
            out = [
                {
                    "name": c.name,
                    "author": c.author,
                    "author_name": c.author_name,
                    "created_time": c.create_time.isoformat() if c.create_time else None,
                    "comment": c.comment,
                    "is_deleted": c.is_deleted,
                }
                for c in comments
            ]
            print(json.dumps(out, indent=2))
            return

        print(f"\n==========================================================================================")
        print(f" CASE COMMENTS: Case #{args.case_id} ({len(comments)} comments)")
        print(f"==========================================================================================")
        if not comments:
            print(" No comments recorded on this case.")
        else:
            for idx, c in enumerate(comments, 1):
                t_str = c.create_time.strftime("%Y-%m-%d %H:%M:%S UTC") if c.create_time else "N/A"
                author_str = c.author_name or c.author or "Unknown"
                print(f" {idx:2d}. [{t_str}] Author: {author_str}")
                for line in c.comment.splitlines():
                    print(f"     {line}")
                print()

    elif args.case_action == "wall":
        print(f"\n[CLI] Retrieving SOAR Case Activity Wall for Case #{args.case_id} (limit={args.limit})...")
        wall_res = engine.get_case_wall(
            case_id=args.case_id,
            limit=args.limit,
            page_token=getattr(args, "page_token", None),
            activity_type=getattr(args, "type", None),
        )

        if getattr(args, "format", "table") == "json":
            import json
            out = {
                "case_id": wall_res.case_id,
                "record_count": wall_res.count,
                "total_size": wall_res.total_size,
                "next_page_token": wall_res.next_page_token,
                "records": [
                    {
                        "activity_id": r.activity_id,
                        "activity_type": r.activity_type,
                        "activity_kind": r.activity_kind,
                        "creator": r.creator_user_id,
                        "created_time": r.create_time.isoformat() if r.create_time else None,
                        "description": r.description,
                        "details": r.details,
                    }
                    for r in wall_res.records
                ],
                "provenance": wall_res.provenance,
            }
            print(json.dumps(out, indent=2))
            return

        print(f"\n==========================================================================================")
        print(f" SOAR CASE ACTIVITY WALL: Case #{wall_res.case_id} (Showing {wall_res.count} of {wall_res.total_size} total records)")
        print(f"==========================================================================================")
        if not wall_res.records:
            print(" No activity records found on the case wall.")
        else:
            for idx, r in enumerate(wall_res.records, 1):
                t_str = r.create_time.strftime("%Y-%m-%d %H:%M:%S UTC") if r.create_time else "N/A"
                user_str = f"by {r.creator_user_id}" if r.creator_user_id else ""
                print(f" {idx:2d}. [{t_str}] [{r.activity_type:<18s}] {r.activity_kind} {user_str}")
                print(f"     {r.description}")
                print()
        if wall_res.next_page_token:
            print(f" Next Page Token: {wall_res.next_page_token}")

    elif args.case_action in ("orchestrate-triage", "triage-batch"):
        cids = getattr(args, "case_id", None) or None
        print(f"\n[CLI] Orchestrating Case Triage (limit={args.limit}, open_only={not args.all_statuses}, explicit_cases={cids})...")
        batch = engine.orchestrate_case_triage(
            case_ids=cids,
            limit=args.limit,
            open_only=not args.all_statuses,
            query_text=args.query,
            priorities=args.priority,
            stages=args.stage,
            tags=args.tag,
            environments=args.environment,
            assigned_users=args.assignee,
            search_precedents=getattr(args, "precedents", True),
            fetch_summary=getattr(args, "summary", False),
        )

        if getattr(args, "format", "table") == "json":
            import json
            out = {
                "total_cases_analyzed": batch.total_cases_analyzed,
                "open_cases_count": batch.open_cases_count,
                "closed_cases_count": batch.closed_cases_count,
                "critical_high_count": batch.critical_high_count,
                "provenance": batch.provenance,
                "cases": [
                    {
                        "case_id": c.case_id,
                        "title": c.title,
                        "priority": c.priority.value if hasattr(c.priority, "value") else str(c.priority),
                        "status": c.status.value if hasattr(c.status, "value") else str(c.status),
                        "stage": c.stage,
                        "is_closed": c.is_closed,
                        "is_novel": c.is_novel,
                        "is_repeat": c.is_repeat,
                        "prior_case_count": c.prior_case_count,
                        "suggested_stage_transition": c.suggested_stage_transition,
                        "alert_count": c.alert_count,
                        "highest_alert_priority": c.highest_alert_priority,
                        "suspicious_entities": c.suspicious_entities,
                        "comment_count": c.comment_count,
                        "latest_comment": c.latest_comment,
                        "triage_verdict": c.triage_verdict.value,
                        "triage_summary": c.triage_summary,
                        "recommended_actions": c.recommended_actions,
                        "suggested_agent_prompt": c.suggested_agent_prompt,
                    }
                    for c in batch.results
                ],
            }
            print(json.dumps(out, indent=2))
            return

        print(f"\n==========================================================================================")
        print(f" SOAR CASE ORCHESTRATED TRIAGE (Analyzed: {batch.total_cases_analyzed} | Open: {batch.open_cases_count} | High Risk / Critical: {batch.critical_high_count})")
        print(f"==========================================================================================")
        if not batch.results:
            print(" No candidate cases found matching criteria.")
            return

        for idx, item in enumerate(batch.results, 1):
            verdict_badge = f"[{item.triage_verdict.value}]"
            prio_badge = f"[{item.priority.value}]"
            status_badge = "[CLOSED]" if item.is_closed else "[OPEN]"
            print(f" {idx:2d}. Case #{item.case_id} | {verdict_badge:28s} | {status_badge:8s} | Prio: {prio_badge:10s} | Alerts: {item.alert_count:2d}")
            print(f"     Title   : {item.title}")
            print(f"     Verdict : {item.triage_summary}")
            if item.precedent_summary and item.precedent_summary.precedent_notes:
                for pn in item.precedent_summary.precedent_notes[:2]:
                    print(f"     Preced. : {pn}")
            if item.suspicious_entities:
                print(f"     Entities: {', '.join(item.suspicious_entities)}")
            if item.recommended_actions:
                print(f"     Actions :")
                for act in item.recommended_actions:
                    print(f"       - {act}")
            if item.latest_comment:
                clean_comm = item.latest_comment.splitlines()[0] if item.latest_comment else ""
                print(f"     Note    : {clean_comm}")
            if getattr(args, "generate_prompts", False):
                print(f"\n     --- Suggested Antigravity Subagent Dispatch Prompt ---")
                for pline in item.suggested_agent_prompt.splitlines():
                    print(f"     | {pline}")
                print(f"     ------------------------------------------------------")
            print()

    elif args.case_action == "update":
        print(f"\n[CLI] Updating Case {args.case_id}...")
        res = engine.update_case(
            case_id=args.case_id,
            assignee=args.assignee,
            stage=args.stage,
            incident=args.incident,
            priority=args.priority,
        )
        print(f" [✓] Case updated successfully.")
        print(f"     Case ID : {res.case_id}")
        print(f"     Assignee: {res.assignee}")
        print(f"     Stage   : {res.stage}")
        print(f"     Incident: {res.incident}")
        print(f"     Priority: {res.priority}")

    elif args.case_action == "assign":
        print(f"\n[CLI] Assigning Case {args.case_id} to '{args.to}'...")
        res = engine.assign_case(case_id=args.case_id, assignee=args.to)
        print(f" [✓] Case assigned successfully.")
        print(f"     Case ID : {res.case_id}")
        print(f"     Assignee: {res.assignee}")

    elif args.case_action == "set-stage":
        print(f"\n[CLI] Updating Case {args.case_id} stage to '{args.stage}'...")
        res = engine.set_case_stage(case_id=args.case_id, stage=args.stage)
        print(f" [✓] Case stage updated successfully.")
        print(f"     Case ID : {res.case_id}")
        print(f"     Stage   : {res.stage}")

    elif args.case_action == "set-incident":
        action_label = "Marking as Incident" if args.incident else "Unmarking as Incident"
        print(f"\n[CLI] {action_label} for Case {args.case_id}...")
        res = engine.set_case_incident(case_id=args.case_id, incident=args.incident)
        print(f" [✓] Case incident status updated successfully.")
        print(f"     Case ID : {res.case_id}")
        print(f"     Incident: {res.incident}")

    elif args.case_action == "alert-priority":
        print(f"\n[CLI] Updating Alert {args.alert_id} priority in Case {args.case_id} to '{args.priority}'...")
        res = engine.set_case_alert_priority(case_id=args.case_id, alert_id=args.alert_id, priority=args.priority)
        print(f" [✓] Case alert priority updated successfully.")
        print(f"     Case ID : {res.case_id}")
        print(f"     Alert ID: {res.alert_id}")
        print(f"     Priority: {res.priority}")

    elif args.case_action == "recommend-alert":
        print(f"\n[CLI] Requesting Gemini AI Recommendation for Alert {args.alert_id} in Case {args.case_id}...")
        if not args.wait:
            job = engine.create_case_alert_recommendation(case_id=args.case_id, alert_id=args.alert_id)
            print(f" [✓] Recommendation job initiated.")
            print(f"     Case ID          : {job.case_id}")
            print(f"     Alert ID         : {job.alert_id}")
            print(f"     Recommendation ID: {job.recommendation_id}")
            print(f"\nTo fetch later: secops case recommend-fetch {job.case_id} {job.recommendation_id}")
        else:
            rec = engine.get_case_alert_recommendation(
                case_id=args.case_id,
                alert_id=args.alert_id,
                timeout_sec=args.timeout,
            )
            print(f" [✓] Recommendation fetch complete.")
            print(f"     State            : {rec.state}")
            print(f"     Recommendation ID: {rec.recommendation_id}")
            if rec.recommendation:
                print(f"\n--- GEMINI AI RECOMMENDATION ---")
                print(rec.recommendation)
            if rec.status_message:
                print(f"     Status Message   : {rec.status_message}")
            if rec.marketplace_actions_triggered_manually:
                print(f"     Marketplace Actions Triggered: {', '.join(rec.marketplace_actions_triggered_manually)}")

    elif args.case_action == "recommend-fetch":
        print(f"\n[CLI] Fetching Gemini AI Recommendation {args.recommendation_id} for Case {args.case_id}...")
        rec = engine.fetch_case_alert_recommendation(case_id=args.case_id, recommendation_id=args.recommendation_id)
        print(f" [✓] Recommendation fetched successfully.")
        print(f"     State            : {rec.state}")
        print(f"     Recommendation ID: {rec.recommendation_id}")
        if rec.recommendation:
            print(f"\n--- GEMINI AI RECOMMENDATION ---")
            print(rec.recommendation)
        if rec.status_message:
            print(f"     Status Message   : {rec.status_message}")
        if rec.marketplace_actions_triggered_manually:
            print(f"     Marketplace Actions Triggered: {', '.join(rec.marketplace_actions_triggered_manually)}")

    elif args.case_action == "summary":
        print(f"\n[CLI] Retrieving Gemini AI Summary for Case {args.case_id}...")
        if args.wait:
            summary = engine.get_case_summary(case_id=args.case_id, timeout_sec=args.timeout)
        else:
            summary = engine.get_or_create_case_summary(case_id=args.case_id)

        print(f" [✓] Case summary status: {summary.state}")
        if summary.update_time:
            print(f"     Last Updated : {summary.update_time}")
        if summary.summary:
            print(f"\n--- CASE SUMMARY ---")
            print(summary.summary)
        if summary.reasons:
            print(f"\n--- KEY REASONS ({len(summary.reasons)}) ---")
            for idx, r in enumerate(summary.reasons, 1):
                print(f" [{idx}] {r}")
        if summary.next_steps:
            print(f"\n--- RECOMMENDED NEXT STEPS ({len(summary.next_steps)}) ---")
            for idx, s in enumerate(summary.next_steps, 1):
                print(f" [{idx}] {s}")


def run_alert_cli(args):
    engine = SecOpsEngine()
    if args.alert_action == "show":
        print(f"\n[CLI] Investigating Alert: {args.alert_name}...")
        inv = engine.investigate_alert(args.alert_name)
        print(f"\n=======================================================")
        print(f" ALERT: {inv.display_name}")
        print(f" Case ID: {inv.case_id} | Priority: {inv.priority} | Status: {inv.status}")
        print(f" Detection Time: {inv.detection_time} | Risk Score: {inv.risk_score}")
        print(f" Rule Name: {inv.rule_name}")
        print(f"=======================================================")

        print(f"\n--- INVOLVED ENTITIES ({len(inv.entities)}) ---")
        for idx, e in enumerate(inv.entities, 1):
            susp_flag = " [SUSPICIOUS]" if e.is_suspicious else ""
            print(f" [{idx}] ({e.entity_type or 'ENTITY'}) {e.identifier}{susp_flag}")


def run_playbook_cli(args):
    from engine import PlaybookType
    engine = SecOpsEngine()

    if args.playbook_action in ("search", "list"):
        query_text = getattr(args, "query", "") if args.playbook_action == "search" else ""
        category = getattr(args, "category", None)
        pt = getattr(args, "type", None)
        playbook_type = PlaybookType(pt) if pt else None
        is_enabled = getattr(args, "enabled", None)
        limit = getattr(args, "limit", 50)

        print(f"\n[CLI] Searching SOAR Playbooks (Query: '{query_text}', Category: '{category or 'ALL'}', Type: '{pt or 'ALL'}')...")
        batch = engine.search_playbooks(
            query=query_text or None,
            category=category,
            playbook_type=playbook_type,
            is_enabled=is_enabled,
            limit=limit,
        )

        print(f"\n=== PLAYBOOKS FOUND: {len(batch.results)} (Total matching: {batch.total_count}) ===")
        for idx, pb in enumerate(batch.results, 1):
            status_str = "[ENABLED]" if pb.is_enabled else "[DISABLED]"
            type_str = f"[{pb.playbook_type.value}]"
            print(f" {idx:2d}. {status_str:10s} {type_str:9s} ID: {pb.id:<6s} | {pb.name}")
            print(f"     Identifier: {pb.identifier}")
            print(f"     Category  : {pb.category_name:<20s} | Creator: {pb.creator_full_name}")
            if pb.environments:
                print(f"     Envs      : {', '.join(pb.environments)}")
            print()

    elif args.playbook_action == "get":
        print(f"\n[CLI] Fetching Playbook: {args.identifier}...")
        try:
            pb = engine.get_playbook(args.identifier)
            print(f"\n=======================================================")
            print(f" PLAYBOOK: {pb.name}")
            status_str = "ENABLED" if pb.is_enabled else "DISABLED"
            print(f" ID: {pb.id} | Identifier: {pb.identifier}")
            print(f" Status: {status_str} | Priority: {pb.priority} | Type: {pb.playbook_type.value}")
            print(f" Category: {pb.category_name} | Creator: {pb.creator}")
            if pb.description:
                print(f"\n Description:\n   {pb.description}")
            print(f"=======================================================")

            if pb.trigger:
                print(f"\n--- TRIGGER ({pb.trigger.trigger_type}) ---")
                print(f" Logical Operator: {pb.trigger.logical_operator}")
                for c_idx, c in enumerate(pb.trigger.conditions, 1):
                    print(f"   [{c_idx}] {c.match_type} -> '{c.value}'")

            print(f"\n--- EXECUTION STEPS / ACTIONS ({len(pb.steps)}) ---")
            for s_idx, s in enumerate(pb.steps, 1):
                auto_str = "AUTO" if s.is_automatic else "MANUAL"
                print(f" [{s_idx}] {s.instance_name} ({auto_str} | {s.step_type})")
                print(f"      Integration: {s.integration} | Action: {s.action_name}")
                if s.description:
                    print(f"      Description: {s.description}")
                if s.parameters:
                    print(f"      Parameters : {len(s.parameters)} param(s)")
                    for p in s.parameters[:5]:
                        val_display = p.value if p.value is not None else "<empty>"
                        if len(str(val_display)) > 60:
                            val_display = str(val_display)[:57] + "..."
                        mand_str = " *" if p.is_mandatory else ""
                        print(f"        - {p.name}{mand_str}: {val_display}")
                    if len(s.parameters) > 5:
                        print(f"        [... +{len(s.parameters) - 5} more parameters ...]")
                print()
        except Exception as e:
            print(f"Error fetching playbook: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.playbook_action == "categories":
        print(f"\n[CLI] Listing SOAR Playbook Categories...")
        cats = engine.list_playbook_categories()
        print(f"\n=== PLAYBOOK CATEGORIES ({len(cats)}) ===")
        for idx, c in enumerate(cats, 1):
            def_badge = " (DEFAULT)" if c.is_default else ""
            print(f" [{idx:2d}] ID: {c.id:<4s} | Name: {c.name}{def_badge} (Type: {c.category_type}, State: {c.category_state})")
        print()

    elif args.playbook_action == "audit":
        import json
        from runbooks.operations.soar_playbook_inventory import (
            generate_playbook_inventory_report,
            print_playbook_inventory_console,
        )

        pt = PlaybookType(args.type) if getattr(args, "type", None) else None
        is_enabled = None
        if getattr(args, "enabled", False):
            is_enabled = True
        elif getattr(args, "disabled", False):
            is_enabled = False

        limit = getattr(args, "limit", 500)
        category = getattr(args, "category", None)
        environment = getattr(args, "environment", None)

        print(f"\n[CLI] Running SOAR Playbook & Reusable Block Audit (limit={limit})...")
        report = generate_playbook_inventory_report(
            engine=engine,
            category=category,
            playbook_type=pt,
            environment=environment,
            is_enabled=is_enabled,
            limit=limit,
        )

        if getattr(args, "json", False):
            print(json.dumps(report, indent=2, default=str))
        else:
            print_playbook_inventory_console(report)

        if getattr(args, "out", None):
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"[+] Playbook audit report written to: {args.out}")

    elif args.playbook_action == "audit-health":
        import json
        from runbooks.operations.soar_playbook_health import (
            generate_soar_playbook_health_report,
            print_soar_playbook_health_console,
        )

        days = getattr(args, "days", 7)
        scan_deep = not getattr(args, "no_deep_scan", False)
        fail_thresh = getattr(args, "fail_threshold", 15.0)
        slow_thresh = getattr(args, "slow_threshold", 3.0)

        if not getattr(args, "json", False):
            print(f"\n[CLI] Running SOAR Playbook Health Check (lookback={days}d, deep_scan={scan_deep})...")

        report = generate_soar_playbook_health_report(
            engine=engine,
            days=days,
            scan_deep=scan_deep,
            fail_threshold_pct=fail_thresh,
            slow_threshold_minutes=slow_thresh,
        )

        if getattr(args, "json", False):
            print(json.dumps(report, indent=2, default=str))
        else:
            print_soar_playbook_health_console(report)

        if getattr(args, "out", None):
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, default=str)
            print(f"[+] SOAR Playbook health report written to: {args.out}")


def run_integration_cli(args):
    engine = SecOpsEngine()

    if args.integration_action in ("search", "list"):
        query_text = getattr(args, "query", "") if args.integration_action == "search" else ""
        env = getattr(args, "env", None)
        is_configured = getattr(args, "configured", None)
        is_certified = getattr(args, "certified", None)
        limit = getattr(args, "limit", 50)

        print(f"\n[CLI] Searching SOAR Integrations (Query: '{query_text}', Env: '{env or 'ALL'}', Configured: {is_configured}, Certified: {is_certified})...")
        batch = engine.search_integrations(
            query=query_text or None,
            environment=env,
            is_configured=is_configured,
            is_certified=is_certified,
            limit=limit,
        )

        print(f"\n=== INTEGRATIONS FOUND: {len(batch.results)} (Total matching: {batch.total_count}) ===")
        for idx, item in enumerate(batch.results, 1):
            cert_badge = "[CERTIFIED]" if item.certified else "[COMMUNITY]"
            cust_badge = "[CUSTOM]" if item.custom else ""
            print(f" {idx:2d}. {cert_badge:11s} {cust_badge:8s} {item.display_name} ({item.identifier}) v{item.version}")
            print(f"     Instances: {item.instances_count} configured instance(s) | Python: {item.python_version}")
            if item.description:
                desc_short = item.description[:100] + ("..." if len(item.description) > 100 else "")
                print(f"     Desc     : {desc_short}")
            print()

    elif args.integration_action == "get":
        print(f"\n[CLI] Fetching Integration: {args.identifier}...")
        try:
            detail = engine.get_integration(args.identifier)
            print(f"\n=======================================================")
            print(f" INTEGRATION: {detail.display_name} ({detail.identifier})")
            cert_str = "CERTIFIED" if detail.certified else "COMMUNITY / UNCERTIFIED"
            cust_str = "CUSTOM" if detail.custom else "STANDARD"
            print(f" Version: {detail.version} | Python: {detail.python_version} | Type: {detail.integration_type.value}")
            print(f" Status: {cert_str} | {cust_str}")
            if detail.documentation_uri:
                print(f" Documentation: {detail.documentation_uri}")
            if detail.categories:
                print(f" Categories   : {', '.join(detail.categories)}")
            if detail.description:
                print(f"\n Description:\n   {detail.description}")
            print(f"=======================================================")

            print(f"\n--- CONFIGURED INSTANCES ({len(detail.instances)}) ---")
            if not detail.instances:
                print("   (No instances deployed for this integration)")
            for idx, inst in enumerate(detail.instances, 1):
                conf_badge = "[CONFIGURED]" if inst.is_configured else "[UNCONFIGURED]"
                rem_badge = " (Remote Agent)" if inst.is_remote else ""
                sys_badge = " (System Default)" if inst.is_system_default else ""
                print(f" [{idx}] {conf_badge:14s} Env: {inst.environment:<20s} | Name: {inst.display_name}{rem_badge}{sys_badge}")
                print(f"      Identifier: {inst.identifier}")

            print(f"\n--- MATCHED REMOTE AGENTS ({len(detail.remote_agents)}) ---")
            for idx, a in enumerate(detail.remote_agents, 1):
                envs_str = ", ".join(a.environments) if a.environments else "ALL"
                print(f" [{idx}] ID: {a.id:<4s} | {a.display_name} (State: {a.agent_state})")
                print(f"      Supported Environments: {envs_str}")
            print()

        except Exception as e:
            print(f"Error fetching integration: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.integration_action == "instances":
        print(f"\n[CLI] Listing Configured Integration Instances (Integration: '{args.integration or 'ALL'}', Env: '{args.env or 'ALL'}')...")
        instances = engine.list_integration_instances(
            integration_id=args.integration,
            environment=args.env,
        )
        print(f"\n=== CONFIGURED INSTANCES ({len(instances)}) ===")
        for idx, inst in enumerate(instances, 1):
            conf_badge = "[CONFIGURED]" if inst.is_configured else "[UNCONFIGURED]"
            rem_badge = " [REMOTE]" if inst.is_remote else ""
            print(f" {idx:3d}. {conf_badge:14s} {inst.integration_identifier:<25s} | Env: {inst.environment:<20s} | {inst.display_name}{rem_badge}")
            print(f"      ID: {inst.identifier}")
        print()

    elif args.integration_action == "agents":
        state_filter = "ACTIVE" if args.active_only else None
        print(f"\n[CLI] Listing Remote Execution Agents (State filter: '{state_filter or 'ALL'}')...")
        agents = engine.list_remote_agents(state_filter=state_filter)
        print(f"\n=== REMOTE EXECUTION AGENTS ({len(agents)}) ===")
        for idx, a in enumerate(agents, 1):
            state_badge = "[ACTIVE]" if a.is_active else f"[{a.agent_state}]"
            envs_str = ", ".join(a.environments) if a.environments else "ALL"
            print(f" [{idx}] {state_badge:10s} ID: {a.id:<4s} | {a.display_name} (Identifier: {a.identifier})")
            print(f"      Logging Level: {a.logging_level}")
            print(f"      Environments : {envs_str}")
            if a.installer_link:
                print(f"      Installer    : {a.installer_link[:70]}...")
            print()


def run_job_cli(args):
    engine = SecOpsEngine()

    if args.job_action in ("search", "list"):
        query_text = getattr(args, "query", "") if args.job_action == "search" else ""
        integration = getattr(args, "integration", None)
        is_enabled = getattr(args, "enabled", None)
        limit = getattr(args, "limit", 50)

        print(f"\n[CLI] Searching SOAR Scheduled Jobs (Query: '{query_text}', Integration: '{integration or 'ALL'}', Enabled: {is_enabled})...")
        batch = engine.search_jobs(
            query=query_text or None,
            integration=integration,
            enabled=is_enabled,
            limit=limit,
        )

        print(f"\n=== SCHEDULED JOBS FOUND: {len(batch.results)} (Total matching: {batch.total_count}) ===")
        for idx, item in enumerate(batch.results, 1):
            en_badge = "[ENABLED]" if item.enabled else "[DISABLED]"
            cron_str = f"Cron: {item.cron_expression}" if item.cron_expression else (f"Interval: {item.interval}s" if item.interval else "Manual/Once")
            print(f" {idx:2d}. {en_badge:10s} {item.display_name} (ID: {item.id}, Integration: {item.integration})")
            print(f"     Schedule : {cron_str} | Deployed Instances: {item.instances_count}")
            if item.description:
                desc_short = item.description[:95] + ("..." if len(item.description) > 95 else "")
                print(f"     Desc     : {desc_short}")
            print()

    elif args.job_action == "get":
        print(f"\n[CLI] Fetching SOAR Job: Integration='{args.integration}', Job ID='{args.job_id}'...")
        try:
            detail = engine.get_job(integration=args.integration, job_id=args.job_id)
            j = detail.job
            en_str = "ENABLED" if j.enabled else "DISABLED"
            cron_str = j.cron_expression or (f"{j.interval}s" if j.interval else "None")
            print(f"\n=======================================================")
            print(f" JOB: {j.display_name} (ID: {j.id})")
            print(f" Integration : {j.integration} | Status: {en_str}")
            print(f" Schedule    : {cron_str} (Type: {j.recurring_type or 'N/A'}, Timeout: {j.timeout or 'N/A'})")
            if j.description:
                print(f"\n Description:\n   {j.description}")
            print(f"=======================================================")

            print(f"\n--- RUNTIME INSTANCES ({len(detail.instances)}) ---")
            if not detail.instances:
                print("   (No deployed instances found for this job)")
            for idx, inst in enumerate(detail.instances, 1):
                status_badge = f"[{inst.last_run_status}]"
                sched = inst.schedule_type or "N/A"
                print(f" [{idx}] {status_badge:11s} Instance ID: {inst.id:<4s} | Name: {inst.display_name} (Env: {inst.environment or 'Global'})")
                print(f"      Schedule Type: {sched} | Agent: {inst.remote_agent_id or 'Local/Cloud'}")
                if inst.last_run_time:
                    print(f"      Last Run Time: {inst.last_run_time}")

            print(f"\n--- RECENT EXECUTION RUNS ({len(detail.recent_logs)}) ---")
            for idx, lg in enumerate(detail.recent_logs, 1):
                print(f" [{idx}] Status: {lg.status:<8s} | Start: {lg.start_time} | End: {lg.end_time}")
                if lg.log_text:
                    preview = lg.log_text[:200].replace('\n', ' ')
                    print(f"      Log Preview: {preview}...")
            print()

        except Exception as e:
            print(f"Error fetching job: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.job_action == "instances":
        print(f"\n[CLI] Listing SOAR Job Instances (Integration: '{args.integration or 'ALL'}', Job ID: '{args.job_id or 'ALL'}')...")
        instances = engine.list_job_instances(
            integration=args.integration,
            job_id=args.job_id,
        )
        print(f"\n=== RUNTIME JOB INSTANCES ({len(instances)}) ===")
        for idx, inst in enumerate(instances, 1):
            status_badge = f"[{inst.last_run_status}]"
            print(f" {idx:2d}. {status_badge:11s} ID: {inst.id:<4s} | {inst.display_name} (Job: {inst.job_name}, Integration: {inst.integration})")
            print(f"     Environment: {inst.environment or 'Global'} | Schedule Type: {inst.schedule_type or 'N/A'}")
        print()

    elif args.job_action == "logs":
        print(f"\n[CLI] Fetching Execution History for Job Instance ID: {args.instance_id}...")
        try:
            logs = engine.get_job_instance_logs(
                job_instance_id=args.instance_id,
                limit=args.limit,
            )
            print(f"\n=== EXECUTION RUNS ({len(logs)}) ===")
            for idx, lg in enumerate(logs, 1):
                print(f" [{idx:2d}] Run Status: {lg.status:<8s} | Start: {lg.start_time} | End: {lg.end_time}")
                if lg.log_text:
                    print(f"      Log Text:\n{lg.log_text[:300]}\n")
            print()
        except Exception as e:
            print(f"Error fetching job instance logs: {e}", file=sys.stderr)
            sys.exit(1)


def run_content_pack_cli(args):
    engine = SecOpsEngine()

    if args.pack_action in ("search", "list"):
        query_text = getattr(args, "query", "") if args.pack_action == "search" else ""
        category = getattr(args, "category", None)
        pack_type = getattr(args, "type", None)
        deployed = getattr(args, "deployed", None)
        limit = getattr(args, "limit", 50)

        print(f"\n[CLI] Searching Content Hub Marketplace Packs (Query: '{query_text}', Category: '{category or 'ALL'}', Type: '{pack_type or 'ALL'}', Deployed: {deployed})...")
        batch = engine.search_content_packs(
            query=query_text or None,
            category=category,
            pack_type=pack_type,
            deployed=deployed,
            limit=limit,
        )

        print(f"\n=== CONTENT PACKS FOUND: {len(batch.results)} (Total matching: {batch.total_count}) ===")
        for idx, item in enumerate(batch.results, 1):
            dep_badge = "[DEPLOYED]" if item.deployed else "[NOT DEPLOYED]"
            cats_str = ", ".join(item.categories) if item.categories else "General"
            bundle_str = (
                f"{item.playbooks_count} Playbook(s), "
                f"{item.integrations_count} Integration(s), "
                f"{item.dashboards_count} Dashboard(s), "
                f"{item.rulesets_count} RuleSet(s), "
                f"{item.queries_count} Query(s)"
            )
            print(f" {idx:2d}. [{item.pack_type}] {item.title} (ID: {item.id})")
            print(f"     Status   : {dep_badge} | Categories: {cats_str} | Uploader: {item.uploader or 'Google Cloud Security'}")
            print(f"     Bundled  : {bundle_str}")
            if item.description:
                desc_clean = item.description.replace("<p>", "").replace("</p>", "").replace("\n", " ").strip()
                desc_short = desc_clean[:95] + ("..." if len(desc_clean) > 95 else "")
                print(f"     Desc     : {desc_short}")
            print()

    elif args.pack_action == "get":
        print(f"\n[CLI] Fetching Content Pack details for: '{args.identifier}'...")
        try:
            detail = engine.get_content_pack(args.identifier)
            p = detail.pack
            dep_badge = "DEPLOYED (INSTALLED)" if p.deployed else "NOT DEPLOYED (AVAILABLE)"
            cats_str = ", ".join(p.categories) if p.categories else "None"
            print(f"\n=======================================================")
            print(f" CONTENT PACK: {p.title}")
            print(f" Identifier   : {p.identifier}")
            print(f" Type         : {p.pack_type} | Status: {dep_badge}")
            print(f" Categories   : {cats_str}")
            print(f" Uploader     : {p.uploader or 'Google Cloud Security'} | Community: {p.community}")
            if p.description:
                desc_clean = p.description.replace("<p>", "").replace("</p>", "").replace("<br>", "\n").strip()
                print(f"\n Description:\n   {desc_clean[:350]}...")
            print(f"=======================================================")

            if detail.playbooks:
                print(f"\n--- BUNDLED PLAYBOOKS ({len(detail.playbooks)}) ---")
                for idx, pb in enumerate(detail.playbooks, 1):
                    print(f" [{idx}] {pb.title} (ID: {pb.id})")

            if detail.integrations:
                print(f"\n--- BUNDLED INTEGRATIONS ({len(detail.integrations)}) ---")
                for idx, it in enumerate(detail.integrations, 1):
                    print(f" [{idx}] {it.title} (ID: {it.id})")

            if detail.dashboards:
                print(f"\n--- BUNDLED DASHBOARDS ({len(detail.dashboards)}) ---")
                for idx, db in enumerate(detail.dashboards, 1):
                    print(f" [{idx}] {db.title} (ID: {db.id})")

            if detail.rulesets:
                print(f"\n--- BUNDLED CURATED RULESETS ({len(detail.rulesets)}) ---")
                for idx, rs in enumerate(detail.rulesets, 1):
                    print(f" [{idx}] {rs.title} (ID: {rs.id})")

            if detail.queries:
                print(f"\n--- BUNDLED SEARCH QUERIES ({len(detail.queries)}) ---")
                for idx, sq in enumerate(detail.queries, 1):
                    print(f" [{idx}] {sq.title} (ID: {sq.id})")

            if detail.rules:
                print(f"\n--- BUNDLED DETECTION RULES ({len(detail.rules)}) ---")
                for idx, dr in enumerate(detail.rules, 1):
                    print(f" [{idx}] {dr.title} (ID: {dr.id})")

            if detail.pre_guidance:
                print(f"\n--- PRE-INSTALLATION GUIDANCE ---\n{detail.pre_guidance}\n")
            if detail.post_guidance:
                print(f"\n--- POST-INSTALLATION GUIDANCE ---\n{detail.post_guidance}\n")
            print()

        except Exception as e:
            print(f"Error fetching content pack: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.pack_action == "categories":
        print(f"\n[CLI] Discovering Content Hub Category Taxonomy...")
        cats = engine.list_content_pack_categories()
        print(f"\n=== CONTENT HUB CATEGORIES ({len(cats)}) ===")
        for idx, c in enumerate(cats, 1):
            print(f" {idx:2d}. {c['category']:<30s} : {c['pack_count']:2d} pack(s)")
        print()


def run_curated_cli(args):
    """Executes Curated Detections subcommands."""
    engine = SecOpsEngine()

    if args.curated_action == "rulesets":
        print(f"\n[CLI] Searching Google SecOps Curated Rule Sets...")
        batch = engine.search_curated_rulesets(
            query=args.query if args.query else None,
            category=args.category,
            mitre_tactic=args.tactic,
            mitre_technique=args.technique,
            log_source=args.log_source,
            limit=args.limit,
        )

        print(f"\n=== CURATED RULE SETS (Found {batch.total_count}, Showing {len(batch.results)}) ===")
        for idx, rs in enumerate(batch.results, 1):
            tactics_str = ", ".join([f"{t.id} ({t.display_name})" for t in rs.tactics]) if rs.tactics else "None"
            techniques_str = ", ".join([f"{t.id} ({t.display_name})" for t in rs.techniques[:3]]) if rs.techniques else "None"
            if len(rs.techniques) > 3:
                techniques_str += f" (+{len(rs.techniques) - 3} more)"
            logs_str = ", ".join(rs.log_sources) if rs.log_sources else "N/A"
            authors_str = ", ".join(rs.authors) if rs.authors else "Google Cloud Security"

            print(f"\n [{idx:2d}] {rs.title}")
            print(f"     ID       : {rs.id}")
            print(f"     Category : {rs.category_name or rs.category_id or 'N/A'}")
            print(f"     Logs     : {logs_str}")
            print(f"     MITRE TA : {tactics_str}")
            print(f"     MITRE T  : {techniques_str}")
            print(f"     Authors  : {authors_str} | Quota: {rs.quota_size}")
            if rs.description:
                desc_clean = rs.description.replace("\n", " ").strip()
                desc_short = desc_clean[:110] + ("..." if len(desc_clean) > 110 else "")
                print(f"     Desc     : {desc_short}")
        print()

    elif args.curated_action == "get":
        print(f"\n[CLI] Deep-inspecting Curated Rule Set: '{args.identifier}'...")
        try:
            detail = engine.get_curated_ruleset(args.identifier)
            rs = detail.rule_set
            tactics_str = ", ".join([f"{t.id} ({t.display_name})" for t in rs.tactics]) if rs.tactics else "None"
            techniques_str = ", ".join([f"{t.id} ({t.display_name})" for t in rs.techniques]) if rs.techniques else "None"
            logs_str = ", ".join(rs.log_sources) if rs.log_sources else "N/A"

            print(f"\n=======================================================")
            print(f" CURATED RULE SET: {rs.title}")
            print(f" Identifier      : {rs.id}")
            print(f" Category        : {rs.category_name or rs.category_id or 'N/A'}")
            print(f" Log Sources     : {logs_str}")
            print(f" MITRE Tactics   : {tactics_str}")
            print(f" MITRE Techniques: {techniques_str}")
            print(f" 7-Day Hits      : {detail.detection_count:,} detection(s)")
            print(f" Authors         : {', '.join(rs.authors) if rs.authors else 'Google Cloud Security'}")
            if rs.description:
                print(f"\n Description:\n   {rs.description.strip()}")
            print(f"=======================================================")

            if detail.deployments:
                print(f"\n--- DEPLOYMENT STATUS ({len(detail.deployments)}) ---")
                for d in detail.deployments:
                    status_str = "ENABLED" if d.enabled else "DISABLED"
                    alert_str = "ALERTING ON" if d.alerting else "ALERTING OFF"
                    print(f" Mode: {d.precision:<8s} | State: {status_str:<9s} | Alerting: {alert_str}")

            if detail.rules:
                print(f"\n--- MEMBER CURATED RULES ({len(detail.rules)}) ---")
                for idx, r in enumerate(detail.rules, 1):
                    techs = ", ".join([t.id for t in r.techniques]) if r.techniques else "N/A"
                    print(f" [{idx:2d}] {r.title}")
                    print(f"      ID: {r.id} | Severity: {r.severity} | Precision: {r.precision} | MITRE: {techs}")
            print()

        except Exception as e:
            print(f"Error inspecting curated rule set: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.curated_action == "rule":
        print(f"\n[CLI] Inspecting Curated Rule: '{args.rule_id}'...")
        try:
            detail = engine.get_curated_rule(args.rule_id)
            r = detail.rule
            tactics_str = ", ".join([f"{t.id} ({t.display_name})" for t in detail.tactics]) if detail.tactics else "None"
            techs_str = ", ".join([f"{t.id} ({t.display_name})" for t in detail.techniques]) if detail.techniques else "None"

            print(f"\n=======================================================")
            print(f" CURATED RULE: {r.title}")
            print(f" Rule ID      : {r.id}")
            print(f" Severity     : {r.severity} | Precision: {r.precision} | Type: {r.rule_type}")
            print(f" Live Enabled : {'YES' if detail.live_status_enabled else 'NO'}")
            print(f" MITRE Tactics: {tactics_str}")
            print(f" MITRE Techs  : {techs_str}")
            if r.description:
                print(f"\n Description:\n   {r.description.strip()}")
            if r.false_positives:
                print(f"\n False Positives:\n   {r.false_positives.strip()}")
            print(f"=======================================================")

            if detail.rule_text:
                print(f"\n--- EXECUTABLE YARA-L RULE LOGIC ---\n")
                print(detail.rule_text)
            else:
                print("\n[Notice] Raw YARA-L logic not published for this rule.")
            print()

        except Exception as e:
            print(f"Error inspecting curated rule: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.curated_action == "metrics":
        days = args.days if args.days > 0 else 7
        print(f"\n[CLI] Querying Curated Detection Telemetry & Engine Quotas (Last {days} days)...")
        now = datetime.now(timezone.utc)
        start_iso = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        end_iso = now.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        try:
            metrics = engine.get_curated_detection_metrics(start_time=start_iso, end_time=end_iso)
            tm = metrics.tenant_metrics
            print(f"\n=== TENANT RULE ENGINE QUOTAS & STATUS ===")
            print(f" Total Active Rules : {tm.total_active_count}")
            print(f" Total Archived     : {tm.total_archived_count}")
            print(f" Total Live Rules   : {tm.total_live_rule_count} / Max {tm.max_live_rule_count}")
            print(f" Rule Quota Usage   : {tm.quota_usage} / Limit {tm.quota_limit}")

            if tm.counts_per_type:
                print("\n Live Rules Breakdown by Type:")
                for ct in tm.counts_per_type:
                    print(f"   - {ct.get('type', 'UNKNOWN'):<15s}: {ct.get('count', 0):,}")

            print(f"\n=== TOP FIRING CURATED RULE SETS (Last {days} Days) ===")
            if metrics.top_firing_rulesets:
                for idx, fs in enumerate(metrics.top_firing_rulesets[:15], 1):
                    print(f" [{idx:2d}] {fs['ruleset_name']:<45s} : {fs['count']:,} hits")
            else:
                print(" No detection hits recorded in this interval.")
            print()

        except Exception as e:
            print(f"Error fetching curated metrics: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.curated_action == "set-deployment":
        if args.enabled is None and args.alerting is None:
            print("Error: Must specify at least one state flag (--enabled/--disabled or --alerting/--no-alerting)", file=sys.stderr)
            sys.exit(1)

        prec = args.precision.upper()
        print(f"\n[CLI] Updating Curated Rule Set '{args.identifier}' deployment ({prec})...")
        try:
            res = engine.set_curated_ruleset_deployment(
                ruleset_id_or_title=args.identifier,
                precision=prec,
                enabled=args.enabled,
                alerting=args.alerting,
                sync_rules=args.sync_rules,
            )
            state_str = "ENABLED" if res.enabled else "DISABLED"
            alert_str = "ALERTING ON" if res.alerting else "ALERTING OFF"
            print(f"\n[Success] Curated Rule Set Deployment updated successfully:")
            print(f"  Resource : {res.resource_name}")
            print(f"  Precision: {res.precision}")
            print(f"  Status   : {state_str}")
            print(f"  Alerting : {alert_str}\n")
        except Exception as e:
            print(f"Error updating curated deployment: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.curated_action == "audit":
        from runbooks.operations.curated_detections_health import (
            generate_curated_detections_health_report,
            print_curated_detections_health_console,
        )
        days = getattr(args, "days", 7) or 7
        try:
            report = generate_curated_detections_health_report(engine=engine, days=days)
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2)
                print(f"[+] Curated Detections health report saved to {args.out}")
            print_curated_detections_health_console(report, json_output=getattr(args, "json", False))
        except Exception as e:
            print(f"Error running curated detections health audit: {e}", file=sys.stderr)
            sys.exit(1)



def run_marketplace_cli(args):
    """Handler for Content Hub Marketplace Response Integrations commands."""
    engine = SecOpsEngine()

    if args.mp_action in ["list", "search"]:
        kw = args.query if hasattr(args, "query") and args.query else None
        cat = args.category if hasattr(args, "category") and args.category else None
        installed = args.installed if hasattr(args, "installed") else None
        updates = args.updates if hasattr(args, "updates") else None
        certified = args.certified if hasattr(args, "certified") else None
        limit = args.limit if hasattr(args, "limit") else 50

        print(f"\n[CLI] Querying Marketplace Response Integrations (Query='{kw or ''}', Category='{cat or 'ALL'}', Installed={installed}, Updates={updates})...")

        try:
            batch = engine.search_marketplace_integrations(
                query=kw,
                category=cat,
                installed=installed,
                update_available=updates,
                certified=certified,
                limit=limit,
            )

            print(f"\n=== MARKETPLACE RESPONSE INTEGRATIONS (Showing {len(batch.results)} of {batch.total_count} matching | Installed: {batch.installed_count} | Updates Available: {batch.updates_count}) ===")
            print(f"{'#':<3s} {'IDENTIFIER':<32s} {'TITLE':<36s} {'VER':<7s} {'INSTALLED':<11s} {'UPDATE':<14s} {'CATEGORIES'}")
            print("-" * 135)

            for idx, item in enumerate(batch.results, 1):
                inst_str = f"v{item.installed_version}" if item.installed else "NO"
                upd_str = "UPDATE READY" if item.update_available else "-"
                cats_str = ", ".join(item.categories[:3]) if item.categories else "None"
                print(f"{idx:<3d} {item.identifier[:31]:<32s} {item.title[:35]:<36s} {item.version:<7s} {inst_str:<11s} {upd_str:<14s} {cats_str}")

            print()

        except Exception as e:
            print(f"Error querying marketplace integrations: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.mp_action == "get":
        ident = args.identifier
        print(f"\n[CLI] Deep-inspecting Marketplace Response Integration: '{ident}'...")

        try:
            detail = engine.get_marketplace_integration(ident)
            integ = detail.integration

            print("\n=== INTEGRATION METADATA ===")
            print(f" Identifier        : {integ.identifier}")
            print(f" Title             : {integ.title}")
            print(f" Latest Version    : {integ.version}")
            print(f" Installed Version : {integ.installed_version} (Installed: {integ.installed})")
            print(f" Update Available  : {integ.update_available}")
            print(f" Categories        : {', '.join(integ.categories)}")
            print(f" Python Runtime    : {integ.python_version}")
            print(f" Certified / Custom: {integ.certified} / {integ.custom}")
            if integ.documentation_uri:
                print(f" Documentation     : {integ.documentation_uri}")
            print(f" Resource Name     : {integ.resource_name}")

            print("\n--- Description ---")
            print(integ.description)

            print(f"\n=== BUNDLED ACTIONS ({len(detail.actions)}) ===")
            if detail.actions:
                for a in detail.actions:
                    print(f"  • {a}")
            else:
                print("  (No discrete actions defined)")

            print(f"\n=== CONNECTORS ({len(detail.connectors)}) ===")
            if detail.connectors:
                for c in detail.connectors:
                    print(f"  • {c}")
            else:
                print("  (No connectors defined)")

            print(f"\n=== SCHEDULED JOBS ({len(detail.jobs)}) ===")
            if detail.jobs:
                for j in detail.jobs:
                    print(f"  • {j}")
            else:
                print("  (No jobs defined)")

            print(f"\n=== MANAGER MODULES ({len(detail.managers)}) ===")
            if detail.managers:
                for m in detail.managers:
                    print(f"  • {m}")
            else:
                print("  (No manager modules defined)")

            print(f"\n=== RELEASE NOTES & CHANGELOGS ({len(detail.release_notes)}) ===")
            if detail.release_notes:
                for rn in detail.release_notes:
                    print(f"\n Version {rn.version} (Published: {rn.publish_time}):")
                    for cl in rn.changelog_items:
                        print(f"   - {cl}")
            else:
                print("  (No release notes available)")

            print()

        except Exception as e:
            print(f"Error inspecting marketplace integration: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.mp_action == "diff":
        ident = args.identifier
        print(f"\n[CLI] Querying Commercial Upgrade Diff for: '{ident}'...")

        try:
            diff = engine.get_marketplace_integration_diff(ident)

            print("\n=== COMMERCIAL UPGRADE DIFF ===")
            print(f" Integration Identifier : {diff.integration_identifier}")
            print(f" Target Version         : {diff.version}")
            print(f" Target Python Runtime  : {diff.python_version}")
            print(f" Mapping Rules Exist    : {diff.mapping_rules_exist}")

            print(f"\n Target Actions ({len(diff.actions)}):")
            for a in diff.actions:
                print(f"   • {a}")

            print(f"\n Target Managers ({len(diff.managers)}):")
            for m in diff.managers:
                print(f"   • {m}")

            diff_dict = diff.diff
            print("\n--- Overrides & Change Manifest ---")
            if diff_dict:
                for category, details in diff_dict.items():
                    if details and isinstance(details, dict):
                        for change_type, items_list in details.items():
                            print(f"  [{category.upper()}] {change_type.upper()}:")
                            for it in items_list:
                                if isinstance(it, dict):
                                    print(f"    - {it.get('displayName', it)}")
                                else:
                                    print(f"    - {it}")
                    elif details and isinstance(details, list):
                        print(f"  [{category.upper()}]:")
                        for it in details:
                            print(f"    - {it}")
            else:
                print("  (No breaking structural overrides detected)")

            print()

        except Exception as e:
            print(f"Error fetching commercial diff: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.mp_action == "affected":
        ident = args.identifier
        print(f"\n[CLI] Querying Downstream Affected Items for: '{ident}'...")

        try:
            affected = engine.get_marketplace_integration_affected_items(ident)

            print(f"\n=== DOWNSTREAM IMPACT ANALYSIS: '{affected.integration_identifier}' ===")
            print(f" Affected Integration Instances : {len(affected.affected_instances)}")
            print(f" Affected Active Playbooks      : {len(affected.affected_playbooks)}")

            print("\n--- Configured Instances ---")
            if affected.affected_instances:
                for inst in affected.affected_instances:
                    print(f"  • {inst.display_name} (Environment: {inst.environment})")
            else:
                print("  (No configured instances in tenant)")

            print("\n--- Active Playbooks ---")
            if affected.affected_playbooks:
                for pb in affected.affected_playbooks:
                    envs = ", ".join(pb.environments) if pb.environments else "Global"
                    print(f"  • {pb.display_name} (Environments: {envs})")
            else:
                print("  (No active playbooks referencing this integration)")

            print()

        except Exception as e:
            print(f"Error fetching affected items: {e}", file=sys.stderr)
            sys.exit(1)


def run_dashboard_cli(args):
    engine = SecOpsEngine()

    if args.dash_action in ["list", "search"]:
        q_text = getattr(args, "query", "") or None
        d_type = getattr(args, "type", None)
        limit = getattr(args, "limit", 50)

        print(f"\n[CLI] Discovering Google SecOps Native Dashboards (Query: '{q_text or '*'}', Type: {d_type or 'ALL'})...")
        try:
            batch = engine.search_dashboards(query=q_text, dashboard_type=d_type, limit=limit)
            print(f"\nFound {batch.total_count} Native Dashboards (showing {len(batch.dashboards)}):")
            print(f"{'ID':<38} {'TYPE':<10} {'CHARTS':<8} {'DISPLAY NAME'}")
            print("-" * 90)
            for d in batch.dashboards:
                print(f"{d.id:<38} {d.type:<10} {d.charts_count:<8} {d.display_name}")
            print()
        except Exception as e:
            print(f"Error listing dashboards: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.dash_action == "get":
        ident = args.identifier
        print(f"\n[CLI] Deep-inspecting Native Dashboard: '{ident}'...")
        try:
            detail = engine.get_dashboard(ident, include_queries=True)
            s = detail.summary
            print(f"\n=== DASHBOARD: '{s.display_name}' ===")
            print(f" ID            : {s.id}")
            print(f" Resource Name : {s.name}")
            print(f" Type          : {s.type}")
            print(f" Access        : {s.access}")
            print(f" Created By    : {s.create_user_id} ({s.create_time})")
            print(f" Updated       : {s.update_time}")
            print(f" Description   : {s.description or 'N/A'}")
            print(f" Total Charts  : {len(detail.charts)}")

            if detail.charts:
                print("\n--- Member Charts & Widgets ---")
                for i, c in enumerate(detail.charts, 1):
                    layout_str = "N/A"
                    if c.layout:
                        layout_str = f"pos=({c.layout.start_x},{c.layout.start_y}) span=({c.layout.span_x}x{c.layout.span_y})"
                    print(f"\n  [{i}] {c.display_name}")
                    print(f"      Chart ID    : {c.id}")
                    print(f"      Tile Type   : {c.tile_type}")
                    print(f"      Data Sources: {', '.join(c.data_sources) if c.data_sources else 'None'}")
                    print(f"      Layout Grid : {layout_str}")
                    if c.query:
                        q_prev = c.query.query_text.replace("\n", " ").strip()
                        if len(q_prev) > 80:
                            q_prev = q_prev[:77] + "..."
                        print(f"      Query ID    : {c.query.id} (Dialect: {c.query.dialect})")
                        print(f"      Query Logic : {q_prev}")

                        if args.execute_queries:
                            print(f"      [Executing Live Telemetry Query...]")
                            try:
                                q_res = engine.execute_dashboard_query(c.query.name)
                                print(f"      -> Hydrated {q_res.total_rows} rows (Columns: {', '.join(q_res.columns)}):")
                                for r in q_res.rows[:3]:
                                    row_vals = [f"{k}={v}" for k, v in r.items()]
                                    print(f"         • {', '.join(row_vals)}")
                                if q_res.total_rows > 3:
                                    print(f"         ... ({q_res.total_rows - 3} more rows)")
                            except Exception as q_err:
                                print(f"      -> Query Execution Failed: {q_err}")

            print()

        except Exception as e:
            print(f"Error fetching dashboard: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.dash_action == "query":
        query_id = args.query_id
        limit = args.limit
        print(f"\n[CLI] Executing Dashboard Query: '{query_id}'...")
        try:
            q_res = engine.execute_dashboard_query(query_id)
            print(f"\n=== QUERY EXECUTION RESULT ===")
            print(f" Dialect       : {q_res.dialect}")
            print(f" Data Sources  : {', '.join(q_res.data_sources) if q_res.data_sources else 'N/A'}")
            print(f" Time Window   : {q_res.time_window.get('startTime', '')} -> {q_res.time_window.get('endTime', '')}")
            print(f" Total Rows    : {q_res.total_rows}")
            print(f" Columns ({len(q_res.columns)}): {', '.join(q_res.columns)}")

            if q_res.rows:
                print(f"\n--- Tabular Records (showing up to {limit}) ---")
                shown = q_res.rows[:limit]
                # Calculate column widths
                col_widths = {c: len(c) for c in q_res.columns}
                for r in shown:
                    for c in q_res.columns:
                        val_str = str(r.get(c, ""))
                        if len(val_str) > col_widths[c]:
                            col_widths[c] = min(len(val_str), 40)

                header = " | ".join(f"{c:<{col_widths[c]}}" for c in q_res.columns)
                print(header)
                print("-" * len(header))
                for r in shown:
                    line = " | ".join(f"{str(r.get(c, '')):<{col_widths[c]}}" for c in q_res.columns)
                    print(line)
            print()

        except Exception as e:
            print(f"Error executing dashboard query: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.dash_action == "validate":
        q_text = args.query_text
        dialect = args.dialect
        print(f"\n[CLI] Validating Query with Dialect: '{dialect}'...")
        try:
            res = engine.validate_dashboard_query(q_text, dialect=dialect)
            if res.valid:
                print(f"✓ Valid: True (Query Type: {res.raw_query_type})")
            else:
                print(f"✗ Valid: False")
                if res.error_message:
                    print(f"  Error: {res.error_message}")
            print()
        except Exception as e:
            print(f"Error validating query: {e}", file=sys.stderr)
            sys.exit(1)


def run_domain_cli(args):
    engine = SecOpsEngine()
    print("\n[CLI] Fetching Approved Managed Email Domains...")
    try:
        settings = engine.get_managed_domain_settings()
        print(f"\n=== APPROVED MANAGED EMAIL DOMAINS ({len(settings.domains)}) ===")
        if not settings.domains:
            print("  No approved email domains configured.")
        else:
            print(f"  {'DOMAIN':30s} {'ADDED TIME':30s} {'ADDED BY':30s}")
            print("  " + "-" * 90)
            for d in settings.domains:
                print(f"  {d.domain:30s} {d.added_time:30s} {d.added_by:30s}")
        print()
    except Exception as e:
        print(f"Error fetching managed domain settings: {e}", file=sys.stderr)
        sys.exit(1)


def run_feed_cli(args):
    engine = SecOpsEngine()
    if args.feed_action == "list":
        query = args.query
        source = args.source
        log_type = args.log_type
        state = args.state
        limit = args.limit

        print(f"\n[CLI] Searching Ingestion Feeds (query='{query}', source='{source}', log_type='{log_type}', state='{state}')...")
        try:
            batch = engine.search_feeds(
                query=query,
                feed_source_type=source,
                log_type=log_type,
                state=state,
                limit=limit,
            )
            print(f"\n=== INGESTION FEEDS (Showing {len(batch.feeds)} of {batch.total_count}) ===")
            if not batch.feeds:
                print("  No feeds matched search criteria.")
            else:
                print(f"  {'FEED ID':38s} {'STATE':10s} {'SOURCE TYPE':20s} {'LOG TYPE':20s} {'DISPLAY NAME'}")
                print("  " + "-" * 110)
                for f in batch.feeds:
                    print(f"  {f.id:38s} {f.state:10s} {f.feed_source_type:20s} {f.log_type:20s} {f.display_name}")
            print()
        except Exception as e:
            print(f"Error listing feeds: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.feed_action == "get":
        target = args.identifier
        print(f"\n[CLI] Retrieving Feed: '{target}'...")
        try:
            detail = engine.get_feed(target)
            f = detail.summary
            print(f"\n=== FEED: {f.display_name} ===")
            print(f"  ID               : {f.id}")
            print(f"  Name             : {f.name}")
            print(f"  State            : {f.state}")
            print(f"  Feed Source Type : {f.feed_source_type}")
            print(f"  Log Type         : {f.log_type}")
            print(f"  Reference ID     : {f.reference_id}")

            if detail.details:
                print("\n--- Source Configuration Details ---")
                for k, v in detail.details.items():
                    if not isinstance(v, (dict, list)):
                        print(f"  {k:20s}: {v}")
            print()
        except Exception as e:
            print(f"Error fetching feed: {e}", file=sys.stderr)
            sys.exit(1)


def run_pipeline_cli(args):
    engine = SecOpsEngine()
    if args.pipeline_action == "list":
        query = args.query
        log_type = args.log_type
        limit = args.limit

        print(f"\n[CLI] Searching Data Processing Pipelines (query='{query}', log_type='{log_type}')...")
        try:
            batch = engine.search_log_processing_pipelines(
                query=query,
                log_type=log_type,
                limit=limit,
            )
            print(f"\n=== LOG PROCESSING PIPELINES (Showing {len(batch.pipelines)} of {batch.total_count}) ===")
            if not batch.pipelines:
                print("  No pipelines matched search criteria.")
            else:
                print(f"  {'PIPELINE ID':38s} {'PROCS':6s} {'STREAMS':25s} {'DISPLAY NAME'}")
                print("  " + "-" * 100)
                for p in batch.pipelines:
                    streams_str = ", ".join(p.streams)[:24]
                    print(f"  {p.id:38s} {p.processors_count:<6d} {streams_str:25s} {p.display_name}")
            print()
        except Exception as e:
            print(f"Error listing pipelines: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.pipeline_action == "get":
        target = args.identifier
        print(f"\n[CLI] Retrieving Pipeline: '{target}'...")
        try:
            detail = engine.get_log_processing_pipeline(target)
            p = detail.summary
            print(f"\n=== PIPELINE: {p.display_name} ===")
            print(f"  ID               : {p.id}")
            print(f"  Name             : {p.name}")
            print(f"  Description      : {p.description}")
            print(f"  Streams          : {', '.join(p.streams)}")
            print(f"  Processors Count : {p.processors_count}")
            print(f"  Bindplane Link   : {p.bindplane_url or 'N/A'}")
            print(f"  Created          : {p.create_time}")
            print(f"  Updated          : {p.update_time}")

            if detail.processors:
                print("\n--- Pipeline Processors & Transforms ---")
                for i, proc in enumerate(detail.processors, 1):
                    proc_type = proc.get("processorType", "UNKNOWN")
                    desc = proc.get("description", "")
                    print(f"  [{i}] Type: {proc_type} ({desc})")
            print()
        except Exception as e:
            print(f"Error fetching pipeline: {e}", file=sys.stderr)
            sys.exit(1)


def run_feed_schema_cli(args):
    engine = SecOpsEngine()
    if args.schema_action == "sources":
        limit = args.limit
        print(f"\n[CLI] Listing Feed Source Type Schemas...")
        try:
            batch = engine.list_feed_source_type_schemas(limit=limit)
            print(f"\n=== FEED SOURCE TYPES (Showing {len(batch.source_types)} of {batch.total_count}) ===")
            print(f"  {'SOURCE TYPE':28s} {'DISPLAY NAME':35s} {'DESCRIPTION'}")
            print("  " + "-" * 100)
            for s in batch.source_types:
                desc = s.description.replace("\n", " ")[:35]
                print(f"  {s.feed_source_type:28s} {s.display_name:35s} {desc}")
            print()
        except Exception as e:
            print(f"Error listing feed source schemas: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.schema_action == "log-types":
        source_type = args.source_type
        limit = args.limit
        include_field_schemas = args.include_field_schemas
        print(f"\n[CLI] Listing Log Type Schemas for Source: '{source_type}'...")
        try:
            batch = engine.list_feed_log_type_schemas(
                feed_source_type=source_type,
                limit=limit,
                include_field_schemas=include_field_schemas,
            )
            print(f"\n=== LOG TYPES FOR {batch.feed_source_type} (Showing {len(batch.log_types)} of {batch.total_count}) ===")
            print(f"  {'LOG TYPE':28s} {'FIELDS':8s} {'DISPLAY NAME'}")
            print("  " + "-" * 80)
            for lt in batch.log_types:
                print(f"  {lt.log_type:28s} {lt.details_field_schemas_count:<8d} {lt.display_name}")
            print()
        except Exception as e:
            print(f"Error listing log type schemas: {e}", file=sys.stderr)
            sys.exit(1)


def run_parser_cli(args):
    engine = SecOpsEngine()
    if args.parser_action == "list":
        query = args.query
        log_type = args.log_type
        creator = args.creator
        state = args.state
        limit = args.limit

        print(f"\n[CLI] Searching SIEM Parsers (log_type='{log_type}', creator='{creator}', state='{state}', query='{query}')...")
        try:
            batch = engine.search_parsers(
                log_type=log_type,
                creator=creator,
                state=state,
                query=query,
                limit=limit,
            )
            print(f"\n=== SIEM PARSERS (Showing {len(batch.parsers)} of {batch.total_count}) ===")
            if not batch.parsers:
                print("  No parsers matched search criteria.")
            else:
                print(f"  {'LOG TYPE':28s} {'STATE':10s} {'CREATOR':10s} {'VERSION':10s} {'PARSER ID'}")
                print("  " + "-" * 90)
                for p in batch.parsers:
                    print(f"  {p.log_type:28s} {p.state:10s} {p.creator_source:10s} {p.version:10s} {p.id}")
            print()
        except Exception as e:
            print(f"Error listing parsers: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.parser_action == "get":
        log_type = args.log_type
        parser_id = args.parser_id
        show_cbn = args.show_cbn

        target_desc = f"{log_type}/{parser_id}" if parser_id else f"{log_type} (active/latest)"
        print(f"\n[CLI] Retrieving Parser: '{target_desc}'...")
        try:
            detail = engine.get_parser(log_type=log_type, parser_id=parser_id)
            p = detail.summary
            print(f"\n=== PARSER: {p.log_type} ===")
            print(f"  ID             : {p.id}")
            print(f"  Name           : {p.name}")
            print(f"  Log Type       : {p.log_type}")
            print(f"  Creator        : {p.creator_source}")
            print(f"  Type           : {p.type}")
            print(f"  State          : {p.state}")
            print(f"  Release Stage  : {p.release_stage}")
            print(f"  Version        : {p.version}")
            print(f"  Latest Version : {p.latest_version}")
            print(f"  Rollback Avail : {p.rollback_available}")
            print(f"  Created At     : {p.create_time}")

            if detail.cbn_code:
                print(f"\n--- Decoded Logstash CBN Filter Code ({len(detail.cbn_code)} chars) ---")
                if show_cbn:
                    print(detail.cbn_code)
                else:
                    lines = detail.cbn_code.strip().split("\n")
                    preview = "\n".join(lines[:12])
                    print(preview)
                    if len(lines) > 12:
                        print(f"  [... {len(lines) - 12} additional lines hidden. Use --show-cbn to view full definition ...]")
            elif detail.cbn_raw:
                print(f"\n  CBN Raw Size   : {len(detail.cbn_raw)} base64 chars")
            print()
        except Exception as e:
            print(f"Error retrieving parser: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.parser_action == "log-types":
        query = args.query
        limit = args.limit
        print(f"\n[CLI] Listing Ingestion Log Types Catalog (query='{query}')...")
        try:
            batch = engine.list_log_types(query=query, limit=limit)
            print(f"\n=== LOG TYPES CATALOG (Showing {len(batch.log_types)} of {batch.total_count}) ===")
            print(f"  {'LOG TYPE ID':32s} {'DISPLAY NAME'}")
            print("  " + "-" * 75)
            for lt in batch.log_types:
                print(f"  {lt.id:32s} {lt.display_name}")
            print()
        except Exception as e:
            print(f"Error listing log types: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.parser_action == "extensions":
        query = args.query
        log_type = args.log_type
        limit = args.limit
        print(f"\n[CLI] Searching Parser Extensions (log_type='{log_type}', query='{query}')...")
        try:
            batch = engine.search_parser_extensions(log_type=log_type, query=query, limit=limit)
            print(f"\n=== PARSER EXTENSIONS (Showing {len(batch.parser_extensions)} of {batch.total_count}) ===")
            if not batch.parser_extensions:
                print("  No parser extensions found.")
            else:
                print(f"  {'LOG TYPE':28s} {'STATE':10s} {'DYNAMIC':10s} {'SNIPPET':10s} {'EXTENSION ID'}")
                print("  " + "-" * 90)
                for ext in batch.parser_extensions:
                    dyn_str = f"YES ({ext.opted_fields_count})" if ext.has_dynamic_parsing else "NO"
                    snip_str = "YES" if ext.has_cbn_snippet else "NO"
                    print(f"  {ext.log_type:28s} {ext.state:10s} {dyn_str:10s} {snip_str:10s} {ext.id}")
            print()
        except Exception as e:
            print(f"Error searching parser extensions: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.parser_action == "extension-get":
        log_type = args.log_type
        extension_id = args.extension_id
        show_snippet = args.show_snippet
        show_log = args.show_log

        print(f"\n[CLI] Retrieving Parser Extension: '{extension_id}' for log type '{log_type}'...")
        try:
            detail = engine.get_parser_extension(log_type=log_type, extension_id=extension_id)
            ext = detail.summary
            print(f"\n=== PARSER EXTENSION: {ext.log_type} / {ext.id} ===")
            print(f"  ID               : {ext.id}")
            print(f"  Log Type         : {ext.log_type}")
            print(f"  State            : {ext.state}")
            print(f"  Created At       : {ext.create_time}")
            print(f"  Last Changed     : {ext.state_last_changed_time}")
            print(f"  Last Live Time   : {ext.last_live_time or 'N/A'}")
            print(f"  Dynamic Parsing  : {ext.has_dynamic_parsing} ({ext.opted_fields_count} opted fields)")
            print(f"  CBN Snippet      : {ext.has_cbn_snippet}")

            if detail.opted_fields:
                print("\n--- Dynamic Parsing Opted Fields ---")
                for f in detail.opted_fields[:10]:
                    path = f.get("path", "")
                    sample = f.get("sampleValue", "")
                    print(f"  - {path:30s}: {sample[:40]}")
                if len(detail.opted_fields) > 10:
                    print(f"  [... {len(detail.opted_fields) - 10} additional opted fields hidden ...]")

            if detail.cbn_snippet:
                print(f"\n--- Decoded Logstash Extension Snippet ---")
                if show_snippet:
                    print(detail.cbn_snippet)
                else:
                    lines = detail.cbn_snippet.strip().split("\n")
                    preview = "\n".join(lines[:8])
                    print(preview)
                    if len(lines) > 8:
                        print(f"  [... {len(lines) - 8} additional snippet lines hidden. Use --show-snippet to view ...]")

            if detail.sample_log:
                print(f"\n--- Decoded Sample Validation Log ---")
                if show_log:
                    print(detail.sample_log)
                else:
                    lines = detail.sample_log.strip().split("\n")
                    preview = "\n".join(lines[:6])
                    print(preview)
                    if len(lines) > 6:
                        print(f"  [... {len(lines) - 6} additional log lines hidden. Use --show-log to view ...]")
            print()
        except Exception as e:
            print(f"Error retrieving parser extension: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.parser_action == "setting":
        log_type = args.log_type
        print(f"\n[CLI] Retrieving Parser Settings for Log Type: '{log_type}'...")
        try:
            setting = engine.get_log_type_setting(log_type=log_type)
            print(f"\n=== PARSER SETTING: {setting.log_type} ===")
            print(f"  Log Type                        : {setting.log_type}")
            print(f"  Autonomous Parsing Extraction   : {setting.autonomous_parsing_extraction_type}")
            if setting.raw_settings:
                print(f"  Raw Config                      : {setting.raw_settings}")
            print()
        except Exception as e:
            print(f"Error retrieving parser setting: {e}", file=sys.stderr)
            sys.exit(1)


def run_preview_cli(args):
    engine = SecOpsEngine()
    if args.preview_action == "list":
        query = args.query
        enabled_only = args.enabled_only
        limit = args.limit

        filter_desc = f"enabled_only={enabled_only}"
        if query:
            filter_desc += f", query='{query}'"
        print(f"\n[CLI] Listing Tenant Preview Features ({filter_desc})...")
        try:
            batch = engine.list_preview_features(
                enabled_only=enabled_only,
                query=query,
                limit=limit,
            )
            print(f"\n=== PREVIEW FEATURES (Showing {len(batch.features)} of {batch.total_count}, Enabled: {batch.enabled_count}) ===")
            if not batch.features:
                print("  No preview features matched search criteria.")
            else:
                print(f"  {'FEATURE ID':40s} {'ENABLED':8s} {'STAGE':30s} {'DISPLAY NAME'}")
                print("  " + "-" * 110)
                for f in batch.features:
                    en_str = "YES" if f.enabled else "NO"
                    print(f"  {f.id:40s} {en_str:8s} {f.stage:30s} {f.display_name}")
            print()
        except Exception as e:
            print(f"Error listing preview features: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.preview_action == "get":
        target = args.feature_id
        print(f"\n[CLI] Retrieving Preview Feature: '{target}'...")
        try:
            f = engine.get_preview_feature(target)
            print(f"\n=== PREVIEW FEATURE: {f.display_name} ===")
            print(f"  ID                  : {f.id}")
            print(f"  Name                : {f.name}")
            print(f"  Display Name        : {f.display_name}")
            print(f"  Enabled             : {f.enabled}")
            print(f"  Stage               : {f.stage}")
            print(f"  Public Doc Link     : {f.public_documentation_link or 'N/A'}")
            if f.expected_retirement_date:
                r_date = f"{f.expected_retirement_date.get('year')}-{f.expected_retirement_date.get('month'):02d}-{f.expected_retirement_date.get('day'):02d}"
                print(f"  Retirement Date     : {r_date}")
            print(f"  Update Time         : {f.update_time or 'N/A'}")
            print(f"  Description         : {f.description}")
            print()
        except Exception as e:
            print(f"Error fetching preview feature: {e}", file=sys.stderr)
            sys.exit(1)


def run_rbac_cli(args):
    engine = SecOpsEngine()
    if args.rbac_action == "scopes":
        query = args.query
        limit = args.limit
        print(f"\n[CLI] Searching Data Access Scopes (query='{query}')...")
        try:
            batch = engine.search_data_access_scopes(query=query, limit=limit)
            print(f"\n=== DATA ACCESS SCOPES (Showing {len(batch.scopes)} of {batch.total_count}, Global Granted: {batch.global_scope_granted}) ===")
            if not batch.scopes:
                print("  No data access scopes matched search criteria.")
            else:
                print(f"  {'SCOPE ID':28s} {'ALLOW ALL':10s} {'ALLOWED':8s} {'DENIED':8s} {'DISPLAY NAME'}")
                print("  " + "-" * 90)
                for s in batch.scopes:
                    allow_all_str = "YES" if s.allow_all else "NO"
                    print(f"  {s.id:28s} {allow_all_str:10s} {s.allowed_labels_count:<8d} {s.denied_labels_count:<8d} {s.display_name}")
            print()
        except Exception as e:
            print(f"Error listing data access scopes: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.rbac_action == "scope-get":
        target = args.scope_id
        print(f"\n[CLI] Retrieving Data Access Scope: '{target}'...")
        try:
            detail = engine.get_data_access_scope(target)
            s = detail.summary
            print(f"\n=== DATA ACCESS SCOPE: {s.display_name} ===")
            print(f"  ID                  : {s.id}")
            print(f"  Name                : {s.name}")
            print(f"  Display Name        : {s.display_name}")
            print(f"  Allow All           : {s.allow_all}")
            print(f"  Author              : {s.author}")
            print(f"  Last Editor         : {s.last_editor}")
            print(f"  Create Time         : {s.create_time}")
            print(f"  Update Time         : {s.update_time}")
            print(f"  Description         : {s.description}")

            if detail.allowed_data_access_labels:
                print("\n--- Allowed Data Access Labels ---")
                for lbl in detail.allowed_data_access_labels:
                    disp = lbl.get("displayName", "")
                    ingest = lbl.get("ingestionLabel", {})
                    ing_str = f" [Ingestion: {ingest.get('ingestionLabelKey')}={ingest.get('ingestionLabelValue')}]" if ingest else ""
                    print(f"  - {disp}{ing_str}")

            if detail.denied_data_access_labels:
                print("\n--- Denied Data Access Labels ---")
                for lbl in detail.denied_data_access_labels:
                    disp = lbl.get("displayName", "")
                    print(f"  - {disp}")
            print()
        except Exception as e:
            print(f"Error fetching data access scope: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.rbac_action == "labels":
        query = args.query
        limit = args.limit
        print(f"\n[CLI] Searching Data Access Labels (query='{query}')...")
        try:
            batch = engine.search_data_access_labels(query=query, limit=limit)
            print(f"\n=== DATA ACCESS LABELS (Showing {len(batch.labels)} of {batch.total_count}) ===")
            if not batch.labels:
                print("  No data access labels matched search criteria.")
            else:
                print(f"  {'LABEL ID':28s} {'DISPLAY NAME':28s} {'UDM QUERY'}")
                print("  " + "-" * 100)
                for l in batch.labels:
                    q_single = l.udm_query.replace("\n", " ")[:40]
                    print(f"  {l.id:28s} {l.display_name:28s} {q_single}")
            print()
        except Exception as e:
            print(f"Error listing data access labels: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.rbac_action == "label-get":
        target = args.label_id
        print(f"\n[CLI] Retrieving Data Access Label: '{target}'...")
        try:
            detail = engine.get_data_access_label(target)
            l = detail.summary
            print(f"\n=== DATA ACCESS LABEL: {l.display_name} ===")
            print(f"  ID                  : {l.id}")
            print(f"  Name                : {l.name}")
            print(f"  Display Name        : {l.display_name}")
            print(f"  Author              : {l.author}")
            print(f"  Last Editor         : {l.last_editor}")
            print(f"  Create Time         : {l.create_time}")
            print(f"  Update Time         : {l.update_time}")
            print(f"  Description         : {l.description}")
            print(f"\n--- UDM Filter Query ---")
            print(l.udm_query)
            print()
        except Exception as e:
            print(f"Error fetching data access label: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.rbac_action == "environments":
        query = args.query
        limit = args.limit
        print(f"\n[CLI] Searching SOAR Multi-Tenant Environments (query='{query}')...")
        try:
            batch = engine.search_environment_scopes(query=query, limit=limit)
            print(f"\n=== SOAR ENVIRONMENTS & DATA RBAC SCOPES (Showing {len(batch.environments)} of {batch.total_count}) ===")
            if not batch.environments:
                print("  No environments matched search criteria.")
            else:
                print(f"  {'ENV ID':10s} {'DISPLAY NAME':25s} {'DATA ACCESS SCOPES':35s} {'CONTACT'}")
                print("  " + "-" * 100)
                for env in batch.environments:
                    scopes_str = ", ".join(env.data_access_scopes) if env.data_access_scopes else "[] (Global/Default)"
                    print(f"  {env.id:10s} {env.display_name:25s} {scopes_str:35s} {env.contact or 'N/A'}")
            print()
        except Exception as e:
            print(f"Error listing environments: {e}", file=sys.stderr)
            sys.exit(1)


def run_enrichment_cli(args):
    engine = SecOpsEngine()
    if args.enrichment_action == "combinations":
        etype = args.enrichment_type
        target_lt = args.target_log_type
        limit = args.limit

        filter_desc = f"type={etype}"
        if target_lt:
            filter_desc += f", target_log_type='{target_lt}'"
        print(f"\n[CLI] Listing Enrichment Combinations ({filter_desc})...")
        try:
            batch = engine.list_enrichment_combinations(
                enrichment_type=etype,
                target_log_type=target_lt,
                limit=limit,
            )
            print(f"\n=== ENRICHMENT COMBINATIONS (Showing {len(batch.records)} of {batch.total_count}) ===")
            if not batch.records:
                print("  No enrichment combinations matched search criteria.")
            else:
                print(f"  {'ENRICHMENT TYPE':36s} {'TARGET LOG TYPE':28s} {'SOURCE LOG / SERVICE'}")
                print("  " + "-" * 100)
                for r in batch.records:
                    src_str = r.external_source or r.source_log_type or "N/A"
                    print(f"  {r.enrichment_type:36s} {r.target_log_type:28s} {src_str}")
            print()
        except Exception as e:
            print(f"Error listing enrichment combinations: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.enrichment_action == "controls":
        query = args.query
        etype = args.type
        limit = args.limit

        print(f"\n[CLI] Searching Deployed Enrichment Controls (query='{query}', type={etype})...")
        try:
            batch = engine.search_enrichment_controls(
                query=query,
                enrichment_type=etype,
                limit=limit,
            )
            print(f"\n=== DEPLOYED ENRICHMENT CONTROLS (Showing {len(batch.controls)} of {batch.total_count}) ===")
            if not batch.controls:
                print("  No deployed enrichment controls found.")
            else:
                print(f"  {'CONTROL ID':40s} {'TYPE':28s} {'TARGET LOG TYPE':24s} {'TIMING RECORDS'}")
                print("  " + "-" * 110)
                for c in batch.controls:
                    print(f"  {c.id:40s} {c.enrichment_type:28s} {c.target_log_type:24s} {c.records_count} record(s)")
            print()
        except Exception as e:
            print(f"Error listing enrichment controls: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.enrichment_action == "control-get":
        target = args.control_id
        print(f"\n[CLI] Retrieving Deployed Enrichment Control: '{target}'...")
        try:
            detail = engine.get_enrichment_control(target)
            c = detail.summary
            print(f"\n=== ENRICHMENT CONTROL: {c.id} ===")
            print(f"  Name                : {c.name}")
            print(f"  Enrichment Type     : {c.enrichment_type}")
            print(f"  Target Log Type     : {c.target_log_type}")
            print(f"  Source              : {c.source}")
            print(f"  Description         : {c.description or 'N/A'}")
            print(f"  Timing Records      : {len(detail.records)}")
            for idx, rec in enumerate(detail.records, 1):
                tr = rec.get("timeRange", {})
                print(f"    [{idx}] Start: {tr.get('startTime', 'N/A')}, End: {tr.get('endTime', 'N/A')}")
                if rec.get("description"):
                    print(f"        Description: {rec.get('description')}")
            print()
        except Exception as e:
            print(f"Error fetching enrichment control: {e}", file=sys.stderr)
            sys.exit(1)


def run_siem_cli(args):
    engine = SecOpsEngine()
    if args.siem_action == "agent-settings":
        print(f"\n[CLI] Retrieving Gemini Triage & Investigation Agent Settings...")
        try:
            settings = engine.get_agent_settings()
            print(f"\n=== GEMINI TRIAGE & INVESTIGATION AGENT SETTINGS ===")
            print(f"  Name                        : {settings.name}")
            print(f"  Auto Investigation Enabled  : {'YES' if settings.auto_investigation_enabled else 'NO'}")
            print(f"  Alert Filter Expression     : {settings.alert_filter or 'N/A'}")
            print(f"  Auto Investigation Delay    : {settings.auto_investigation_delay or 'N/A'}")
            print(f"  Auto Quota Limit            : {settings.auto_quota_limit or 'N/A'}")
            print(f"  Manual Quota Limit          : {settings.manual_quota_limit or 'N/A'}")
            print()
        except Exception as e:
            print(f"Error retrieving agent settings: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.siem_action == "risk-config":
        print(f"\n[CLI] Retrieving UEBA Entity Risk Scoring Configuration...")
        try:
            risk = engine.get_entity_risk_config()
            print(f"\n=== ENTITY RISK SCORING CONFIGURATION ===")
            print(f"  Name                        : {risk.name}")
            print(f"  Default Detection Risk Score: {risk.default_detection_risk_score}")
            print(f"  Default Alert Risk Score    : {risk.default_alert_risk_score}")
            print(f"  Default Weighting Factor    : {risk.default_weighting_factor}")
            print(f"  Default Closed Alert Coeff  : {risk.default_closed_alert_coefficient}")
            print()
        except Exception as e:
            print(f"Error retrieving entity risk config: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.siem_action == "tenant":
        print(f"\n[CLI] Retrieving Root Tenant Instance Details...")
        try:
            tenant = engine.get_tenant_instance()
            print(f"\n=== SEC OPS TENANT INSTANCE: {tenant.customer_code} ===")
            print(f"  ID                          : {tenant.id}")
            print(f"  Name                        : {tenant.name}")
            print(f"  State                       : {tenant.state}")
            print(f"  Customer Code               : {tenant.customer_code}")
            print(f"  Display Name                : {tenant.display_name or 'N/A'}")
            print(f"  Create Time                 : {tenant.create_time or 'N/A'}")
            print(f"  SecOps UI Enabled           : {'YES' if tenant.secops_ui_enabled else 'NO'}")
            print(f"  Data RBAC Enabled           : {'YES' if tenant.data_rbac_enabled else 'NO'}")
            print(f"  Triage Agent Enabled        : {'YES' if tenant.triage_agent_enabled else 'NO'}")
            print(f"  SecOps URLs                 : {', '.join(tenant.secops_urls)}")
            if tenant.frontend_paths:
                print(f"  Frontend Path Configs       : {len(tenant.frontend_paths)} configured")
            print()
        except Exception as e:
            print(f"Error retrieving tenant details: {e}", file=sys.stderr)
            sys.exit(1)


def run_soar_users_cli(args):
    engine = SecOpsEngine()
    query = args.query
    role = args.role
    limit = args.limit
    role_str = f"role={role}" if role is not None else "all roles"
    print(f"\n[CLI] Searching SOAR Users (query='{query}', {role_str})...")
    try:
        batch = engine.search_soar_users(query=query, role_filter=role, limit=limit)
        print(f"\n=== SOAR USERS (Showing {len(batch.users)} of {batch.total_count}) ===")
        if not batch.users:
            print("  No users matched search criteria.")
        else:
            print(f"  {'USER ID':10s} {'FULL NAME':26s} {'EMAIL':32s} {'ROLES':15s} {'STATE'}")
            print("  " + "-" * 95)
            for u in batch.users:
                roles_str = str(u.soc_roles) if u.soc_roles else "[]"
                print(f"  {u.id:10s} {u.user_full_name:26s} {u.email:32s} {roles_str:15s} {u.account_state}")
        print()
    except Exception as e:
        print(f"Error listing SOAR users: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_user_get_cli(args):
    engine = SecOpsEngine()
    target = args.user_id
    print(f"\n[CLI] Retrieving SOAR User Profile: '{target}'...")
    try:
        detail = engine.get_soar_user(target)
        u = detail.summary
        print(f"\n=== SOAR USER: {u.user_full_name} ===")
        print(f"  ID                  : {u.id}")
        print(f"  Name                : {u.name}")
        print(f"  Full Name           : {u.user_full_name}")
        print(f"  First / Last Name   : {u.first_name} {u.last_name}")
        print(f"  Email               : {u.email}")
        print(f"  Login Identifier    : {u.login_identifier}")
        print(f"  Provider Name       : {u.provider_name}")
        print(f"  User Type           : {u.user_type}")
        print(f"  Account State       : {u.account_state}")
        print(f"  SOC Roles           : {u.soc_roles}")
        perm_names = [p.get("name", "") for p in u.permission_groups if isinstance(p, dict)]
        print(f"  Permission Groups   : {', '.join(perm_names) if perm_names else 'None'}")
        print(f"  All Envs Access     : {'YES' if u.has_all_environments_access else 'NO'}")
        print(f"  Environments JSON   : {detail.environments_json or '[]'}")
        print(f"  Allowed Platforms   : {', '.join(detail.allowed_platforms) if detail.allowed_platforms else 'None'}")
        print()
    except Exception as e:
        print(f"Error fetching SOAR user: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_roles_cli(args):
    engine = SecOpsEngine()
    limit = args.limit
    print(f"\n[CLI] Listing SOAR SOC Roles...")
    try:
        batch = engine.list_soc_roles(limit=limit)
        print(f"\n=== SOAR SOC ROLES ({len(batch.roles)}) ===")
        if not batch.roles:
            print("  No SOC roles configured.")
        else:
            print(f"  {'ROLE ID':10s} {'DISPLAY NAME':28s} {'ADDITIONAL ROLES ACCESS'}")
            print("  " + "-" * 75)
            for r in batch.roles:
                add_str = ", ".join(r.additional_roles_access) if r.additional_roles_access else "None"
                print(f"  {r.id:10s} {r.display_name:28s} {add_str}")
        print()
    except Exception as e:
        print(f"Error listing SOC roles: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_company_cli(args):
    engine = SecOpsEngine()
    print(f"\n[CLI] Retrieving SOAR Company Rebranding & Reporting Settings...")
    try:
        batch = engine.get_company_settings()
        print(f"\n=== SOAR COMPANY SETTINGS ({len(batch.properties)} properties) ===")
        if not batch.properties:
            print("  No company settings returned.")
        else:
            print(f"  {'PROPERTY KEY':35s} {'DISPLAY NAME':35s} {'VALUE'}")
            print("  " + "-" * 95)
            for p in batch.properties:
                print(f"  {p.property_key:35s} {p.display_name:35s} {p.value}")
        print()
    except Exception as e:
        print(f"Error retrieving company settings: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_retention_cli(args):
    engine = SecOpsEngine()
    print(f"\n[CLI] Retrieving SOAR Data Retention & Environment Policy Settings...")
    try:
        batch = engine.get_data_retention_settings()
        print(f"\n=== SOAR DATA RETENTION SETTINGS ({len(batch.properties)} properties) ===")
        if not batch.properties:
            print("  No data retention settings returned.")
        else:
            print(f"  {'PROPERTY KEY':38s} {'DISPLAY NAME':35s} {'VALUE'}")
            print("  " + "-" * 95)
            for p in batch.properties:
                print(f"  {p.property_key:38s} {p.display_name:35s} {p.value}")
        print()
    except Exception as e:
        print(f"Error retrieving data retention settings: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_environments_cli(args):
    engine = SecOpsEngine()
    query = args.query
    limit = args.limit
    print(f"\n[CLI] Searching Multi-Tenancy Environments (query='{query}', limit={limit})...")
    try:
        batch = engine.search_environments(query=query, limit=limit)
        print(f"\n=== SOAR ENVIRONMENTS (Showing {len(batch.environments)} of {batch.total_count}) ===")
        if not batch.environments:
            print("  No environments matched criteria.")
        else:
            print(f"  {'ID / RESOURCE NAME':30s} {'DISPLAY NAME':25s} {'SYSTEM':8s} {'RETENTION':12s} {'ALIASES'}")
            print("  " + "-" * 105)
            for env in batch.environments:
                sys_str = "YES" if env.system else "NO"
                ret_str = f"{env.retention_duration} days" if env.retention_duration else "DEFAULT"
                aliases_str = ", ".join(env.aliases) if env.aliases else "None"
                print(f"  {env.id:30s} {env.display_name:25s} {sys_str:8s} {ret_str:12s} {aliases_str}")
        print()
    except Exception as e:
        print(f"Error searching environments: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_environment_get_cli(args):
    engine = SecOpsEngine()
    env_id = args.env_id
    print(f"\n[CLI] Retrieving Environment: '{env_id}'...")
    try:
        detail = engine.get_environment(env_id)
        env = detail.summary
        print(f"\n=== SOAR ENVIRONMENT: {env.display_name} ({env.id}) ===")
        print(f"  ID                  : {env.id}")
        print(f"  Resource Name       : {env.name}")
        print(f"  Display Name        : {env.display_name}")
        print(f"  System Environment  : {'YES' if env.system else 'NO'}")
        print(f"  Retention Duration  : {env.retention_duration} days")
        print(f"  Weight              : {env.weight}")
        if env.aliases:
            print(f"  Aliases ({len(env.aliases)}):")
            for a in env.aliases:
                print(f"    - {a}")
        else:
            print("  Aliases             : None")
        if env.data_access_scopes:
            print(f"  Data Access Scopes ({len(env.data_access_scopes)}):")
            for s in env.data_access_scopes:
                print(f"    - {s}")
        else:
            print("  Data Access Scopes  : None")
        print()
    except Exception as e:
        print(f"Error retrieving environment: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_environment_groups_cli(args):
    engine = SecOpsEngine()
    query = args.query
    limit = args.limit
    print(f"\n[CLI] Searching Environment Groups (query='{query}', limit={limit})...")
    try:
        batch = engine.search_environment_groups(query=query, limit=limit)
        print(f"\n=== SOAR ENVIRONMENT GROUPS (Showing {len(batch.groups)} of {batch.total_count}) ===")
        if not batch.groups:
            print("  No environment groups matched criteria.")
        else:
            print(f"  {'GROUP ID':30s} {'DISPLAY NAME':30s} {'BOUND ENVIRONMENTS'}")
            print("  " + "-" * 95)
            for g in batch.groups:
                envs_str = ", ".join(g.environments) if g.environments else "None"
                print(f"  {g.id:30s} {g.display_name:30s} {envs_str}")
        print()
    except Exception as e:
        print(f"Error searching environment groups: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_remote_agents_cli(args):
    engine = SecOpsEngine()
    query = args.query
    environment = args.env
    agent_state = args.state
    limit = args.limit
    print(f"\n[CLI] Searching Remote SOAR Agents (query='{query}', env='{environment}', state='{agent_state}', limit={limit})...")
    try:
        batch = engine.search_remote_agents(
            query=query,
            environment=environment,
            agent_state=agent_state,
            limit=limit,
        )
        print(f"\n=== REMOTE SOAR AGENTS (Showing {len(batch.remote_agents)} of {batch.total_count}) ===")
        if not batch.remote_agents:
            print("  No remote agents matched criteria.")
        else:
            print(f"  {'ID':20s} {'DISPLAY NAME':22s} {'STATE':10s} {'LOGGING':10s} {'IDENTIFIER':38s} {'ENVIRONMENTS'}")
            print("  " + "-" * 125)
            for a in batch.remote_agents:
                envs_str = ", ".join(a.environments) if a.environments else "None"
                print(f"  {a.id:20s} {a.display_name:22s} {a.agent_state:10s} {a.logging_level:10s} {a.identifier:38s} {envs_str}")
        print()
    except Exception as e:
        print(f"Error searching remote agents: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_remote_agent_get_cli(args):
    engine = SecOpsEngine()
    agent_id = args.agent_id
    print(f"\n[CLI] Retrieving Remote Agent: '{agent_id}'...")
    try:
        detail = engine.get_remote_agent(agent_id)
        a = detail.summary
        print(f"\n=== REMOTE SOAR AGENT: {a.display_name} ({a.id}) ===")
        print(f"  ID                  : {a.id}")
        print(f"  Resource Name       : {a.name}")
        print(f"  Display Name        : {a.display_name}")
        print(f"  Identifier / UUID   : {a.identifier}")
        print(f"  Agent State         : {a.agent_state}")
        print(f"  Logging Level       : {a.logging_level}")
        print(f"  Installer Link      : {a.installer_link or 'N/A'}")
        if a.environments:
            print(f"  Bound Environments ({len(a.environments)}):")
            for env in a.environments:
                print(f"    - {env}")
        else:
            print("  Bound Environments  : None")
        if detail.certificate:
            cert_lines = detail.certificate.strip().splitlines()
            print(f"  Certificate         : Present ({len(cert_lines)} lines, starts: {cert_lines[0] if cert_lines else ''})")
        else:
            print("  Certificate         : None")
        print()
    except Exception as e:
        print(f"Error retrieving remote agent: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_email_settings_cli(args):
    engine = SecOpsEngine()
    print(f"\n[CLI] Retrieving SOAR Email Transport Configuration...")
    try:
        batch = engine.get_email_settings()
        mode_str = "Custom SMTP Server" if batch.use_custom else "Google Default SMTP Server"
        print(f"\n=== SOAR EMAIL SETTINGS (Transport: {mode_str}) ===")
        print(f"  Use Custom SMTP     : {'YES' if batch.use_custom else 'NO'}")
        print(f"\n  {'PROPERTY KEY':30s} {'DISPLAY NAME':30s} {'VALUE'}")
        print("  " + "-" * 85)
        for p in batch.properties:
            # Mask passwords for CLI display
            val = "********" if "password" in p.property_key.lower() and p.value else p.value
            print(f"  {p.property_key:30s} {p.display_name:30s} {val}")
        print()
    except Exception as e:
        print(f"Error retrieving email settings: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_support_settings_cli(args):
    engine = SecOpsEngine()
    print(f"\n[CLI] Retrieving Google Support Access Delegation Parameters...")
    try:
        batch = engine.get_support_settings()
        print(f"\n=== GOOGLE SUPPORT ACCESS SETTINGS ({len(batch.properties)} properties) ===")
        if not batch.properties:
            print("  No support access settings returned.")
        else:
            print(f"  {'PROPERTY KEY':25s} {'DISPLAY NAME':30s} {'VALUE'}")
            print("  " + "-" * 85)
            for p in batch.properties:
                print(f"  {p.property_key:25s} {p.display_name:30s} {p.value}")
        print()
    except Exception as e:
        print(f"Error retrieving support settings: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_networks_cli(args):
    engine = SecOpsEngine()
    query = args.query
    environment = args.env
    limit = args.limit
    print(f"\n[CLI] Searching SOAR Networks (query='{query}', env='{environment}', limit={limit})...")
    try:
        batch = engine.search_soar_networks(query=query, environment=environment, limit=limit)
        print(f"\n=== SOAR NETWORKS (Showing {len(batch.networks)} of {batch.total_count}) ===")
        if not batch.networks:
            print("  No SOAR networks matched criteria.")
        else:
            print(f"  {'ID':6s} {'DISPLAY NAME':28s} {'IP RANGE / CIDR':22s} {'PRIORITY':10s} {'BOUND ENVIRONMENTS'}")
            print("  " + "-" * 95)
            for n in batch.networks:
                envs_str = ", ".join(n.environments) if n.environments else "All / Global"
                print(f"  {n.id:6s} {n.display_name:28s} {n.address:22s} {str(n.priority):10s} {envs_str}")
        print()
    except Exception as e:
        print(f"Error searching SOAR networks: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_network_get_cli(args):
    engine = SecOpsEngine()
    network_id = args.network_id
    print(f"\n[CLI] Retrieving SOAR Network: '{network_id}'...")
    try:
        detail = engine.get_soar_network(network_id)
        n = detail.summary
        print(f"\n=== SOAR NETWORK: {n.display_name} ({n.id}) ===")
        print(f"  ID                  : {n.id}")
        print(f"  Resource Name       : {n.name}")
        print(f"  Display Name        : {n.display_name}")
        print(f"  IP Range / CIDR     : {n.address}")
        print(f"  Priority            : {n.priority}")
        if n.environments:
            print(f"  Bound Environments ({len(n.environments)}):")
            for env in n.environments:
                print(f"    - {env}")
        else:
            print("  Bound Environments  : All / Global")
        print()
    except Exception as e:
        print(f"Error retrieving SOAR network: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_domains_cli(args):
    engine = SecOpsEngine()
    query = args.query
    environment = args.env
    limit = args.limit
    print(f"\n[CLI] Searching SOAR Approved Domains (query='{query}', env='{environment}', limit={limit})...")
    try:
        batch = engine.search_soar_domains(query=query, environment=environment, limit=limit)
        print(f"\n=== SOAR APPROVED DOMAINS (Showing {len(batch.domains)} of {batch.total_count}) ===")
        if not batch.domains:
            print("  No SOAR domains matched criteria.")
        else:
            print(f"  {'ID':6s} {'DOMAIN NAME':36s} {'BOUND ENVIRONMENTS'}")
            print("  " + "-" * 75)
            for d in batch.domains:
                envs_str = ", ".join(d.environments) if d.environments else "All / Global"
                print(f"  {d.id:6s} {d.display_name:36s} {envs_str}")
        print()
    except Exception as e:
        print(f"Error searching SOAR domains: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_domain_get_cli(args):
    engine = SecOpsEngine()
    domain_id = args.domain_id
    print(f"\n[CLI] Retrieving SOAR Approved Domain: '{domain_id}'...")
    try:
        detail = engine.get_soar_domain(domain_id)
        d = detail.summary
        print(f"\n=== SOAR DOMAIN: {d.display_name} ({d.id}) ===")
        print(f"  ID                  : {d.id}")
        print(f"  Resource Name       : {d.name}")
        print(f"  Domain Name         : {d.display_name}")
        if d.environments:
            print(f"  Bound Environments ({len(d.environments)}):")
            for env in d.environments:
                print(f"    - {env}")
        else:
            print("  Bound Environments  : All / Global")
        print()
    except Exception as e:
        print(f"Error retrieving SOAR domain: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_custom_lists_cli(args):
    engine = SecOpsEngine()
    query = args.query
    category = args.category
    environment = args.env
    limit = args.limit
    print(f"\n[CLI] Searching SOAR Custom Lists (query='{query}', category='{category}', env='{environment}', limit={limit})...")
    try:
        batch = engine.search_soar_custom_lists(query=query, category=category, environment=environment, limit=limit)
        print(f"\n=== SOAR CUSTOM LISTS (Showing {len(batch.custom_lists)} of {batch.total_count}) ===")
        if not batch.custom_lists:
            print("  No custom lists matched criteria.")
        else:
            print(f"  {'ID':6s} {'NAME / IDENTIFIER':32s} {'CATEGORY':22s} {'BOUND ENVIRONMENTS'}")
            print("  " + "-" * 95)
            for cl in batch.custom_lists:
                envs_str = ", ".join(cl.environments) if cl.environments else "All / Global"
                print(f"  {cl.id:6s} {cl.entity_identifier:32s} {cl.category:22s} {envs_str}")
        print()
    except Exception as e:
        print(f"Error searching SOAR custom lists: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_custom_list_get_cli(args):
    engine = SecOpsEngine()
    list_id = args.list_id
    print(f"\n[CLI] Retrieving SOAR Custom List: '{list_id}'...")
    try:
        detail = engine.get_soar_custom_list(list_id)
        cl = detail.summary
        print(f"\n=== SOAR CUSTOM LIST: {cl.entity_identifier} ({cl.id}) ===")
        print(f"  ID                  : {cl.id}")
        print(f"  Resource Name       : {cl.name}")
        print(f"  Entity Identifier   : {cl.entity_identifier}")
        print(f"  Category            : {cl.category}")
        if cl.environments:
            print(f"  Bound Environments ({len(cl.environments)}):")
            for env in cl.environments:
                print(f"    - {env}")
        else:
            print("  Bound Environments  : All / Global")
        print()
    except Exception as e:
        print(f"Error retrieving SOAR custom list: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_email_templates_cli(args):
    engine = SecOpsEngine()
    query = args.query
    template_type = args.type
    environment = args.env
    limit = args.limit
    print(f"\n[CLI] Searching Email Templates (query='{query}', type='{template_type}', env='{environment}', limit={limit})...")
    try:
        batch = engine.search_email_templates(query=query, template_type=template_type, environment=environment, limit=limit)
        print(f"\n=== SOAR EMAIL TEMPLATES (Showing {len(batch.email_templates)} of {batch.total_count}) ===")
        if not batch.email_templates:
            print("  No email templates matched criteria.")
        else:
            print(f"  {'ID':6s} {'NAME':36s} {'TYPE':14s} {'AUTHOR':20s} {'BOUND ENVIRONMENTS'}")
            print("  " + "-" * 105)
            for t in batch.email_templates:
                envs_str = ", ".join(t.environments) if t.environments else "All / Global"
                print(f"  {t.id:6s} {t.display_name:36s} {t.template_type:14s} {t.author:20s} {envs_str}")
        print()
    except Exception as e:
        print(f"Error searching email templates: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_email_template_get_cli(args):
    engine = SecOpsEngine()
    template_id = args.template_id
    print(f"\n[CLI] Retrieving Email Template: '{template_id}'...")
    try:
        detail = engine.get_email_template(template_id)
        t = detail.summary
        print(f"\n=== EMAIL TEMPLATE: {t.display_name} ({t.id}) ===")
        print(f"  ID                  : {t.id}")
        print(f"  Resource Name       : {t.name}")
        print(f"  Display Name        : {t.display_name}")
        print(f"  Template Type       : {t.template_type}")
        print(f"  Author              : {t.author}")
        if t.environments:
            print(f"  Bound Environments ({len(t.environments)}):")
            for env in t.environments:
                print(f"    - {env}")
        else:
            print("  Bound Environments  : All / Global")
        if detail.content:
            print(f"\n--- Content Body ({len(detail.content)} bytes) ---")
            lines = detail.content.strip().splitlines()
            for line in lines[:15]:
                print(f"  {line}")
            if len(lines) > 15:
                print(f"  ... ({len(lines) - 15} more lines)")
        print()
    except Exception as e:
        print(f"Error retrieving email template: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_entities_blocklists_cli(args):
    engine = SecOpsEngine()
    query = args.query
    entity_type = args.entity_type
    environment = args.env
    limit = args.limit
    print(f"\n[CLI] Searching Entities Blocklists (query='{query}', entity_type='{entity_type}', env='{environment}', limit={limit})...")
    try:
        batch = engine.search_entities_blocklists(query=query, entity_type=entity_type, environment=environment, limit=limit)
        print(f"\n=== SOAR ENTITIES BLOCKLIST (Showing {len(batch.blocklist_entries)} of {batch.total_count}) ===")
        if not batch.blocklist_entries:
            print("  No entity blocklist entries matched criteria.")
        else:
            print(f"  {'ID':6s} {'ENTITY TYPE':18s} {'VALUE':36s} {'ACTION':22s} {'BOUND ENVIRONMENTS'}")
            print("  " + "-" * 105)
            for eb in batch.blocklist_entries:
                envs_str = ", ".join(eb.environments) if eb.environments else "All / Global"
                print(f"  {eb.id:6s} {eb.entity_type:18s} {eb.entity_identifier:36s} {eb.action:22s} {envs_str}")
        print()
    except Exception as e:
        print(f"Error searching entities blocklists: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_entities_blocklist_get_cli(args):
    engine = SecOpsEngine()
    blocklist_id = args.blocklist_id
    print(f"\n[CLI] Retrieving Entities Blocklist Entry: '{blocklist_id}'...")
    try:
        detail = engine.get_entities_blocklist(blocklist_id)
        eb = detail.summary
        print(f"\n=== ENTITY BLOCKLIST ENTRY: {eb.entity_identifier} ({eb.id}) ===")
        print(f"  ID                  : {eb.id}")
        print(f"  Resource Name       : {eb.name}")
        print(f"  Entity Type         : {eb.entity_type}")
        print(f"  Entity Identifier   : {eb.entity_identifier}")
        print(f"  Action              : {eb.action}")
        if eb.environments:
            print(f"  Bound Environments ({len(eb.environments)}):")
            for env in eb.environments:
                print(f"    - {env}")
        else:
            print("  Bound Environments  : All / Global")
        print()
    except Exception as e:
        print(f"Error retrieving entities blocklist entry: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_sla_definitions_cli(args):
    engine = SecOpsEngine()
    query = args.query
    sla_type = args.sla_type
    environment = args.env
    limit = args.limit
    print(f"\n[CLI] Searching SLA Definitions (query='{query}', sla_type='{sla_type}', env='{environment}', limit={limit})...")
    try:
        batch = engine.search_sla_definitions(query=query, sla_type=sla_type, environment=environment, limit=limit)
        print(f"\n=== SOAR SLA DEFINITIONS (Showing {len(batch.sla_definitions)} of {batch.total_count}) ===")
        if not batch.sla_definitions:
            print("  No SLA definitions matched criteria.")
        else:
            print(f"  {'ID':6s} {'NAME':28s} {'SLA TYPE':16s} {'TYPE VALUES':20s} {'PERIOD':14s} {'BOUND ENVIRONMENTS'}")
            print("  " + "-" * 105)
            for s in batch.sla_definitions:
                period_str = f"{s.sla_period} {s.sla_period_time_unit}" if s.sla_period else "N/A"
                envs_str = ", ".join(s.environments) if s.environments else "All / Global"
                types_str = ", ".join(s.sla_type_values) if s.sla_type_values else "N/A"
                print(f"  {s.id:6s} {s.name:28s} {s.sla_type:16s} {types_str:20s} {period_str:14s} {envs_str}")
        print()
    except Exception as e:
        print(f"Error searching SLA definitions: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_sla_definition_get_cli(args):
    engine = SecOpsEngine()
    sla_id = args.sla_id
    print(f"\n[CLI] Retrieving SLA Definition: '{sla_id}'...")
    try:
        detail = engine.get_sla_definition(sla_id)
        s = detail.summary
        print(f"\n=== SLA DEFINITION: {s.name} ({s.id}) ===")
        print(f"  ID                  : {s.id}")
        print(f"  Resource Name       : {s.name}")
        print(f"  SLA Type            : {s.sla_type}")
        types_str = ", ".join(s.sla_type_values) if s.sla_type_values else "N/A"
        print(f"  SLA Type Values     : {types_str}")
        print(f"  Standard Period     : {s.sla_period} {s.sla_period_time_unit}")
        if s.critical_sla_period:
            print(f"  Critical Period     : {s.critical_sla_period} {s.critical_sla_period_time_unit}")
        if s.environments:
            print(f"  Bound Environments ({len(s.environments)}):")
            for env in s.environments:
                print(f"    - {env}")
        else:
            print("  Bound Environments  : All / Global")
        print()
    except Exception as e:
        print(f"Error retrieving SLA definition: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_request_templates_cli(args):
    engine = SecOpsEngine()
    query = args.query
    environment = args.env
    limit = args.limit
    print(f"\n[CLI] Searching Request Templates (query='{query}', env='{environment}', limit={limit})...")
    try:
        batch = engine.search_request_templates(query=query, environment=environment, limit=limit)
        print(f"\n=== SOAR REQUEST TEMPLATES (Showing {len(batch.request_templates)} of {batch.total_count}) ===")
        if not batch.request_templates:
            print("  No request templates matched criteria.")
        else:
            print(f"  {'ID':6s} {'NAME':30s} {'FIELDS':8s} {'BOUND ENVIRONMENTS':20s} {'VISUAL FAMILY'}")
            print("  " + "-" * 95)
            for rt in batch.request_templates:
                envs_str = ", ".join(rt.environments) if rt.environments else "All / Global"
                print(f"  {rt.id:6s} {rt.display_name:30s} {str(rt.field_count):8s} {envs_str:20s} {rt.visual_family}")
        print()
    except Exception as e:
        print(f"Error searching request templates: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_request_template_get_cli(args):
    engine = SecOpsEngine()
    template_id = args.template_id
    print(f"\n[CLI] Retrieving Request Template: '{template_id}'...")
    try:
        detail = engine.get_request_template(template_id)
        rt = detail.summary
        print(f"\n=== REQUEST TEMPLATE: {rt.display_name} ({rt.id}) ===")
        print(f"  ID                  : {rt.id}")
        print(f"  Resource Name       : {rt.name}")
        print(f"  Display Name        : {rt.display_name}")
        print(f"  Visual Family       : {rt.visual_family}")
        print(f"  Allow Description   : {'YES' if rt.allow_description else 'NO'}")
        if rt.environments:
            print(f"  Bound Environments ({len(rt.environments)}):")
            for env in rt.environments:
                print(f"    - {env}")
        else:
            print("  Bound Environments  : All / Global")
        print(f"\n--- Form Field Definitions ({len(detail.event_field_definitions)}) ---")
        if not detail.event_field_definitions:
            print("  No custom fields defined on template.")
        else:
            print(f"  {'FIELD NAME':25s} {'TYPE':12s} {'WATERMARK / PLACEHOLDER':30s} {'ENTITY TYPES'}")
            print("  " + "-" * 90)
            for f in detail.event_field_definitions:
                et_str = ", ".join(f.entity_types) if f.entity_types else "None"
                print(f"  {f.name:25s} {f.field_type:12s} {f.watermark:30s} {et_str}")
        print()
    except Exception as e:
        print(f"Error retrieving request template: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_ingestion_connectors_cli(args):
    engine = SecOpsEngine()
    query = args.query
    integration = args.integration
    connector_id = args.connector_id
    environment = args.env
    enabled = args.enabled
    limit = args.limit
    print(f"\n[CLI] Searching SOAR Ingestion Connectors (query='{query}', integration='{integration}', connector_id='{connector_id}', env='{environment}', enabled_only={enabled}, limit={limit})...")
    try:
        batch = engine.search_soar_ingestion_connectors(
            query=query,
            integration=integration,
            connector_id=connector_id,
            environment=environment,
            enabled_only=enabled,
            limit=limit,
        )
        print(f"\n=== SOAR INGESTION CONNECTORS (Showing {len(batch.connectors)} of {batch.total_count}) ===")
        if not batch.connectors:
            print("  No ingestion connector instances matched criteria.")
        else:
            print(f"  {'ID':6s} {'DISPLAY NAME':34s} {'INTEGRATION':26s} {'INTERVAL':10s} {'ENABLED':9s} {'REMOTE':8s} {'ENVIRONMENT'}")
            print("  " + "-" * 115)
            for ic in batch.connectors:
                en_str = "YES" if ic.enabled else "NO"
                rem_str = "YES" if ic.remote else "NO"
                int_str = f"{ic.interval_seconds}s" if ic.interval_seconds else "N/A"
                env_str = ic.environment or "All / Global"
                print(f"  {ic.id:6s} {ic.display_name:34s} {ic.integration:26s} {int_str:10s} {en_str:9s} {rem_str:8s} {env_str}")
        print()
    except Exception as e:
        print(f"Error searching ingestion connectors: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_ingestion_connector_get_cli(args):
    engine = SecOpsEngine()
    instance_id = args.instance_id
    integration = args.integration
    connector_id = args.connector_id
    print(f"\n[CLI] Retrieving SOAR Ingestion Connector: '{instance_id}'...")
    try:
        detail = engine.get_soar_ingestion_connector(
            instance_id=instance_id,
            integration=integration,
            connector_id=connector_id,
        )
        c = detail.summary
        print(f"\n=== SOAR INGESTION CONNECTOR: {c.display_name} ({c.id}) ===")
        print(f"  ID                  : {c.id}")
        print(f"  Resource Name       : {c.name}")
        print(f"  Display Name        : {c.display_name}")
        print(f"  Identifier          : {c.identifier}")
        print(f"  Integration         : {c.integration}")
        print(f"  Connector ID        : {c.connector_id}")
        print(f"  Definition Name     : {c.connector_definition_name}")
        print(f"  Environment         : {c.environment or 'All / Global'}")
        print(f"  Enabled             : {'YES' if c.enabled else 'NO'}")
        print(f"  Remote Execution    : {'YES' if c.remote else 'NO'}")
        print(f"  Interval (seconds)  : {c.interval_seconds}")
        print(f"  Timeout (seconds)   : {detail.timeout_seconds or 'N/A'}")
        print(f"  Status              : {detail.status}")
        print(f"  Version             : {detail.version or 'N/A'} (Integration v{detail.integration_version or 'N/A'})")
        print(f"  Product Field Name  : {detail.product_field_name or 'N/A'}")
        print(f"  Event Field Name    : {detail.event_field_name or 'N/A'}")
        if detail.documentation_link:
            print(f"  Documentation Link  : {detail.documentation_link}")
        if detail.description:
            print(f"  Description         : {detail.description}")
        if detail.parameters:
            print(f"\n--- Connector Parameters ({len(detail.parameters)}) ---")
            for idx, p in enumerate(detail.parameters, 1):
                p_name = p.get("name", p.get("displayName", "param"))
                p_val = p.get("value", "<hidden/empty>")
                p_type = p.get("type", "STRING")
                print(f"  [{idx}] {p_name} ({p_type}): {p_val}")
        print()
    except Exception as e:
        print(f"Error retrieving ingestion connector: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_webhooks_cli(args):
    engine = SecOpsEngine()
    query = args.query
    environment = args.env
    enabled = args.enabled
    limit = args.limit
    print(f"\n[CLI] Searching SOAR Event Ingestion Webhooks (query='{query}', env='{environment}', enabled_only={enabled}, limit={limit})...")
    try:
        batch = engine.search_soar_webhooks(
            query=query,
            environment=environment,
            enabled_only=enabled,
            limit=limit,
        )
        print(f"\n=== SOAR INGESTION WEBHOOKS (Showing {len(batch.webhooks)} of {batch.total_count}) ===")
        if not batch.webhooks:
            print("  No ingestion webhooks matched criteria.")
        else:
            print(f"  {'ID':38s} {'DISPLAY NAME':30s} {'ENABLED':9s} {'ENVIRONMENT':20s} {'DESCRIPTION'}")
            print("  " + "-" * 125)
            for wh in batch.webhooks:
                en_str = "YES" if wh.enabled else "NO"
                env_str = wh.environment or "All / Global"
                desc_short = (wh.description[:35] + "...") if len(wh.description) > 35 else wh.description
                print(f"  {wh.id:38s} {wh.display_name:30s} {en_str:9s} {env_str:20s} {desc_short}")
        print()
    except Exception as e:
        print(f"Error searching ingestion webhooks: {e}", file=sys.stderr)
        sys.exit(1)


def run_soar_webhook_get_cli(args):
    engine = SecOpsEngine()
    webhook_id = args.webhook_id
    print(f"\n[CLI] Retrieving SOAR Ingestion Webhook: '{webhook_id}'...")
    try:
        detail = engine.get_soar_webhook(webhook_id)
        wh = detail.summary
        print(f"\n=== SOAR INGESTION WEBHOOK: {wh.display_name} ===")
        print(f"  ID                  : {wh.id}")
        print(f"  Resource Name       : {wh.name}")
        print(f"  Display Name        : {wh.display_name}")
        print(f"  Environment         : {wh.environment or 'All / Global'}")
        print(f"  Enabled             : {'YES' if wh.enabled else 'NO'}")
        if wh.description:
            print(f"  Description         : {wh.description}")
        if detail.postfix:
            print(f"  Ingestion Path      : {detail.postfix}")
        print(f"\n--- Webhook JSON Schema Mapping ({len(detail.webhook_mapping)}) ---")
        if not detail.webhook_mapping:
            print("  No field mappings configured.")
        else:
            print(f"  {'TARGET FIELD':28s} {'EXTRACTION EXPRESSION'}")
            print("  " + "-" * 75)
            for k, v in detail.webhook_mapping.items():
                print(f"  {k:28s} {v}")
        print()
    except Exception as e:
        print(f"Error retrieving ingestion webhook: {e}", file=sys.stderr)
        sys.exit(1)


def run_case_config_cli(args):
    engine = SecOpsEngine()
    if args.config_action == "tags":
        query = args.query
        criteria = args.criteria
        limit = args.limit
        print(f"\n[CLI] Searching Case Tag Definitions (query='{query}', criteria='{criteria}')...")
        try:
            batch = engine.search_case_tag_definitions(query=query, match_criteria=criteria, limit=limit)
            print(f"\n=== CASE TAG DEFINITIONS (Showing {len(batch.tags)} of {batch.total_count}) ===")
            if not batch.tags:
                print("  No case tag definitions matched criteria.")
            else:
                print(f"  {'TAG ID':10s} {'DISPLAY NAME':36s} {'MATCH CRITERIA':20s} {'COMPARISON':12s} {'PRIORITY':8s} {'CAN TITLE'}")
                print("  " + "-" * 105)
                for t in batch.tags:
                    print(f"  {t.id:10s} {t.display_name:36s} {t.match_criteria:20s} {t.comparison_type:12s} {str(t.priority):8s} {'YES' if t.can_be_case_title else 'NO'}")
            print()
        except Exception as e:
            print(f"Error listing case tag definitions: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "stages":
        limit = args.limit
        print(f"\n[CLI] Listing Case Stage Definitions...")
        try:
            batch = engine.list_case_stage_definitions(limit=limit)
            print(f"\n=== CASE STAGE DEFINITIONS ({len(batch.stages)}) ===")
            if not batch.stages:
                print("  No case stage definitions found.")
            else:
                print(f"  {'STAGE ID':10s} {'ORDER':8s} {'DISPLAY NAME'}")
                print("  " + "-" * 50)
                for s in batch.stages:
                    print(f"  {s.id:10s} {str(s.order):8s} {s.display_name}")
            print()
        except Exception as e:
            print(f"Error listing case stage definitions: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "close-reasons":
        limit = args.limit
        print(f"\n[CLI] Listing Case Close Definitions...")
        try:
            batch = engine.list_case_close_definitions(limit=limit)
            print(f"\n=== CASE CLOSE DEFINITIONS ({len(batch.definitions)}) ===")
            if not batch.definitions:
                print("  No case close definitions found.")
            else:
                print(f"  {'ID':10s} {'CLOSE REASON':22s} {'ROOT CAUSE'}")
                print("  " + "-" * 60)
                for d in batch.definitions:
                    print(f"  {d.id:10s} {d.close_reason:22s} {d.root_cause}")
            print()
        except Exception as e:
            print(f"Error listing case close definitions: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "close-params":
        limit = args.limit
        print(f"\n[CLI] Listing Close Case Dynamic Form Parameters...")
        try:
            batch = engine.list_case_close_dynamic_parameters(limit=limit)
            print(f"\n=== CLOSE CASE DYNAMIC PARAMETERS ({len(batch.parameters)}) ===")
            if not batch.parameters:
                print("  No close case dynamic parameters found.")
            else:
                print(f"  {'ORDER':8s} {'CUSTOM FIELD ID':18s} {'FIELD NAME':22s} {'TYPE':12s} {'OPTIONS / VALUES'}")
                print("  " + "-" * 85)
                for p in batch.parameters:
                    opts_str = ", ".join(p.allowed_values) if p.allowed_values else "(any)"
                    print(f"  {str(p.order):8s} {p.related_custom_field_id:18s} {p.custom_field_display_name:22s} {p.custom_field_type:12s} {opts_str}")
            print()
        except Exception as e:
            print(f"Error listing close case dynamic parameters: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "title-rules":
        print(f"\n[CLI] Retrieving Case Title Setting Properties...")
        try:
            batch = engine.get_case_title_settings()
            print(f"\n=== CASE TITLE FORMATTING RULES ({len(batch.properties)} rules) ===")
            if not batch.properties:
                print("  No title formatting rules found.")
            else:
                print(f"  {'PRIORITY':10s} {'NAME / KEY':20s} {'EXPRESSION VALUE'}")
                print("  " + "-" * 60)
                for p in batch.properties:
                    print(f"  {p.display_name:10s} {p.property_key:20s} {p.value}")
            print()
        except Exception as e:
            print(f"Error retrieving case title settings: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "views":
        query = args.query
        vtype = args.type
        limit = args.limit
        type_str = f"type={vtype}" if vtype else "all types"
        print(f"\n[CLI] Searching Case & Alert Views (query='{query}', {type_str})...")
        try:
            batch = engine.search_case_views(query=query, view_type=vtype, limit=limit)
            print(f"\n=== CASE & ALERT VIEWS (Showing {len(batch.views)} of {batch.total_count}) ===")
            if not batch.views:
                print("  No views matched search criteria.")
            else:
                print(f"  {'VIEW ID':10s} {'TYPE':24s} {'IDENTIFIER':38s} {'DISPLAY NAME'}")
                print("  " + "-" * 95)
                for v in batch.views:
                    vtype_disp = v.type or "CUSTOM"
                    print(f"  {v.id:10s} {vtype_disp:24s} {v.identifier:38s} {v.display_name}")
            print()
        except Exception as e:
            print(f"Error searching views: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "view-get":
        view_id = args.view_id
        print(f"\n[CLI] Retrieving View Layout & Widgets: '{view_id}'...")
        try:
            detail = engine.get_case_view(view_id)
            v = detail.summary
            print(f"\n=== VIEW: {v.display_name} ===")
            print(f"  ID                  : {v.id}")
            print(f"  Identifier          : {v.identifier}")
            print(f"  Name                : {v.name}")
            print(f"  Type                : {v.type or 'CUSTOM'}")
            print(f"  Is Default          : {'YES' if v.is_default else 'NO'}")
            print(f"  Total Widgets       : {len(detail.widgets)}")

            if detail.widgets:
                print(f"\n--- Member Widgets & Layout Configuration ---")
                print(f"  {'ORDER':6s} {'TYPE':22s} {'WIDTH':12s} {'TITLE':26s} {'IDENTIFIER'}")
                print("  " + "-" * 110)
                for w in detail.widgets:
                    m = w.metadata
                    print(f"  {str(m.order):6s} {m.type:22s} {m.width:12s} {m.title:26s} {m.identifier}")
            print()
        except Exception as e:
            print(f"Error retrieving view: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "custom-fields":
        query = args.query
        ftype = args.type
        scope = args.scope
        limit = args.limit
        print(f"\n[CLI] Searching Custom Fields (query='{query}', type='{ftype or 'ALL'}', scope='{scope or 'ALL'}')...")
        try:
            batch = engine.search_custom_fields(query=query, field_type=ftype, scope=scope, limit=limit)
            print(f"\n=== CUSTOM FIELDS (Showing {len(batch.custom_fields)} of {batch.total_count}) ===")
            if not batch.custom_fields:
                print("  No custom fields matched search criteria.")
            else:
                print(f"  {'ID':6s} {'TYPE':22s} {'SCOPE':10s} {'VALUES / OPTIONS':35s} {'DISPLAY NAME'}")
                print("  " + "-" * 105)
                for cf in batch.custom_fields:
                    vals_str = ", ".join(cf.values) if cf.values else "N/A"
                    if len(vals_str) > 33:
                        vals_str = vals_str[:30] + "..."
                    print(f"  {cf.id:6s} {cf.type:22s} {cf.scopes:10s} {vals_str:35s} {cf.display_name}")
            print()
        except Exception as e:
            print(f"Error searching custom fields: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "custom-field-get":
        field_id = args.field_id
        print(f"\n[CLI] Retrieving Custom Field Definition: '{field_id}'...")
        try:
            detail = engine.get_custom_field(field_id)
            cf = detail.summary
            print(f"\n=== CUSTOM FIELD: {cf.display_name} ===")
            print(f"  ID                  : {cf.id}")
            print(f"  Resource Name       : {cf.name}")
            print(f"  Display Name        : {cf.display_name}")
            print(f"  Field Type          : {cf.type}")
            print(f"  Scope               : {cf.scopes}")
            print(f"  Values              : {cf.values if cf.values else 'N/A'}")

            if detail.ordered_values:
                print(f"\n--- Ordered Values / Options ---")
                for item in detail.ordered_values:
                    idx = item.get("orderIndex", 0)
                    val = item.get("value", "")
                    print(f"  [{idx}] {val}")
            print()
        except Exception as e:
            print(f"Error retrieving custom field: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "calculated-fields":
        query = args.query
        limit = args.limit
        print(f"\n[CLI] Searching Calculated Fields (query='{query}')...")
        try:
            batch = engine.search_calculated_fields(query=query, limit=limit)
            print(f"\n=== CALCULATED FIELDS (Showing {len(batch.definitions)} of {batch.total_count}) ===")
            if not batch.definitions:
                print("  No calculated fields configured in tenant.")
            else:
                print(f"  {'ID':6s} {'TARGET FIELD':24s} {'ENABLED':8s} {'FORMULA'}")
                print("  " + "-" * 80)
                for d in batch.definitions:
                    en_str = "YES" if d.enabled else "NO"
                    print(f"  {d.id:6s} {d.target_field:24s} {en_str:8s} {d.formula}")
            print()
        except Exception as e:
            print(f"Error searching calculated fields: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "calculated-field-get":
        definition_id = args.definition_id
        print(f"\n[CLI] Retrieving Calculated Field Definition: '{definition_id}'...")
        try:
            detail = engine.get_calculated_field(definition_id)
            d = detail.summary
            print(f"\n=== CALCULATED FIELD: {d.target_field} ===")
            print(f"  ID                  : {d.id}")
            print(f"  Name                : {d.name}")
            print(f"  Target Field        : {d.target_field}")
            print(f"  Formula             : {d.formula}")
            print(f"  Enabled             : {'YES' if d.enabled else 'NO'}")
            print(f"  Description         : {d.description or 'N/A'}")
            print()
        except Exception as e:
            print(f"Error retrieving calculated field: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "alert-grouping-rules":
        query = args.query
        category = args.category
        limit = args.limit
        print(f"\n[CLI] Searching Alert Grouping Rules (query='{query}', category='{category}')...")
        try:
            batch = engine.search_alert_grouping_rules(query=query, category=category, limit=limit)
            print(f"\n=== ALERT GROUPING RULES (Showing {len(batch.rules)} of {batch.total_count}) ===")
            if not batch.rules:
                print("  No alert grouping rules matched criteria.")
            else:
                print(f"  {'ID':6s} {'CATEGORY':18s} {'GROUPING TYPE':30s} {'ENTITIES / DETAILS'}")
                print("  " + "-" * 90)
                for r in batch.rules:
                    if r.entity_types:
                        info_str = f"{len(r.entity_types)} entity types ({', '.join(r.entity_types[:3])}{'...' if len(r.entity_types) > 3 else ''})"
                    else:
                        info_str = f"{r.category_details_count} target details"
                    print(f"  {r.id:6s} {r.category:18s} {r.grouping_type:30s} {info_str}")
            print()
        except Exception as e:
            print(f"Error searching alert grouping rules: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "alert-grouping-rule-get":
        rule_id = args.rule_id
        print(f"\n[CLI] Retrieving Alert Grouping Rule: '{rule_id}'...")
        try:
            detail = engine.get_alert_grouping_rule(rule_id)
            r = detail.summary
            print(f"\n=== ALERT GROUPING RULE: Rule {r.id} ({r.category}) ===")
            print(f"  ID                  : {r.id}")
            print(f"  Name                : {r.name}")
            print(f"  Category            : {r.category}")
            print(f"  Grouping Type       : {r.grouping_type}")
            if r.entity_types:
                print(f"  Entity Types ({len(r.entity_types)}):")
                for et in r.entity_types:
                    print(f"    - {et}")
            if detail.category_details:
                print(f"  Category Details ({len(detail.category_details)}):")
                for cd in detail.category_details:
                    print(f"    - {cd.identifier:40s} ({cd.display_name})")
            print()
        except Exception as e:
            print(f"Error retrieving alert grouping rule: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.config_action == "alert-grouping-settings":
        print(f"\n[CLI] Retrieving Global Alert Grouping Configuration Parameters...")
        try:
            batch = engine.get_alert_grouping_settings()
            print(f"\n=== ALERT GROUPING SETTINGS ({len(batch.properties)} properties) ===")
            if not batch.properties:
                print("  No alert grouping settings returned.")
            else:
                print(f"  {'PROPERTY KEY':42s} {'DISPLAY NAME':40s} {'VALUE'}")
                print("  " + "-" * 105)
                for p in batch.properties:
                    print(f"  {p.property_key:42s} {p.display_name:40s} {p.value}")
            print()
        except Exception as e:
            print(f"Error retrieving alert grouping settings: {e}", file=sys.stderr)
            sys.exit(1)


def run_data_table_cli(args):
    engine = SecOpsEngine()
    action = args.dt_action

    if action == "list":
        print(f"\n[CLI] Listing Chronicle SIEM Data Tables (limit={args.limit})...")
        try:
            res = engine.list_data_tables(page_size=args.limit)
            if getattr(args, "json", False):
                print(json.dumps([t.__dict__ for t in res.data_tables], indent=2, default=str))
                return
            print(f"\n=== CHRONICLE SIEM DATA TABLES ({len(res.data_tables)} tables) ===")
            if not res.data_tables:
                print("  No Data Tables found in tenant.")
            else:
                print(f"  {'ID / NAME':45s} {'DISPLAY NAME':30s} {'COLUMNS':10s} {'TTL':10s}")
                print("  " + "-" * 95)
                for dt in res.data_tables:
                    col_count = str(len(dt.column_info))
                    ttl = dt.row_time_to_live or "-"
                    print(f"  {dt.table_id:45s} {dt.display_name[:28]:30s} {col_count:10s} {ttl:10s}")
            print()
        except Exception as e:
            print(f"Error listing data tables: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "get":
        print(f"\n[CLI] Fetching Data Table: '{args.table}'...")
        try:
            dt = engine.get_data_table(args.table)
            if getattr(args, "json", False):
                print(json.dumps(dt.__dict__, indent=2, default=str))
                return
            print(f"\n=== DATA TABLE: {dt.display_name} ({dt.table_id}) ===")
            print(f"  Name        : {dt.name}")
            print(f"  Table ID    : {dt.table_id}")
            print(f"  Display Name: {dt.display_name}")
            print(f"  Description : {dt.description or '-'}")
            print(f"  TTL         : {dt.row_time_to_live or '-'}")
            print(f"  Created Time: {dt.create_time or '-'}")
            print(f"  Updated Time: {dt.update_time or '-'}")
            print("\n  Columns:")
            for col in dt.column_info:
                key_marker = " [KEY]" if col.is_key_column else ""
                print(f"    - {col.column_name:25s} {col.data_type:15s}{key_marker}")
            print()
        except Exception as e:
            print(f"Error fetching data table: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "create":
        print(f"\n[CLI] Creating Data Table '{args.table_id}'...")
        try:
            cols = []
            for col_spec in args.columns.split(","):
                parts = col_spec.strip().split(":")
                col_name = parts[0]
                data_type = parts[1] if len(parts) > 1 else "STRING"
                is_key = len(parts) > 2 and parts[2].lower() in ("key", "true", "1")
                cols.append({
                    "column_name": col_name,
                    "data_type": data_type,
                    "is_key_column": is_key,
                })

            dt = engine.create_data_table(
                table_id=args.table_id,
                display_name=args.display_name,
                description=args.description,
                column_info=cols,
                row_time_to_live=args.ttl,
            )
            if getattr(args, "json", False):
                print(json.dumps(dt.__dict__, indent=2, default=str))
                return
            print(f"\n[+] Successfully created Data Table: {dt.table_id}")
            print(f"  Display Name: {dt.display_name}")
            print(f"  Columns     : {len(dt.column_info)}")
            print()
        except Exception as e:
            print(f"Error creating data table: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "delete":
        print(f"\n[CLI] Deleting Data Table '{args.table}'...")
        try:
            res = engine.delete_data_table(args.table)
            print(f"[+] Successfully deleted Data Table '{args.table}'")
            print()
        except Exception as e:
            print(f"Error deleting data table: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "rows":
        print(f"\n[CLI] Querying rows in Data Table '{args.table}' (limit={args.limit})...")
        try:
            res = engine.list_data_table_rows(
                table_name_or_id=args.table,
                page_size=args.limit,
                filter_expr=args.filter,
            )
            if getattr(args, "json", False):
                print(json.dumps([r.__dict__ for r in res.rows], indent=2, default=str))
                return
            print(f"\n=== ROWS IN TABLE '{args.table}' ({len(res.rows)} rows) ===")
            if not res.rows:
                print("  No rows found.")
            else:
                for idx, row in enumerate(res.rows, 1):
                    print(f"  [{idx}] Row ID: {row.row_id} (Created: {row.create_time or '-'})")
                    print(f"      Values: {row.values}")
            print()
        except Exception as e:
            print(f"Error querying data table rows: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "add-row":
        print(f"\n[CLI] Adding row to Data Table '{args.table}'...")
        try:
            val_list = [v.strip() for v in args.values.split(",")]
            res = engine.add_data_table_rows(
                table_name_or_id=args.table,
                rows=[{"values": val_list}],
            )
            if getattr(args, "json", False):
                print(json.dumps(res, indent=2, default=str))
                return
            print(f"[+] Successfully added row to '{args.table}'.")
            print()
        except Exception as e:
            print(f"Error adding row to data table: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "delete-row":
        print(f"\n[CLI] Deleting row '{args.row_id}' from Data Table '{args.table}'...")
        try:
            res = engine.delete_data_table_row(
                table_name_or_id=args.table,
                row_id=args.row_id,
            )
            print(f"[+] Successfully deleted row '{args.row_id}'.")
            print()
        except Exception as e:
            print(f"Error deleting data table row: {e}", file=sys.stderr)
            sys.exit(1)


def _read_rule_input(input_val: str) -> str:
    """Reads rule text either from direct argument or file path."""
    import os
    if os.path.exists(input_val) and os.path.isfile(input_val):
        with open(input_val, "r", encoding="utf-8") as f:
            return f.read()
    return input_val


def run_rule_cli(args):
    engine = SecOpsEngine()
    action = args.rule_action

    if action == "list":
        print(f"\n[CLI] Listing Chronicle SIEM detection rules (limit={args.limit})...")
        try:
            res = engine.list_rules(
                page_size=args.limit,
                filter_expr=args.filter,
                view=args.view,
            )
            if getattr(args, "json", False):
                print(json.dumps([r.__dict__ for r in res.rules], indent=2, default=str))
                return
            print(f"\n=== CHRONICLE DETECTION RULES ({len(res.rules)} rules) ===")
            if not res.rules:
                print("  No detection rules found.")
            else:
                print(f"  {'RULE ID':45s} {'DISPLAY NAME':35s} {'SEVERITY':10s} {'TYPE':15s} {'FREQ':10s}")
                print("  " + "-" * 120)
                for r in res.rules:
                    freq = r.run_frequency or (r.allowed_run_frequencies[0] if r.allowed_run_frequencies else "-")
                    print(f"  {r.rule_id:45s} {r.display_name[:33]:35s} {r.severity:10s} {r.rule_type:15s} {freq:10s}")
            print()
        except Exception as e:
            print(f"Error listing detection rules: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "get":
        print(f"\n[CLI] Fetching detection rule: '{args.rule}'...")
        try:
            r = engine.get_rule(args.rule, view=args.view)
            if getattr(args, "json", False):
                print(json.dumps(r.__dict__, indent=2, default=str))
                return
            print(f"\n=== DETECTION RULE: {r.display_name} ({r.rule_id}) ===")
            print(f"  Name            : {r.name}")
            print(f"  Rule ID         : {r.rule_id}")
            print(f"  Revision ID     : {r.revision_id or '-'}")
            print(f"  Author          : {r.author or '-'}")
            print(f"  Severity        : {r.severity}")
            print(f"  Compilation     : {r.compilation_state}")
            print(f"  Type            : {r.rule_type}")
            print(f"  Run Frequency   : {r.run_frequency or '-'}")
            print(f"  Created Time    : {r.create_time or '-'}")
            print(f"  Revision Time   : {r.revision_create_time or '-'}")
            if r.metadata:
                print(f"  Metadata        : {r.metadata}")
            if r.text:
                print("\n--- YARA-L 2.0 Code ---")
                print(r.text)
                print("-" * 23)
            print()
        except Exception as e:
            print(f"Error fetching detection rule: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "verify":
        print("\n[CLI] Verifying YARA-L rule text...")
        try:
            rule_text = _read_rule_input(args.rule_input)
            res = engine.verify_rule(rule_text)
            if getattr(args, "json", False):
                print(json.dumps(res.__dict__, indent=2, default=str))
                return
            if res.success:
                print("[+] YARA-L 2.0 Syntax Verification SUCCEEDED. Rule text is valid.")
            else:
                print("[-] YARA-L 2.0 Syntax Verification FAILED.")
                for d in res.diagnostics:
                    line_info = f"line {d.start_line}, col {d.start_column}" if d.start_line else "general"
                    print(f"  * [{d.severity}] ({line_info}): {d.message}")
            print()
        except Exception as e:
            print(f"Error verifying rule: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "create":
        print("\n[CLI] Creating detection rule...")
        try:
            rule_text = _read_rule_input(args.rule_input)
            r = engine.create_rule(rule_text)
            if getattr(args, "json", False):
                print(json.dumps(r.__dict__, indent=2, default=str))
                return
            print(f"[+] Detection rule created successfully: {r.display_name} ({r.rule_id})")
            print(f"  Compilation State: {r.compilation_state}")
            print(f"  Revision ID      : {r.revision_id}")
            print()
        except Exception as e:
            print(f"Error creating rule: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "patch":
        print(f"\n[CLI] Updating detection rule '{args.rule}'...")
        try:
            rule_text = _read_rule_input(args.rule_input)
            r = engine.patch_rule(args.rule, rule_text)
            if getattr(args, "json", False):
                print(json.dumps(r.__dict__, indent=2, default=str))
                return
            print(f"[+] Detection rule updated successfully: {r.display_name} ({r.rule_id})")
            print(f"  New Revision ID  : {r.revision_id}")
            print(f"  Compilation State: {r.compilation_state}")
            print()
        except Exception as e:
            print(f"Error updating rule: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "delete":
        print(f"\n[CLI] Deleting detection rule '{args.rule}'...")
        try:
            res = engine.delete_rule(args.rule)
            print(f"[+] Detection rule '{args.rule}' deleted successfully.")
            print()
        except Exception as e:
            print(f"Error deleting rule: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "revisions":
        print(f"\n[CLI] Listing revisions for rule '{args.rule}' (limit={args.limit})...")
        try:
            res = engine.list_rule_revisions(args.rule, page_size=args.limit)
            if getattr(args, "json", False):
                print(json.dumps([rev.__dict__ for rev in res.revisions], indent=2, default=str))
                return
            print(f"\n=== RULE REVISIONS: {args.rule} ({len(res.revisions)} revisions) ===")
            if not res.revisions:
                print("  No revisions found.")
            else:
                print(f"  {'REVISION ID':35s} {'COMPILATION':15s} {'REVISION TIME':30s} {'AUTHOR':20s}")
                print("  " + "-" * 105)
                for rev in res.revisions:
                    print(f"  {rev.revision_id:35s} {rev.compilation_state:15s} {rev.revision_create_time[:28]:30s} {rev.author or '-':20s}")
            print()
        except Exception as e:
            print(f"Error listing rule revisions: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "deployment":
        print(f"\n[CLI] Fetching deployment status for rule '{args.rule}'...")
        try:
            dep = engine.get_rule_deployment(args.rule)
            if getattr(args, "json", False):
                print(json.dumps(dep.__dict__, indent=2, default=str))
                return
            print(f"\n=== RULE DEPLOYMENT: {args.rule} ===")
            print(f"  Name            : {dep.name}")
            print(f"  Run Frequency   : {dep.run_frequency}")
            print(f"  Execution State : {dep.execution_state}")
            print(f"  Enabled         : {dep.enabled}")
            print(f"  Alerting        : {dep.alerting}")
            print(f"  Last Alert Chg  : {dep.last_alert_status_change_time or '-'}")
            print()
        except Exception as e:
            print(f"Error fetching rule deployment: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "set-deployment":
        print(f"\n[CLI] Updating deployment settings for rule '{args.rule}'...")
        try:
            enabled = True if args.enabled else (False if args.disabled else None)
            alerting = True if args.alerting else (False if args.no_alerting else None)
            dep = engine.update_rule_deployment(
                args.rule,
                enabled=enabled,
                alerting=alerting,
                run_frequency=args.frequency,
            )
            if getattr(args, "json", False):
                print(json.dumps(dep.__dict__, indent=2, default=str))
                return
            print(f"[+] Rule deployment updated: {args.rule}")
            print(f"  Run Frequency   : {dep.run_frequency}")
            print(f"  Execution State : {dep.execution_state}")
            print(f"  Enabled         : {dep.enabled}")
            print(f"  Alerting        : {dep.alerting}")
            print()
        except Exception as e:
            print(f"Error updating rule deployment: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "errors":
        print(f"\n[CLI] Listing rule execution errors (limit={args.limit})...")
        try:
            res = engine.list_rule_errors(args.rule, page_size=args.limit)
            if getattr(args, "json", False):
                print(json.dumps([err.__dict__ for err in res.errors], indent=2, default=str))
                return
            print(f"\n=== RULE EXECUTION ERRORS ({len(res.errors)} errors) ===")
            if not res.errors:
                print("  No rule execution errors found.")
            else:
                print(f"  {'RULE ID':45s} {'ERROR CODE':12s} {'START TIME':25s} {'MESSAGE':40s}")
                print("  " + "-" * 125)
                for err in res.errors:
                    print(f"  {err.rule_id:45s} {str(err.error_code):12s} {err.start_time[:24]:25s} {err.error_message[:38]:40s}")
            print()
        except Exception as e:
            print(f"Error listing rule errors: {e}", file=sys.stderr)
            sys.exit(1)

    elif action == "audit":
        from runbooks.operations.yara_l_rules_audit import (
            generate_yara_l_rules_audit_report,
            print_yara_l_rules_audit_console,
        )
        print(f"\n[CLI] Running YARA-L detection rules audit (limit={args.limit})...")
        try:
            report = generate_yara_l_rules_audit_report(
                engine=engine,
                page_size=args.limit,
                filter_expr=args.filter,
            )
            if getattr(args, "json", False):
                print(json.dumps(report, indent=2, default=str))
                return
            print_yara_l_rules_audit_console(report)
            if getattr(args, "out", None):
                with open(args.out, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, default=str)
                print(f"[+] Audit report written to {args.out}")
        except Exception as e:
            print(f"Error executing rules audit: {e}", file=sys.stderr)
            sys.exit(1)




def run_investigate_cli(args):





    engine = SecOpsEngine()
    print(f"\n[CLI] Investigating Event ID: {args.event_id}")

    try:
        investigation = engine.investigate_event(
            event_ref=args.event_id,
            eager_load_raw_log=args.raw_log,
        )
        print("\n--- Event Metadata ---")
        metadata = investigation.event.get("metadata", {})
        for k, v in metadata.items():
            if not isinstance(v, (dict, list)):
                print(f"  {k:20s}: {v}")

        print("\n--- Key Entities ---")
        principal = investigation.event.get("principal", {})
        if principal:
            print(f"  Principal Hostname  : {principal.get('hostname', 'N/A')}")
            print(f"  Principal IP        : {principal.get('ip', 'N/A')}")
            print(f"  Principal User      : {principal.get('user', {}).get('userid', 'N/A')}")

        target = investigation.event.get("target", {})
        if target:
            print(f"  Target Hostname     : {target.get('hostname', 'N/A')}")
            print(f"  Target IP           : {target.get('ip', 'N/A')}")
            print(f"  Target User         : {target.get('user', {}).get('userid', 'N/A')}")

        if args.raw_log:
            print("\n--- Raw Log ---")
            raw_log = investigation.load_raw_log()
            print(f"  Source Product      : {raw_log.source_product}")
            print(f"  Log Type            : {raw_log.log_type}")
            print(f"  Ingested Timestamp  : {raw_log.timestamp}")
            print(f"  Raw Size (bytes)    : {raw_log.raw_bytes_size}")
            print("\nVerbatim Log Content:")
            print(raw_log.raw_text[:2000])
            if len(raw_log.raw_text) > 2000:
                print(f"\n[... truncated {len(raw_log.raw_text) - 2000} bytes ...]")

        print("\n--- Provenance ---")
        print(f"  Provider            : {investigation.provenance.provider}")
        print(f"  Workflow ID         : {investigation.provenance.workflow_id}")
        print(f"  Retrieved At        : {investigation.provenance.retrieved_at.isoformat()}")

    except Exception as e:
        print(f"Investigation failed: {e}", file=sys.stderr)
        sys.exit(1)


def run_search_cli(args):
    now = datetime.now(timezone.utc)

    end_time = args.end or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_time = args.start or (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

    req = SearchRequest(
        query=args.query,
        start_time=start_time,
        end_time=end_time,
        receive_limit=args.limit,
        batch_size=args.batch_size,
    )

    engine = SecOpsEngine()

    is_cancelled = False

    def handle_sigint(signum, frame):
        nonlocal is_cancelled
        if not is_cancelled:
            is_cancelled = True
            print("\n[CLI] Cancellation requested (Ctrl+C). Signaling engine...", file=sys.stderr)

    signal.signal(signal.SIGINT, handle_sigint)

    def cancel_token() -> bool:
        return is_cancelled

    last_state = None

    def on_state_change(*args, **kwargs):
        nonlocal last_state
        session = args[-1] if args else kwargs.get("session")
        if not session or not hasattr(session, "lifecycle"):
            return
        if session.lifecycle != last_state:
            last_state = session.lifecycle
            if session.lifecycle == LifecycleState.VALIDATING:
                print("Validating query syntax against Google SecOps...")
            elif session.lifecycle == LifecycleState.STARTING:
                print("Query valid. Starting asynchronous search operation...")
            elif session.lifecycle == LifecycleState.RUNNING:
                print(f"Search started. Session ID: {session.session_id}")
            elif session.lifecycle == LifecycleState.CANCELLING:
                print("Engine cancelling backend operation...")
            elif session.lifecycle == LifecycleState.CANCELLED:
                print(f"Operation cancelled. Events retained: {session.received_count}")
            elif session.lifecycle == LifecycleState.FAILED:
                print(f"Error: {session.error}", file=sys.stderr)

    start_perf = time.time()

    print(f"\n[bold green]Initiating Search Session...[/bold green]")

    def on_batch(batch: SearchBatchResult, session: SearchSession):
        s_idx = getattr(batch, "returned_start_index", getattr(batch, "requested_start_index", 1))
        e_idx = getattr(batch, "returned_end_index", getattr(batch, "requested_end_index", 1))
        prov_info = f" [dim](Op: {batch.operation_id[-12:] if batch.operation_id else 'N/A'}, idx: {s_idx}-{e_idx})[/dim]"
        print(
            f" [bold blue]➜ Batch received:[/bold blue] {batch.batch_count} events "
            f"(Total so far: {session.received_count}){prov_info}"
        )

    session = engine.search_udm(
        request=req,
        on_batch=on_batch,
        on_state_change=on_state_change,
        cancel_token=cancel_token,
    )

    duration = time.time() - start_perf

    print("\n--- Search Execution Summary ---")
    print(f"Session ID    : {session.session_id}")
    print(f"Lifecycle     : {session.lifecycle.value}")
    print(f"Completeness  : {session.completeness.value}")
    print(f"Total Events  : {session.received_count:,}")
    print(f"Duration      : {duration:.2f}s")

    if session.lifecycle == LifecycleState.FAILED:
        sys.exit(1)


def run_search_stats_cli(args):
    now = datetime.now(timezone.utc)
    end_time = args.end or now.strftime("%Y-%m-%dT%H:%M:%SZ")
    start_time = args.start or (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_format = getattr(args, "format", "table")
    dedup = getattr(args, "dedup", False)

    engine = SecOpsEngine()

    is_cancelled = False

    def handle_sigint(signum, frame):
        nonlocal is_cancelled
        if not is_cancelled:
            is_cancelled = True
            print("\n[CLI] Cancellation requested (Ctrl+C). Signaling engine...", file=sys.stderr)

    signal.signal(signal.SIGINT, handle_sigint)

    def cancel_token() -> bool:
        return is_cancelled

    last_state = None

    def on_state_change(lifecycle, completeness, session):
        nonlocal last_state
        if lifecycle != last_state:
            last_state = lifecycle
            target_out = sys.stderr if out_format in ("json", "csv") else sys.stdout
            if lifecycle == LifecycleState.VALIDATING:
                print("Validating stats query syntax against Google SecOps...", file=target_out)
            elif lifecycle == LifecycleState.STARTING:
                print("Query valid. Starting asynchronous stats operation...", file=target_out)
            elif lifecycle == LifecycleState.RUNNING:
                print(f"Stats operation started. Session ID: {session.session_id}", file=target_out)
            elif lifecycle == LifecycleState.CANCELLING:
                print("Engine cancelling backend operation...", file=target_out)
            elif lifecycle == LifecycleState.CANCELLED:
                print("Operation cancelled.", file=target_out)
            elif lifecycle == LifecycleState.FAILED:
                print(f"Error: {session.error}", file=sys.stderr)

    start_perf = time.time()
    if out_format == "table":
        print(f"\n[bold green]Initiating UDM Stats Search...[/bold green]")
    else:
        print(f"Initiating UDM Stats Search...", file=sys.stderr)

    session = engine.search_udm_stats(
        query=args.query,
        start_time=start_time,
        end_time=end_time,
        max_events=args.limit,
        case_insensitive=not getattr(args, "case_sensitive", False),
        on_state_change=on_state_change,
        cancel_token=cancel_token,
    )

    duration = time.time() - start_perf

    if session.lifecycle == LifecycleState.FAILED:
        print(f"\n[bold red]Stats Search Failed:[/bold red] {session.error}", file=sys.stderr)
        sys.exit(1)

    res = session.result
    if not res or not res.rows:
        target_out = sys.stderr if out_format in ("json", "csv") else sys.stdout
        print("\nNo stats rows returned for the specified time range and query.", file=target_out)
        return

    rows = res.dedup_rows() if dedup else res.rows

    if out_format == "json":
        import json

        payload = {
            "query": args.query,
            "total_results": len(rows),
            "filtered_result_count": res.filtered_result_count,
            "data_query_expression": res.data_query_expression,
            "columns": [
                {
                    "column": c.column,
                    "filterable": c.filterable,
                    "filter_expression": c.filter_expression,
                    "data_type": c.column_metadata.data_type if c.column_metadata else "STRING",
                    "function": c.column_metadata.function_name_used if c.column_metadata else None,
                }
                for c in res.columns
            ],
            "rows": rows,
        }
        print(json.dumps(payload, indent=2, default=str))

    elif out_format == "csv":
        import csv
        import io

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=res.column_names())
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        print(buf.getvalue().strip())

    else:  # table format
        try:
            from rich.console import Console
            from rich.table import Table

            console = Console()
            table = Table(
                title=f"UDM Stats Results ({len(rows)} rows)",
                show_header=True,
                header_style="bold magenta",
            )
            for col in res.columns:
                header_title = col.column
                if col.column_metadata and col.column_metadata.function_name_used:
                    header_title = f"{col.column} ({col.column_metadata.function_name_used})"
                table.add_column(
                    header_title, style="dim" if col.column.startswith("_") else "cyan"
                )

            for row in rows:
                table.add_row(*[str(row.get(c.column, "")) for c in res.columns])

            console.print(table)

            if res.aggregations:
                agg_table = Table(
                    title="Field Distribution Aggregations",
                    show_header=True,
                    header_style="bold green",
                )
                agg_table.add_column("Field", style="cyan")
                agg_table.add_column("Events", justify="right")
                agg_table.add_column("Distinct Values", justify="right")
                agg_table.add_column("Top Values", style="dim")
                for agg in res.aggregations:
                    top_vals = ", ".join(
                        f"{v.value} ({v.event_count})" for v in agg.all_values[:3]
                    )
                    agg_table.add_row(
                        agg.field_name,
                        str(agg.event_count),
                        str(agg.value_count),
                        top_vals,
                    )
                console.print(agg_table)

        except ImportError:
            headers = res.column_names()
            print("\t".join(headers))
            print("-" * 40)
            for row in rows:
                print("\t".join(str(row.get(h, "")) for h in headers))

    if out_format == "table":
        print(f"\n--- Stats Execution Summary ---")
        print(f"Session ID    : {session.session_id}")
        print(f"Total Rows    : {len(rows):,}")
        print(f"Duration      : {duration:.2f}s")


if __name__ == "__main__":
    main()
