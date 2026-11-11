"""Evaluation metrics for note detection."""

import numpy as np
import mir_eval
from typing import Dict, List, Tuple, Optional
from mt.schema import load_json


def midi_to_hz(pitch: int) -> float:
    """Convert MIDI note number to frequency in Hz."""
    return 440.0 * (2.0 ** ((pitch - 69) / 12.0))


def notes_to_mir_eval_format(notes: List[Dict]) -> Tuple[np.ndarray, np.ndarray]:
    """Convert notes list to mir_eval transcription format.
    
    Returns:
        (pitches_hz, intervals)
        pitches_hz: array of frequencies in Hz
        intervals: array of (onset, offset) tuples in seconds
    """
    if not notes:
        return np.array([]), np.array([])
    
    pitches_hz = np.array([midi_to_hz(n["pitch"]) for n in notes])
    intervals = np.array([[n["onset"], n["offset"]] for n in notes])
    
    return pitches_hz, intervals


def compute_metrics(
    reference_notes: List[Dict],
    estimated_notes: List[Dict],
    onset_tolerance: float = 0.05,
    offset_ratio: Optional[float] = None,
    offset_min_tolerance: Optional[float] = None,
) -> Dict:
    """Compute precision, recall, F1 using mir_eval.
    
    Args:
        reference_notes: Ground truth notes
        estimated_notes: Detected notes
        onset_tolerance: Tolerance for onset matching in seconds
        offset_ratio: Ratio for offset matching (None for onset-only)
        offset_min_tolerance: Minimum tolerance for offset matching
    
    Returns:
        Dict with precision, recall, f1_score
    """
    ref_pitches, ref_intervals = notes_to_mir_eval_format(reference_notes)
    est_pitches, est_intervals = notes_to_mir_eval_format(estimated_notes)
    
    precision, recall, f1_score, _ = mir_eval.transcription.precision_recall_f1_overlap(
        ref_intervals,
        ref_pitches,
        est_intervals,
        est_pitches,
        onset_tolerance=onset_tolerance,
        offset_ratio=offset_ratio,
        offset_min_tolerance=offset_min_tolerance,
    )
    
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1_score),
    }


def evaluate_file(
    reference_path: str,
    estimated_path: str,
    onset_tolerance: float = 0.05,
    offset_ratio: Optional[float] = None,
    offset_min_tolerance: Optional[float] = None,
) -> Dict:
    """Evaluate a single file.
    
    Args:
        reference_path: Path to ground truth JSON
        estimated_path: Path to estimated JSON
    
    Returns:
        Dict with metrics
    """
    ref_data = load_json(reference_path)
    est_data = load_json(estimated_path)
    
    metrics = compute_metrics(
        ref_data["notes"],
        est_data["notes"],
        onset_tolerance=onset_tolerance,
        offset_ratio=offset_ratio,
        offset_min_tolerance=offset_min_tolerance,
    )
    
    return metrics


def evaluate_onset_only(
    reference_notes: List[Dict],
    estimated_notes: List[Dict],
    onset_tolerance: float = 0.05,
) -> Dict:
    """Evaluate with onset-only matching."""
    return compute_metrics(
        reference_notes,
        estimated_notes,
        onset_tolerance=onset_tolerance,
        offset_ratio=None,
    )


def evaluate_onset_offset(
    reference_notes: List[Dict],
    estimated_notes: List[Dict],
    onset_tolerance: float = 0.05,
    offset_ratio: float = 0.2,
    offset_min_tolerance: float = 0.05,
) -> Dict:
    """Evaluate with onset+offset matching."""
    return compute_metrics(
        reference_notes,
        estimated_notes,
        onset_tolerance=onset_tolerance,
        offset_ratio=offset_ratio,
        offset_min_tolerance=offset_min_tolerance,
    )
