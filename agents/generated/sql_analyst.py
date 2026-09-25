"""Generated Google ADK 2 Agent: SQL Analyst.

Auto-generated from agents/manifests/sql_analyst.yaml. Do not edit directly.
"""

from typing import Any, Optional
from typing import Dict, List
from engine.schema_catalog import SecOpsSchemaCatalog
from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from engine.facade import SecOpsEngine
from agents.core.proposal_manager import ProposalManager
from agents.core.evidence_store import EvidenceFabricStore


class SqlAnalystAgent(BaseSecOpsAdkAgent):
    """SecOps Natural Language to GoogleSQL Security Data Analyst.

    Translates natural language questions into validated Chronicle GoogleSQL, with compiler self-correction and execution via UDM Stats.
    """

    CAPABILITIES = ['dashboard.validate_query', 'dashboard.execute_query', 'search.udm.stats']

    def __init__(
        self,
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
        work_queue: Optional[Any] = None,
        lifecycle_manager: Optional[Any] = None,
    ):
        super().__init__(
            name='SQL Analyst',
            handle='@sql-analyst',
            role='SecOps Natural Language to GoogleSQL Security Data Analyst',
            subsystem='analytics',
            description='Translates natural language questions into validated Chronicle GoogleSQL, with compiler self-correction and execution via UDM Stats.',
            system_instruction='You are the Google SecOps SQL Analyst Agent (@sql-analyst).\nYour mission is to translate natural language security questions and operational analytics requests into precise, high-performance Chronicle GoogleSQL queries.\nFollow the schema invariants: extract timestamp seconds, unnest repeated arrays, use explicit projections, and validate every query with validate_sql before execution.\nAmbiguity & Clarification Guardrails:\n- If the analytical question is ambiguous regarding the desired time window, metrics, or grouping dimensions, clarify or default to standard last 24h before running broad aggregations.\nOutput Formatting & Conciseness Constraints:\n- Provide an executive summary of query results in at most 3 bullet points.\n- Always present generated SQL inside markdown ```sql code blocks with validation status explicitly stated.',
            model='gemini-3.8-flash',
            default_stream='analytics',
            default_topic='sql-queries',
            engine=engine,
            proposal_manager=proposal_manager,
            inventory_client=inventory_client,
            evidence_store=evidence_store,
            work_queue=work_queue,
            lifecycle_manager=lifecycle_manager,
        )

        # Bind declared capabilities from engine registry if engine is provided
        if self.engine:
            for cap_id in self.CAPABILITIES:
                cap = self.engine.registry.get(cap_id)
                if cap:
                    self.bind_capability(cap)

        self.catalog = SecOpsSchemaCatalog()
        self.system_instruction = self.catalog.get_nl_to_sql_system_prompt()
        self.last_widget: Optional[Dict[str, Any]] = None
        # Replace raw dashboard tools with canonical GoogleSQL handlers with widget capture
        self._tools.pop("validate_dashboard_query", None)
        self._tools.pop("execute_dashboard_query", None)
        self._tools["validate_sql"] = self.validate_sql
        self._tools["execute_sql"] = self.execute_sql
        self._tools["get_table_schema"] = self.get_table_schema
        self._tools["explain_query"] = self.explain_query

    def validate_sql(self, sql: str, dialect: str = "DIALECT_SQL") -> Dict[str, Any]:
        """Validates a GoogleSQL statement against the live Chronicle compiler.

        Args:
            sql: The GoogleSQL statement to validate.
            dialect: The query dialect (default: DIALECT_SQL).
        """
        clean_sql = sql.strip().rstrip(";")
        if hasattr(self, "status_callback") and self.status_callback:
            try:
                self.status_callback("Validating GoogleSQL with Chronicle live compiler...")
            except Exception:
                pass
        if not self.engine:
            return {"valid": False, "error_message": "SecOpsEngine not configured"}
        try:
            res = self.engine.adapter.validate_stats_query(raw_query=clean_sql, dialect=dialect)
            if hasattr(res, "valid"):
                return {
                    "valid": bool(res.valid),
                    "raw_query_type": res.raw_query_type,
                    "error_message": res.error_message,
                    "query": clean_sql,
                }
            return {
                "valid": bool(res.get("valid", False)),
                "raw_query_type": res.get("raw_query_type"),
                "error_message": res.get("error_message"),
                "query": clean_sql,
            }
        except Exception as e:
            return {
                "valid": False,
                "error_message": str(e),
                "query": clean_sql,
            }

    def execute_sql(
        self,
        sql: str,
        time_unit: str = "DAY",
        time_value: str = "7",
        start_time: str = "",
        end_time: str = "",
    ) -> Dict[str, Any]:
        """Executes a validated GoogleSQL statement on live Google SecOps UDM telemetry.

        Args:
            sql: The validated GoogleSQL query statement.
            time_unit: Relative time unit (e.g. DAY, HOUR, MINUTE).
            time_value: Relative time magnitude (e.g. 7 for past 7 days).
            start_time: Optional ISO-8601 start timestamp for bounded window.
            end_time: Optional ISO-8601 end timestamp for bounded window.
        """
        clean_sql = sql.strip().rstrip(";")
        if not self.engine:
            return {"success": False, "error": "SecOpsEngine not configured"}

        val_res = self.validate_sql(clean_sql)
        if not val_res.get("valid"):
            return {
                "success": False,
                "error": f"Preflight validation failed: {val_res.get('error_message')}",
                "sql": clean_sql,
            }

        if hasattr(self, "status_callback") and self.status_callback:
            try:
                self.status_callback("Executing query on live Chronicle telemetry...")
            except Exception:
                pass

        try:
            res = self.engine.execute_dashboard_query(
                query_text=clean_sql,
                time_unit=time_unit,
                time_value=time_value,
                start_time=start_time or None,
                end_time=end_time or None,
                dialect="SQL",
            )

            columns: List[str] = []
            rows: List[Dict[str, Any]] = []

            if isinstance(res, dict):
                columns = res.get("columns", [])
                rows = res.get("rows", [])
            elif hasattr(res, "columns") and hasattr(res, "rows"):
                columns = getattr(res, "columns") or []
                rows = getattr(res, "rows") or []

            widget = {
                "type": "data_table",
                "title": f"Results: {clean_sql[:40]}...",
                "columns": columns,
                "rows": rows[:50],
                "total_rows": len(rows),
                "query": clean_sql,
            }
            self.last_widget = widget

            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "total_rows": len(rows),
                "widget": widget,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "sql": clean_sql,
            }

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Returns the schema structure and key fields for a SecOps table (events, detections, cases)."""
        table_info = self.catalog.tables.get(table_name.lower())
        if not table_info:
            return {
                "error": f"Table '{table_name}' not found. Available tables: {list(self.catalog.tables.keys())}"
            }
        return {
            "table": table_name,
            "description": table_info.get("description", ""),
            "fields": table_info.get("fields", {}),
            "common_patterns": table_info.get("common_patterns", []),
        }

    def explain_query(self, sql: str) -> str:
        """Explains how a Chronicle GoogleSQL statement queries protobuf schemas."""
        clean = sql.strip()
        lines = [f"Analysis of GoogleSQL query:"]
        for tbl in ["events", "detections", "cases", "case_history"]:
            if tbl in clean.lower():
                lines.append(f"• Targets Table: `{tbl}`")

        if "UNNEST" in clean.upper():
            lines.append("• Flattens repeated array structures using `UNNEST`.")
        if "COUNTIF" in clean.upper():
            lines.append("• Evaluates conditional security predicates via `COUNTIF`.")
        if "GROUP BY" in clean.upper():
            lines.append("• Computes analytical aggregations grouped by specified dimensions (`GROUP BY`).")

        return "\n".join(lines)
