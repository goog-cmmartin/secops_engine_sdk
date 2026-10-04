"""Google ADK Autonomous MITRE ATT&CK Strategic Mapping Agent.

Connects the SecOps Engine SDK workflows to a Google ADK Agent for
contextual threat profile mapping, live ingestion telemetry correlation,
resilience scoring, and tactical blind-spot discovery.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

# Ensure project root is in PYTHONPATH
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.facade import SecOpsEngine
from engine.domain import MitreCoverageAssessment


# ----------------------------------------------------------------------
# 1. SDK Tools Exposed to ADK
# ----------------------------------------------------------------------

_ENGINE: Optional[SecOpsEngine] = None


def get_engine() -> SecOpsEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = SecOpsEngine()
    return _ENGINE


def audit_mitre_coverage(
    profile_id: str = "global_baseline",
    time_unit: str = "DAY",
    time_value: str = "7",
) -> str:
    """Evaluates tenant detection rules and live telemetry against MITRE ATT&CK.

    Args:
        profile_id: Target industry threat profile (e.g. 'global_baseline',
          'financial_services', 'cloud_native', 'healthcare_critical',
          'critical_infrastructure').
        time_unit: Telemetry lookback unit ('DAY', 'HOUR').
        time_value: Lookback quantity string.

    Returns:
        JSON string containing the MitreCoverageAssessment with coverage scores,
        tactical visibility counts, blind tactics, and technique breakdowns.
    """
    engine = get_engine()
    assessment = engine.analyze_mitre_coverage(
        profile_id=profile_id,
        sync_cache_if_empty=True,
        time_unit=time_unit,
        time_value=time_value,
    )

    result = {
        "profile_id": assessment.profile_id,
        "profile_name": assessment.profile_name,
        "coverage_score": round(assessment.coverage_score, 2),
        "validated_technique_count": assessment.validated_technique_count,
        "total_rules_evaluated": assessment.total_rules_evaluated,
        "enabled_rules_count": assessment.enabled_rules_count,
        "visibility_tactics_count": assessment.visibility_tactics_count,
        "detection_tactics_count": assessment.detection_tactics_count,
        "blind_tactics": assessment.blind_tactics,
        "critical_techniques_uncovered": assessment.critical_techniques,
        "visibility_gaps_count": len(assessment.visibility_gaps),
        "visibility_gaps": assessment.visibility_gaps[:10],
        "detection_gaps_count": len(assessment.detection_gaps),
        "detection_gaps": assessment.detection_gaps[:10],
        "resilient_techniques_count": len(assessment.resilient_techniques),
        "fragile_techniques_count": len(assessment.fragile_techniques),
        "created_at": assessment.created_at,
    }
    return json.dumps(result, indent=2, default=str)


def sync_mitre_rules_cache(
    force_refresh: bool = False,
    max_rules: Optional[int] = None,
) -> str:
    """Synchronizes customer and Content Hub Marketplace rules to Firestore cache.

    Args:
        force_refresh: Whether to force re-download of all rules.
        max_rules: Optional cap for testing or partial runs.

    Returns:
        JSON string with count of synchronized rules and MITRE techniques mapped.
    """
    engine = get_engine()
    res = engine.sync_mitre_rules(
        force_refresh=force_refresh,
        include_curated=True,
        max_rules=max_rules,
    )
    return json.dumps(res, indent=2, default=str)


def get_technique_rules(technique_id: str) -> str:
    """Retrieves all detection rules mapped to a specific MITRE ATT&CK technique.

    Args:
        technique_id: MITRE technique or sub-technique ID (e.g. 'T1059', 'T1059.001').

    Returns:
        JSON string listing detection rules with rule IDs, names, authors, and severities.
    """
    engine = get_engine()
    rules = engine.get_technique_rules(technique_id=technique_id)
    return json.dumps(
        {
            "technique_id": technique_id,
            "rule_count": len(rules),
            "rules": rules,
        },
        indent=2,
        default=str,
    )


def list_mitre_threat_profiles() -> str:
    """Lists all available industry threat profiles and their risk-weighted techniques.

    Returns:
        JSON string detailing supported threat profiles.
    """
    engine = get_engine()
    profiles = engine.list_mitre_threat_profiles()
    return json.dumps(profiles, indent=2, default=str)


def generate_mitre_report(profile_id: str = "global_baseline") -> str:
    """Generates an executive-ready Markdown report of MITRE ATT&CK posture.

    Args:
        profile_id: Target industry threat profile.

    Returns:
        Markdown-formatted executive summary report.
    """
    engine = get_engine()
    res = engine.generate_mitre_report(profile_id=profile_id)
    if isinstance(res, dict):
        return res.get("markdown", str(res))
    return str(res)


# ----------------------------------------------------------------------
# 2. ADK Agent Factory
# ----------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are the SecOps MITRE ATT&CK Strategic Mapping Agent, an autonomous security operations agent.
Your mission is to map tenant detection rules and live ingestion telemetry against the MITRE ATT&CK Enterprise Matrix (v18.1),
evaluating posture across industry threat profiles (Financial Services, Cloud-Native, Ransomware Defense, Critical Infrastructure).

Guidelines:
1. Call `audit_mitre_coverage()` to compute contextual coverage scores, tactical visibility, and single points of failure.
2. If critical technique gaps or blind tactics are found, call `get_technique_rules()` to inspect mapped detections.
3. Call `list_mitre_threat_profiles()` to evaluate industry-tailored threat scenarios.
4. Distinguish between Visibility Gaps (telemetry missing) and Detection Gaps (rules missing).
5. Highlight Single Points of Failure (techniques defended by exactly 1 rule) versus Resilient Detections (>= 2 rules).
6. Provide concise, actionable remediation steps for detection engineering and telemetry ingestion.
"""


def create_mitre_agent():
    """Creates a configured Google ADK Agent instance."""
    try:
        from google.adk import Agent
        from google.adk.tools import FunctionTool

        tools = [
            FunctionTool(audit_mitre_coverage),
            FunctionTool(sync_mitre_rules_cache),
            FunctionTool(get_technique_rules),
            FunctionTool(list_mitre_threat_profiles),
            FunctionTool(generate_mitre_report),
        ]

        agent = Agent(
            name="secops_mitre_attack_agent",
            model="gemini-2.5-pro",
            instructions=SYSTEM_INSTRUCTION,
            tools=tools,
        )
        return agent
    except ImportError as e:
        print(f"[ADK Warning] Google ADK package import issue: {e}", file=sys.stderr)
        return None


# ----------------------------------------------------------------------
# 3. Direct Runner & Execution CLI
# ----------------------------------------------------------------------

def run_direct_audit(profile_id: str = "global_baseline") -> None:
    """Executes a direct audit pass using the underlying SDK workflows."""
    print("==================================================================")
    print("  Google SecOps Autonomous MITRE ATT&CK Agent (Direct Audit Mode)")
    print("==================================================================\n")

    res_str = audit_mitre_coverage(profile_id=profile_id)
    data = json.loads(res_str)

    score = data.get("coverage_score", 0.0)
    score_pill = f"[{score:.1f}%]"

    print(f"Target Profile:        {data.get('profile_name')} ({data.get('profile_id')})")
    print(f"Coverage Score:        {score_pill}")
    print(f"Covered Techniques:    {data.get('validated_technique_count', 0)}")
    print(f"Total Rules Evaluated: {data.get('total_rules_evaluated', 0):,}")
    print(f"Active Enabled Rules:  {data.get('enabled_rules_count', 0):,}")
    print(f"Tactical Visibility:   {data.get('visibility_tactics_count', 0)} / 14 tactics")
    print(f"Tactical Detections:   {data.get('detection_tactics_count', 0)} / 14 tactics")
    print("------------------------------------------------------------------")
    print(f"Resilient Techniques:  {data.get('resilient_techniques_count', 0)} (>=2 rules)")
    print(f"Fragile Detections:    {data.get('fragile_techniques_count', 0)} (Single Point of Failure)")
    print(f"Visibility Gaps:       {data.get('visibility_gaps_count', 0)}")
    print(f"Detection Gaps:        {data.get('detection_gaps_count', 0)}")
    print(f"Blind Tactics:         {len(data.get('blind_tactics', []))}")
    if data.get("blind_tactics"):
        print(f"  • {', '.join(data['blind_tactics'])}")
    print("==================================================================\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Google SecOps Autonomous MITRE ATT&CK Agent")
    parser.add_argument("--profile", default="global_baseline", help="Target threat profile")
    parser.add_argument("--technique", help="Inspect rules for a specific MITRE technique")
    parser.add_argument("--sync", action="store_true", help="Sync rules cache from SecOps")
    parser.add_argument("--report", action="store_true", help="Print executive Markdown report")
    parser.add_argument("--profiles", action="store_true", help="List available threat profiles")

    args = parser.parse_args()

    if args.profiles:
        print(list_mitre_threat_profiles())
    elif args.sync:
        print("Synchronizing rules cache...")
        print(sync_mitre_rules_cache())
    elif args.technique:
        print(get_technique_rules(args.technique))
    elif args.report:
        print(generate_mitre_report(args.profile))
    else:
        run_direct_audit(args.profile)


if __name__ == "__main__":
    main()
