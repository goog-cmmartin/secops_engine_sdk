#!/usr/bin/env python3
"""Validation utility for Google SecOps GoogleSQL and PipedSQL queries.

Usage:
    python scripts/validate_sql.py "FROM events |> AGGREGATE COUNT(1) GROUP BY metadata.log_type"
    cat query.sql | python scripts/validate_sql.py
"""

import sys
import os

# Ensure workspace root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
workspace_root = os.path.abspath(os.path.join(current_dir, "../../../.."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

from adapters.google_secops import GoogleSecOpsAdapter


def main():
    if len(sys.argv) > 1:
        query_text = " ".join(sys.argv[1:])
    else:
        query_text = sys.stdin.read().strip()

    if not query_text:
        print("Error: No SQL query provided.", file=sys.stderr)
        sys.exit(1)

    adapter = GoogleSecOpsAdapter()
    
    # If the query explicitly targets the ingestion table, use dashboard validation
    if "ingestion" in query_text.lower():
        try:
            # Append LIMIT 1 if no LIMIT is present to avoid long scans
            test_query = query_text
            if "limit" not in test_query.lower():
                test_query += "\n|> LIMIT 1;" if "|>" in test_query else "\nLIMIT 1;"
            adapter.execute_dashboard_query(query_name="", query_text=test_query, dialect="SQL")
            print("STATUS: VALID (Dashboard Engine)")
            sys.exit(0)
        except Exception as e:
            print("STATUS: INVALID (Dashboard Engine)", file=sys.stderr)
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(2)

    try:
        res = adapter.validate_query(query_text, dialect="DIALECT_SQL")
        if res.valid:
            print("STATUS: VALID (Search Engine)")
            sys.exit(0)
        elif "selecting from ingestion is not supported in search" in (res.error_message or ""):
            # Fallback to dashboard execution for ingestion references
            try:
                adapter.execute_dashboard_query(query_name="", query_text=query_text, dialect="SQL")
                print("STATUS: VALID (Dashboard Engine Fallback)")
                sys.exit(0)
            except Exception as e:
                print("STATUS: INVALID (Dashboard Engine)", file=sys.stderr)
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(2)
        else:
            print("STATUS: INVALID", file=sys.stderr)
            print(f"ERROR: {res.error_message}", file=sys.stderr)
            sys.exit(2)
    except Exception as e:
        print(f"API_ERROR: {e}", file=sys.stderr)
        sys.exit(3)


if __name__ == "__main__":
    main()
