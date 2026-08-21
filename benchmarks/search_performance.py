"""Automated Performance & Memory Benchmark Harness for SecOps Lean.

Measures:
1. Time to First Row (TTFR) / First Batch Arrival.
2. Time to complete N events (e.g. 1,000, 5,000, 10,000).
3. Streaming throughput (events per second).
4. Process memory footprint (Initial RSS, Peak RSS, Memory per 1,000 events).
5. Live cancellation responsiveness & latency.
6. Qt Virtual Model batch insertion overhead.
"""

import gc
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import psutil

# Ensure headless Qt support
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Ensure secops-lean is on pythonpath
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from adapters.google_secops import GoogleSecOpsAdapter
from clients.desktop.models import EventTableModel
from engine import (
    CompletenessState,
    LifecycleState,
    SearchBatchResult,
    SearchRequest,
    SearchSession,
    SecOpsEngine,
)


def run_benchmark(
    limits: List[int] = [500, 1000, 2500],
    query: str = 'metadata.event_type = "USER_LOGIN"',
    batch_size: int = 500,
) -> Dict[str, Any]:
    """Runs live performance benchmarks across target event limits."""
    adapter = GoogleSecOpsAdapter()
    engine = SecOpsEngine(adapter)
    process = psutil.Process(os.getpid())

    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    benchmark_results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "batch_size": batch_size,
        "system": {
            "os": sys.platform,
            "python_version": sys.version,
            "cpu_count": psutil.cpu_count(),
        },
        "runs": [],
        "cancellation_benchmark": {},
        "model_overhead_benchmark": {},
    }

    print(f"\n=================================================================")
    print(f"SecOps Engine Performance & Memory Benchmark")
    print(f"Query: {query}")
    print(f"Batch Size: {batch_size}")
    print(f"=================================================================\n")

    for limit in limits:
        gc.collect()
        mem_before_mb = process.memory_info().rss / (1024 * 1024)

        t_start = time.perf_counter()
        ttfr: Optional[float] = None
        batch_times: List[float] = []
        batches_received: int = 0

        def on_batch(batch: SearchBatchResult, session: SearchSession):
            nonlocal ttfr, batches_received
            now_t = time.perf_counter()
            if ttfr is None and batch.events:
                ttfr = now_t - t_start
            batches_received += 1
            batch_times.append(now_t - t_start)

        req = SearchRequest(
            query=query,
            start_time=start_time,
            end_time=end_time,
            receive_limit=limit,
            batch_size=batch_size,
        )

        session = engine.search_udm(req, on_batch=on_batch)
        t_total = time.perf_counter() - t_start

        mem_after_mb = process.memory_info().rss / (1024 * 1024)
        mem_delta_mb = mem_after_mb - mem_before_mb

        throughput = session.received_count / t_total if t_total > 0 else 0

        run_stat = {
            "requested_limit": limit,
            "emitted_event_count": session.received_count,
            "time_to_first_row_sec": round(ttfr, 4) if ttfr is not None else None,
            "total_elapsed_sec": round(t_total, 4),
            "events_per_second": round(throughput, 2),
            "batches_received": batches_received,
            "memory_initial_rss_mb": round(mem_before_mb, 2),
            "memory_final_rss_mb": round(mem_after_mb, 2),
            "memory_delta_mb": round(mem_delta_mb, 2),
            "lifecycle": session.lifecycle.value,
            "completeness": session.completeness.value,
        }
        benchmark_results["runs"].append(run_stat)

        print(f"[*] Target Limit: {limit} events")
        print(f"    - Emitted Events   : {session.received_count}")
        print(f"    - Time to First Row: {run_stat['time_to_first_row_sec']}s")
        print(f"    - Total Duration   : {run_stat['total_elapsed_sec']}s")
        print(f"    - Throughput       : {run_stat['events_per_second']} events/sec")
        print(f"    - Memory (Delta)   : {run_stat['memory_delta_mb']} MB (Final: {run_stat['memory_final_rss_mb']} MB)")
        print(f"    - Lifecycle State  : {run_stat['lifecycle']} ({run_stat['completeness']})\n")

    # Cancellation Benchmark
    print("[*] Running Cancellation Latency Benchmark...")
    import threading
    cancel_token = threading.Event()
    cancel_trigger_time: Optional[float] = None
    cancel_halt_time: Optional[float] = None

    def on_cancel_batch(batch: SearchBatchResult, session: SearchSession):
        nonlocal cancel_trigger_time
        if cancel_trigger_time is None:
            cancel_trigger_time = time.perf_counter()
            cancel_token.set()

    t_cancel_start = time.perf_counter()
    cancel_req = SearchRequest(
        query=query,
        start_time=start_time,
        end_time=end_time,
        receive_limit=5000,
        batch_size=100,
    )
    cancel_session = engine.search_udm(cancel_req, on_batch=on_cancel_batch, cancel_token=cancel_token)
    cancel_halt_time = time.perf_counter()

    cancel_latency_ms = (cancel_halt_time - cancel_trigger_time) * 1000 if cancel_trigger_time else 0
    benchmark_results["cancellation_benchmark"] = {
        "cancel_latency_ms": round(cancel_latency_ms, 2),
        "lifecycle": cancel_session.lifecycle.value,
        "events_before_halt": cancel_session.received_count,
    }
    print(f"    - Cancel Latency   : {cancel_latency_ms:.2f} ms")
    print(f"    - Final State      : {cancel_session.lifecycle.value}")
    print(f"    - Events Retained  : {cancel_session.received_count}\n")

    # Qt Model Insertion Overhead Benchmark
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    model = EventTableModel()

    sample_batch = cancel_session.events[:100] if cancel_session.events else []
    t_model_start = time.perf_counter()
    for _ in range(10):
        model.append_events(sample_batch)
    t_model_total = time.perf_counter() - t_model_start
    model_rows = model.rowCount()

    benchmark_results["model_overhead_benchmark"] = {
        "virtual_rows_loaded": model_rows,
        "total_insertion_time_ms": round(t_model_total * 1000, 2),
        "ms_per_thousand_rows": round((t_model_total / (model_rows / 1000)) * 1000, 2) if model_rows > 0 else 0,
    }
    print(f"[*] Qt Virtual Model Overhead Benchmark")
    print(f"    - Rows Inserted    : {model_rows}")
    print(f"    - Total Time       : {benchmark_results['model_overhead_benchmark']['total_insertion_time_ms']} ms")
    print(f"    - Rate             : {benchmark_results['model_overhead_benchmark']['ms_per_thousand_rows']} ms / 1,000 rows\n")

    # Save to Evidence
    evidence_path = os.path.join(
        os.path.dirname(__file__), "../evidence/performance/m4_benchmark_report.json"
    )
    os.makedirs(os.path.dirname(evidence_path), exist_ok=True)
    with open(evidence_path, "w") as f:
        json.dump(benchmark_results, f, indent=2)

    print(f"[✓] Benchmark report saved to: {evidence_path}\n")
    return benchmark_results


if __name__ == "__main__":
    run_benchmark()
