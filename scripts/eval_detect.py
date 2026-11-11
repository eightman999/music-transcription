#!/usr/bin/env python3
"""Evaluation harness for note detection backends.

Usage: python scripts/eval_detect.py --dataset synth --backends naive

Datasets are directories containing <name>.wav + <name>.gt.json pairs.
The special dataset name 'synth' refers to out/synth.
"""

import os
import sys
import json
import time
import hashlib
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt.schema import load_json
from mt.evaluate import (
    evaluate_onset_only,
    evaluate_onset_offset,
    evaluate_onset_offset_sustained,
    evaluate_onset_velocity,
    compute_onset_deviation,
    midi_to_hz,
)
from mt.backends import run_backend, list_backends


def compute_sha256(filepath: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def get_cache_dir(dataset_name: str, backend_name: str) -> Path:
    """Get the cache directory for a dataset and backend."""
    return Path("out") / "detect" / dataset_name / backend_name


def get_cache_path(dataset_name: str, backend_name: str, clip_name: str) -> Tuple[Path, Path]:
    """Get the cache paths for a clip.
    
    Returns:
        Tuple of (output_json_path, run_json_path)
    """
    cache_dir = get_cache_dir(dataset_name, backend_name)
    cache_dir.mkdir(parents=True, exist_ok=True)
    return (
        cache_dir / f"{clip_name}.json",
        cache_dir / f"{clip_name}.run.json",
    )


def save_cache(
    output_json: str,
    run_json: str,
    wav_path: str,
    wall_time: float,
    peak_rss_mb: float,
    real_time_factor: float,
) -> None:
    """Save cache files for a backend run."""
    # Save the output JSON (already exists from run_backend)
    # Save the run metadata
    run_data = {
        "wav_sha256": compute_sha256(wav_path),
        "wall_time": wall_time,
        "real_time_factor": real_time_factor,
        "peak_rss_mb": peak_rss_mb,
    }
    with open(run_json, 'w', encoding='utf-8') as f:
        json.dump(run_data, f, indent=2, ensure_ascii=False)


def load_cache_valid(wav_path: str, run_json_path: str) -> bool:
    """Check if cache is valid for the current wav file."""
    run_json = Path(run_json_path)
    if not run_json.exists():
        return False
    
    try:
        with open(run_json, 'r', encoding='utf-8') as f:
            run_data = json.load(f)
        
        current_sha256 = compute_sha256(wav_path)
        return run_data.get("wav_sha256") == current_sha256
    except Exception:
        return False


def sort_notes_by_onset_pitch(notes):
    """Sort notes by (onset, pitch) to ensure consistent ordering."""
    return sorted(notes, key=lambda n: (n["onset"], n["pitch"]))


def load_dataset(dataset_path: str) -> List[Tuple[str, str, str]]:
    """Load a dataset directory.
    
    Returns:
        List of (name, wav_path, gt_json_path) tuples
    """
    dataset_path = Path(dataset_path)
    clips = []
    
    for wav_file in dataset_path.glob("*.wav"):
        name = wav_file.stem
        gt_json = wav_file.with_suffix(".gt.json")
        
        if gt_json.exists():
            clips.append((name, str(wav_file), str(gt_json)))
    
    return clips


def evaluate_backend_on_clip(
    backend_name: str,
    wav_path: str,
    gt_json_path: str,
    dataset_name: str,
    no_cache: bool = False,
) -> Dict:
    """Evaluate a single backend on a single clip.
    
    Args:
        backend_name: Name of the backend
        wav_path: Path to WAV file
        gt_json_path: Path to ground truth JSON
        dataset_name: Name of the dataset (for cache directory)
        no_cache: If True, force re-run even if cache exists
        
    Returns:
        Dict with metrics and timing info
    """
    clip_name = Path(wav_path).stem
    
    # Load ground truth
    gt_data = load_json(gt_json_path)
    
    # Check cache
    cache_json, cache_run = get_cache_path(dataset_name, backend_name, clip_name)
    use_cache = not no_cache and cache_json.exists() and cache_run.exists() and load_cache_valid(wav_path, str(cache_run))
    
    if use_cache:
        # Load from cache
        print(f"    cached")
        try:
            est_data = load_json(str(cache_json))
            
            # Load run metadata
            with open(str(cache_run), 'r', encoding='utf-8') as f:
                run_data = json.load(f)
            
            wall_time = run_data["wall_time"]
            peak_rss_mb = run_data["peak_rss_mb"]
            real_time_factor = run_data["real_time_factor"]
            
            # Sort notes by (onset, pitch) to ensure consistent ordering
            est_data["notes"] = sort_notes_by_onset_pitch(est_data.get("notes", []))
            num_est_notes = len(est_data["notes"])
            
            # Get meta if present
            meta = est_data.get("meta", {})
            device = meta.get("device", "")
            version = meta.get("version", "")
            
        except Exception as e:
            return {
                "clip": clip_name,
                "backend": backend_name,
                "num_gt_notes": len(gt_data["notes"]),
                "num_est_notes": 0,
                "onset_only": None,
                "onset_offset": None,
                "onset_offset_sustained": None,
                "onset_velocity": None,
                "onset_dev_median_ms": None,
                "wall_time": 0,
                "real_time_factor": 0,
                "peak_rss_mb": 0,
                "device": "",
                "version": "",
                "failed": True,
                "error": f"Failed to load cache: {e}",
            }
    else:
        # Run backend
        start_time = time.time()
        try:
            wall_time, peak_rss_mb = run_backend(backend_name, wav_path, str(cache_json))
            backend_failed = False
            error_message = None
        except Exception as e:
            wall_time = 0
            peak_rss_mb = 0
            backend_failed = True
            error_message = str(e)
        end_time = time.time()
        
        if backend_failed:
            # Backend failed - return error
            return {
                "clip": clip_name,
                "backend": backend_name,
                "num_gt_notes": len(gt_data["notes"]),
                "num_est_notes": 0,
                "onset_only": None,
                "onset_offset": None,
                "onset_offset_sustained": None,
                "onset_velocity": None,
                "onset_dev_median_ms": None,
                "wall_time": wall_time,
                "real_time_factor": 0,
                "peak_rss_mb": peak_rss_mb,
                "device": "",
                "version": "",
                "failed": True,
                "error": error_message,
            }
        
        # Load estimated notes
        try:
            est_data = load_json(str(cache_json))
            
            # Sort notes by (onset, pitch) to ensure consistent ordering
            est_data["notes"] = sort_notes_by_onset_pitch(est_data.get("notes", []))
            num_est_notes = len(est_data["notes"])
            
            # Get meta if present
            meta = est_data.get("meta", {})
            device = meta.get("device", "")
            version = meta.get("version", "")
            
            # Calculate real-time factor
            import soundfile as sf
            audio, fs = sf.read(wav_path)
            audio_duration = len(audio) / fs
            real_time_factor = wall_time / audio_duration if audio_duration > 0 else 0
            
            # Save cache
            save_cache(str(cache_json), str(cache_run), wav_path, wall_time, peak_rss_mb, real_time_factor)
            
        except Exception as e:
            return {
                "clip": clip_name,
                "backend": backend_name,
                "num_gt_notes": len(gt_data["notes"]),
                "num_est_notes": 0,
                "onset_only": None,
                "onset_offset": None,
                "onset_offset_sustained": None,
                "onset_velocity": None,
                "onset_dev_median_ms": None,
                "wall_time": wall_time,
                "real_time_factor": 0,
                "peak_rss_mb": peak_rss_mb,
                "device": "",
                "version": "",
                "failed": True,
                "error": f"Failed to load output: {e}",
            }
    
    # Compute metrics
    metrics_onset = evaluate_onset_only(
        gt_data["notes"],
        est_data["notes"],
        onset_tolerance=0.05,
    )
    
    metrics_onset_offset = evaluate_onset_offset(
        gt_data["notes"],
        est_data["notes"],
        onset_tolerance=0.05,
        offset_ratio=0.2,
        offset_min_tolerance=0.05,
    )
    
    # Compute sustained offset metrics
    pedal = gt_data.get("pedal", None)
    if pedal is not None:
        metrics_onset_offset_sustained = evaluate_onset_offset_sustained(
            gt_data["notes"],
            est_data["notes"],
            reference_pedal=pedal,
            onset_tolerance=0.05,
            offset_ratio=0.2,
            offset_min_tolerance=0.05,
        )
    else:
        metrics_onset_offset_sustained = None
    
    # Compute velocity metrics
    metrics_onset_velocity = evaluate_onset_velocity(
        gt_data["notes"],
        est_data["notes"],
        onset_tolerance=0.05,
        velocity_tolerance=0.1,
    )
    
    # Compute onset deviation
    onset_dev = compute_onset_deviation(
        gt_data["notes"],
        est_data["notes"],
        onset_tolerance=0.05,
    )
    onset_dev_median_ms = onset_dev["onset_dev_median_ms"] if onset_dev else None
    
    return {
        "clip": clip_name,
        "backend": backend_name,
        "num_gt_notes": len(gt_data["notes"]),
        "num_est_notes": num_est_notes,
        "onset_only": metrics_onset,
        "onset_offset": metrics_onset_offset,
        "onset_offset_sustained": metrics_onset_offset_sustained,
        "onset_velocity": metrics_onset_velocity,
        "onset_dev_median_ms": onset_dev_median_ms,
        "wall_time": wall_time,
        "real_time_factor": real_time_factor,
        "peak_rss_mb": peak_rss_mb,
        "device": device,
        "version": version,
        "failed": False,
        "error": None,
    }


def format_metrics(metrics: Dict) -> str:
    """Format metrics for display."""
    def fmt_metrics(m):
        if m is None:
            return "n/a"
        return f"{m['precision']:.3f}/{m['recall']:.3f}/{m['f1']:.3f}"
    
    def fmt_float(v):
        if v is None:
            return "n/a"
        return f"{v:.1f}"
    
    return (
        f"On+Off key: {fmt_metrics(metrics.get('onset_offset'))} | "
        f"On+Off sustained: {fmt_metrics(metrics.get('onset_offset_sustained'))} | "
        f"Onset dev: {fmt_float(metrics.get('onset_dev_median_ms'))} ms | "
        f"RT: {metrics['real_time_factor']:.2f}x | "
        f"RSS: {metrics['peak_rss_mb']:.1f} MB"
    )


def print_markdown_table(results: List[Dict], dataset_name: str) -> str:
    """Print results as a Markdown table.
    
    Returns:
        Markdown table string
    """
    # Sort by clip name, then backend
    results = sorted(results, key=lambda r: (r["clip"], r["backend"]))
    
    # Helper functions for formatting
    def fmt_metrics(m):
        if m is None:
            return "n/a"
        return f"{m['precision']:.3f}/{m['recall']:.3f}/{m['f1']:.3f}"
    
    def fmt_float(v):
        if v is None:
            return "n/a"
        return f"{v:.1f}"
    
    # Build table
    table_lines = []
    
    # Header
    table_lines.append("| Clip | Backend | GT | Est | On+Off key (P/R/F1) | On+Off sustained (P/R/F1) | Onset dev (ms) | RT | RSS | Clips |")
    table_lines.append("|------|---------|----|-----|---------------------|--------------------------|---------------|----|-----|-------|")
    
    # Rows
    for r in results:
        clip = r["clip"]
        backend = r["backend"]
        num_gt = r["num_gt_notes"]
        num_est = r["num_est_notes"]
        
        if r["failed"]:
            # Failed run - show error but don't include in mean
            error_msg = r["error"] if r["error"] else "Unknown error"
            table_lines.append(
                f"| {clip} | {backend} | {num_gt} | FAILED | n/a | n/a | n/a | - | - | error |"
            )
        else:
            onset_offset_str = fmt_metrics(r.get("onset_offset"))
            onset_offset_sustained_str = fmt_metrics(r.get("onset_offset_sustained"))
            onset_dev_str = fmt_float(r.get("onset_dev_median_ms"))
            rt_factor = f"{r['real_time_factor']:.2f}x"
            peak_rss = f"{r['peak_rss_mb']:.1f} MB"
            
            table_lines.append(
                f"| {clip} | {backend} | {num_gt} | {num_est} | {onset_offset_str} | {onset_offset_sustained_str} | {onset_dev_str} | {rt_factor} | {peak_rss} | |")
    
    # Mean row per backend (only for successful runs)
    successful_results = [r for r in results if not r["failed"]]
    if successful_results:
        # Group by backend
        backends = set(r["backend"] for r in successful_results)
        for backend in sorted(backends):
            backend_results = [r for r in successful_results if r["backend"] == backend]
            
            # Onset+offset metrics (key release)
            onset_offset_p = [r["onset_offset"]["precision"] for r in backend_results if r["onset_offset"] is not None]
            onset_offset_r = [r["onset_offset"]["recall"] for r in backend_results if r["onset_offset"] is not None]
            onset_offset_f1 = [r["onset_offset"]["f1"] for r in backend_results if r["onset_offset"] is not None]
            
            # Onset+offset sustained metrics
            onset_offset_sustained_p = [r["onset_offset_sustained"]["precision"] for r in backend_results if r.get("onset_offset_sustained") is not None]
            onset_offset_sustained_r = [r["onset_offset_sustained"]["recall"] for r in backend_results if r.get("onset_offset_sustained") is not None]
            onset_offset_sustained_f1 = [r["onset_offset_sustained"]["f1"] for r in backend_results if r.get("onset_offset_sustained") is not None]
            
            # Onset deviation
            onset_dev_values = [r["onset_dev_median_ms"] for r in backend_results if r.get("onset_dev_median_ms") is not None]
            
            mean_onset_offset_str = fmt_metrics({
                "precision": np.mean(onset_offset_p) if onset_offset_p else 0,
                "recall": np.mean(onset_offset_r) if onset_offset_r else 0,
                "f1": np.mean(onset_offset_f1) if onset_offset_f1 else 0,
            }) if onset_offset_p else "n/a"
            
            mean_onset_offset_sustained_str = fmt_metrics({
                "precision": np.mean(onset_offset_sustained_p) if onset_offset_sustained_p else 0,
                "recall": np.mean(onset_offset_sustained_r) if onset_offset_sustained_r else 0,
                "f1": np.mean(onset_offset_sustained_f1) if onset_offset_sustained_f1 else 0,
            }) if onset_offset_sustained_p else "n/a"
            
            mean_onset_dev_str = fmt_float(np.mean(onset_dev_values)) if onset_dev_values else "n/a"
            
            mean_rt = np.mean([r["real_time_factor"] for r in backend_results])
            mean_rss = np.mean([r["peak_rss_mb"] for r in backend_results])
            
            mean_num_gt = int(np.mean([r["num_gt_notes"] for r in backend_results]))
            mean_num_est = int(np.mean([r["num_est_notes"] for r in backend_results]))
            
            # Count total clips for this backend
            total_clips = len([r for r in results if r["backend"] == backend])
            ok_clips = len(backend_results)
            
            table_lines.append(
                f"| **mean** | {backend} | {mean_num_gt} | {mean_num_est} | {mean_onset_offset_str} | {mean_onset_offset_sustained_str} | {mean_onset_dev_str} | {mean_rt:.2f}x | {mean_rss:.1f} MB | {ok_clips}/{total_clips} |")
    
    table = "\n".join(table_lines)
    
    # Add title
    title = f"# Evaluation Results: {dataset_name}\n\n"
    
    return title + table


def save_results_json(results: List[Dict], dataset_name: str, output_dir: str = "results") -> str:
    """Save results as JSON.
    
    Returns:
        Path to saved JSON file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Use basename of dataset_name to avoid path separators in filename
    dataset_basename = os.path.basename(dataset_name)
    output_path = os.path.join(output_dir, f"detect_{dataset_basename}.json")
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    return output_path


def save_results_md(table: str, dataset_name: str, output_dir: str = "results") -> str:
    """Save results as Markdown.
    
    Returns:
        Path to saved Markdown file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Use basename of dataset_name to avoid path separators in filename
    dataset_basename = os.path.basename(dataset_name)
    output_path = os.path.join(output_dir, f"detect_{dataset_basename}.md")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(table)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Evaluate note detection backends")
    parser.add_argument("--dataset", type=str, required=True, 
                        help="Dataset name or path. Use 'synth' for the synthetic dataset.")
    parser.add_argument("--backends", type=str, required=True, 
                        help="Comma-separated list of backend names")
    parser.add_argument("--output-dir", type=str, default="results", 
                        help="Output directory for results")
    parser.add_argument("--no-cache", action="store_true",
                        help="Force re-run backends, ignoring cache")
    args = parser.parse_args()
    
    # Parse backends
    backend_names = [b.strip() for b in args.backends.split(",")]
    
    # Resolve dataset path
    dataset_path = args.dataset
    if dataset_path == "synth":
        # Special case: synth dataset is in out/synth
        dataset_path = os.path.join("out", "synth")
    elif not os.path.isabs(dataset_path):
        # Relative path: resolve from current directory
        dataset_path = os.path.abspath(dataset_path)
    
    # Load dataset
    clips = load_dataset(dataset_path)
    
    if not clips:
        print(f"No clips found in dataset: {dataset_path}")
        sys.exit(1)
    
    print(f"Evaluating {len(clips)} clips with backends: {backend_names}")
    
    # Run evaluation
    all_results = []
    
    # Get dataset basename for cache directory
    dataset_basename = os.path.basename(dataset_path)
    
    for clip_name, wav_path, gt_json_path in clips:
        print(f"\nProcessing clip: {clip_name}")
        
        for backend_name in backend_names:
            print(f"  Backend: {backend_name}")
            
            try:
                result = evaluate_backend_on_clip(
                    backend_name,
                    wav_path,
                    gt_json_path,
                    dataset_basename,
                    no_cache=args.no_cache,
                )
                all_results.append(result)
                
                if result["failed"]:
                    print(f"    FAILED: {result['error']}")
                else:
                    print(f"    {format_metrics(result)}")
            except Exception as e:
                print(f"    ERROR: {e}")
                import traceback
                traceback.print_exc()
                all_results.append({
                    "clip": clip_name,
                    "backend": backend_name,
                    "num_gt_notes": 0,
                    "num_est_notes": 0,
                    "onset_only": None,
                    "onset_offset": None,
                    "onset_offset_sustained": None,
                    "onset_velocity": None,
                    "onset_dev_median_ms": None,
                    "wall_time": 0,
                    "real_time_factor": 0,
                    "peak_rss_mb": 0,
                    "device": "",
                    "version": "",
                    "failed": True,
                    "error": str(e),
                })
    
    # Print and save results
    table = print_markdown_table(all_results, args.dataset)
    print("\n" + table)
    
    # Save files
    md_path = save_results_md(table, args.dataset, args.output_dir)
    json_path = save_results_json(all_results, args.dataset, args.output_dir)
    
    print(f"\nSaved results to:")
    print(f"  {md_path}")
    print(f"  {json_path}")


if __name__ == "__main__":
    main()
