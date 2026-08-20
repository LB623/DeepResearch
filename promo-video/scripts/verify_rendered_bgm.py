#!/usr/bin/env python3
"""Verify that the rendered BGM keeps the intended source-audio offset.

The rendered BGM is isolated by subtracting the SFX-only render before this
script is called.  Correlating a stable middle window avoids the deliberate
fade-in/out and measures mux/render timing independently of beat detection.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, resample_poly, sosfilt


def read_mono(path: Path) -> tuple[int, np.ndarray]:
    sample_rate, data = wavfile.read(path)
    samples = np.asarray(data)
    if samples.ndim == 2:
        samples = samples.mean(axis=1)
    if np.issubdtype(samples.dtype, np.integer):
        scale = float(max(abs(np.iinfo(samples.dtype).min), np.iinfo(samples.dtype).max))
        samples = samples.astype(np.float64) / scale
    else:
        samples = samples.astype(np.float64)
    return sample_rate, samples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("rendered_isolated", type=Path)
    parser.add_argument("--expected-offset", type=float, required=True)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source_rate, source = read_mono(args.source)
    rendered_rate, rendered = read_mono(args.rendered_isolated)
    if source_rate != rendered_rate:
        raise RuntimeError(f"Sample-rate mismatch: {source_rate} vs {rendered_rate}")

    target_rate = 3000
    source = resample_poly(source, target_rate, source_rate)
    rendered = resample_poly(rendered, target_rate, rendered_rate)

    # Remove low-frequency gain-envelope differences left by the mix and AAC.
    highpass = butter(3, 80, btype="highpass", fs=target_rate, output="sos")
    source = sosfilt(highpass, source)
    rendered = sosfilt(highpass, rendered)

    window_start = int(2.0 * target_rate)
    window_end = min(int(22.0 * target_rate), len(rendered) - 1)
    probe = rendered[window_start:window_end]
    probe_norm = np.linalg.norm(probe)
    if probe_norm == 0:
        raise RuntimeError("Rendered BGM probe is silent")

    lo = int(-0.02 * target_rate)
    hi = int(0.15 * target_rate)
    best_offset = 0
    best_score = -1.0
    for offset in range(lo, hi + 1):
        start = window_start + offset
        candidate = source[start : start + len(probe)]
        if len(candidate) != len(probe):
            continue
        denom = probe_norm * np.linalg.norm(candidate)
        score = float(np.dot(probe, candidate) / denom) if denom else -1.0
        if score > best_score:
            best_score = score
            best_offset = offset

    measured_seconds = best_offset / target_rate
    error_seconds = measured_seconds - args.expected_offset
    result = {
        "expected_source_offset_seconds": args.expected_offset,
        "measured_source_offset_seconds": measured_seconds,
        "absolute_error_seconds": abs(error_seconds),
        "absolute_error_frames": abs(error_seconds) * args.fps,
        "correlation": best_score,
        "analysis_window_seconds": [2.0, window_end / target_rate],
        "analysis_sample_rate": target_rate,
    }
    payload = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{payload}\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
