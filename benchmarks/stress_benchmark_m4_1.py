"""M4.1 High-Scale Stress Benchmark Suite for SecOps Lean.

Tests:
1. Live Stream Ingestion from Google SecOps (TTFR, network throughput, memory delta).
2. Scale-Up Stress Profiling across 10k, 50k, and 100k events:
   - RSS memory growth curve (per 10k events).
   - Qt EventTableModel insertion & cell access latency (µs per row/col).
   - Python Nested Dict vs Compact Columnar projection memory and filter scan speeds.
   - GC execution time and memory release efficiency.
"""

import gc
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import psutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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


def run_m4_1_benchmark() -> Dict[str, Any]:
    process = psutil.Process(os.getpid())
    adapter = GoogleSecOpsAdapter()
    engine = SecOpsEngine(adapter)

    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_time = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    query = 'metadata.event_type = "USER_LOGIN" or metadata.event_type = "NETWORK_CONNECTION"'

    print(f"\n=========================================================================")
    print(f"SecOps Milestone 4.1 Scale & Stress Benchmark Suite")
    print(f"Initial Process RSS: {process.memory_info().rss / (1024 * 1024):.2f} MB")
    print(f"=========================================================================\n")

    # -------------------------------------------------------------------------
    # Phase 1: Live Stream Search Benchmark
    # -------------------------------------------------------------------------
    print(f"[Phase 1] Executing Live Streaming UDM Search against Google SecOps...")
    gc.collect()
    p1_rss_start = process.memory_info().rss / (1024 * 1024)

    t0 = time.perf_counter()
    ttfr: Optional[float] = None
    live_events: List[Dict[str, Any]] = []

    def on_batch(batch: SearchBatchResult, session: SearchSession):
        nonlocal ttfr
        now_t = time.perf_counter()
        if ttfr is None and batch.events:
            ttfr = now_t - t0
        live_events.extend(batch.events)

    req = SearchRequest(
        query=query,
        start_time=start_time,
        end_time=end_time,
        receive_limit=10000,
        batch_size=2000,
    )

    session = engine.search_udm(req, on_batch=on_batch)
    t_live_end = time.perf_counter()
    live_duration = t_live_end - t0
    p1_rss_peak = process.memory_info().rss / (1024 * 1024)

    print(f"  Live Events Retrieved: {len(live_events):,}")
    print(f"  Live TTFR: {ttfr:.2f}s" if ttfr else "  Live TTFR: N/A")
    print(f"  Live Duration: {live_duration:.2f}s")
    print(f"  Live Throughput: {len(live_events) / live_duration:.2f} eps")
    print(f"  Live RSS Peak: {p1_rss_peak:.2f} MB (Delta: +{p1_rss_peak - p1_rss_start:.2f} MB)")

    if not live_events:
        raise RuntimeError("No live events retrieved for stress testing.")

    # -------------------------------------------------------------------------
    # Phase 2: High-Scale Stress & Memory Growth Profiling (10k, 50k, 100k tiers)
    # -------------------------------------------------------------------------
    print(f"\n[Phase 2] High-Scale Stress & Memory Growth Profiling (10k, 50k, 100k)...")

    from PySide6.QtCore import QModelIndex, Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(sys.argv)

    scale_tiers = [10000, 50000, 100000]
    tier_results: List[Dict[str, Any]] = []

    for target_count in scale_tiers:
        print(f"\n--- Profiling Scale Tier: {target_count:,} Events ---")
        gc.collect()
        rss_tier_start = process.memory_info().rss / (1024 * 1024)

        # Build scale dataset from live-retrieved event templates
        multiplier = (target_count // len(live_events)) + 1
        raw_events_dataset: List[Dict[str, Any]] = []
        for i in range(multiplier):
            for ev in live_events:
                if len(raw_events_dataset) < target_count:
                    # Shallow copy dict and update unique event id
                    ev_copy = dict(ev)
                    ev_copy["id"] = f"{ev.get('id', 'ev')}-{len(raw_events_dataset)}"
                    raw_events_dataset.append(ev_copy)
                else:
                    break

        rss_dataset_loaded = process.memory_info().rss / (1024 * 1024)
        dataset_mem_mb = rss_dataset_loaded - rss_tier_start

        # 1. Compact Columnar Projection Benchmark
        t_proj_0 = time.perf_counter()
        compact_columns: List[Tuple] = []
        for ev in raw_events_dataset:
            udm = ev.get("udm", ev)
            meta = udm.get("metadata", {})
            pr = udm.get("principal", {})
            tg = udm.get("target", {})
            compact_columns.append(
                (
                    meta.get("id", ""),
                    meta.get("eventTimestamp", ""),
                    meta.get("eventType", ""),
                    pr.get("hostname", ""),
                    pr.get("user", {}).get("userid", ""),
                    tg.get("hostname", ""),
                    tg.get("ip", [""])[0] if isinstance(tg.get("ip"), list) and tg.get("ip") else "",
                )
            )
        t_proj_1 = time.perf_counter()
        proj_time_ms = (t_proj_1 - t_proj_0) * 1000
        rss_after_compact = process.memory_info().rss / (1024 * 1024)
        compact_mem_mb = rss_after_compact - rss_dataset_loaded

        # 2. In-Memory Filter Scan Speed: Dicts vs Compact Tuples
        t_scan_dict_0 = time.perf_counter()
        d_matches = sum(
            1 for ev in raw_events_dataset
            if ev.get("udm", {}).get("metadata", {}).get("eventType") == "USER_LOGIN"
        )
        t_scan_dict_1 = time.perf_counter()
        scan_dict_ms = (t_scan_dict_1 - t_scan_dict_0) * 1000

        t_scan_comp_0 = time.perf_counter()
        c_matches = sum(1 for rec in compact_columns if rec[2] == "USER_LOGIN")
        t_scan_comp_1 = time.perf_counter()
        scan_comp_ms = (t_scan_comp_1 - t_scan_comp_0) * 1000
        scan_speedup = (scan_dict_ms / scan_comp_ms) if scan_comp_ms > 0 else 1.0

        # 3. Qt EventTableModel Insertion & Incremental Batch Overhead
        model = EventTableModel()
        chunk_size = 10000
        t_append_start = time.perf_counter()
        append_chunk_times_ms: List[float] = []

        for offset in range(0, target_count, chunk_size):
            chunk = raw_events_dataset[offset : offset + chunk_size]
            t_chunk_0 = time.perf_counter()
            model.append_events(chunk)
            t_chunk_1 = time.perf_counter()
            append_chunk_times_ms.append(round((t_chunk_1 - t_chunk_0) * 1000, 2))

        t_append_end = time.perf_counter()
        total_append_ms = (t_append_end - t_append_start) * 1000
        rss_after_model = process.memory_info().rss / (1024 * 1024)

        # 4. Virtual Cell Extraction Latency (10,000 random cell accesses)
        sample_size = min(10000, target_count)
        t_cell_0 = time.perf_counter()
        for r in range(sample_size):
            for c in range(model.columnCount()):
                idx = model.index(r, c)
                _ = model.data(idx, Qt.DisplayRole)
        t_cell_1 = time.perf_counter()
        cell_latency_ms = (t_cell_1 - t_cell_0) * 1000
        latency_per_row_us = (cell_latency_ms * 1000.0) / sample_size if sample_size > 0 else 0.0

        # 5. GC & Reclamation Test
        model.clear()
        del model
        del raw_events_dataset
        del compact_columns
        t_gc_0 = time.perf_counter()
        gc.collect()
        t_gc_1 = time.perf_counter()
        gc_time_ms = (t_gc_1 - t_gc_0) * 1000
        rss_after_gc = process.memory_info().rss / (1024 * 1024)

        tier_summary = {
            "tier_events": target_count,
            "memory": {
                "dataset_rss_mb": round(dataset_mem_mb, 2),
                "peak_process_rss_mb": round(rss_after_model, 2),
                "rss_per_10k_events_mb": round(dataset_mem_mb / (target_count / 10000.0), 2),
                "rss_after_gc_mb": round(rss_after_gc, 2),
                "reclaimed_mb": round(rss_after_model - rss_after_gc, 2),
            },
            "qt_model": {
                "total_insertion_time_ms": round(total_append_ms, 2),
                "insertion_ms_per_10k": round(total_append_ms / (target_count / 10000.0), 2),
                "chunk_10k_times_ms": append_chunk_times_ms,
                "cell_access_10k_sample_ms": round(cell_latency_ms, 2),
                "latency_per_row_microseconds": round(latency_per_row_us, 2),
            },
            "representation": {
                "projection_time_ms": round(proj_time_ms, 2),
                "compact_added_mem_mb": round(compact_mem_mb, 2),
                "raw_dict_scan_ms": round(scan_dict_ms, 2),
                "compact_scan_ms": round(scan_comp_ms, 2),
                "filter_scan_speedup": round(scan_speedup, 2),
            },
            "gc_duration_ms": round(gc_time_ms, 2),
        }
        tier_results.append(tier_summary)

        print(f"  Dataset RSS: {dataset_mem_mb:.2f} MB ({tier_summary['memory']['rss_per_10k_events_mb']:.2f} MB / 10k events)")
        print(f"  Peak RSS with Qt Model: {rss_after_model:.2f} MB")
        print(f"  Model Insertion Time: {total_append_ms:.2f} ms ({tier_summary['qt_model']['insertion_ms_per_10k']:.2f} ms / 10k)")
        print(f"  Cell Access Latency: {cell_latency_ms:.2f} ms ({latency_per_row_us:.2f} µs/row)")
        print(f"  Scan Filter Speedup (Compact vs Dict): {scan_speedup:.2f}x ({scan_dict_ms:.2f}ms vs {scan_comp_ms:.2f}ms)")
        print(f"  GC Time: {gc_time_ms:.2f} ms (Reclaimed: {tier_summary['memory']['reclaimed_mb']:.2f} MB)")

    # -------------------------------------------------------------------------
    # Final Benchmark Report Assembly
    # -------------------------------------------------------------------------
    report = {
        "benchmark": "M4.1 Scale & Stress Benchmark",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "os": sys.platform,
            "python": sys.version,
            "cpu_cores": psutil.cpu_count(),
        },
        "phase1_live_stream": {
            "query": query,
            "time_range": {"start": start_time, "end": end_time},
            "events_retrieved": len(live_events),
            "ttfr_seconds": round(ttfr, 3) if ttfr else None,
            "duration_seconds": round(live_duration, 2),
            "throughput_eps": round(len(live_events) / live_duration, 2) if live_duration > 0 else 0,
            "rss_peak_mb": round(p1_rss_peak, 2),
            "rss_growth_mb": round(p1_rss_peak - p1_rss_start, 2),
        },
        "phase2_scale_tiers": tier_results,
    }

    evidence_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "evidence", "performance"))
    os.makedirs(evidence_dir, exist_ok=True)
    report_path = os.path.join(evidence_dir, "m4_1_stress_benchmark_report.json")
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n=========================================================================")
    print(f"Benchmark Complete. Full JSON report saved to:")
    print(f"{report_path}")
    print(f"=========================================================================\n")
    return report


if __name__ == "__main__":
    run_m4_1_benchmark()
