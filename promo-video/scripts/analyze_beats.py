#!/usr/bin/env python3
"""Create the auditable beat-grid artifacts required by video-shotcraft."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import librosa
import numpy as np
from scipy.signal import butter, sosfilt


def band_env(y: np.ndarray, sr: int, lo: float, hi: float) -> tuple[np.ndarray, np.ndarray]:
    sos = butter(4, [lo, hi], btype="band", fs=sr, output="sos")
    env = librosa.onset.onset_strength(y=sosfilt(sos, y), sr=sr)
    return env, librosa.times_like(env, sr=sr)


def nearest_error(values: np.ndarray, target: np.ndarray) -> np.ndarray:
    idx = np.searchsorted(values, target)
    idx = np.clip(idx, 1, len(values) - 1)
    left = values[idx - 1]
    right = values[idx]
    return np.where(np.abs(target - left) <= np.abs(right - target), left - target, right - target)


def candidate_metrics(
    onset_times: np.ndarray,
    t0: float,
    period: float,
    end: float,
) -> dict[str, float | int | bool]:
    beats = np.arange(t0, end, period)
    errors = nearest_error(onset_times, beats)
    matched = np.abs(errors) <= 0.035
    usable = errors[matched]
    if len(usable) > 1:
        slope = float(np.polyfit(beats[matched], usable, 1)[0])
        drift_ms = abs(slope * (beats[matched][-1] - beats[matched][0]) * 1000)
    else:
        drift_ms = float("inf")
    return {
        "beat_count": int(len(beats)),
        "match": float(np.mean(matched)) if len(matched) else 0.0,
        "mean_abs_ms": float(np.mean(np.abs(usable)) * 1000) if len(usable) else float("inf"),
        "drift_ms": drift_ms,
        "first_beat_has_transient": bool(len(errors) and abs(errors[0]) <= 0.035),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--analysis-seconds", type=float, default=60.0)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    y, sr = librosa.load(args.input, sr=None, mono=True, duration=args.analysis_seconds)
    _, y_perc = librosa.effects.hpss(y)

    _tempo, beat_times = librosa.beat.beat_track(
        y=y_perc,
        sr=sr,
        tightness=400,
        units="time",
    )
    if len(beat_times) < 8:
        raise RuntimeError("Too few beats detected for a stable grid")

    i = np.arange(len(beat_times), dtype=float)
    design = np.vstack([i, np.ones_like(i)]).T
    (period, t0), *_ = np.linalg.lstsq(design, beat_times, rcond=None)
    residual = beat_times - (t0 + i * period)

    onset_env = librosa.onset.onset_strength(y=y_perc, sr=sr)
    onset_times_all = librosa.times_like(onset_env, sr=sr)
    onset_idx = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units="frames")
    onset_times = onset_times_all[onset_idx]

    candidate_rows: list[dict[str, object]] = []
    for bpm_factor in (0.5, 1.0, 2.0):
        candidate_period = period / bpm_factor
        metrics = candidate_metrics(onset_times, t0, candidate_period, len(y) / sr)
        candidate_rows.append(
            {
                "factor": bpm_factor,
                "bpm": 60.0 / candidate_period,
                "period": candidate_period,
                **metrics,
            }
        )

    # Machine-made house music is expected around 90–150 BPM. Within that range,
    # prefer onset coverage, then alignment error, then drift.
    eligible = [row for row in candidate_rows if 90 <= float(row["bpm"]) <= 150]
    winner = max(
        eligible or candidate_rows,
        key=lambda row: (
            float(row["match"]),
            -float(row["mean_abs_ms"]),
            -float(row["drift_ms"]),
        ),
    )
    winning_period = float(winner["period"])
    winning_bpm = float(winner["bpm"])

    # Re-anchor the winning grid to the closest detected transient around t0.
    near = onset_times[np.argmin(np.abs(onset_times - t0))]
    winning_t0 = float(near)
    while winning_t0 - winning_period >= 0:
        winning_t0 -= winning_period
    beats = np.arange(winning_t0, len(y) / sr, winning_period)

    kick_env, band_times = band_env(y_perc, sr, 40, 160)
    snare_low, _ = band_env(y_perc, sr, 150, 500)
    snare_hi, _ = band_env(y_perc, sr, 1000, 3000)
    hat_env, _ = band_env(y_perc, sr, 6000, min(14000, sr / 2 - 100))
    bands = {
        "kick": kick_env / (np.max(kick_env) + 1e-9),
        "snare": (snare_low / (np.max(snare_low) + 1e-9) + snare_hi / (np.max(snare_hi) + 1e-9)) / 2,
        "hihat": hat_env / (np.max(hat_env) + 1e-9),
    }
    hits: list[dict[str, object]] = []
    for n, beat in enumerate(beats):
        idx = int(np.argmin(np.abs(band_times - beat)))
        scores = {name: float(env[idx]) for name, env in bands.items()}
        kind = max(scores, key=scores.get)
        hits.append({"beat": n, "t": float(beat), "s": scores[kind], "k": kind, "bands": scores})

    rms = librosa.feature.rms(y=y)[0]
    rms_times = librosa.times_like(rms, sr=sr)
    rms_rows = [{"t": float(t), "v": float(v)} for t, v in zip(rms_times, rms, strict=True)]

    strongest = sorted(hits, key=lambda h: float(h["bands"]["kick"]), reverse=True)[:12]
    beat_data = {
        "source": args.input.name,
        "sample_rate": sr,
        "analyzed_seconds": len(y) / sr,
        "bpm": winning_bpm,
        "t0": winning_t0,
        "T": winning_period,
        "fit_residual_max_ms": float(np.max(np.abs(residual)) * 1000),
        "beats": [float(v) for v in beats],
        "hits": hits,
        "strongest_kicks": strongest,
        "rms": rms_rows,
        "sections": [],
    }
    (args.output_dir / "beat_data.json").write_text(json.dumps(beat_data, indent=2), encoding="utf-8")

    grid_drift = {
        "candidates": candidate_rows,
        "winner": winner,
        "winner_reason": "Highest transient coverage in the expected house-music BPM range, then lowest mean error and drift.",
        "raw_fit": {
            "bpm": 60.0 / period,
            "t0": float(t0),
            "period": float(period),
            "residual_max_ms": float(np.max(np.abs(residual)) * 1000),
        },
    }
    (args.output_dir / "grid_drift.json").write_text(json.dumps(grid_drift, indent=2), encoding="utf-8")

    print(json.dumps({"beat_data": beat_data, "grid_drift": grid_drift}, indent=2))


if __name__ == "__main__":
    main()
