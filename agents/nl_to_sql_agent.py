"""Google ADK 2 Natural Language to GoogleSQL Agent for Google SecOps.

Translates natural language security questions and investigation intents
into strictly validated Chronicle GoogleSQL queries, grounded by Protocol Buffer
schemas (udm.proto, collections.proto, case.proto, case_history.proto), with
self-correcting compiler validation pre-checks and live execution via UDM stats.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import re
import sys
from typing import Any, Dict, List, Optional

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from agents.core.base_adk_agent import BaseSecOpsAdkAgent
from agents.core.evidence_store import EvidenceFabricStore
from agents.core.proposal_manager import ProposalManager
from engine.facade import SecOpsEngine
from engine.schema_catalog import SecOpsSchemaCatalog

logger = logging.getLogger(__name__)


class SecOpsNL2SQLAgent(BaseSecOpsAdkAgent):
    """SecOps Natural Language to GoogleSQL Security Data Analyst Agent (@sql-analyst)."""

    CAPABILITIES = [
        "dashboard.validate_query",
        "dashboard.execute_query",
        "search.udm.stats",
    ]

    def __init__(
        self,
        engine: Optional[SecOpsEngine] = None,
        proposal_manager: Optional[ProposalManager] = None,
        inventory_client: Any = None,
        evidence_store: Optional[EvidenceFabricStore] = None,
    ):
        self.catalog = SecOpsSchemaCatalog()
        self.last_widget: Optional[Dict[str, Any]] = None

        system_instruction = self._build_system_instruction()

        super().__init__(
            name="SQL Analyst",
            handle="@sql-analyst",
            role="SecOps Natural Language to GoogleSQL Security Data Analyst",
            subsystem="analytics",
            description="Translates natural language security questions into validated Chronicle GoogleSQL, with compiler self-correction and execution via UDM Stats.",
            system_instruction=system_instruction,
            model="gemini-3.8-flash",
            default_stream="analytics",
            default_topic="sql-queries",
            engine=engine,
            proposal_manager=proposal_manager,
            inventory_client=inventory_client,
            evidence_store=evidence_store,
        )

        # Bind core tools
        self._tools["validate_sql"] = self.validate_sql
        self._tools["execute_sql"] = self.execute_sql
        self._tools["get_table_schema"] = self.get_table_schema
        self._tools["explain_query"] = self.explain_query

    def _build_system_instruction(self) -> str:
        """Constructs system instruction with schema catalog grounding and dialect invariants."""
        catalog_prompt = self.catalog.get_grounding_prompt()

        few_shots = []
        for eg in self.catalog.FEW_SHOT_EXAMPLES:
            few_shots.append(f"User Question: {eg['question']}\n```sql\n{eg['sql']}\n```\n")

        examples_text = "\n".join(few_shots)

        return f"""You are the Google SecOps SQL Analyst Agent (@sql-analyst).
Your mission is to answer security and operational telemetry questions by generating and executing Chronicle GoogleSQL queries.

{catalog_prompt}

# MANDATORY WORKFLOW FOR EVERY QUERY:
1. SCHEMA RESOLUTION: Determine the target table(s) (`events`, `detections`, `cases`, `case_history`, `rules`) and required fields. You can call `get_table_schema(table_name)` if you need field specifics.
2. SYNTAX GENERATION: Draft the Chronicle GoogleSQL query adhering strictly to the compiler invariants above (e.g. `TIMESTAMP_SECONDS`, unnesting `ARRAY<T>`, explicit column projections on cases).
3. COMPILER PREFLIGHT VALIDATION: ALWAYS call `validate_sql(sql)` BEFORE presenting or executing the query.
4. SELF-HEALING / ERROR CORRECTION: If `validate_sql` returns valid=False, carefully inspect the compiler `error_message`. Fix the specific syntax, type, array unnest, or column issue and re-validate (up to 3 attempts).
5. MANDATORY EXECUTION: Once valid=True, ALWAYS call `execute_sql(sql, time_unit='DAY', time_value='7')` to execute against live Chronicle data and render the results data table. Do NOT stop after generating or validating the SQL query unless the user specifically requested 'Write the SQL query' or 'Show me the SQL syntax only'.
6. RESPONSE FORMAT:
   - Provide a concise summary of the security intent.
   - Present the validated GoogleSQL query in a ```sql block.
   - Explain the query's key components and security relevance.
   - Summarize the query results and data observations from the live execution.

# CANONICAL REFERENCE EXAMPLES:
{examples_text}
"""

    def validate_sql(self, sql: str, dialect: str = "DIALECT_SQL") -> Dict[str, Any]:
        """Validates a GoogleSQL statement against Chronicle's live stats compiler.

        Args:
            sql: The GoogleSQL statement to validate.
            dialect: Query dialect ('DIALECT_SQL').

        Returns:
            Dict containing 'valid' (bool), 'error_message' (str or None), and 'raw_query_type'.
        """
        clean_sql = sql.strip().rstrip(";")
        if hasattr(self, "status_callback") and self.status_callback:
            try:
                self.status_callback("Validating GoogleSQL with Chronicle live compiler...")
            except Exception:
                pass
        if not self.engine:
            return {"valid": False, "error_message": "SecOpsEngine not configured", "dialect": dialect}

        try:
            res = self.engine.adapter.validate_stats_query(raw_query=clean_sql, dialect=dialect)
            return {
                "valid": bool(res.valid),
                "error_message": res.error_message,
                "raw_query_type": res.raw_query_type,
                "query": clean_sql,
                "dialect": dialect,
            }
        except Exception as e:
            return {
                "valid": False,
                "error_message": str(e),
                "dialect": dialect,
            }

    def execute_sql(
        self,
        sql: str,
        time_unit: str = "DAY",
        time_value: str = "7",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes a validated GoogleSQL query against live Google SecOps and returns tabular results.

        Args:
            sql: The validated GoogleSQL query string.
            time_unit: Relative time unit ('DAY', 'HOUR', 'WEEK', 'MONTH'). Default is 'DAY'.
            time_value: Relative time quantity (e.g. '1', '7', '30'). Default is '7'.
            start_time: Optional RFC3339 start timestamp (e.g. '2026-09-10T00:00:00Z').
            end_time: Optional RFC3339 end timestamp (e.g. '2026-09-20T00:00:00Z').

        Returns:
            Dict containing 'columns', 'rows', 'row_count', and execution metadata.
        """
        if hasattr(self, "status_callback") and self.status_callback:
            try:
                self.status_callback("Executing query on live Chronicle telemetry...")
            except Exception:
                pass
        if not self.engine:
            return {"error": "SecOpsEngine not configured"}

        clean_sql = sql.strip().rstrip(";")
        try:
            res = self.engine.execute_dashboard_query(
                query_text=clean_sql,
                dialect="SQL",
                time_unit=time_unit,
                time_value=str(time_value),
                start_time=start_time,
                end_time=end_time,
            )

            widget = {
                "type": "data_table",
                "title": "GoogleSQL Query Results",
                "columns": res.columns,
                "rows": res.rows[:50],
                "total_rows": len(res.rows),
                "query": clean_sql,
            }
            self.last_widget = widget

            return {
                "success": True,
                "columns": res.columns,
                "rows": res.rows[:50],
                "row_count": len(res.rows),
                "total_returned": len(res.rows),
            }
        except Exception as e:
            logger.error(f"Failed to execute GoogleSQL: {e}")
            return {
                "success": False,
                "error": str(e),
                "columns": [],
                "rows": [],
                "row_count": 0,
            }

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Returns the schema definition and fields for a specific SecOps table.

        Args:
            table_name: Table name ('events', 'detections', 'cases', 'case_history', 'rules').
        """
        schema = self.catalog.get_table_schema(table_name)
        if not schema:
            return {
                "error": f"Unknown table '{table_name}'. Available tables: {self.catalog.list_tables()}"
            }
        return schema

    def explain_query(self, sql: str) -> str:
        """Explains the security logic, table sources, and aggregation metrics of a GoogleSQL query."""
        clean = sql.strip()
        lines = [f"Analysis of GoogleSQL query:"]
        for tbl in self.catalog.list_tables():
            if re.search(rf"\b{tbl}\b", clean, re.IGNORECASE):
                lines.append(f"• Targets Table: `{tbl}`")

        if "UNNEST" in clean.upper():
            lines.append("• Flattens repeated array structures using `UNNEST`.")
        if "COUNTIF" in clean.upper():
            lines.append("• Evaluates conditional security predicates via `COUNTIF`.")
        if "GROUP BY" in clean.upper():
            lines.append("• Computes analytical aggregations grouped by specified dimensions (`GROUP BY`).")

        return "\n".join(lines)


if __name__ == "__main__":
    agent = SecOpsNL2SQLAgent(engine=SecOpsEngine())
    test_q = "SELECT metadata.event_type, count(*) AS total FROM events GROUP BY 1 LIMIT 5"
    print("Validating:", test_q)
    v_res = agent.validate_sql(test_q)
    print("Validation Result:", v_res)
    if v_res.get("valid"):
        print("Executing:")
        e_res = agent.execute_sql(test_q)
        print("Columns:", e_res.get("columns"))
        print("Rows count:", e_res.get("row_count"))
        for r in e_res.get("rows", []):
            print(" ", r)
