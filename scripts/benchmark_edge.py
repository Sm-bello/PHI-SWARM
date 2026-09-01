#!/usr/bin/env python3
"""
Edge readiness benchmark: model size, CPU inference latency (batch-1 and
batch-8), and rough memory footprint. Runs on whatever CPU this script is
run on — labelled honestly as "laptop/dev-machine CPU", not an edge/embedded
target, since no Raspberry Pi/Jetson-class hardware is in this loop.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import torch

from zerotwin.models import UAVPHMModel, count_parameters


def bench_batch(model, batch_size: int, window_len: int = 64, n_iters: int = 50) -> dict:
    x = torch.randn(batch_size, window_len, 4)
    model.eval()
    with torch.no_grad():
        for _ in range(5):  # warmup
            model(x)
        times = []
        for _ in range(n_iters):
            t0 = time.perf_counter()
            model(x)
            times.append((time.perf_counter() - t0) * 1000.0)
    times = np.array(times)
    return {
        "batch_size": batch_size,
        "mean_ms": round(float(times.mean()), 3),
        "p50_ms": round(float(np.median(times)), 3),
        "p95_ms": round(float(np.percentile(times, 95)), 3),
        "throughput_windows_per_sec": round(1000.0 * batch_size / float(times.mean()), 1),
    }


def main():
    model = UAVPHMModel()
    n_params = count_parameters(model)
    fp32_bytes = n_params * 4

    tmp = ROOT / "zerotwin" / "results" / "_tmp_model.pt"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), tmp)
    saved_size_bytes = tmp.stat().st_size
    tmp.unlink()

    result = {
        "hardware": {
            "note": "dev/laptop CPU — NOT a Raspberry Pi/Jetson-class edge target; that benchmark is future work",
            "processor": platform.processor() or platform.machine(),
            "python": platform.python_version(),
            "torch": torch.__version__,
            "torch_threads": torch.get_num_threads(),
        },
        "model": {
            "parameters": n_params,
            "fp32_theoretical_MB": round(fp32_bytes / (1024 * 1024), 4),
            "saved_state_dict_MB": round(saved_size_bytes / (1024 * 1024), 4),
        },
        "inference": [bench_batch(model, bs) for bs in (1, 8)],
    }

    out = ROOT / "zerotwin" / "results" / "edge_benchmark.json"
    with open(out, "w") as f:
        json.dump(result, f, indent=2)

    print("=== ZeroTwin edge benchmark ===")
    print(f"Hardware:   {result['hardware']['processor']}  (dev CPU, not embedded target)")
    print(f"Parameters: {n_params:,}")
    print(f"Model size: {result['model']['saved_state_dict_MB']} MB (state_dict, fp32)")
    for r in result["inference"]:
        print(f"batch={r['batch_size']:<2} mean={r['mean_ms']:>6.3f} ms  p95={r['p95_ms']:>6.3f} ms  "
              f"throughput={r['throughput_windows_per_sec']:>8.1f} windows/s")
    print(f"Wrote {out}")
    print("================================\n")


if __name__ == "__main__":
    main()
