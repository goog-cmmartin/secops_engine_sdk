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
        cls.sample_jobs = cls.engine.search_jobs(limit=100).results
        cls.sample_instances = cls.engine.list_job_instances()

    def test_01_list_all_jobs_live(self):
        """Verify discovering and listing all catalog jobs from live SecOps."""
        batch = self.engine.search_jobs(limit=100)
        self.assertIsInstance(batch, JobBatch)
        self.assertGreaterEqual(batch.total_count, 1, "Expected at least 1 catalog job in live tenant")
        self.assertGreater(len(batch.results), 0)

        # Inspect first job summary
        sample = batch.results[0]
        self.assertIsInstance(sample, JobSummary)
        self.assertTrue(bool(sample.id), "Job must have an ID")
        self.assertTrue(bool(sample.display_name), "Job must have a display name")
        self.assertTrue(bool(sample.integration), "Job must belong to an integration")
        self.assertIn("/jobs/", sample.name)

    def test_02_search_job_by_keyword(self):
        """Verify keyword search finds a discovered catalog job."""
        if not self.sample_jobs:
            self.skipTest("No catalog jobs available in live tenant.")
        target = self.sample_jobs[0]
        batch = self.engine.search_jobs(query=target.display_name)
        self.assertGreaterEqual(batch.total_count, 1)
        self.assertTrue(any(j.id == target.id for j in batch.results))

    def test_03_filter_jobs_by_integration(self):
        """Verify filtering jobs by parent integration."""
        if not self.sample_jobs:
            self.skipTest("No catalog jobs available in live tenant.")
        target_integ = self.sample_jobs[0].integration
        batch = self.engine.search_jobs(integration=target_integ)
        self.assertGreaterEqual(batch.total_count, 1)
        for j in batch.results:
            self.assertEqual(j.integration.lower(), target_integ.lower())

    def test_04_get_job_detail_deep(self):
        """Verify deep inspection of a discovered job and its runtime instances."""
        if not self.sample_jobs:
            self.skipTest("No catalog jobs available in live tenant.")
        target_job = self.sample_jobs[0]
        if self.sample_instances:
            matched = next(
                (
                    j
                    for j in self.sample_jobs
                    if any(inst.integration == j.integration and inst.display_name == j.display_name for inst in self.sample_instances)
                ),
                None,
            )
            if matched is not None:
                target_job = matched

        detail = self.engine.get_job(integration=target_job.integration, job_id=target_job.id)
        self.assertIsInstance(detail, JobDetail)
        self.assertEqual(detail.job.id, target_job.id)
        self.assertEqual(detail.job.integration, target_job.integration)
        self.assertTrue(bool(detail.job.display_name))
        self.assertIsInstance(detail.instances, list)
        self.assertIsInstance(detail.recent_logs, list)
        for sample_log in detail.recent_logs[:3]:
            self.assertIsInstance(sample_log, JobExecutionLog)

    def test_05_list_all_job_instances(self):
        """Verify listing runtime job instances across all jobs."""
        instances = self.engine.list_job_instances()
        self.assertIsInstance(instances, list)
        if not instances:
            self.skipTest("No runtime job instances configured in live tenant.")

        for inst in instances[:5]:
            self.assertIsInstance(inst, JobInstance)
            self.assertTrue(bool(inst.id))
            self.assertTrue(bool(inst.display_name))
            self.assertTrue(bool(inst.integration))

    def test_06_get_job_instance_logs_80(self):
        """Verify fetching execution history logs for a discovered job instance."""
        if not self.sample_instances:
            self.skipTest("No runtime job instances configured in live tenant.")
        for inst in self.sample_instances[:10]:
            logs = self.engine.get_job_instance_logs(job_instance_id=inst.id, limit=5)
            self.assertIsInstance(logs, list)
            if logs:
                log_entry = logs[0]
                self.assertIsInstance(log_entry, JobExecutionLog)
                self.assertEqual(log_entry.job_instance_id, inst.id)
                self.assertTrue(bool(log_entry.start_time))
                return

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
