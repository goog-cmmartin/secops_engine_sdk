import unittest
from engine.facade import SecOpsEngine
from tests.test_helpers import get_live_engine


class TestMilestone72CaseUpdates(unittest.TestCase):
    """Acceptance tests for Case update capabilities and lifecycle management."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_case_update_capabilities_registered(self):
        """Verify new case update capabilities are registered in the capability registry."""
        capabilities = {c.capability_id: c for c in self.engine.registry.list_capabilities()}

        expected_ids = [
            "case.update",
            "case.assign",
            "case.set_stage",
            "case.set_incident",
            "case_alert.update",
            "case_alert.set_priority",
            "case_alert.create_recommendation",
            "case_alert.fetch_recommendation",
            "case_alert.get_recommendation",
        ]
        for cap_id in expected_ids:
            self.assertIn(cap_id, capabilities, f"Missing registered capability: {cap_id}")
            cap = capabilities[cap_id]
            self.assertEqual(cap.domain, "case")

    def test_live_case_assignment_and_stage_updates(self):
        """Tests mutating case assignee and stage against live Google SecOps and restoring original values."""
        # Query a live case to use as test target
        cases_batch = self.engine.search_cases(page_size=1)
        if not cases_batch.results:
            self.skipTest("No live cases available for testing.")

        target_case_id = cases_batch.results[0].case_id
        orig_case = self.engine.adapter.get_case(target_case_id)
        orig_assignee = orig_case.get("assignee")
        orig_stage = orig_case.get("stage")
        orig_incident = orig_case.get("incident", False)

        try:
            # 1. Test role assignment (@Tier1)
            res1 = self.engine.assign_case(case_id=target_case_id, assignee="@Tier1")
            self.assertEqual(res1.case_id, target_case_id)
            self.assertEqual(res1.assignee, "@Tier1")

            # 2. Test stage transition
            res2 = self.engine.set_case_stage(case_id=target_case_id, stage="Assessment")
            self.assertEqual(res2.case_id, target_case_id)
            self.assertEqual(res2.stage, "Assessment")

            # 3. Test incident marker
            res3 = self.engine.set_case_incident(case_id=target_case_id, incident=True)
            self.assertEqual(res3.case_id, target_case_id)
            self.assertTrue(res3.incident)

        finally:
            # Restore original state
            restore_updates = {}
            restore_masks = []
            if orig_assignee is not None:
                restore_updates["assignee"] = orig_assignee
                restore_masks.append("assignee")
            if orig_stage is not None:
                restore_updates["stage"] = orig_stage
                restore_masks.append("stage")
            if orig_incident is not None:
                restore_updates["incident"] = orig_incident
                restore_masks.append("incident")

            if restore_updates:
                self.engine.adapter.update_case(
                    case_id=target_case_id,
                    updates=restore_updates,
                    update_mask=",".join(restore_masks),
                )

    def test_live_case_alert_priority_update(self):
        """Tests updating case alert priority on a live case alert and restoring."""
        cases_batch = self.engine.search_cases(page_size=5)
        target_case_id = None
        target_alert_id = None
        orig_priority = None

        for c in cases_batch.results:
            alerts = self.engine.adapter.list_case_alerts(c.case_id)
            if alerts:
                target_case_id = c.case_id
                target_alert = alerts[0]
                target_alert_id = target_alert.get("name", "").split("/")[-1] or target_alert.get("identifier")
                orig_priority = target_alert.get("priority")
                break

        if not target_case_id or not target_alert_id:
            self.skipTest("No case with alerts available for alert priority test.")

        try:
            # Update priority to CRITICAL
            res = self.engine.set_case_alert_priority(
                case_id=target_case_id,
                alert_id=target_alert_id,
                priority="CRITICAL",
            )
            self.assertEqual(res.case_id, target_case_id)
            self.assertEqual(res.alert_id, target_alert_id)
            self.assertIn("CRITICAL", str(res.priority).upper())

        finally:
            if orig_priority:
                self.engine.adapter.update_case_alert(
                    case_id=target_case_id,
                    alert_id=target_alert_id,
                    updates={"priority": orig_priority},
                    update_mask="priority",
                )

    def test_live_soar_users_with_filter(self):
        """Tests listing SOAR users with a server-side filter expression."""
        res = self.engine.adapter.list_soar_users(
            filter="(accountState = 'Active')",
            page_size=10,
        )
        self.assertIsInstance(res, dict)
        users = res.get("legacySoarUsers", [])
        self.assertIsInstance(users, list)
    def test_live_case_alert_recommendation_lifecycle(self):
        """Tests triggering and fetching a Gemini AI Case Alert Recommendation against live endpoints."""
        cases_batch = self.engine.search_cases(page_size=5)
        target_case_id = None
        target_alert_id = None

        for c in cases_batch.results:
            alerts = self.engine.adapter.list_case_alerts(c.case_id)
            if alerts:
                target_case_id = c.case_id
                target_alert = alerts[0]
                target_alert_id = target_alert.get("name", "").split("/")[-1] or target_alert.get("identifier")
                break

        if not target_case_id or not target_alert_id:
            self.skipTest("No case with alerts available for recommendation test.")

        # 1. Test create_case_alert_recommendation
        job = self.engine.create_case_alert_recommendation(
            case_id=target_case_id,
            alert_id=target_alert_id,
        )
        self.assertEqual(job.case_id, target_case_id)
        self.assertEqual(job.alert_id, target_alert_id)
        self.assertTrue(bool(job.recommendation_id))

        # 2. Test fetch_case_alert_recommendation
        rec = self.engine.fetch_case_alert_recommendation(
            case_id=target_case_id,
            recommendation_id=job.recommendation_id,
        )
        self.assertEqual(rec.case_id, target_case_id)
        self.assertEqual(rec.recommendation_id, job.recommendation_id)
        self.assertIn(rec.state, ("SUCCEEDED", "RUNNING", "FAILED", "UNSPECIFIED"))

        # 3. Test get_case_alert_recommendation workflow with short timeout
        wf_rec = self.engine.get_case_alert_recommendation(
            case_id=target_case_id,
            alert_id=target_alert_id,
            timeout_sec=5.0,
            poll_interval_sec=1.0,
        )
        self.assertEqual(wf_rec.case_id, target_case_id)
        self.assertTrue(bool(wf_rec.recommendation_id))
        self.assertIn(wf_rec.state, ("SUCCEEDED", "RUNNING", "FAILED", "UNSPECIFIED"))


if __name__ == "__main__":
    unittest.main()
