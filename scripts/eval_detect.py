#!/usr/bin/env python3
"""Evaluation harness for note detection backends.

Usage: python scripts/eval_detect.py --dataset synth --backends naive

Datasets are directories containing <name>.wav + <name>.gt.json pairs.
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt.schema import load_json
from mt.evaluate import (
    evaluate_onset_only,
    evaluate_onset_offset,
    midi_to_hz,
)
from mt.backends import run_backend, list_backends


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
    tmp_dir: str = "tmp",
) -> Dict:
    """Evaluate a single backend on a single clip.
    
    Returns:
        Dict with metrics and timing info
    """
    os.makedirs(tmp_dir, exist_ok=True)
    
    # Generate output path
    output_json = os.path.join(tmp_dir, f"{backend_name}_{Path(wav_path).stem}.json")
    
    # Load ground truth
    gt_data = load_json(gt_json_path)
    
    # Run backend
    start_time = time.time()
    wall_time, peak_rss_kb = run_backend(backend_name, wav_path, output_json)
    end_time = time.time()
    
    # Load estimated notes
    est_data = load_json(output_json)
    
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
    
    # Calculate real-time factor
    # Need to get audio duration
    import soundfile as sf
    audio, fs = sf.read(wav_path)
    audio_duration = len(audio) / fs
    real_time_factor = wall_time / audio_duration if audio_duration > 0 else 0
    
    # Convert peak RSS to MB
    peak_rss_mb = peak_rss_kb / 1024.0
    
    return {
        "clip": Path(wav_path).stem,
        "backend": backend_name,
        "num_gt_notes": len(gt_data["notes"]),
        "num_est_notes": len(est_data["notes"]),
        "onset_only": metrics_onset,
        "onset_offset": metrics_onset_offset,
        "wall_time": wall_time,
        "real_time_factor": real_time_factor,
        "peak_rss_mb": peak_rss_mb,
    }


def format_metrics(metrics: Dict) -> str:
    """Format metrics for display."""
    onset = metrics["onset_only"]
    onset_offset = metrics["onset_offset"]
    
    return (
        f"{metrics['onset_only']['precision']:.3f} / "
        f"{metrics['onset_only']['recall']:.3f} / "
        f"{metrics['onset_only']['f1']:.3f} | "
        f"{metrics['onset_offset']['precision']:.3f} / "
        f"{metrics['onset_offset']['recall']:.3f} / "
        f"{metrics['onset_offset']['f1']:.3f} | "
        f"{metrics['real_time_factor']:.2f}x | "
        f"{metrics['peak_rss_mb']:.1f} MB"
    )


def print_markdown_table(results: List[Dict], dataset_name: str) -> str:
    """Print results as a Markdown table.
    
    Returns:
        Markdown table string
    """
    # Sort by clip name
    results = sorted(results, key=lambda r: r["clip"])
    
    # Build table
    table_lines = []
    
    # Header
    table_lines.append("| Clip | Backend | Notes | Onset-only (P/R/F1) | Onset+Offset (P/R/F1) | RT Factor | Peak RSS |")
    table_lines.append("|------|---------|-------|---------------------|----------------------|-----------|----------|")
    
    # Rows
    for r in results:
        clip = r["clip"]
        backend = r["backend"]
        notes = f"{r['num_gt_notes']}/{r['num_est_notes']}"
        
        onset = r["onset_only"]
        onset_str = f"{onset['precision']:.3f}/{onset['recall']:.3f}/{onset['f1']:.3f}"
        
        onset_offset = r["onset_offset"]
        onset_offset_str = f"{onset_offset['precision']:.3f}/{onset_offset['recall']:.3f}/{onset_offset['f1']:.3f}"
        
        rt_factor = f"{r['real_time_factor']:.2f}x"
        peak_rss = f"{r['peak_rss_mb']:.1f} MB"
        
        table_lines.append(
            f"| {clip} | {backend} | {notes} | {onset_str} | {onset_offset_str} | {rt_factor} | {peak_rss} |"
        )
    
    # Mean row
    if results:
        mean_onset_p = np.mean([r["onset_only"]["precision"] for r in results])
        mean_onset_r = np.mean([r["onset_only"]["recall"] for r in results])
        mean_onset_f1 = np.mean([r["onset_only"]["f1"] for r in results])
        
        mean_onset_offset_p = np.mean([r["onset_offset"]["precision"] for r in results])
        mean_onset_offset_r = np.mean([r["onset_offset"]["recall"] for r in results])
        mean_onset_offset_f1 = np.mean([r["onset_offset"]["f1"] for r in results])
        
        mean_rt = np.mean([r["real_time_factor"] for r in results])
        mean_rss = np.mean([r["peak_rss_mb"] for r in results])
        
        mean_onset_str = f"{mean_onset_p:.3f}/{mean_onset_r:.3f}/{mean_onset_f1:.3f}"
        mean_onset_offset_str = f"{mean_onset_offset_p:.3f}/{mean_onset_offset_r:.3f}/{mean_onset_offset_f1:.3f}"
        
        table_lines.append("| **mean** | | | " + mean_onset_str + " | " + mean_onset_offset_str + f" | {mean_rt:.2f}x | {mean_rss:.1f} MB |")
    
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
    
    output_path = os.path.join(output_dir, f"detect_{dataset_name}.json")
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    return output_path


def save_results_md(table: str, dataset_name: str, output_dir: str = "results") -> str:
    """Save results as Markdown.
    
    Returns:
        Path to saved Markdown file
    """
    os.makedirs(output_dir, exist_ok=True)
    
    output_path = os.path.join(output_dir, f"detect_{dataset_name}.md")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(table)
    
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Evaluate note detection backends")
    parser.add_argument("--dataset", type=str, required=True, help="Dataset name or path")
    parser.add_argument("--backends", type=str, required=True, 
                        help="Comma-separated list of backend names")
    parser.add_argument("--output-dir", type=str, default="results", 
                        help="Output directory for results")
    args = parser.parse_args()
    
    # Parse backends
    backend_names = [b.strip() for b in args.backends.split(",")]
    
    # Load dataset
    dataset_path = args.dataset
    if not os.path.isabs(dataset_path):
        dataset_path = os.path.join("out", dataset_path)
    
    clips = load_dataset(dataset_path)
    
    if not clips:
        print(f"No clips found in dataset: {dataset_path}")
        sys.exit(1)
    
    print(f"Evaluating {len(clips)} clips with backends: {backend_names}")
    
    # Run evaluation
    all_results = []
    
    for clip_name, wav_path, gt_json_path in clips:
        print(f"\nProcessing clip: {clip_name}")
        
        for backend_name in backend_names:
            print(f"  Backend: {backend_name}")
            
            try:
                result = evaluate_backend_on_clip(
                    backend_name,
                    wav_path,
                    gt_json_path,
                )
                all_results.append(result)
                print(f"    {format_metrics(result)}")
            except Exception as e:
                print(f"    ERROR: {e}")
                import traceback
                traceback.print_exc()
    
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
