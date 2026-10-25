"""Unit tests for SecOps MCP response evaluator and patcher."""

import unittest
from engine.mcp_response_patcher import (
    patch_secops_tool_response,
    prune_deep_object,
)


class TestMcpResponsePatcher(unittest.TestCase):

    def test_prune_deep_object_bounds_recursion(self):
        deep = {"a": {"b": {"c": {"d": {"e": {"f": "too deep"}}}}}}
        pruned = prune_deep_object(deep, max_depth=3)
        self.assertIn("a", pruned)
        self.assertIn("b", pruned["a"])
        self.assertIn("c", pruned["a"]["b"])
        # At depth 3, d should be summarized
        self.assertTrue(isinstance(pruned["a"]["b"]["c"], str))
        self.assertIn("Object with", pruned["a"]["b"]["c"])

    def test_prune_deep_object_bounds_arrays(self):
        long_arr = list(range(100))
        pruned = prune_deep_object(long_arr)
        self.assertEqual(len(pruned), 15)

    def test_prune_deep_object_strips_empty(self):
        obj = {"valid": 123, "empty_dict": {}, "empty_list": [], "empty_none": None}
        pruned = prune_deep_object(obj)
        self.assertEqual(pruned, {"valid": 123})

    def test_patch_list_feeds(self):
        raw = {
            "feeds": [
                {
                    "name": "projects/p/locations/us/instances/c/feeds/feed-1",
                    "displayName": "CrowdStrike EDR",
                    "details": {
                        "feedSourceType": "AMAZON_S3_V2",
                        "logType": "CS_EDR",
                        "amazonS3V2Settings": {"s3Uri": "s3://bucket/"},
                        "emptySettings": {},
                    },
                    "state": "SUCCEEDED",
                    "uid": "feed-1",
                }
            ]
        }
        res = patch_secops_tool_response("list_feeds", raw)
        self.assertEqual(res["totalFeeds"], 1)
        self.assertEqual(res["feeds"][0]["feedId"], "feed-1")
        self.assertEqual(res["feeds"][0]["displayName"], "CrowdStrike EDR")
        self.assertIn("settings", res["feeds"][0])
        self.assertNotIn("emptySettings", res["feeds"][0])

    def test_patch_feed_operation(self):
        raw = {
            "name": "projects/p/locations/us/instances/c/feeds/feed-2",
            "displayName": "PubSub Feed",
            "details": {
                "feedSourceType": "HTTPS_PUSH_GOOGLE_CLOUD_PUBSUB",
                "logType": "GCP_CLOUDAUDIT",
            },
            "state": "ACTIVE",
            "uid": "feed-2",
        }
        res = patch_secops_tool_response("create_feed", raw)
        self.assertEqual(res["operation"], "create_feed")
        self.assertEqual(res["feedId"], "feed-2")
        self.assertEqual(res["logType"], "GCP_CLOUDAUDIT")

    def test_patch_udm_search(self):
        raw = {
            "events": [
                {
                    "metadata": {"eventType": "USER_LOGIN", "productName": "Okta"},
                    "principal": {"user": {"userid": "admin@example.com"}, "ip": "1.2.3.4"},
                    "target": {"hostname": "corp-srv"},
                    "securityResult": [{"action": "BLOCK", "severity": "HIGH"}],
                }
            ]
        }
        res = patch_secops_tool_response("udm_search", raw)
        self.assertEqual(res["totalEventsMatched"], 1)
        self.assertEqual(res["events"][0]["eventType"], "USER_LOGIN")
        self.assertEqual(res["events"][0]["principal"]["user"], "admin@example.com")
        self.assertEqual(res["events"][0]["securityResult"][0]["action"], "BLOCK")

    def test_patch_security_alerts(self):
        raw = {
            "alerts": {
                "alerts": [
                    {
                        "id": "alert-99",
                        "detection": [{"ruleName": "Suspicious PowerShell", "ruleId": "ru_123"}],
                        "feedbackSummary": {"status": "OPEN", "severityDisplay": "HIGH"},
                        "events": [{"dummy": 1}, {"dummy": 2}],
                    }
                ]
            }
        }
        res = patch_secops_tool_response("list_security_alerts", raw)
        self.assertEqual(res["totalAlerts"], 1)
        self.assertEqual(res["alerts"][0]["ruleName"], "Suspicious PowerShell")
        self.assertEqual(res["alerts"][0]["matchedEventsCount"], 2)
        # Raw events should NOT be embedded inside alert
        self.assertNotIn("events", res["alerts"][0])

    def test_patch_search_raw_logs(self):
        raw = {
            "rawLogs": [
                {
                    "timestamp": "2026-09-29T10:00:00Z",
                    "logType": {"displayName": "GCP Audit"},
                    "rawText": "A" * 1000,
                }
            ]
        }
        res = patch_secops_tool_response("search_raw_logs", raw)
        self.assertEqual(res["totalLogsMatched"], 1)
        self.assertTrue(len(res["logs"][0]["snippet"]) <= 325)
        self.assertTrue(res["logs"][0]["snippet"].endswith("... [truncated]"))

    def test_patch_investigation(self):
        raw = {
            "investigation": {
                "id": "inv-101",
                "status": "COMPLETED",
                "verdict": "MALICIOUS",
                "summary": "Compromised credential activity detected.",
                "findings": [{"title": "Brute force", "severity": "CRITICAL", "description": "100 failed logins"}],
                "recommendations": ["Reset password"],
            }
        }
        res = patch_secops_tool_response("get_investigation_by_id", raw)
        self.assertEqual(res["investigationId"], "inv-101")
        self.assertEqual(res["verdict"], "MALICIOUS")
        self.assertEqual(len(res["findings"]), 1)

    def test_patch_entity(self):
        raw = {
            "entityId": "e-1",
            "entityType": "IP_ADDRESS",
            "displayName": "192.168.1.50",
            "riskScore": 85,
            "associatedUsers": ["alice", "bob"],
        }
        res = patch_secops_tool_response("summarize_entity", raw)
        self.assertEqual(res["entityId"], "e-1")
        self.assertEqual(res["riskScore"], 85)

    def test_patch_preserves_explicit_errors(self):
        err = {"error": "Access Denied 403"}
        res = patch_secops_tool_response("udm_search", err)
        self.assertEqual(res, err)


if __name__ == "__main__":
    unittest.main()
