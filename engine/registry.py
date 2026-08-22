"""Workflow Capability Registry for SecOps Workflow Engine.

Provides a unified namespace of capabilities that map directly to engine workflows,
CLI commands, UI actions, and MCP tool definitions.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine.taxonomy import VALID_KINDS, derive_domain, derive_kind


@dataclass
class WorkflowCapability:
    """Represents a discrete or composed capability registered in the engine."""

    capability_id: str
    name: str
    description: str
    category: str  # e.g., 'search', 'investigation', 'entity', 'rule'
    handler: Callable[..., Any]
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    mcp_tool_name: Optional[str] = None
    composed: bool = False
    evidence_path: Optional[str] = None
    # --- Step 2 taxonomy fields (auto-derived when left unset) ---------------
    kind: Optional[str] = None
    domain: Optional[str] = None
    side_effects: List[str] = field(default_factory=list)
    # --- Step 3 composition graph: capability_ids this workflow composes -
    uses: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        """Derive taxonomy fields from existing data; explicit values win."""
        if self.domain is None:
            self.domain = derive_domain(self.capability_id, self.category)
        if self.kind is None:
            self.kind = derive_kind(self.capability_id, self.composed)
        if self.kind not in VALID_KINDS:
            raise ValueError(
                f"Capability '{self.capability_id}' has invalid kind "
                f"'{self.kind}'; must be one of {sorted(VALID_KINDS)}."
            )
        # Invariant: a query is read-only. Catch mislabeling at construction.
        if self.kind == "query" and self.side_effects:
            raise ValueError(
                f"Capability '{self.capability_id}' is kind=query but declares "
                f"side_effects={self.side_effects}; queries must be side-effect free."
            )
        # Invariant: only composed workflows may declare `uses` edges, and a
        # capability may never list itself (trivial cycle). The full DAG /
        # dangling-edge check lives in the capability contract suite, which
        # can see the whole registry at once.
        if self.uses:
            if self.kind != "workflow":
                raise ValueError(
                    f"Capability '{self.capability_id}' declares uses="
                    f"{self.uses!r} but kind={self.kind!r}; only workflows "
                    f"may compose other capabilities."
                )
            if self.capability_id in self.uses:
                raise ValueError(
                    f"Capability '{self.capability_id}' lists itself in "
                    f"uses; a capability cannot compose itself."
                )


class WorkflowRegistry:
    """Central registry tracking all operational workflow capabilities."""

    def __init__(self):
        self._capabilities: Dict[str, WorkflowCapability] = {}

    def register(self, capability: WorkflowCapability) -> None:
        """Registers a workflow capability."""
        self._capabilities[capability.capability_id] = capability

    def get(self, capability_id: str) -> Optional[WorkflowCapability]:
        """Retrieves a capability by ID."""
        return self._capabilities.get(capability_id)

    def list_capabilities(self, category: Optional[str] = None) -> List[WorkflowCapability]:
        """Lists registered capabilities, optionally filtered by category."""
        if category:
            return [c for c in self._capabilities.values() if c.category == category]
        return list(self._capabilities.values())

    def execute(self, capability_id: str, *args, **kwargs) -> Any:
        """Executes a capability by ID."""
        cap = self._capabilities.get(capability_id)
        if not cap:
            raise KeyError(f"Capability '{capability_id}' not found in registry.")
        return cap.handler(*args, **kwargs)


# Global default registry instance
registry = WorkflowRegistry()
