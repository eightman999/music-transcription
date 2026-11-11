"""Evaluation metrics for note detection."""

import numpy as np
import mir_eval
from typing import Dict, List, Tuple, Optional
from mt.schema import load_json
from mt.gt import sustain_extended


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


def evaluate_onset_velocity(
    reference_notes: List[Dict],
    estimated_notes: List[Dict],
    onset_tolerance: float = 0.05,
    velocity_tolerance: float = 0.1,
) -> Dict:
    """Evaluate onset+velocity matching using mir_eval.
    
    Uses mir_eval.transcription_velocity.precision_recall_f1_overlap with
    onset tolerance 0.05, offset_ratio=None (onset-only), and default velocity tolerance 0.1.
    
    Velocities are compared after mir_eval's own linear rescaling, so this measures
    relative dynamics, not absolute loudness.
    
    Args:
        reference_notes: Ground truth notes
        estimated_notes: Detected notes
        onset_tolerance: Tolerance for onset matching in seconds
        velocity_tolerance: Tolerance for velocity matching (default 0.1)
    
    Returns:
        Dict with precision, recall, f1_score
    """
    ref_pitches, ref_intervals = notes_to_mir_eval_format(reference_notes)
    est_pitches, est_intervals = notes_to_mir_eval_format(estimated_notes)
    
    # Get velocities
    ref_velocities = np.array([n["velocity"] for n in reference_notes])
    est_velocities = np.array([n["velocity"] for n in estimated_notes])
    
    precision, recall, f1_score, _ = mir_eval.transcription_velocity.precision_recall_f1_overlap(
        ref_intervals,
        ref_pitches,
        ref_velocities,
        est_intervals,
        est_pitches,
        est_velocities,
        onset_tolerance=onset_tolerance,
        offset_ratio=None,
        velocity_tolerance=velocity_tolerance,
    )
    
    return {
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1_score),
    }


def compute_onset_deviation(
    reference_notes: List[Dict],
    estimated_notes: List[Dict],
    onset_tolerance: float = 0.05,
) -> Optional[Dict]:
    """Compute onset timing deviation metrics.
    
    With mir_eval.transcription.match_notes (onset 0.05, offset_ratio=None),
    over the matched pairs compute est_onset - ref_onset.
    Returns onset_dev_median_ms and onset_dev_mean_abs_ms.
    
    Args:
        reference_notes: Ground truth notes
        estimated_notes: Detected notes
        onset_tolerance: Tolerance for onset matching in seconds
        
    Returns:
        Dict with onset_dev_median_ms and onset_dev_mean_abs_ms (in milliseconds)
        or None if there are no matches
    """
    ref_pitches, ref_intervals = notes_to_mir_eval_format(reference_notes)
    est_pitches, est_intervals = notes_to_mir_eval_format(estimated_notes)
    
    if len(ref_intervals) == 0 or len(est_intervals) == 0:
        return None
    
    # Match notes with onset-only matching
    matched_pairs = mir_eval.transcription.match_notes(
        ref_intervals,
        ref_pitches,
        est_intervals,
        est_pitches,
        onset_tolerance=onset_tolerance,
        offset_ratio=None,
    )
    
    if len(matched_pairs) == 0:
        return None
    
    # Compute deviations in seconds
    deviations = []
    for ref_idx, est_idx in matched_pairs:
        ref_onset = ref_intervals[ref_idx, 0]
        est_onset = est_intervals[est_idx, 0]
        deviations.append(float(est_onset - ref_onset))
    
    # Convert to milliseconds
    deviations_ms = [d * 1000.0 for d in deviations]
    
    median_ms = float(np.median(deviations_ms))
    mean_abs_ms = float(np.mean([abs(d) for d in deviations_ms]))
    
    return {
        "onset_dev_median_ms": median_ms,
        "onset_dev_mean_abs_ms": mean_abs_ms,
    }


def evaluate_onset_offset_sustained(
    reference_notes: List[Dict],
    estimated_notes: List[Dict],
    reference_pedal: Optional[List[Dict]] = None,
    onset_tolerance: float = 0.05,
    offset_ratio: float = 0.2,
    offset_min_tolerance: float = 0.05,
) -> Optional[Dict]:
    """Evaluate with onset+offset matching using sustained offsets.
    
    If reference_pedal is provided, extends the reference notes using sustain_extended.
    If reference_pedal is None, returns None.
    
    Args:
        reference_notes: Ground truth notes
        estimated_notes: Detected notes
        reference_pedal: Pedal intervals from ground truth (optional)
        onset_tolerance: Tolerance for onset matching in seconds
        offset_ratio: Ratio for offset matching
        offset_min_tolerance: Minimum tolerance for offset matching
        
    Returns:
        Dict with precision, recall, f1_score or None if no pedal data
    """
    if reference_pedal is None:
        return None
    
    # Extend reference notes with pedal
    extended_ref_notes = sustain_extended(reference_notes, reference_pedal)
    
    return compute_metrics(
        extended_ref_notes,
        estimated_notes,
        onset_tolerance=onset_tolerance,
        offset_ratio=offset_ratio,
        offset_min_tolerance=offset_min_tolerance,
    )
