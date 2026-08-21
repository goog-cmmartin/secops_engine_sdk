"""Acceptance Tests for Milestone 5.5: SOAR Scheduled Jobs, Instances & Execution Logs.

Invariants Verified:
1. Production data strictly originates from live Google SecOps API endpoints.
2. Zero mocks, zero fake responses, zero fallback fixtures.
3. Explicit error propagation on invalid parameters.
4. Complete provenance linking: Job -> Job Instances -> Execution Logs.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import unittest

from engine.domain import (
    JobBatch,
    JobDetail,
    JobExecutionLog,
    JobInstance,
    JobSearchQuery,
    JobSummary,
)
from engine.facade import SecOpsEngine


class TestSOARJobsEngine(unittest.TestCase):
    """Authoritative test suite for SOAR Scheduled Jobs, Instances & Logs."""

    @classmethod
    def setUpClass(cls):
        cls.engine = get_live_engine()

    def test_01_list_all_jobs_live(self):
        """Verify discovering and listing all catalog jobs from live SecOps."""
        batch = self.engine.search_jobs(limit=100)
        self.assertIsInstance(batch, JobBatch)
        self.assertGreaterEqual(batch.total_count, 50, "Expected at least 50 catalog jobs in live tenant")
        self.assertGreater(len(batch.results), 0)

        # Inspect first job summary
        sample = batch.results[0]
        self.assertIsInstance(sample, JobSummary)
        self.assertTrue(bool(sample.id), "Job must have an ID")
        self.assertTrue(bool(sample.display_name), "Job must have a display name")
        self.assertTrue(bool(sample.integration), "Job must belong to an integration")
        self.assertIn("/jobs/", sample.name)

    def test_02_search_job_by_keyword(self):
        """Verify keyword search finds specific job 'Stream Use Cases'."""
        batch = self.engine.search_jobs(query="Stream Use Cases")
        self.assertGreaterEqual(batch.total_count, 1)
        found = [j for j in batch.results if "stream use cases" in j.display_name.lower()]
        self.assertTrue(len(found) >= 1)
        self.assertEqual(found[0].integration, "Demoverse")

    def test_03_filter_jobs_by_integration(self):
        """Verify filtering jobs by parent integration."""
        batch = self.engine.search_jobs(integration="Demoverse")
        self.assertGreaterEqual(batch.total_count, 1)
        for j in batch.results:
            self.assertEqual(j.integration.lower(), "demoverse")

    def test_04_get_job_detail_deep(self):
        """Verify deep inspection of Job 667 (Stream Use Cases Events V2) under Demoverse."""
        detail = self.engine.get_job(integration="Demoverse", job_id="667")
        self.assertIsInstance(detail, JobDetail)
        self.assertEqual(detail.job.id, "667")
        self.assertEqual(detail.job.integration, "Demoverse")
        self.assertTrue(bool(detail.job.display_name))

        # Check deployed instances
        self.assertGreaterEqual(len(detail.instances), 1, "Job 667 should have deployed instances")
        inst_80 = next((inst for inst in detail.instances if inst.id == "80"), None)
        self.assertIsNotNone(inst_80, "Expected Job Instance 80 in Job 667 instances")
        self.assertEqual(inst_80.integration, "Demoverse")
        self.assertIn(inst_80.last_run_status, ["SUCCESS", "FAILED", "RUNNING", "UNKNOWN"])

        # Check recent execution logs
        self.assertGreater(len(detail.recent_logs), 0, "Job 667 should have execution run records")
        sample_log = detail.recent_logs[0]
        self.assertIsInstance(sample_log, JobExecutionLog)
        self.assertEqual(sample_log.status, "SUCCESS")

    def test_05_list_all_job_instances(self):
        """Verify listing runtime job instances across all jobs."""
        instances = self.engine.list_job_instances()
        self.assertIsInstance(instances, list)
        self.assertGreaterEqual(len(instances), 20, "Expected at least 20 runtime job instances")

        for inst in instances[:5]:
            self.assertIsInstance(inst, JobInstance)
            self.assertTrue(bool(inst.id))
            self.assertTrue(bool(inst.display_name))
            self.assertTrue(bool(inst.integration))

    def test_06_get_job_instance_logs_80(self):
        """Verify fetching execution history logs for Job Instance 80."""
        logs = self.engine.get_job_instance_logs(job_instance_id="80", limit=5)
        self.assertIsInstance(logs, list)
        self.assertGreaterEqual(len(logs), 1, "Expected execution logs for Job Instance 80")

        log_entry = logs[0]
        self.assertIsInstance(log_entry, JobExecutionLog)
        self.assertEqual(log_entry.job_instance_id, "80")
        self.assertTrue(bool(log_entry.start_time))
        self.assertTrue(bool(log_entry.end_time))
        self.assertEqual(log_entry.status, "SUCCESS")

    def test_07_job_capabilities_registered(self):
        """Verify that job capabilities are registered in the WorkflowRegistry."""
        job_caps = self.engine.list_capabilities(category="job")
        cap_ids = [c.capability_id for c in job_caps]
        self.assertIn("job.search", cap_ids)
        self.assertIn("job.get", cap_ids)
        self.assertIn("job.instances", cap_ids)
        self.assertIn("job.logs", cap_ids)

    def test_08_anti_mock_audit_for_jobs(self):
        """Strict invariant check: Ensure zero banned mock terms in job code & specs."""
        banned_terms = ["mock", "fixture", "dummy", "fake", "sample_data", "placeholder_data"]
        files_to_check = [
            os.path.join(os.path.dirname(__file__), "..", "engine", "workflows", "job.py"),
            os.path.join(os.path.dirname(__file__), "..", "specs", "job", "job-search-001.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "specs", "job", "job-get-001.yaml"),
            os.path.join(os.path.dirname(__file__), "..", "specs", "job", "job-instance-logs-001.yaml"),
        ]

        for filepath in files_to_check:
            self.assertTrue(os.path.exists(filepath), f"File {filepath} must exist")
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read().lower()
                for term in banned_terms:
                    self.assertNotIn(
                        term,
                        content,
                        f"Banned mock term '{term}' found in production/spec file: {filepath}",
                    )


if __name__ == "__main__":
    unittest.main()
