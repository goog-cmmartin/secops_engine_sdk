"""Workflow implementation for querying Google Cloud Monitoring for Chronicle and SecOps telemetry."""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional

from engine.domain import (
    GcpMonitoringQueryResult,
    MetricPoint,
    TimeSeriesData,
)

logger = logging.getLogger(__name__)


def _extract_point_value(val_dict: Any) -> Any:
    """Extracts typed value from a Google Cloud Monitoring TimeSeries point value dict."""
    if not isinstance(val_dict, dict):
        return val_dict
    if "int64Value" in val_dict:
        try:
            return int(val_dict["int64Value"])
        except (ValueError, TypeError):
            return val_dict["int64Value"]
    if "doubleValue" in val_dict:
        try:
            return float(val_dict["doubleValue"])
        except (ValueError, TypeError):
            return val_dict["doubleValue"]
    if "boolValue" in val_dict:
        return bool(val_dict["boolValue"])
    if "stringValue" in val_dict:
        return str(val_dict["stringValue"])
    if "distributionValue" in val_dict:
        return val_dict["distributionValue"]
    return val_dict


def _normalize_time_series(raw: Dict[str, Any]) -> TimeSeriesData:
    """Transforms a raw Google Cloud Monitoring JSON TimeSeries into a typed TimeSeriesData."""
    metric = raw.get("metric", {}) if isinstance(raw.get("metric"), dict) else {}
    resource = raw.get("resource", {}) if isinstance(raw.get("resource"), dict) else {}

    raw_points = raw.get("points", []) or []
    points: List[MetricPoint] = []
    for p in raw_points:
        if isinstance(p, dict):
            interval = p.get("interval", {}) if isinstance(p.get("interval"), dict) else {}
            val = _extract_point_value(p.get("value", {}))
            points.append(
                MetricPoint(
                    start_time=interval.get("startTime", ""),
                    end_time=interval.get("endTime", ""),
                    value=val,
                )
            )

    return TimeSeriesData(
        metric_type=metric.get("type", ""),
        metric_labels=metric.get("labels", {}) if isinstance(metric.get("labels"), dict) else {},
        resource_type=resource.get("type", ""),
        resource_labels=resource.get("labels", {}) if isinstance(resource.get("labels"), dict) else {},
        metric_kind=raw.get("metricKind", "GAUGE"),
        value_type=raw.get("valueType", "INT64"),
        points=points,
        raw=raw,
    )


class GcpMonitoringQueryWorkflow:
    """Executes time series queries against Google Cloud Monitoring API (v3) for SecOps telemetry."""

    def __init__(self, adapter: Any):
        self.adapter = adapter

    def execute(
        self,
        filter_str: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        hours: int = 24,
        project_id: Optional[str] = None,
        alignment_period: Optional[str] = None,
        per_series_aligner: Optional[str] = None,
        cross_series_reducer: Optional[str] = None,
        group_by_fields: Optional[List[str]] = None,
        page_size: int = 50,
        page_token: Optional[str] = None,
    ) -> GcpMonitoringQueryResult:
        """Executes a Cloud Monitoring time series query with interval calculation, alignment, and normalization."""
        if not filter_str:
            raise ValueError("Cloud Monitoring query requires a non-empty filter_str expression.")

        now = datetime.now(timezone.utc)
        if not end_time:
            end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        if not start_time:
            start_dt = now - timedelta(hours=hours)
            start_time = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        raw_resp = self.adapter.query_cloud_monitoring_time_series(
            filter_str=filter_str,
            start_time=start_time,
            end_time=end_time,
            project_id=project_id,
            alignment_period=alignment_period,
            per_series_aligner=per_series_aligner,
            cross_series_reducer=cross_series_reducer,
            group_by_fields=group_by_fields,
            page_size=page_size,
            page_token=page_token,
        )

        raw_series = raw_resp.get("timeSeries", []) or []
        series = [_normalize_time_series(s) for s in raw_series]
        next_token = raw_resp.get("nextPageToken")
        queried_projects = [project_id] if project_id else [getattr(self.adapter, "project_id", "")]

        return GcpMonitoringQueryResult(
            time_series=series,
            next_page_token=next_token,
            total_series=len(series),
            filter_applied=filter_str,
            time_interval=f"{start_time} - {end_time}",
            projects_queried=queried_projects,
        )

    def query_chronicle_ingestion_metrics(
        self,
        hours: int = 24,
        log_type: Optional[str] = None,
        alignment_period: str = "3600s",
        per_series_aligner: str = "ALIGN_SUM",
        project_id: Optional[str] = None,
    ) -> GcpMonitoringQueryResult:
        """Queries Chronicle log ingestion count and volume metrics."""
        filter_parts = ['metric.type = starts_with("chronicle.googleapis.com/")']
        if log_type:
            filter_parts.append(f'metric.label.log_type = "{log_type}"')

        combined_filter = " AND ".join(filter_parts)
        return self.execute(
            filter_str=combined_filter,
            hours=hours,
            project_id=project_id,
            alignment_period=alignment_period,
            per_series_aligner=per_series_aligner,
        )

    def query_chronicle_normalizer_metrics(
        self,
        hours: int = 24,
        log_type: Optional[str] = None,
        alignment_period: str = "3600s",
        per_series_aligner: str = "ALIGN_SUM",
        project_id: Optional[str] = None,
    ) -> GcpMonitoringQueryResult:
        """Queries Chronicle normalizer and parser throughput metrics."""
        filter_parts = ['metric.type = starts_with("chronicle.googleapis.com/normalizer")']
        if log_type:
            filter_parts.append(f'metric.label.log_type = "{log_type}"')

        combined_filter = " AND ".join(filter_parts)
        return self.execute(
            filter_str=combined_filter,
            hours=hours,
            project_id=project_id,
            alignment_period=alignment_period,
            per_series_aligner=per_series_aligner,
        )

    def query_chronicle_api_metrics(
        self,
        hours: int = 24,
        alignment_period: str = "3600s",
        per_series_aligner: str = "ALIGN_RATE",
        cross_series_reducer: str = "REDUCE_SUM",
        project_id: Optional[str] = None,
    ) -> GcpMonitoringQueryResult:
        """Queries Chronicle API consumption and request rate metrics (serviceruntime)."""
        combined_filter = (
            'metric.type = "serviceruntime.googleapis.com/api/request_count" '
            'AND resource.type = "consumed_api" '
            'AND resource.label.service = "chronicle.googleapis.com"'
        )
        return self.execute(
            filter_str=combined_filter,
            hours=hours,
            project_id=project_id,
            alignment_period=alignment_period,
            per_series_aligner=per_series_aligner,
            cross_series_reducer=cross_series_reducer,
        )

    def query_chronicle_agent_metrics(
        self,
        hours: int = 24,
        alignment_period: str = "300s",
        per_series_aligner: str = "ALIGN_MEAN",
        project_id: Optional[str] = None,
    ) -> GcpMonitoringQueryResult:
        """Queries Chronicle forwarder agent queue size, capacity, and CPU consumption."""
        combined_filter = 'metric.type = starts_with("chronicle.googleapis.com/agent/")'
        return self.execute(
            filter_str=combined_filter,
            hours=hours,
            project_id=project_id,
            alignment_period=alignment_period,
            per_series_aligner=per_series_aligner,
        )
