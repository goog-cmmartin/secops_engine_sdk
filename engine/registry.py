"""Workflow Capability Registry for SecOps Workflow Engine.

Provides a unified namespace of capabilities that map directly to engine workflows,
CLI commands, UI actions, and MCP tool definitions.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


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
