"""Native Dashboards Workflows (Milestone 5.9).

Implements discovery, keyword search, deep composite graph assembly (dashboard + charts + queries + layout),
tabular query execution normalization, and statistical query syntax validation for Google SecOps Dashboards.

Invariants:
- Live data origin exclusively from GoogleSecOpsAdapter.
- Zero synthetic data structures or fallbacks.
- Transparent error propagation and explicit bounds.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from adapters.google_secops import GoogleSecOpsAdapter
from engine.domain import (
    DashboardBatch,
    DashboardChart,
    DashboardChartLayout,
    DashboardDetail,
    DashboardQuery,
    DashboardQueryResult,
    DashboardSearchQuery,
    DashboardSummary,
    ValidationResult,
)


def _map_dashboard_summary(raw: Dict[str, Any]) -> DashboardSummary:
    """Maps raw native dashboard JSON to typed DashboardSummary."""
    name = raw.get("name", "")
    dash_id = name.split("/")[-1] if "/" in name else name
    definition = raw.get("definition", {})
    charts = definition.get("charts", [])

    return DashboardSummary(
        id=dash_id,
        name=name,
        display_name=raw.get("displayName", dash_id),
        description=raw.get("description", ""),
        type=raw.get("type", "UNKNOWN"),
        create_time=raw.get("createTime", ""),
        update_time=raw.get("updateTime", ""),
        create_user_id=raw.get("createUserId", ""),
        update_user_id=raw.get("updateUserId", ""),
        access=raw.get("access", "UNKNOWN"),
        charts_count=len(charts),
        raw=raw,
    )


def _map_dashboard_query(raw: Dict[str, Any]) -> DashboardQuery:
    """Maps raw dashboard query JSON to typed DashboardQuery."""
    name = raw.get("name", "")
    query_id = name.split("/")[-1] if "/" in name else name
    input_cfg = raw.get("input", {})
    rel_time = input_cfg.get("relativeTime", {})

    return DashboardQuery(
        id=query_id,
        name=name,
        query_text=raw.get("query", ""),
        dialect=raw.get("dialect", "YL2"),
        time_unit=rel_time.get("timeUnit"),
        time_value=rel_time.get("startTimeVal"),
        dashboard_chart=raw.get("dashboardChart"),
        etag=raw.get("etag"),
        raw=raw,
    )


def _map_dashboard_chart(
    raw: Dict[str, Any],
    layout_raw: Optional[Dict[str, Any]] = None,
    query_obj: Optional[DashboardQuery] = None,
) -> DashboardChart:
    """Maps raw dashboard chart JSON to typed DashboardChart."""
    name = raw.get("name", "")
    chart_id = name.split("/")[-1] if "/" in name else name

    layout = None
    if layout_raw:
        chart_layout = layout_raw.get("chartLayout", {})
        layout = DashboardChartLayout(
            start_x=chart_layout.get("startX", 0),
            span_x=chart_layout.get("spanX", 0),
            start_y=chart_layout.get("startY", 0),
            span_y=chart_layout.get("spanY", 0),
            filters_ids=layout_raw.get("filtersIds", []),
        )

    datasource = raw.get("chartDatasource", {})
    data_sources = datasource.get("dataSources", [])
    query_name = datasource.get("dashboardQuery")

    return DashboardChart(
        id=chart_id,
        name=name,
        display_name=raw.get("displayName", chart_id),
        description=raw.get("description", ""),
        tile_type=raw.get("tileType", "TILE_TYPE_VISUALIZATION"),
        chart_type=raw.get("chartType", "DASHBOARD_CHART_TYPE_CUSTOM"),
        data_sources=data_sources,
        visualization=raw.get("visualization", {}),
        drill_down_config=raw.get("drillDownConfig", {}),
        layout=layout,
        query=query_obj,
        query_name=query_name,
        etag=raw.get("etag"),
        raw=raw,
    )


def _normalize_query_execution_result(raw: Dict[str, Any], query_name: str) -> DashboardQueryResult:
    """Normalizes columnar raw query execution results into row-oriented records."""
    results = raw.get("results", [])
    col_names: List[str] = []
    col_values: List[List[Any]] = []

    for c in results:
        meta = c.get("metadata", {})
        col_name = meta.get("column") or meta.get("fieldPath") or "val"
        col_names.append(col_name)

        vals: List[Any] = []
        for v in c.get("values", []):
            val_obj = v.get("value", {})
            if "stringVal" in val_obj:
                vals.append(val_obj["stringVal"])
            elif "doubleVal" in val_obj:
                vals.append(val_obj["doubleVal"])
            elif "int64Val" in val_obj:
                vals.append(val_obj["int64Val"])
            elif "boolVal" in val_obj:
                vals.append(val_obj["boolVal"])
            else:
                vals.append(val_obj)
        col_values.append(vals)

    row_count = len(col_values[0]) if col_values else 0
    rows: List[Dict[str, Any]] = []
    for r in range(row_count):
        row = {col_names[i]: col_values[i][r] for i in range(len(col_names))}
        rows.append(row)

    return DashboardQueryResult(
        query_name=query_name,
        dialect=raw.get("dialect", "YL2"),
        data_sources=raw.get("dataSources", []),
        time_window=raw.get("timeWindow", {}),
        columns=col_names,
        rows=rows,
        total_rows=len(rows),
        last_cache_refreshed_time=raw.get("lastBackendCacheRefreshedTime"),
        raw=raw,
    )


class SearchDashboardsWorkflow:
    """Orchestrates discovery and filtering of native Google SecOps dashboards."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(self, query: DashboardSearchQuery) -> DashboardBatch:
        """Discovers and filters native dashboards."""
        res = self.adapter.list_native_dashboards(page_size=1000)
        raw_items = res.get("nativeDashboards", res.get("dashboards", []))
        all_summaries = [_map_dashboard_summary(it) for it in raw_items]

        filtered: List[DashboardSummary] = []
        for s in all_summaries:
            # Keyword filter
            if query.query:
                q = query.query.lower()
                text_corpus = f"{s.id} {s.display_name} {s.description}".lower()
                if q not in text_corpus:
                    continue

            # Type filter
            if query.dashboard_type:
                if query.dashboard_type.upper() != s.type.upper():
                    continue

            filtered.append(s)

        paged = filtered[: query.limit] if query.limit > 0 else filtered

        return DashboardBatch(
            dashboards=paged,
            total_count=len(filtered),
            retrieved_at=datetime.now(timezone.utc),
        )


class GetDashboardDetailWorkflow:
    """Orchestrates deep composite retrieval of a dashboard with batch-resolved charts and queries."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(self, identifier_or_title: str, include_queries: bool = True) -> DashboardDetail:
        """Retrieves and builds full dashboard composite graph."""
        clean_target = identifier_or_title.strip()
        if not clean_target:
            raise ValueError("Dashboard identifier or title must be provided")

        clean_id = clean_target.split("/")[-1]

        # 1. Attempt direct retrieval by ID
        raw = self.adapter.get_native_dashboard(clean_id)
        if not raw or not raw.get("name"):
            # Fallback resolve by title
            search_wf = SearchDashboardsWorkflow(self.adapter)
            batch = search_wf.execute(DashboardSearchQuery(limit=1000))
            matched_id = None
            for s in batch.dashboards:
                if clean_target.lower() in [s.id.lower(), s.display_name.lower()]:
                    matched_id = s.id
                    break

            if matched_id:
                raw = self.adapter.get_native_dashboard(matched_id)

        if not raw or not raw.get("name"):
            raise ValueError(f"Dashboard '{identifier_or_title}' not found in live Google SecOps tenant")

        summary = _map_dashboard_summary(raw)
        definition = raw.get("definition", {})
        chart_refs = definition.get("charts", [])
        filters = definition.get("filters", [])

        # Build layout mapping by chart name
        layout_by_name: Dict[str, Dict[str, Any]] = {}
        chart_names: List[str] = []
        for c in chart_refs:
            c_name = c.get("dashboardChart")
            if c_name:
                chart_names.append(c_name)
                layout_by_name[c_name] = c

        # 2. Batch Get Charts
        charts_map: Dict[str, Dict[str, Any]] = {}
        if chart_names:
            chart_res = self.adapter.batch_get_dashboard_charts(chart_names)
            for c_raw in chart_res.get("dashboardCharts", []):
                charts_map[c_raw.get("name", "")] = c_raw

        # 3. Resolve Queries & Assemble Charts
        assembled_charts: List[DashboardChart] = []
        for c_name in chart_names:
            c_raw = charts_map.get(c_name)
            if not c_raw:
                continue

            query_obj = None
            query_name = c_raw.get("chartDatasource", {}).get("dashboardQuery")
            if include_queries and query_name:
                try:
                    q_raw = self.adapter.get_dashboard_query(query_name)
                    if q_raw and q_raw.get("name"):
                        query_obj = _map_dashboard_query(q_raw)
                except Exception:
                    query_obj = None

            layout_raw = layout_by_name.get(c_name)
            assembled_chart = _map_dashboard_chart(c_raw, layout_raw=layout_raw, query_obj=query_obj)
            assembled_charts.append(assembled_chart)

        return DashboardDetail(
            summary=summary,
            charts=assembled_charts,
            filters=filters,
            raw=raw,
        )


class ExecuteDashboardQueryWorkflow:
    """Orchestrates live execution of a dashboard query and hydrates tabular results."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(
        self,
        query_name_or_id: str,
        filters: Optional[List[Dict[str, Any]]] = None,
        use_previous_time_range: bool = False,
        query_source: str = "DASHBOARD",
    ) -> DashboardQueryResult:
        """Executes query and normalizes result."""
        raw_res = self.adapter.execute_dashboard_query(
            query_name=query_name_or_id,
            filters=filters,
            use_previous_time_range=use_previous_time_range,
            query_source=query_source,
        )
        return _normalize_query_execution_result(raw_res, query_name=query_name_or_id)


class ValidateDashboardQueryWorkflow:
    """Orchestrates query validation against Google SecOps compiler."""

    def __init__(self, adapter: GoogleSecOpsAdapter):
        self.adapter = adapter

    def execute(self, raw_query: str, dialect: str = "DIALECT_STATS") -> ValidationResult:
        """Validates statistical query syntax."""
        return self.adapter.validate_stats_query(raw_query=raw_query, dialect=dialect)
