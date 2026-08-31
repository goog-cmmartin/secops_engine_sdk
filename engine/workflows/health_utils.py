"""Shared telemetry utilities for Feed, Parser, and Detection Health workflows.

Connects to Google SecOps curated dashboards:
- Health Hub (1b0cb92f-c162-424a-9d31-05b35180c8a5)
- Data Health Deep Dive (5cf5988b-951f-4e54-830d-330ef5ad438a)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from adapters.google_secops import GoogleSecOpsAdapter

from engine.workflows.dashboards import (
    ExecuteDashboardQueryWorkflow,
    GetDashboardDetailWorkflow,
)

# Dashboard UUIDs
HEALTH_HUB_DASHBOARD_ID = "1b0cb92f-c162-424a-9d31-05b35180c8a5"
DATA_HEALTH_DEEP_DIVE_DASHBOARD_ID = "5cf5988b-951f-4e54-830d-330ef5ad438a"

# Canonical Collector ID Mapping from Data Health Deep Dive
COLLECTOR_UUID_MAP: Dict[str, str] = {
    "aaaa3333-aaaa-3333-aaaa-3333aaaa3333": "Native GCP Ingestion",
    "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb": "/unstructuredlogentries:batchCreate",
    "cccccccc-cccc-cccc-cccc-cccccccccccc": "/udmevents:batchCreate",
    "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee": "/entities:batchCreate",
    "ffffffff-ffff-ffff-ffff-ffffffffffff": "SOAR Alert",
    "aaaa1111-aaaa-1111-aaaa-1111aaaa1111": "Collection Agent",
    "aaaa1111-aaaa-1111-aaaa-1111aaaa1112": "BindPlane Enterprise Google",
    "aaaa1111-aaaa-1111-aaaa-1111aaaa1113": "BindPlane Enterprise Regular",
    "aaaa1111-aaaa-1111-aaaa-1111aaaa1114": "Headless Agent",
    "dddddddd-dddd-dddd-dddd-dddddddddddd": "Internal API / Native Workspace",
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": "Feeds",
    "aaaa2222-aaaa-2222-aaaa-2222aaaa2222": "HTTPS Push Feeds",
    "aaaa4444-aaaa-4444-aaaa-4444aaaa4444": "Azure Event Hub Feeds",
}


def resolve_collector_name(collector_id: str, log_type: str = "") -> str:
    """Resolves collector UUID or custom collector string to human-readable taxonomy name."""
    if not collector_id:
        return "Unknown"
    cid = str(collector_id).strip().lower()
    if cid in COLLECTOR_UUID_MAP:
        if cid == "dddddddd-dddd-dddd-dddd-dddddddddddd" and log_type == "WORKSPACE_ACTIVITY":
            return "Native Workspace Ingestion"
        return COLLECTOR_UUID_MAP[cid]
    return collector_id


@dataclass
class DeepDiveTelemetry:
    """Aggregated telemetry from Data Health Deep Dive and Health Hub dashboards."""
    collector_by_log_type: Dict[str, str] = field(default_factory=dict)
    parser_errors_by_log_type: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    volume_funnel_by_log_type: Dict[str, Dict[str, int]] = field(default_factory=dict)
    quota_rejected_volume_mb: Dict[str, float] = field(default_factory=dict)
    quota_limit_mb_per_sec: Dict[str, float] = field(default_factory=dict)


def fetch_deep_dive_telemetry(adapter: GoogleSecOpsAdapter) -> DeepDiveTelemetry:
    """Queries Data Health Deep Dive dashboard and returns structured telemetry."""
    telemetry = DeepDiveTelemetry()
    try:
        get_dash_wf = GetDashboardDetailWorkflow(adapter)
        dash_detail = get_dash_wf.execute(DATA_HEALTH_DEEP_DIVE_DASHBOARD_ID, include_queries=False)
        exec_wf = ExecuteDashboardQueryWorkflow(adapter)

        for chart in dash_detail.charts:
            q_name = chart.raw.get("chartDatasource", {}).get("dashboardQuery")
            if not q_name:
                continue

            c_name = (chart.display_name or "").lower().strip()

            # 1. Log Count By Collector Id & Log Type
            if "log count by collector id" in c_name:
                try:
                    res = exec_wf.execute(query_name_or_id=q_name)
                    for row in res.rows:
                        lt = row.get("Log_Type") or row.get("log_type") or ""
                        c_name_val = row.get("collector_name") or ""
                        total_logs = int(row.get("total_logs") or 0)
                        if lt and c_name_val and total_logs > 0:
                            # Map collector
                            telemetry.collector_by_log_type[lt] = resolve_collector_name(c_name_val, lt)
                except Exception:
                    pass

            # 2. Parser Error History (Last 200 Errors)
            elif "parser error history" in c_name:
                try:
                    res = exec_wf.execute(query_name_or_id=q_name)
                    for row in res.rows:
                        lt = row.get("log") or row.get("log_type") or ""
                        if lt:
                            telemetry.parser_errors_by_log_type.setdefault(lt, []).append(row)
                except Exception:
                    pass

            # 3. Ingestion - Events by Status (Funnel)
            elif "ingestion - events by status" in c_name:
                try:
                    res = exec_wf.execute(query_name_or_id=q_name)
                    for row in res.rows:
                        lt = row.get("log_type") or ""
                        if not lt:
                            continue
                        if lt not in telemetry.volume_funnel_by_log_type:
                            telemetry.volume_funnel_by_log_type[lt] = {
                                "total_logs": 0,
                                "validated_events": 0,
                                "normalized_events": 0,
                                "parsing_error_events": 0,
                                "validation_error_events": 0,
                                "indexing_error_events": 0,
                            }
                        funnel = telemetry.volume_funnel_by_log_type[lt]
                        funnel["total_logs"] += int(row.get("Total_Logs") or 0)
                        funnel["validated_events"] += int(row.get("Total_Validated_Events") or 0)
                        funnel["normalized_events"] += int(row.get("Total_Normalized_Events") or 0)
                        funnel["parsing_error_events"] += int(row.get("Total_Parsing_Error_Events") or 0)
                        funnel["validation_error_events"] += int(row.get("Total_Validation_Error_Events") or 0)
                        funnel["indexing_error_events"] += int(row.get("Total_Indexing_Error_Events") or 0)
                except Exception:
                    pass

            # 4. Burst Rejection Graph
            elif "burst rejection" in c_name:
                try:
                    res = exec_wf.execute(query_name_or_id=q_name)
                    for row in res.rows:
                        lt = row.get("log_type") or ""
                        vol = float(row.get("Max_Of_Quota_Rejected_Log_Volume") or 0.0)
                        if lt and vol > 0.0:
                            telemetry.quota_rejected_volume_mb[lt] = max(
                                telemetry.quota_rejected_volume_mb.get(lt, 0.0), vol
                            )
                except Exception:
                    pass

            # 5. Burst Limit Graph - Quota Limit
            elif "burst limit graph" in c_name:
                try:
                    res = exec_wf.execute(query_name_or_id=q_name)
                    for row in res.rows:
                        lt = row.get("log_type") or ""
                        limit_val = float(row.get("Max_Qouta_Limit_MB_Per_Second") or 0.0)
                        if lt and limit_val > 0.0:
                            telemetry.quota_limit_mb_per_sec[lt] = max(
                                telemetry.quota_limit_mb_per_sec.get(lt, 0.0), limit_val
                            )
                except Exception:
                    pass
    except Exception:
        pass

    return telemetry
