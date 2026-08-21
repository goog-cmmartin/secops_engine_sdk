"""SOAR Playbook Workflow Engine Components.

Implements playbook search, multi-facet filtering, category hierarchy retrieval,
and step-level execution DAG inspection.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from engine.domain import (
    PlaybookBatch,
    PlaybookCategory,
    PlaybookDetail,
    PlaybookSearchQuery,
    PlaybookStep,
    PlaybookStepParameter,
    PlaybookSummary,
    PlaybookTrigger,
    PlaybookTriggerCondition,
    PlaybookType,
)


class SearchPlaybooksWorkflow:
    """Orchestrates SOAR Playbook discovery and multi-facet filtering."""

    def __init__(self, adapter: Optional[Any] = None):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter
            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter

    def execute(self, query: Optional[PlaybookSearchQuery] = None) -> PlaybookBatch:
        q = query or PlaybookSearchQuery()
        types = None
        if q.playbook_type:
            types = [q.playbook_type.value]

        raw_cards = self.adapter.get_playbook_menu_cards(playbook_types=types)
        summaries: List[PlaybookSummary] = []

        query_str = q.query.lower().strip() if q.query else None
        cat_filter = q.category.lower().strip() if q.category else None
        env_filter = q.environment.lower().strip() if q.environment else None

        for card in raw_cards:
            name = card.get("name", "")
            creator_name = card.get("creatorFullName", "")
            identifier = card.get("identifier", "")
            card_id = str(card.get("id", ""))
            category_name = card.get("categoryName", "")
            is_enabled = bool(card.get("isEnabled", False))
            environments = card.get("environments", [])
            pt_str = card.get("playbookType", "REGULAR")

            # Keyword filter
            if query_str:
                matched = (
                    query_str in name.lower()
                    or query_str in creator_name.lower()
                    or query_str in identifier.lower()
                    or query_str == card_id
                )
                if not matched:
                    continue

            # Category filter
            if cat_filter:
                if cat_filter != category_name.lower():
                    continue

            # Enabled filter
            if q.is_enabled is not None:
                if is_enabled != q.is_enabled:
                    continue

            # Environment filter
            if env_filter:
                if not any(env_filter == env.lower() for env in environments):
                    continue

            # Playbook Type enum
            try:
                playbook_type = PlaybookType(pt_str)
            except ValueError:
                playbook_type = PlaybookType.UNKNOWN

            # Parse timestamps
            created_at = None
            if "creationTime" in card and card["creationTime"]:
                try:
                    created_at = datetime.fromisoformat(card["creationTime"].replace("Z", "+00:00"))
                except Exception:
                    pass
            elif "creationTimeUnixTimeInMs" in card and card["creationTimeUnixTimeInMs"]:
                try:
                    ms = int(card["creationTimeUnixTimeInMs"])
                    created_at = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
                except Exception:
                    pass

            modified_at = None
            if "modificationTimeUnixTimeInMs" in card and card["modificationTimeUnixTimeInMs"]:
                try:
                    ms = int(card["modificationTimeUnixTimeInMs"])
                    modified_at = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
                except Exception:
                    pass

            summaries.append(
                PlaybookSummary(
                    id=card_id,
                    identifier=identifier,
                    original_identifier=card.get("originalWorkflowIdentifier", identifier),
                    name=name,
                    is_enabled=is_enabled,
                    is_debug_mode=bool(card.get("isDebugMode", False)),
                    priority=int(card.get("priority", 0)),
                    category_id=int(card.get("categoryId", 0)),
                    category_name=category_name,
                    creator=card.get("creator", ""),
                    creator_full_name=creator_name,
                    environments=environments,
                    playbook_type=playbook_type,
                    has_restricted_environments=bool(card.get("hasRestrictedEnvironments", False)),
                    creation_time=created_at,
                    modification_time=modified_at,
                    raw=card,
                )
            )

        total = len(summaries)
        if q.limit and q.limit > 0:
            summaries = summaries[: q.limit]

        return PlaybookBatch(
            results=summaries,
            total_count=total,
            retrieved_at=datetime.now(timezone.utc),
        )


class GetPlaybookWorkflow:
    """Orchestrates full playbook retrieval and step-level DAG inspection."""

    def __init__(self, adapter: Optional[Any] = None):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter
            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter

    def execute(self, identifier_or_id: str) -> PlaybookDetail:
        target = identifier_or_id.strip()
        if not target:
            raise ValueError("Playbook identifier or ID must not be empty.")

        workflow_identifier = target

        # If numeric ID provided (e.g. "2277"), resolve to UUID identifier via index
        if target.isdigit() or "-" not in target:
            cards = self.adapter.get_playbook_menu_cards()
            found = False
            for c in cards:
                if str(c.get("id")) == target or c.get("name", "").lower() == target.lower():
                    workflow_identifier = c.get("identifier", target)
                    found = True
                    break
            if not found:
                # Still try target directly
                workflow_identifier = target

        raw_info = self.adapter.get_playbook_full_info(workflow_identifier=workflow_identifier)
        if not raw_info:
            raise RuntimeError(f"Playbook '{target}' not found on live Google SecOps endpoint.")

        # Parse Trigger
        trigger_obj = None
        raw_trig = raw_info.get("trigger")
        if isinstance(raw_trig, dict):
            conditions: List[PlaybookTriggerCondition] = []
            for cond in raw_trig.get("conditions", []):
                conditions.append(
                    PlaybookTriggerCondition(
                        value=cond.get("value", ""),
                        match_type=cond.get("matchType", "EQUAL"),
                    )
                )
            trigger_obj = PlaybookTrigger(
                id=str(raw_trig.get("id", "")),
                identifier=raw_trig.get("identifier", ""),
                trigger_type=raw_trig.get("type", ""),
                logical_operator=raw_trig.get("logicalOperator", "AND"),
                conditions=conditions,
                reaction_logical_operator=raw_trig.get("reactionLogicalOperator", "OR"),
                raw=raw_trig,
            )

        # Parse Steps
        steps: List[PlaybookStep] = []
        for s in raw_info.get("steps", []):
            params: List[PlaybookStepParameter] = []
            for p in s.get("parameters", []):
                params.append(
                    PlaybookStepParameter(
                        name=p.get("name", ""),
                        value=p.get("value"),
                        is_mandatory=bool(p.get("isMandatory", False)),
                    )
                )
            steps.append(
                PlaybookStep(
                    identifier=s.get("identifier", ""),
                    original_step_identifier=s.get("originalStepIdentifier", ""),
                    name=s.get("name", ""),
                    instance_name=s.get("instanceName", ""),
                    integration=s.get("integration", ""),
                    action_name=s.get("actionName", ""),
                    action_provider=s.get("actionProvider", ""),
                    step_type=s.get("type", "ACTION"),
                    description=s.get("description", ""),
                    is_automatic=bool(s.get("isAutomatic", True)),
                    is_skippable=bool(s.get("isSkippable", False)),
                    auto_skip_on_failure=bool(s.get("autoSkipOnFailure", False)),
                    parameters=params,
                    workflow_identifier=s.get("workflowIdentifier", workflow_identifier),
                    raw=s,
                )
            )

        # Parse playbook type
        pt_str = raw_info.get("playbookType", "REGULAR")
        try:
            playbook_type = PlaybookType(pt_str)
        except ValueError:
            playbook_type = PlaybookType.UNKNOWN

        # Parse timestamps
        created_at = None
        if "creationTimeUnixTimeInMs" in raw_info and raw_info["creationTimeUnixTimeInMs"]:
            try:
                ms = int(raw_info["creationTimeUnixTimeInMs"])
                created_at = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            except Exception:
                pass

        modified_at = None
        if "modificationTimeUnixTimeInMs" in raw_info and raw_info["modificationTimeUnixTimeInMs"]:
            try:
                ms = int(raw_info["modificationTimeUnixTimeInMs"])
                modified_at = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            except Exception:
                pass

        return PlaybookDetail(
            id=str(raw_info.get("id", "")),
            identifier=raw_info.get("identifier", workflow_identifier),
            name=raw_info.get("name", "Untitled Playbook"),
            description=raw_info.get("description", ""),
            is_enabled=bool(raw_info.get("isEnabled", False)),
            is_debug_mode=bool(raw_info.get("isDebugMode", False)),
            priority=int(raw_info.get("priority", 0)),
            category_id=int(raw_info.get("categoryId", 0)),
            category_name=raw_info.get("categoryName", ""),
            creator=raw_info.get("creator", ""),
            modified_by=raw_info.get("modifiedBy"),
            environments=raw_info.get("environments", []),
            playbook_type=playbook_type,
            trigger=trigger_obj,
            steps=steps,
            creation_time=created_at,
            modification_time=modified_at,
            raw=raw_info,
        )


class ListPlaybookCategoriesWorkflow:
    """Lists all SOAR Playbook categories/folders."""

    def __init__(self, adapter: Optional[Any] = None):
        if adapter is None:
            from adapters.google_secops import GoogleSecOpsAdapter
            adapter = GoogleSecOpsAdapter()
        self.adapter = adapter

    def execute(self) -> List[PlaybookCategory]:
        raw_cats = self.adapter.get_playbook_categories()
        categories: List[PlaybookCategory] = []
        for cat in raw_cats:
            categories.append(
                PlaybookCategory(
                    id=str(cat.get("id", "")),
                    name=cat.get("name", ""),
                    category_state=cat.get("categoryState", "FULL"),
                    category_type=cat.get("type", "REGULAR"),
                    is_default=bool(cat.get("isDefaultCategory", False)),
                    raw=cat,
                )
            )
        return categories
