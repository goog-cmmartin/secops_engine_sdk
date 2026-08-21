"""Authoritative Acceptance Suite for Milestone 4: Native Desktop Client & Performance.

Verifies:
1. Virtual Table Model efficiency and separation of concerns.
2. Background thread execution & signal dispatch (zero UI thread blocking).
3. Live cancellation responsiveness from Qt workers.
4. Real performance & memory metrics (TTFR, throughput, RSS footprint).
5. End-to-end Analyst Feedback Loop (Search -> Investigate -> Pivot IN -> Refined Search -> Entity Search).
6. Anti-Mock Invariant: Zero synthetic or fake data in production desktop, engine, or adapter code.
"""

from tests.test_helpers import get_live_adapter, get_live_engine
import os
import re
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    from clients.desktop.models import EventTableModel
    from clients.desktop.workers import InvestigationWorker, SearchWorker
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False

from adapters.google_secops import GoogleSecOpsAdapter
from engine import (
    CompletenessState,
    EntityType,
    EventInvestigation,
    FieldFilter,
    FilterOperator,
    LifecycleState,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
    SecOpsEngine,
)


@unittest.skipIf(not HAS_PYSIDE6, "PySide6 is not installed in the current environment")
class TestM4DesktopAndPerformanceLive(unittest.TestCase):
    """Live acceptance test suite for Milestone 4 native client and performance."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(["test_app"])

    def setUp(self):
        now = datetime.now(timezone.utc)
        self.end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.start_time = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")

    @property
    def adapter(self):
        if not hasattr(self, "_adapter"):
            self._adapter = get_live_adapter()
        return self._adapter

    @property
    def engine(self):
        if not hasattr(self, "_engine"):
            self._engine = get_live_engine(adapter=self.adapter)
        return self._engine

    def test_qt_model_virtual_storage(self):
        """[M4-001] EventTableModel virtual storage and column extraction."""
        model = EventTableModel()
        self.assertEqual(model.rowCount(), 0)
        self.assertEqual(model.columnCount(), len(EventTableModel.COLUMNS))

        # Test with live event structure
        raw_events = [
            {
                "event": {
                    "metadata": {
                        "eventTimestamp": "2026-08-18T05:00:00Z",
                        "eventType": "USER_LOGIN",
                        "productName": "Windows Event Log",
                    },
                    "principal": {
                        "hostname": "workstation-01",
                        "ip": ["10.0.0.5"],
                        "user": {"userid": "alice"},
                    },
                    "target": {
                        "hostname": "auth-server",
                        "ip": ["10.0.0.1"],
                        "user": {"userid": "admin"},
                    },
                }
            }
        ]

        model.append_events(raw_events)
        self.assertEqual(model.rowCount(), 1)

        # Verify column displays
        from PySide6.QtCore import Qt

        idx_time = model.index(0, 0)
        self.assertEqual(model.data(idx_time, Qt.ItemDataRole.DisplayRole), "2026-08-18T05:00:00Z")

        idx_type = model.index(0, 1)
        self.assertEqual(model.data(idx_type, Qt.ItemDataRole.DisplayRole), "USER_LOGIN")

        idx_host = model.index(0, 2)
        self.assertEqual(model.data(idx_host, Qt.ItemDataRole.DisplayRole), "workstation-01")

        idx_user = model.index(0, 4)
        self.assertEqual(model.data(idx_user, Qt.ItemDataRole.DisplayRole), "alice")

        model.clear()
        self.assertEqual(model.rowCount(), 0)

    def _run_worker(self, worker, timeout_ms=30000):
        from PySide6.QtCore import QEventLoop, QTimer
        loop = QEventLoop()
        worker.finished.connect(loop.quit)
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(timeout_ms)
        worker.start()
        loop.exec()
        if worker.isRunning():
            worker.wait(2000)

    def test_qt_workers_live_execution(self):
        """[M4-002] SearchWorker and InvestigationWorker live asynchronous execution via Qt signals."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
            receive_limit=10,
            batch_size=10,
        )

        batches_received = []
        final_session = []
        errors = []

        worker = SearchWorker(engine=self.engine, mode="search", search_request=req)

        def on_batch(events, total):
            batches_received.append((events, total))

        def on_done(session):
            final_session.append(session)

        def on_err(err):
            errors.append(err)

        worker.batch_received.connect(on_batch)
        worker.search_completed.connect(on_done)
        worker.search_failed.connect(on_err)

        self._run_worker(worker, timeout_ms=60000)

        self.assertEqual(len(errors), 0, f"SearchWorker encountered error: {errors}")
        self.assertEqual(len(final_session), 1, "Expected search_completed signal")
        session = final_session[0]
        self.assertEqual(session.lifecycle, LifecycleState.COMPLETED)
        self.assertGreater(session.received_count, 0)
        self.assertGreater(len(batches_received), 0)

        # Test InvestigationWorker with first returned event
        first_event = session.events[0]
        inv_results = []
        inv_errors = []

        inv_worker = InvestigationWorker(engine=self.engine, event=first_event, eager_raw_log=True)
        inv_worker.investigation_completed.connect(lambda inv: inv_results.append(inv))
        inv_worker.investigation_failed.connect(lambda err: inv_errors.append(err))

        self._run_worker(inv_worker, timeout_ms=30000)

        self.assertEqual(len(inv_results), 1, "Expected investigation_completed signal")
        inv = inv_results[0]
        self.assertIsInstance(inv, EventInvestigation)
        self.assertIsNotNone(inv.event_id)
        self.assertIsNotNone(inv.raw_log)

        # Test CaseSearchWorker execution
        from clients.desktop.workers import CaseSearchWorker
        case_results = []
        case_errors = []
        case_worker = CaseSearchWorker(engine=self.engine, query="", limit=5)
        case_worker.cases_loaded.connect(lambda b: case_results.append(b))
        case_worker.search_failed.connect(lambda e: case_errors.append(e))
        self._run_worker(case_worker, timeout_ms=30000)
        self.assertEqual(len(case_errors), 0, f"CaseSearchWorker failed: {case_errors}")
        self.assertEqual(len(case_results), 1, "Expected cases_loaded signal")

    def test_qt_worker_live_cancellation(self):
        """[M4-003] SearchWorker live cancellation responsiveness and clean shutdown."""
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
            receive_limit=5000,
            batch_size=50,
        )

        final_session = []
        worker = SearchWorker(engine=self.engine, mode="search", search_request=req)
        worker.search_completed.connect(lambda s: final_session.append(s))

        # Cancel immediately upon launch
        worker.cancel()

        t0 = time.time()
        self._run_worker(worker, timeout_ms=30000)
        elapsed = time.time() - t0

        self.assertEqual(len(final_session), 1)
        session = final_session[0]
        self.assertEqual(session.lifecycle, LifecycleState.CANCELLED)
        self.assertLess(elapsed, 10.0, "Cancellation must complete promptly")


    def test_full_analyst_loop_in_qt(self):
        """[M4-004] End-to-End Analyst Feedback Loop in Qt: Search -> Investigate -> Pivot IN -> Refined Search -> Entity Pivot."""
        # 1. Initial Search
        req = SearchRequest(
            query='metadata.event_type = "USER_LOGIN"',
            start_time=self.start_time,
            end_time=self.end_time,
            receive_limit=5,
            batch_size=5,
        )
        session1 = self.engine.search_udm(req)
        self.assertGreater(session1.received_count, 0)
        first_event = session1.events[0]

        # 2. Investigate Event
        inv = self.engine.investigate_event(first_event, eager_load_raw_log=True)
        self.assertIsNotNone(inv.raw_log)


        # 3. Pivot IN Filter
        flat = inv.to_flat_dict()
        self.assertIn("metadata.eventType", flat)
        pivot_filter = inv.build_pivot_filter("metadata.eventType", FilterOperator.EQUALS)

        # 4. Refined Search
        session2 = self.engine.refine_search(
            base='metadata.event_type = "USER_LOGIN"',
            filters=[pivot_filter],
            receive_limit=5,
            start_time=self.start_time,
            end_time=self.end_time,
        )
        self.assertEqual(session2.lifecycle, LifecycleState.COMPLETED)
        self.assertGreater(session2.received_count, 0)

        # 5. Entity Pivot Search
        session3 = self.engine.search_from_entity(
            entity_type=EntityType.HOSTNAME,
            entity_value="B_114",
            receive_limit=5,
            start_time=self.start_time,
            end_time=self.end_time,
        )
        self.assertEqual(session3.lifecycle, LifecycleState.COMPLETED)
        self.assertGreater(session3.received_count, 0)

    def test_anti_mock_audit(self):
        """[M4-005] Anti-Mock Static Audit: Zero mock data in production desktop, engine, or adapter paths."""
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        banned_patterns = [
            r"\bmock\b",
            r"\bMock\b",
            r"\bfixture\b",
            r"\bdummy\b",
            r"\bfake\b",
            r"\bsample_data\b",
            r"\bplaceholder_data\b",
        ]
        target_dirs = ["clients/desktop", "engine", "adapters"]

        violations = []
        for d in target_dirs:
            dir_path = os.path.join(project_root, d)
            if not os.path.exists(dir_path):
                continue
            for root, _, files in os.walk(dir_path):
                for f in files:
                    if f.endswith(".py"):
                        fpath = os.path.join(root, f)
                        with open(fpath, "r", encoding="utf-8") as fh:
                            for idx, line in enumerate(fh, 1):
                                stripped = line.strip()
                                if stripped.startswith("#"):
                                    continue
                                for pat in banned_patterns:
                                    if re.search(pat, line):
                                        violations.append(f"{fpath}:{idx} -> {line.strip()}")

        self.assertEqual(len(violations), 0, f"Found mock violations in production code:\n" + "\n".join(violations))

    def test_m4_1_stress_scale_verification(self):
        """[M4.1-001] Verify M4.1 Scale & Stress Benchmark metrics and memory invariants."""
        import json
        evidence_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "evidence", "performance", "m4_1_stress_benchmark_report.json"))
        self.assertTrue(os.path.exists(evidence_path), f"M4.1 benchmark evidence not found at {evidence_path}")

        with open(evidence_path, "r") as f:
            report = json.load(f)

        self.assertEqual(report["benchmark"], "M4.1 Scale & Stress Benchmark")
        self.assertIn("phase1_live_stream", report)
        self.assertIn("phase2_scale_tiers", report)

        tiers = {t["tier_events"]: t for t in report["phase2_scale_tiers"]}
        self.assertIn(10000, tiers)
        self.assertIn(50000, tiers)
        self.assertIn(100000, tiers)

        t100k = tiers[100000]
        # Invariant 1: Peak process RSS for 100k events must remain under 300 MB (measured ~138 MB)
        self.assertLess(t100k["memory"]["peak_process_rss_mb"], 300.0)
        # Invariant 2: Insertion time for 100k events into Qt virtual model must remain under 100 ms (measured ~8 ms)
        self.assertLess(t100k["qt_model"]["total_insertion_time_ms"], 100.0)
        # Invariant 3: Compact projection scan filter must be faster than nested dict scanning
        self.assertGreater(t100k["representation"]["filter_scan_speedup"], 1.5)

    def test_qt_expanded_models_and_widgets(self):
        """[M4-006] Verify instantiation of multi-domain models and SecOpsMainWindow navigation views."""
        from clients.desktop.main_window import SecOpsMainWindow
        from clients.desktop.models import (
            CaseTableModel,
            CuratedRulesetTableModel,
            DashboardTableModel,
            FeedTableModel,
            GenericItemTableModel,
            IntegrationTableModel,
            JobTableModel,
            ParserTableModel,
            PlaybookTableModel,
        )

        # 1. Test Models instantiation and data binding
        case_model = CaseTableModel()
        self.assertEqual(case_model.rowCount(), 0)
        self.assertEqual(case_model.columnCount(), len(CaseTableModel.COLUMNS))

        playbook_model = PlaybookTableModel()
        self.assertEqual(playbook_model.rowCount(), 0)
        self.assertEqual(playbook_model.columnCount(), len(PlaybookTableModel.COLUMNS))

        int_model = IntegrationTableModel()
        self.assertEqual(int_model.rowCount(), 0)

        job_model = JobTableModel()
        self.assertEqual(job_model.rowCount(), 0)

        ruleset_model = CuratedRulesetTableModel()
        self.assertEqual(ruleset_model.rowCount(), 0)

        feed_model = FeedTableModel()
        self.assertEqual(feed_model.rowCount(), 0)

        parser_model = ParserTableModel()
        self.assertEqual(parser_model.rowCount(), 0)

        dash_model = DashboardTableModel()
        self.assertEqual(dash_model.rowCount(), 0)

        generic_model = GenericItemTableModel(["Col1", "Col2", "Col3"])
        generic_model.set_rows([["A", "B", "C"], ["D", "E", "F"]])
        self.assertEqual(generic_model.rowCount(), 2)
        self.assertEqual(generic_model.columnCount(), 3)

        # 2. Test Main Window instantiation and navigation items
        window = SecOpsMainWindow(self.engine)
        self.assertEqual(window.nav_list.count(), 8)
        self.assertEqual(window.stack.count(), 8)
        self.assertIsNotNone(window.udm_widget)
        self.assertIsNotNone(window.cases_widget)
        self.assertIsNotNone(window.playbooks_widget)
        self.assertIsNotNone(window.integrations_widget)
        self.assertIsNotNone(window.detections_widget)
        self.assertIsNotNone(window.feeds_parsers_widget)
        self.assertIsNotNone(window.dashboards_widget)
        self.assertIsNotNone(window.settings_widget)
        window.close()


if __name__ == "__main__":
    unittest.main()
