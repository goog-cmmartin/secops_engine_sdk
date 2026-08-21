"""Centralized parsing, normalization, and type conversion helpers for SecOps workflows."""

from datetime import datetime, timezone
from typing import Any, Optional

from engine.domain import CasePriority, CaseStatus


def parse_timestamp(val: Any) -> Optional[datetime]:
    """Parses timestamps in ISO-8601 strings, millisecond epochs, or second epochs into UTC datetime."""
    if not val:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, (int, float)):
        # Milliseconds or seconds epoch
        if val > 1e11:
            return datetime.fromtimestamp(val / 1000.0, tz=timezone.utc)
        return datetime.fromtimestamp(float(val), tz=timezone.utc)
    if isinstance(val, str):
        try:
            if val.isdigit():
                num = int(val)
                if num > 1e11:
                    return datetime.fromtimestamp(num / 1000.0, tz=timezone.utc)
                return datetime.fromtimestamp(float(num), tz=timezone.utc)
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def parse_status(status_str: Optional[str]) -> CaseStatus:
    """Parses raw case status strings into CaseStatus enum."""
    if not status_str:
        return CaseStatus.UNKNOWN
    s = status_str.upper()
    if "OPEN" in s:
        return CaseStatus.OPEN
    if "CLOSE" in s:
        return CaseStatus.CLOSED
    return CaseStatus.UNKNOWN


def parse_priority(priority_str: Optional[str]) -> CasePriority:
    """Parses raw case priority strings into CasePriority enum."""
    if not priority_str:
        return CasePriority.UNKNOWN
    p = priority_str.upper()
    if "CRITICAL" in p:
        return CasePriority.CRITICAL
    if "HIGH" in p:
        return CasePriority.HIGH
    if "MEDIUM" in p:
        return CasePriority.MEDIUM
    if "LOW" in p:
        return CasePriority.LOW
    return CasePriority.UNKNOWN
