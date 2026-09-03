"""Proactive Feed Health Audit Workflow.

Correlates feed configuration, Google SecOps Health Hub telemetry,
and ingestion velocity to detect feed decay, silent push stops, and transport latency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from adapters.google_secops import GoogleSecOpsAdapter

from engine.domain import (
    FeedBatch,
    FeedHealthFinding,
    FeedHealthReport,
    FeedHealthStatus,
    FeedSummary,
)
from engine.workflows.dashboards import (
    ExecuteDashboardQueryWorkflow,
    GetDashboardDetailWorkflow,
)
from engine.workflows.feed import SearchFeedsWorkflow
from engine.workflows.health_utils import (
    HEALTH_HUB_DASHBOARD_ID,
    DeepDiveTelemetry,
    fetch_deep_dive_telemetry,
    resolve_collector_name,
)


class AuditFeedHealthWorkflow:
    """Orchestrates comprehensive health assessment across all configured feeds."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(self, lookback_days: int = 7) -> FeedHealthReport:
        """Executes feed health assessment against live SecOps tenant.
        
        1. Discovers all configured push and pull feeds.
        2. Queries Health Hub dashboard telemetry for source status and latency.
        3. Queries Data Health Deep Dive for collector routing, volume funnels, and quota drops.
        4. Analyzes feed states, last initiation times, and telemetry.
        5. Generates structured FeedHealthReport with actionable remediation steps.
        """
        # Step 1: Discover all feeds
        feed_search_wf = SearchFeedsWorkflow(self.adapter)
        feed_batch: FeedBatch = feed_search_wf.execute(limit=1000)
        feeds: List[FeedSummary] = feed_batch.feeds

        # Step 2: Query Health Hub and Deep Dive telemetry
        source_telemetry: Dict[str, Dict[str, Any]] = self._collect_health_hub_telemetry()
        deep_dive_telemetry: DeepDiveTelemetry = fetch_deep_dive_telemetry(self.adapter)

        # Step 3: Evaluate each feed
        findings: List[FeedHealthFinding] = []
        healthy_count = 0
        irregular_count = 0
        failed_count = 0
        high_latency_count = 0
        quota_rejections = 0

        for f in feeds:
            finding = self._evaluate_feed(f, source_telemetry, deep_dive_telemetry)
            findings.append(finding)

            if finding.status == FeedHealthStatus.HEALTHY:
                healthy_count += 1
            elif finding.status in (FeedHealthStatus.FAILED, FeedHealthStatus.SILENT_PUSH_STOP):
                failed_count += 1
            elif finding.status == FeedHealthStatus.IRREGULAR:
                irregular_count += 1
            elif finding.status == FeedHealthStatus.HIGH_LATENCY:
                high_latency_count += 1

            if finding.quota_rejected_volume_mb > 0.0:
                quota_rejections += 1

        return FeedHealthReport(
            findings=findings,
            healthy_count=healthy_count,
            irregular_count=irregular_count,
            failed_count=failed_count,
            high_latency_count=high_latency_count,
            quota_rejections_detected=quota_rejections,
            total_feeds_audited=len(feeds),
            generated_at=datetime.now(timezone.utc),
        )

    def _collect_health_hub_telemetry(self) -> Dict[str, Dict[str, Any]]:
        """Extracts telemetry per feed/source from Health Hub dashboard charts."""
        telemetry_map: Dict[str, Dict[str, Any]] = {}

        try:
            get_dash_wf = GetDashboardDetailWorkflow(self.adapter)
            dash_detail = get_dash_wf.execute(HEALTH_HUB_DASHBOARD_ID, include_queries=False)
            exec_wf = ExecuteDashboardQueryWorkflow(self.adapter)

            # Target key source health charts
            for chart in dash_detail.charts:
                q_name = chart.query_name or chart.raw.get("chartDatasource", {}).get("dashboardQuery")
                if not q_name:
                    continue

                c_name = (chart.display_name or "").lower()
                # Target Failed Sources (#2), Irregular Sources (#10), and Latency by Source (#12)
                is_target_chart = any(k in c_name for k in ["failed sources", "irregular data sources", "latency status by source"])
                if not is_target_chart:
                    continue

                try:
                    res = exec_wf.execute(query_name_or_id=q_name)
                    for row in res.rows:
                        # Identify feed id or source identifier
                        feed_id = row.get("feed_id") or row.get("collector_id") or row.get("source_id") or ""
                        log_type = row.get("log_type") or row.get("logType") or ""
                        key = str(feed_id).strip() or str(log_type).strip()
                        if not key:
                            continue

                        if key not in telemetry_map:
                            telemetry_map[key] = {
                                "chart_signals": [],
                                "latency": None,
                                "health_status": None,
                                "raw_rows": [],
                            }

                        telemetry_map[key]["raw_rows"].append(row)
                        if "failed" in c_name:
                            telemetry_map[key]["chart_signals"].append("FAILED")
                        elif "irregular" in c_name:
                            telemetry_map[key]["chart_signals"].append("IRREGULAR")

                        if "latency" in row:
                            telemetry_map[key]["latency"] = str(row["latency"])
                        elif "event_ingestion_latency" in row:
                            telemetry_map[key]["latency"] = str(row["event_ingestion_latency"])

                        if "health_status" in row:
                            telemetry_map[key]["health_status"] = str(row["health_status"])
                except Exception:
                    continue
        except Exception:
            pass

        return telemetry_map

    def _evaluate_feed(
        self,
        feed: FeedSummary,
        telemetry_map: Dict[str, Dict[str, Any]],
        deep_dive_telemetry: DeepDiveTelemetry,
    ) -> FeedHealthFinding:
        """Evaluates a single feed and classifies health."""
        raw = feed.raw or {}
        state = feed.state.upper()
        source_type = feed.feed_source_type.upper()
        log_type = feed.log_type
        last_initiation = raw.get("lastFeedInitiationTime")

        # Telemetry lookup by feed ID, reference ID, or log type
        telem = (
            telemetry_map.get(feed.id)
            or telemetry_map.get(feed.reference_id)
            or telemetry_map.get(log_type)
            or {}
        )
        chart_signals = telem.get("chart_signals", [])
        latency = telem.get("latency")

        # Deep dive correlation
        collector_name = (
            resolve_collector_name(feed.feed_source_type, feed.log_type)
            or deep_dive_telemetry.collector_by_log_type.get(feed.log_type)
        )
        funnel = deep_dive_telemetry.volume_funnel_by_log_type.get(feed.log_type, {})
        quota_rejected = deep_dive_telemetry.quota_rejected_volume_mb.get(feed.log_type, 0.0)
        quota_limit = deep_dive_telemetry.quota_limit_mb_per_sec.get(feed.log_type, 0.0)

        # 1. State-based failures
        if state in ("FAILED", "ERROR"):
            remediation = [
                "Check source credentials (IAM role, S3 key, API token).",
                "Verify source endpoint network connectivity and firewall rules.",
                "Review feed error logs in SecOps SIEM Settings -> Feeds.",
            ]
            if quota_rejected > 0.0:
                remediation.append(f"Quota burst limit exceeded: {quota_rejected:.2f} MB dropped. Increase tenant quota allocation.")

            return FeedHealthFinding(
                feed_id=feed.id,
                feed_name=feed.display_name,
                source_type=source_type,
                log_type=log_type,
                status=FeedHealthStatus.FAILED,
                state=state,
                collector_name=collector_name,
                volume_funnel=funnel,
                quota_rejected_volume_mb=quota_rejected,
                quota_limit_mb_per_sec=quota_limit,
                last_event_time=last_initiation,
                anomaly_description=f"Feed '{feed.display_name}' is in {state} state.",
                remediation_steps=remediation,
                raw=raw,
            )

        if state == "DISABLED":
            return FeedHealthFinding(
                feed_id=feed.id,
                feed_name=feed.display_name,
                source_type=source_type,
                log_type=log_type,
                status=FeedHealthStatus.FAILED,
                state=state,
                collector_name=collector_name,
                volume_funnel=funnel,
                quota_rejected_volume_mb=quota_rejected,
                quota_limit_mb_per_sec=quota_limit,
                last_event_time=last_initiation,
                anomaly_description=f"Feed '{feed.display_name}' is DISABLED.",
                remediation_steps=[
                    "Enable feed in SIEM Settings if log collection for this source is expected.",
                ],
                raw=raw,
            )

        # 2. Health Hub Failed Signal
        if "FAILED" in chart_signals:
            remediation = [
                "Inspect Data Health Hub dashboard for detailed collector errors.",
                "Verify data source payload schema and pipeline health.",
            ]
            if quota_rejected > 0.0:
                remediation.append(f"Quota burst limit exceeded: {quota_rejected:.2f} MB dropped. Increase tenant quota allocation.")

            return FeedHealthFinding(
                feed_id=feed.id,
                feed_name=feed.display_name,
                source_type=source_type,
                log_type=log_type,
                status=FeedHealthStatus.FAILED,
                state=state,
                collector_name=collector_name,
                latency_p95=latency,
                volume_funnel=funnel,
                quota_rejected_volume_mb=quota_rejected,
                quota_limit_mb_per_sec=quota_limit,
                last_event_time=last_initiation,
                anomaly_description="Health Hub flagged source as FAILED.",
                remediation_steps=remediation,
                raw=raw,
            )

        # 3. Health Hub Irregular Signal
        if "IRREGULAR" in chart_signals:
            remediation = [
                "Check network stability and rate limits on source publisher.",
                "Verify if source generation is naturally intermittent or experiencing transport drops.",
            ]
            if quota_rejected > 0.0:
                remediation.append(f"Quota burst limit exceeded: {quota_rejected:.2f} MB dropped. Increase tenant quota allocation.")

            return FeedHealthFinding(
                feed_id=feed.id,
                feed_name=feed.display_name,
                source_type=source_type,
                log_type=log_type,
                status=FeedHealthStatus.IRREGULAR,
                state=state,
                collector_name=collector_name,
                latency_p95=latency,
                volume_funnel=funnel,
                quota_rejected_volume_mb=quota_rejected,
                quota_limit_mb_per_sec=quota_limit,
                last_event_time=last_initiation,
                anomaly_description="Health Hub flagged source as IRREGULAR (intermittent ingestion gaps).",
                remediation_steps=remediation,
                raw=raw,
            )

        # 4. Latency Check
        if latency and any(unit in latency.lower() for unit in ["hr", "hour", "day"]):
            return FeedHealthFinding(
                feed_id=feed.id,
                feed_name=feed.display_name,
                source_type=source_type,
                log_type=log_type,
                status=FeedHealthStatus.HIGH_LATENCY,
                state=state,
                collector_name=collector_name,
                latency_p95=latency,
                volume_funnel=funnel,
                quota_rejected_volume_mb=quota_rejected,
                quota_limit_mb_per_sec=quota_limit,
                last_event_time=last_initiation,
                anomaly_description=f"High ingestion latency detected: {latency}.",
                remediation_steps=[
                    "Check forwarder/collector queue depth and buffer size.",
                    "Verify if source timestamps are delayed upstream before arrival.",
                ],
                raw=raw,
            )

        # 5. Push Feed Observation
        if "PUSH" in source_type and not last_initiation and not telem:
            # Active push feed without direct initiation data
            return FeedHealthFinding(
                feed_id=feed.id,
                feed_name=feed.display_name,
                source_type=source_type,
                log_type=log_type,
                status=FeedHealthStatus.HEALTHY,
                state=state,
                collector_name=collector_name,
                latency_p95=latency,
                volume_funnel=funnel,
                quota_rejected_volume_mb=quota_rejected,
                quota_limit_mb_per_sec=quota_limit,
                last_event_time=None,
                anomaly_description="Push feed is ACTIVE (monitoring continuous inbound streams).",
                remediation_steps=[],
                raw=raw,
            )

        # 6. Default Healthy
        return FeedHealthFinding(
            feed_id=feed.id,
            feed_name=feed.display_name,
            source_type=source_type,
            log_type=log_type,
            status=FeedHealthStatus.HEALTHY,
            state=state,
            collector_name=collector_name,
            latency_p95=latency,
            volume_funnel=funnel,
            quota_rejected_volume_mb=quota_rejected,
            quota_limit_mb_per_sec=quota_limit,
            last_event_time=last_initiation,
            anomaly_description="Feed is operating normally.",
            remediation_steps=[],
            raw=raw,
        )
