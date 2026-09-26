"""Target baselines for change proposals (stale-target protection).

When a proposal is created we record the state of the resource it is based on.
Before the change is applied we read the resource again; if it no longer matches,
someone changed it in the meantime and applying would silently overwrite their
edit, so the merge is refused and the proposal must be redone.

Baseline shapes (stored in ``ChangeProposal.base_revision``):
  rule text:   {"kind": "rule_text", "revision_id", "text_sha256", "captured_at"}
  deployment:  {"kind": "rule_deployment", "enabled", "alerting", "captured_at"}
"""

from datetime import datetime, timezone
import hashlib
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

RULE_TEXT_ACTIONS = frozenset({"PATCH_RULE", "UPDATE_RULE_TEXT"})
RULE_DEPLOYMENT_ACTIONS = frozenset({
    "UPDATE_RULE_DEPLOYMENT",
    "TOGGLE_RULE_DEPLOYMENT",
    "DEPLOY_RULE",
    "UNDEPLOY_RULE",
})


class StaleTargetError(Exception):
    """Raised when the target changed since the proposal was created, or cannot be verified."""

    STALE_TARGET = "STALE_TARGET"
    TARGET_UNVERIFIABLE = "TARGET_UNVERIFIABLE"

    def __init__(self, code: str, message: str, expected: Optional[Dict[str, Any]] = None,
                 current: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.expected = expected or {}
        self.current = current or {}

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "expected": self.expected, "current": self.current}


def supports_baseline(action_type: str) -> bool:
    action = (action_type or "").upper()
    return action in RULE_TEXT_ACTIONS or action in RULE_DEPLOYMENT_ACTIONS


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _read_state(engine: Any, action_type: str, target_resource_id: str) -> Dict[str, Any]:
    """Reads the comparable state of the target. Raises on API failure."""
    action = (action_type or "").upper()
    if action in RULE_TEXT_ACTIONS:
        rule = engine.get_rule(target_resource_id, view="FULL")
        text = getattr(rule, "text", None)
        if text is None:
            text = getattr(rule, "rule_text", "") or ""
        return {
            "kind": "rule_text",
            "revision_id": str(getattr(rule, "revision_id", "") or ""),
            "text_sha256": _sha256(text),
        }
    if action in RULE_DEPLOYMENT_ACTIONS:
        dep = engine.get_rule_deployment(target_resource_id)
        return {
            "kind": "rule_deployment",
            "enabled": bool(getattr(dep, "enabled", False)),
            "alerting": bool(getattr(dep, "alerting", False)),
        }
    raise ValueError(f"No baseline supported for action {action_type}")


def capture_baseline(engine: Any, action_type: str, target_resource_id: str) -> Optional[Dict[str, Any]]:
    """Best-effort snapshot at proposal creation. Returns None if unsupported or unreadable."""
    if engine is None or not target_resource_id or not supports_baseline(action_type):
        return None
    try:
        state = _read_state(engine, action_type, target_resource_id)
    except Exception as err:
        logger.warning("Could not capture baseline for %s (%s): %s", target_resource_id, action_type, err)
        return None
    state["captured_at"] = datetime.now(timezone.utc).isoformat()
    return state


def _matches(expected: Dict[str, Any], current: Dict[str, Any]) -> bool:
    if expected.get("kind") == "rule_text":
        # A revision ID change means a new version was saved, even if the text is identical.
        if expected.get("revision_id") and current.get("revision_id"):
            if expected["revision_id"] != current["revision_id"]:
                return False
        return expected.get("text_sha256") == current.get("text_sha256")
    if expected.get("kind") == "rule_deployment":
        return (bool(expected.get("enabled")) == bool(current.get("enabled"))
                and bool(expected.get("alerting")) == bool(current.get("alerting")))
    return False


def verify_unchanged(engine: Any, action_type: str, target_resource_id: str,
                     baseline: Optional[Dict[str, Any]]) -> bool:
    """Checks the target still matches its baseline before a production write.

    Returns True if verified, False if there was no baseline to check against.
    Raises StaleTargetError if the target changed or could not be read.
    """
    if not baseline or not supports_baseline(action_type):
        return False
    if engine is None:
        raise StaleTargetError(
            StaleTargetError.TARGET_UNVERIFIABLE,
            f"Cannot verify {target_resource_id} is unchanged: no engine available.",
            expected=baseline,
        )
    try:
        current = _read_state(engine, action_type, target_resource_id)
    except Exception as err:
        raise StaleTargetError(
            StaleTargetError.TARGET_UNVERIFIABLE,
            f"Cannot verify {target_resource_id} is unchanged: {err}",
            expected=baseline,
        ) from err

    expected = {k: v for k, v in baseline.items() if k != "captured_at"}
    if not _matches(expected, current):
        raise StaleTargetError(
            StaleTargetError.STALE_TARGET,
            f"{target_resource_id} changed after this proposal was created. "
            "Applying it would overwrite that change; reject it and have the agent redo the proposal.",
            expected=expected,
            current=current,
        )
    return True
