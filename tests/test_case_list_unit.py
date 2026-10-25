"""Offline unit tests for `case.list` filter building, item parsing and paging bounds.

No network. The item payload below is copied verbatim from a live response
recorded in discovery/observations/04_case_list_native_collection.md.
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock

from engine.domain import CaseListBatch, CaseListItem, CasePriority, CaseStatus
from engine.workflows.case_list import (
    MAX_PAGE_SIZE,
    ListCasesWorkflow,
    build_case_filter,
    normalize_priority,
    normalize_status,
    parse_case_list_item,
    quote_filter_value,
)

OBSERVED_OPEN_ITEM = {
    "name": "projects/p/locations/us/instances/i/cases/20999",
    "lastModifyingUserId": "Siemplify automation",
    "createTime": "1791328366962",
    "updateTime": "1791329016674",
    "displayName": "ATI High Priority Rule Match for File IoCs (target.file.sha256)",
    "alertCount": 1,
    "stage": "Investigation",
    "priority": "PRIORITY_HIGH",
    "important": False,
    "incident": False,
    "assignee": "@Tier1",
    "type": "EXTERNAL",
    "overflowCase": False,
    "environment": "Demoverse",
    "status": "OPENED",
    "workflowStatus": "PENDING_FOR_USER",
    "source": "Server",
    "involvedSuspiciousEntity": True,
    "moveEnvironment": {},
    "dataAccessScopes": ["i_*"],
}


class TestCaseListFilterBuilder(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(build_case_filter(), "")

    def test_status_aliases(self):
        self.assertEqual(normalize_status("open"), "OPENED")
        self.assertEqual(normalize_status("OPENED"), "OPENED")
        self.assertEqual(normalize_status(CaseStatus.OPEN), "OPENED")
        self.assertEqual(normalize_status("closed"), "CLOSED")
        self.assertEqual(normalize_status(CaseStatus.CLOSED), "CLOSED")
        with self.assertRaises(ValueError):
            normalize_status("UNKNOWN")
        with self.assertRaises(ValueError):
            normalize_status(CaseStatus.UNKNOWN)

    def test_priority_aliases(self):
        self.assertEqual(normalize_priority("critical"), "PRIORITY_CRITICAL")
        self.assertEqual(normalize_priority("PRIORITY_HIGH"), "PRIORITY_HIGH")
        self.assertEqual(normalize_priority(CasePriority.LOW), "PRIORITY_LOW")
        self.assertEqual(normalize_priority("info"), "PRIORITY_INFO")
        with self.assertRaises(ValueError):
            normalize_priority(CasePriority.UNKNOWN)
        with self.assertRaises(ValueError):
            normalize_priority("URGENT")

    def test_single_values(self):
        f = build_case_filter(status="OPEN", environments="Demoverse", priorities="HIGH")
        self.assertEqual(f, 'status="OPENED" AND environment="Demoverse" AND priority="PRIORITY_HIGH"')

    def test_multi_values_or_in_parentheses(self):
        f = build_case_filter(
            status=CaseStatus.OPEN,
            environments=["Demoverse", "Default Environment"],
            priorities=[CasePriority.CRITICAL, "low", "PRIORITY_LOW"],
            stages=["Triage", "Investigation"],
            assignees=["@Tier1"],
        )
        self.assertEqual(
            f,
            'status="OPENED"'
            ' AND (environment="Demoverse" OR environment="Default Environment")'
            ' AND (priority="PRIORITY_CRITICAL" OR priority="PRIORITY_LOW")'
            ' AND (stage="Triage" OR stage="Investigation")'
            ' AND assignee="@Tier1"',
        )

    def test_booleans_unquoted(self):
        f = build_case_filter(is_important=True, is_incident=False)
        self.assertEqual(f, "important=true AND incident=false")
        with self.assertRaises(ValueError):
            build_case_filter(is_important="true")

    def test_raw_filter_passthrough(self):
        f = build_case_filter(status="OPENED", raw_filter=" createTime > 1791000000000 ")
        self.assertEqual(f, '(createTime > 1791000000000) AND status="OPENED"')

    def test_quote_rejects_unescapable(self):
        self.assertEqual(quote_filter_value(" O'Brien ", "environment"), '"O\'Brien"')
        for bad in ('De"mo', "back\\slash", "", "   "):
            with self.assertRaises(ValueError):
                quote_filter_value(bad, "environment")
        with self.assertRaises(ValueError):
            quote_filter_value(3, "environment")
        with self.assertRaises(ValueError):
            build_case_filter(environments=['bad"env'])

    def test_rejects_non_list_container(self):
        with self.assertRaises(ValueError):
            build_case_filter(environments=42)


class TestCaseListItemParsing(unittest.TestCase):
    def test_observed_item(self):
        item = parse_case_list_item(OBSERVED_OPEN_ITEM)
        self.assertIsInstance(item, CaseListItem)
        self.assertEqual(item.case_id, "20999")
        self.assertEqual(item.id, "20999")
        self.assertEqual(item.title, OBSERVED_OPEN_ITEM["displayName"])
        self.assertEqual(item.create_time, datetime.fromtimestamp(1791328366.962, tz=timezone.utc))
        self.assertEqual(item.update_time, datetime.fromtimestamp(1791329016.674, tz=timezone.utc))
        self.assertEqual(item.create_time.tzinfo, timezone.utc)
        self.assertEqual(item.priority, CasePriority.HIGH)
        self.assertEqual(item.raw_priority, "PRIORITY_HIGH")
        self.assertEqual(item.status, CaseStatus.OPEN)
        self.assertEqual(item.raw_status, "OPENED")
        self.assertFalse(item.is_closed)
        self.assertEqual(item.environment, "Demoverse")
        self.assertEqual(item.assignee, "@Tier1")
        self.assertEqual(item.alert_count, 1)
        self.assertTrue(item.involved_suspicious_entity)
        self.assertEqual(item.workflow_status, "PENDING_FOR_USER")
        self.assertEqual(item.case_type, "EXTERNAL")
        self.assertIs(item.raw, OBSERVED_OPEN_ITEM)

    def test_priority_mapping(self):
        for raw, expected in (
            ("PRIORITY_CRITICAL", CasePriority.CRITICAL),
            ("PRIORITY_HIGH", CasePriority.HIGH),
            ("PRIORITY_MEDIUM", CasePriority.MEDIUM),
            ("PRIORITY_LOW", CasePriority.LOW),
            ("PRIORITY_INFO", CasePriority.UNKNOWN),
        ):
            item = parse_case_list_item({**OBSERVED_OPEN_ITEM, "priority": raw})
            self.assertEqual(item.priority, expected, raw)
            self.assertEqual(item.raw_priority, raw)

    def test_closed_status(self):
        item = parse_case_list_item({**OBSERVED_OPEN_ITEM, "status": "CLOSED"})
        self.assertEqual(item.status, CaseStatus.CLOSED)
        self.assertTrue(item.is_closed)

    def test_missing_name_is_an_error(self):
        bad = dict(OBSERVED_OPEN_ITEM)
        del bad["name"]
        with self.assertRaises(ValueError):
            parse_case_list_item(bad)

    def test_bad_alert_count_is_an_error(self):
        with self.assertRaises(ValueError):
            parse_case_list_item({**OBSERVED_OPEN_ITEM, "alertCount": "many"})


def _page(ids, token=None, total=None):
    res = {"cases": [{**OBSERVED_OPEN_ITEM, "name": f"projects/p/locations/us/instances/i/cases/{i}"} for i in ids]}
    if token:
        res["nextPageToken"] = token
    if total is not None:
        res["totalSize"] = total
    return res


class TestCaseListPagingBounds(unittest.TestCase):
    """Paging logic with a scripted adapter (test-only stand-in; no SecOps data synthesized in production)."""

    def test_follows_tokens_and_requests_only_remaining(self):
        adapter = MagicMock()
        adapter.list_cases.side_effect = [_page([1, 2, 3], "t1", 9), _page([4, 5], "t2", 9)]
        batch = ListCasesWorkflow(adapter).execute(status="OPENED", max_results=5, page_size=3)
        self.assertIsInstance(batch, CaseListBatch)
        self.assertEqual([c.case_id for c in batch.cases], ["1", "2", "3", "4", "5"])
        self.assertEqual(batch.total_count, 9)
        self.assertEqual(batch.next_page_token, "t2")
        self.assertTrue(batch.truncated)
        calls = adapter.list_cases.call_args_list
        self.assertEqual(calls[0].kwargs["page_size"], 3)
        self.assertIsNone(calls[0].kwargs["page_token"])
        self.assertEqual(calls[1].kwargs["page_size"], 2)
        self.assertEqual(calls[1].kwargs["page_token"], "t1")
        self.assertEqual(calls[0].kwargs["filter"], 'status="OPENED"')
        self.assertEqual(batch.provenance["pages_fetched"], 2)
        self.assertEqual(batch.provenance["filter"], 'status="OPENED"')
        self.assertEqual(len(batch), 5)

    def test_empty_body_means_zero(self):
        adapter = MagicMock()
        adapter.list_cases.return_value = {}
        batch = ListCasesWorkflow(adapter).execute(environments="NoSuchEnvironment")
        self.assertEqual(batch.total_count, 0)
        self.assertEqual(batch.cases, [])
        self.assertIsNone(batch.next_page_token)
        self.assertFalse(batch.truncated)

    def test_repeated_token_raises(self):
        adapter = MagicMock()
        adapter.list_cases.side_effect = [_page([1], "same", 5), _page([2], "same", 5)]
        with self.assertRaises(RuntimeError):
            ListCasesWorkflow(adapter).execute(max_results=10, page_size=1)

    def test_api_error_propagates(self):
        adapter = MagicMock()
        adapter.list_cases.side_effect = RuntimeError("HTTP 400 bogus field")
        with self.assertRaises(RuntimeError):
            ListCasesWorkflow(adapter).execute(status="OPENED")

    def test_bounds_validation(self):
        wf = ListCasesWorkflow(MagicMock())
        for kwargs in ({"max_results": 0}, {"max_results": True}, {"page_size": 0}, {"page_size": MAX_PAGE_SIZE + 1}):
            with self.assertRaises(ValueError):
                wf.execute(**kwargs)


class TestCaseListAgentPolicy(unittest.TestCase):
    """case.list is an unbounded query: autonomous callers must supply a filter."""

    def test_registration_and_policy(self):
        from engine.facade import SecOpsEngine
        from engine.taxonomy import REQUIRE_FILTER_POLICY_KEY

        engine = SecOpsEngine(adapter=MagicMock())
        cap = engine.registry.get("case.list")
        self.assertIsNotNone(cap)
        self.assertIs(engine.registry.get("list_cases"), cap)
        self.assertEqual(cap.kind, "query")
        self.assertEqual(cap.cardinality, "unbounded")
        self.assertTrue(cap.agent.get(REQUIRE_FILTER_POLICY_KEY))
        for unfiltered in ({}, {"max_results": 5000}, {"page_size": 10, "order_by": "createTime desc"}, {"status": None}):
            with self.assertRaises(ValueError, msg=unfiltered):
                engine.registry.validate_agent_call(cap, **unfiltered)
        for filtered in ({"status": "OPENED"}, {"environments": ["Demoverse"]}, {"filter": "important=true"}):
            engine.registry.validate_agent_call(cap, **filtered)


if __name__ == "__main__":
    unittest.main()
