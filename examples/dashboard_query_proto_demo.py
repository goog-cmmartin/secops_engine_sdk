#!/usr/bin/env python3
"""Dashboard Query Validation Demo using SecOps Proto Schemas.

This script demonstrates validating YARA-L 2.0 dashboard queries against
all 10 protocol buffer schemas documented in the secops_protos repository.

Usage:
    python3 examples/dashboard_query_proto_demo.py [query_name]

Examples:
    python3 examples/dashboard_query_proto_demo.py events
    python3 examples/dashboard_query_proto_demo.py cases
    python3 examples/dashboard_query_proto_demo.py all
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import SecOpsEngine
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel

console = Console()

# Verified YARA-L 2.0 queries from secops_protos repository
PROTO_QUERIES = {
    "events": {
        "name": "UDM Events - User Login Status",
        "proto": "udm.proto",
        "description": "Queries unified data model events for user login activity",
        "query": """metadata.event_type = "USER_LOGIN"

match:
  metadata.event_timestamp.seconds,
  security_result.action,
  principal.user.userid,
  target.ip

limit:
  10""",
    },
    "cases": {
        "name": "SOAR Cases - Open Incidents by Priority",
        "proto": "case.proto",
        "description": "Queries open SOAR cases ordered by priority",
        "query": """case.status = "OPENED"

match:
  case.name,
  case.display_name,
  case.stage,
  case.priority

order:
  case.priority desc

limit:
  10""",
    },
    "case_history": {
        "name": "Case History - Recent Closures",
        "proto": "case_history.proto",
        "description": "Queries case activity history for closure events",
        "query": """case_history.case_activity = "CLOSE_CASE"

match:
  case_history.case_response_platform_info.case_id,
  case_history.case_activity,
  case_history.action_time.seconds

limit:
  10""",
    },
    "detections": {
        "name": "Detections - Top Active Rules",
        "proto": "collections.proto",
        "description": "Queries detection collections for active rule triggers",
        "query": """detection.detection.rule_name != ""

match:
  detection.detection.rule_name,
  detection.collection_elements.references.event.metadata.log_type

limit:
  10""",
    },
    "gemini": {
        "name": "Gemini Investigation Agent - Recent Verdicts",
        "proto": "gemini_investigation.proto",
        "description": "Queries AI-assisted investigation results and verdicts",
        "query": """gemini_investigation.id != ""

match:
  gemini_investigation.id,
  gemini_investigation.alert_type,
  gemini_investigation.verdict,
  gemini_investigation.security_token_count

order:
  gemini_investigation.security_token_count desc

limit:
  10""",
    },
    "ingestion": {
        "name": "Ingestion Metrics - By Component",
        "proto": "ingestion.proto",
        "description": "Queries log ingestion metrics and component health",
        "query": """ingestion.component = "Ingestion API"

match:
  ingestion.log_type,
  ingestion.component,
  ingestion.event_time.seconds

limit:
  10""",
    },
    "iocs": {
        "name": "IoC Matches - High-Frequency Indicators",
        "proto": "ioc.proto",
        "description": "Queries indicator of compromise matches from threat feeds",
        "query": """ioc.ioc_value != ""

match:
  ioc.ioc_value,
  ioc.ioc_type,
  ioc.category,
  ioc.severity

limit:
  10""",
    },
    "playbooks": {
        "name": "SOAR Playbooks - Automation Workflows",
        "proto": "playbook.proto",
        "description": "Queries configured SOAR automation playbooks",
        "query": """playbook.name != ""

match:
  playbook.name,
  playbook.display_name,
  playbook.playbook_type

limit:
  10""",
    },
    "rules": {
        "name": "Detection Rules - Active Rules by Detection Count",
        "proto": "rule.proto",
        "description": "Queries enabled detection rules ordered by trigger frequency",
        "query": """rules.live_status = "ENABLED"

match:
  rules.display_name,
  rules.live_status,
  rules.severity,
  rules.author,
  rules.total_detection_count

order:
  rules.total_detection_count desc

limit:
  10""",
    },
    "rulesets": {
        "name": "Rule Sets - Curated Detection Coverage",
        "proto": "ruleset.proto",
        "description": "Queries managed rule sets and their deployment status",
        "query": """ruleset.ruleset != ""

match:
  ruleset.ruleset,
  ruleset.ruleset_family,
  ruleset.precise_live,
  ruleset.broad_live

limit:
  10""",
    },
}


def display_query_info(query_key: str, query_data: dict):
    """Display formatted query information."""
    console.print()
    console.print(Panel(
        f"[bold cyan]{query_data['name']}[/bold cyan]\n"
        f"[dim]Protocol Buffer: {query_data['proto']}[/dim]\n"
        f"[dim]{query_data['description']}[/dim]",
        title=f"Query: {query_key}",
        border_style="cyan"
    ))
    
    syntax = Syntax(query_data['query'], "sql", theme="monokai", line_numbers=False)
    console.print(syntax)


def validate_query(engine: SecOpsEngine, query_key: str, query_data: dict):
    """Validate a dashboard query and display results."""
    display_query_info(query_key, query_data)
    
    console.print(f"\n[yellow]Validating query...[/yellow]")
    
    try:
        validation = engine.validate_dashboard_query(
            raw_query=query_data['query'],
            dialect="DIALECT_STATS"
        )
        
        if not validation.valid:
            console.print(f"[red]✗ Query validation failed:[/red]")
            console.print(f"  Error: {validation.error_message}")
            return False
        
        # Build success table
        table = Table(title="Validation Results", show_header=True, header_style="bold green")
        table.add_column("Property", style="cyan")
        table.add_column("Value", style="white")
        
        table.add_row("Status", "[green]✓ Valid[/green]")
        table.add_row("Dialect", validation.dialect or "STATS")
        
        if validation.raw_query_type:
            table.add_row("Query Type", validation.raw_query_type)
        
        console.print(table)
        return True
        
    except Exception as e:
        console.print(f"[red]✗ Validation error:[/red] {e}")
        return False


def main():
    """Main execution function."""
    # Parse arguments
    if len(sys.argv) < 2:
        console.print("[yellow]Usage:[/yellow] python3 dashboard_query_proto_demo.py [query_name|all]")
        console.print("\n[cyan]Available queries:[/cyan]")
        for key, data in PROTO_QUERIES.items():
            console.print(f"  • {key:15} - {data['name']}")
        console.print(f"  • {'all':15} - Validate all queries")
        sys.exit(1)
    
    query_arg = sys.argv[1].lower()
    
    # Initialize engine
    console.print("[cyan]Initializing SecOps Engine...[/cyan]")
    try:
        engine = SecOpsEngine()
    except Exception as e:
        console.print(f"[red]Failed to initialize engine:[/red] {e}")
        console.print("\n[yellow]Ensure GOOGLE_CLOUD_PROJECT and SECOPS_CUSTOMER_ID are set[/yellow]")
        sys.exit(1)
    
    # Validate requested query/queries
    if query_arg == "all":
        results = {}
        for key, data in PROTO_QUERIES.items():
            results[key] = validate_query(engine, key, data)
        
        # Summary
        console.print("\n" + "="*80)
        console.print("[bold]Validation Summary[/bold]")
        console.print("="*80)
        
        passed = sum(1 for v in results.values() if v)
        total = len(results)
        
        for key, success in results.items():
            status = "[green]✓[/green]" if success else "[red]✗[/red]"
            console.print(f"{status} {key:15} - {PROTO_QUERIES[key]['name']}")
        
        console.print(f"\nPassed: {passed}/{total}")
        
    elif query_arg in PROTO_QUERIES:
        validate_query(engine, query_arg, PROTO_QUERIES[query_arg])
    else:
        console.print(f"[red]Unknown query:[/red] {query_arg}")
        console.print("\n[cyan]Available queries:[/cyan] " + ", ".join(PROTO_QUERIES.keys()) + ", all")
        sys.exit(1)


if __name__ == "__main__":
    main()
