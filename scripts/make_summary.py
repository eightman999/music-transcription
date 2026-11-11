#!/usr/bin/env python3
"""Generate Phase 1a summary from evaluation results.

Reads results/detect_<name>.json for: synth, maestro_test5, smd5, maestro_test5_degraded
Writes results/phase1a_summary.md in Japanese.
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_results(dataset_name: str) -> Optional[List[Dict]]:
    """Load results JSON for a dataset."""
    results_path = Path("results") / f"detect_{dataset_name}.json"
    if not results_path.exists():
        return None
    with open(results_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_backend_metrics(results: List[Dict], backend: str) -> Dict:
    """Get aggregated metrics for a backend from results."""
    backend_results = [r for r in results if r['backend'] == backend and not r.get('failed', False)]
    if not backend_results:
        return {'count': 0}
    
    # Onset-only metrics
    onset_only_f1s = [r['onset_only']['f1'] for r in backend_results if r.get('onset_only')]
    onset_offset_f1s = [r['onset_offset']['f1'] for r in backend_results if r.get('onset_offset')]
    onset_offset_sustained_f1s = [r['onset_offset_sustained']['f1'] for r in backend_results if r.get('onset_offset_sustained')]
    onset_velocity_f1s = [r['onset_velocity']['f1'] for r in backend_results if r.get('onset_velocity')]
    onset_devs = [r['onset_dev_median_ms'] for r in backend_results if r.get('onset_dev_median_ms') is not None]
    rt_factors = [r['real_time_factor'] for r in backend_results]
    rss_mbs = [r['peak_rss_mb'] for r in backend_results]
    
    # Device and version from first result
    device = backend_results[0].get('device', '')
    version = backend_results[0].get('version', '')
    
    total_clips = len([r for r in results if r['backend'] == backend])
    ok_clips = len(backend_results)
    
    return {
        'onset_only_f1': sum(onset_only_f1s) / len(onset_only_f1s) if onset_only_f1s else None,
        'onset_only_p': sum([r['onset_only']['precision'] for r in backend_results if r.get('onset_only')]) / len(onset_only_f1s) if onset_only_f1s else None,
        'onset_only_r': sum([r['onset_only']['recall'] for r in backend_results if r.get('onset_only')]) / len(onset_only_f1s) if onset_only_f1s else None,
        'onset_offset_f1': sum(onset_offset_f1s) / len(onset_offset_f1s) if onset_offset_f1s else None,
        'onset_offset_sustained_f1': sum(onset_offset_sustained_f1s) / len(onset_offset_sustained_f1s) if onset_offset_sustained_f1s else None,
        'onset_velocity_f1': sum(onset_velocity_f1s) / len(onset_velocity_f1s) if onset_velocity_f1s else None,
        'onset_dev_median': sum(onset_devs) / len(onset_devs) if onset_devs else None,
        'rt_factor': sum(rt_factors) / len(rt_factors) if rt_factors else None,
        'rss_mb': sum(rss_mbs) / len(rss_mbs) if rss_mbs else None,
        'device': device,
        'version': version,
        'ok_clips': ok_clips,
        'total_clips': total_clips,
    }


def format_f1(f1: Optional[float]) -> str:
    """Format F1 score."""
    if f1 is None:
        return "未測定"
    return f"{f1:.4f}"


def format_median(dev: Optional[float]) -> str:
    """Format median onset deviation."""
    if dev is None:
        return "未測定"
    return f"{dev:.1f}"


def format_rt(rt: Optional[float]) -> str:
    """Format real-time factor."""
    if rt is None:
        return "未測定"
    return f"{rt:.2f}x"


def format_rss(rss: Optional[float]) -> str:
    """Format RSS in MB."""
    if rss is None:
        return "未測定"
    return f"{rss:.1f} MB"


def make_dataset_table(dataset_name: str, results: List[Dict]) -> str:
    """Create a markdown table for a single dataset."""
    backends = sorted(set(r['backend'] for r in results if not r.get('failed', False)))
    
    lines = []
    lines.append(f"### {dataset_name}")
    lines.append("")
    lines.append("| Backend | Onset-only P | Onset-only R | Onset-only F1 | On+Off key F1 | On+Off sustained F1 | Onset+Velocity F1 | Onset dev median (ms) | RT | RSS | Device | Version | ok/total |")
    lines.append("|---------|--------------|--------------|--------------|---------------|---------------------|-------------------|----------------------|----|-----|--------|---------|---------|")
    
    for backend in backends:
        metrics = get_backend_metrics(results, backend)
        p_str = f"{metrics['onset_only_p']:.4f}" if metrics['onset_only_p'] is not None else "未測定"
        r_str = f"{metrics['onset_only_r']:.4f}" if metrics['onset_only_r'] is not None else "未測定"
        lines.append(f"| {backend} | {p_str} | {r_str} | {format_f1(metrics['onset_only_f1'])} | {format_f1(metrics['onset_offset_f1'])} | {format_f1(metrics['onset_offset_sustained_f1'])} | {format_f1(metrics['onset_velocity_f1'])} | {format_median(metrics['onset_dev_median'])} | {format_rt(metrics['rt_factor'])} | {format_rss(metrics['rss_mb'])} | {metrics['device']} | {metrics['version']} | {metrics['ok_clips']}/{metrics['total_clips']} |")
    
    return "\n".join(lines)


def make_overview_table(all_metrics: Dict[str, Dict[str, Dict]]) -> str:
    """Create overview table with onset-only F1 for all datasets."""
    datasets = ['synth', 'maestro_test5', 'smd5', 'maestro_test5_degraded']
    backends = sorted(set(b for d in all_metrics.values() for b in d.keys()))
    
    lines = []
    lines.append("### 概要 (Onset-only F1)")
    lines.append("")
    
    # Header
    header = "| Backend | synth | maestro_test5 | smd5 | maestro_test5_degraded |"
    lines.append(header)
    lines.append("|---------|-------|---------------|------|------------------------|")
    
    for backend in backends:
        cells = [f"{backend}"]
        for ds in datasets:
            if ds in all_metrics and backend in all_metrics[ds]:
                f1 = all_metrics[ds][backend].get('onset_only_f1')
                cells.append(format_f1(f1))
            else:
                cells.append("未測定")
        lines.append(f"| {' | '.join(cells)} |")
    
    return "\n".join(lines)


def make_decision_section(all_metrics: Dict[str, Dict[str, Dict]]) -> Tuple[str, str]:
    """Make decision section according to PLAN.md 4.5.
    
    Returns:
        (decision_text, status)
    """
    # Check which datasets are available
    has_maestro = 'maestro_test5' in all_metrics
    has_smd = 'smd5' in all_metrics
    
    # Get naive F1 on maestro_test5
    naive_maestro_f1 = None
    if has_maestro and 'naive' in all_metrics['maestro_test5']:
        naive_maestro_f1 = all_metrics['maestro_test5']['naive'].get('onset_only_f1')
    
    # Get naive F1 on smd5
    naive_smd_f1 = None
    if has_smd and 'naive' in all_metrics['smd5']:
        naive_smd_f1 = all_metrics['smd5']['naive'].get('onset_only_f1')
    
    # Get learned backends (everything except naive)
    learned_backends = []
    if has_maestro:
        for backend in all_metrics['maestro_test5']:
            if backend != 'naive' and all_metrics['maestro_test5'][backend].get('onset_only_f1') is not None:
                if naive_maestro_f1 is None or all_metrics['maestro_test5'][backend]['onset_only_f1'] > naive_maestro_f1:
                    learned_backends.append(backend)
    
    # Filter candidates: must beat naive on both maestro_test5 and smd5
    candidates = []
    for backend in learned_backends:
        maestro_f1 = all_metrics['maestro_test5'][backend].get('onset_only_f1') if has_maestro else None
        smd_f1 = all_metrics['smd5'].get(backend, {}).get('onset_only_f1') if has_smd else None
        
        if maestro_f1 is not None and (naive_maestro_f1 is None or maestro_f1 > naive_maestro_f1):
            if not has_smd or (smd_f1 is not None and (naive_smd_f1 is None or smd_f1 > naive_smd_f1)):
                candidates.append(backend)
    
    # If smd5 is absent, use maestro_test5 for decision
    if not has_smd:
        # Use maestro_test5 for ranking
        candidate_f1s = {}
        for backend in candidates:
            f1 = all_metrics['maestro_test5'][backend].get('onset_only_f1')
            if f1 is not None:
                candidate_f1s[backend] = f1
        
        if not candidate_f1s:
            return "候補がいません。", "未測定"
        
        best_f1 = max(candidate_f1s.values())
        tied = [b for b, f1 in candidate_f1s.items() if best_f1 - f1 <= 0.010]
        
        # Get RT factors on maestro_test5
        tied_rt = {b: all_metrics['maestro_test5'][b].get('rt_factor') for b in tied}
        adopted = min(tied_rt, key=tied_rt.get)
        
        decision_text = f"**暫定採用**: {adopted}\n\n"
        decision_text += f"候補: {candidates}\n"
        decision_text += f"F1 (maestro_test5): {', '.join(f'{b}: {candidate_f1s[b]:.4f}' for b in candidates)}\n"
        decision_text += f"同率: {tied}\n"
        decision_text += f"RT (maestro_test5): {', '.join(f'{b}: {tied_rt[b]:.2f}x' for b in tied)}\n"
        decision_text += f"採用: {adopted} (最も軽い)\n"
        
        return decision_text, "暫定採用"
    else:
        # Use smd5 for ranking
        candidate_f1s = {}
        for backend in candidates:
            f1 = all_metrics['smd5'][backend].get('onset_only_f1')
            if f1 is not None:
                candidate_f1s[backend] = f1
        
        if not candidate_f1s:
            return "候補がいません。", "未測定"
        
        best_f1 = max(candidate_f1s.values())
        tied = [b for b, f1 in candidate_f1s.items() if best_f1 - f1 <= 0.010]
        
        # Get RT factors on smd5
        tied_rt = {b: all_metrics['smd5'][b].get('rt_factor') for b in tied}
        adopted = min(tied_rt, key=tied_rt.get)
        
        decision_text = f"**採用**: {adopted}\n\n"
        decision_text += f"候補: {candidates}\n"
        decision_text += f"F1 (smd5): {', '.join(f'{b}: {candidate_f1s[b]:.4f}' for b in candidates)}\n"
        decision_text += f"同率: {tied}\n"
        decision_text += f"RT (smd5): {', '.join(f'{b}: {tied_rt[b]:.2f}x' for b in tied)}\n"
        decision_text += f"採用: {adopted} (最も軽い)\n"
        
        return decision_text, "採用"


def get_failed_clips(all_results: Dict[str, List[Dict]]) -> List[Tuple[str, str, str]]:
    """Get list of failed clips (backend, clip, error)."""
    failed = []
    for dataset, results in all_results.items():
        for r in results:
            if r.get('failed', False):
                failed.append((r['backend'], r['clip'], r.get('error', 'Unknown error')))
    return failed


def get_unmeasured_datasets() -> List[str]:
    """Get list of unmeasured datasets."""
    datasets = ['synth', 'maestro_test5', 'smd5', 'maestro_test5_degraded']
    unmeasured = []
    for ds in datasets:
        if not Path("results").joinpath(f"detect_{ds}.json").exists():
            unmeasured.append(ds)
    return unmeasured


def get_newest_modification_date():
    """Get the newest modification date among result JSON files."""
    from datetime import datetime
    datasets = ['synth', 'maestro_test5', 'smd5', 'maestro_test5_degraded']
    newest_date = None
    
    for ds in datasets:
        results_path = Path("results") / f"detect_{ds}.json"
        if results_path.exists():
            mtime = results_path.stat().st_mtime
            if newest_date is None or mtime > newest_date:
                newest_date = mtime
    
    if newest_date is None:
        return "未測定"
    return datetime.fromtimestamp(newest_date).strftime("%Y-%m-%d")


def main():
    # Load all results
    datasets = ['synth', 'maestro_test5', 'smd5', 'maestro_test5_degraded']
    all_results = {}
    all_metrics = {}
    
    for ds in datasets:
        results = load_results(ds)
        if results:
            all_results[ds] = results
            all_metrics[ds] = {}
            for r in results:
                backend = r['backend']
                if backend not in all_metrics[ds]:
                    all_metrics[ds][backend] = get_backend_metrics(results, backend)
    
    # Build summary
    lines = []
    lines.append("# Phase 1a: 検出部の比較と選定 - サマリー")
    lines.append("")
    lines.append("## 実行日")
    lines.append(get_newest_modification_date())
    lines.append("")
    
    # Dataset tables
    lines.append("## データセット別結果")
    lines.append("")
    
    for ds in datasets:
        if ds in all_results:
            lines.append(make_dataset_table(ds, all_results[ds]))
            lines.append("")
        else:
            lines.append(f"### {ds}")
            lines.append("")
            lines.append("未測定")
            lines.append("")
    
    # Overview table
    lines.append("## 概要表")
    lines.append("")
    lines.append(make_overview_table(all_metrics))
    lines.append("")
    
    # Decision section
    decision_text, status = make_decision_section(all_metrics)
    lines.append("## 採用決定 (PLAN.md 4.5)")
    lines.append("")
    lines.append("### 基準")
    lines.append("1. (b) MAESTRO test split と (c) SMD の onset F1 平均が素朴バックエンドを上回ること")
    lines.append("2. 候補間の優劣は (c) SMD を優先する")
    lines.append("3. 差が 1 ポイント未満なら軽い方を採る")
    lines.append("4. (c) が未測定の場合は「暫定採用」")
    lines.append("")
    lines.append("### 決定")
    lines.append(decision_text)
    
    # Attention section
    lines.append("## 注意")
    lines.append("")
    lines.append("- MAESTRO の test split は kong / transkun の学習データと同じ分布（同じコンクール・同じ系統のピアノ）であり、SMD が分布外の確認である。")
    lines.append("- On+Off は基準が 2 通りある（鍵を離した時刻／サステインペダルで延長した時刻）。モデルごとに出力の流儀が違うため両方を載せ、主指標は onset-only とする。")
    lines.append("- 劣化版（残響・ピンクノイズ・MP3）は頑健性の参考であり、実環境の録音の代わりではない。")
    lines.append("- onset+velocity は mir_eval の線形再スケーリング後の比較で、相対的な強弱の一致を見ている。")
    lines.append("")
    
    # Failed clips
    failed = get_failed_clips(all_results)
    if failed:
        lines.append("## 失敗したクリップ")
        lines.append("")
        for backend, clip, error in failed:
            lines.append(f"- {backend}: {clip} - {error}")
        lines.append("")
    
    # Unmeasured datasets
    unmeasured = get_unmeasured_datasets()
    if unmeasured:
        lines.append("## 未測定のデータセット")
        lines.append("")
        for ds in unmeasured:
            lines.append(f"- {ds}")
        lines.append("")
    
    # Write output
    output_path = Path("results") / "phase1a_summary.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    
    print(f"Summary written to {output_path}")


if __name__ == "__main__":
    main()
