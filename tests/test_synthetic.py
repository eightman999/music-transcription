#!/usr/bin/env python3
"""Tests for synthetic test clip and naive backend."""

import os
import sys
import tempfile
import shutil
import subprocess

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt.schema import load_json
from mt.evaluate import evaluate_onset_only


def test_synthetic_generation():
    """Test that synthetic clip generation produces exactly 16 notes."""
    # Run the generation script
    result = subprocess.run(
        [sys.executable, "scripts/make_test_wav.py", "--sr", "44100", "--bpm", "120"],
        capture_output=True,
        text=True,
        check=True,
    )
    
    # Check that the output files exist
    assert os.path.exists("out/synth/test.wav")
    assert os.path.exists("out/synth/test.gt.json")
    
    # Load ground truth
    gt_data = load_json("out/synth/test.gt.json")
    
    # Check that we have exactly 16 notes
    assert len(gt_data["notes"]) == 16, f"Expected 16 notes, got {len(gt_data['notes'])}"
    
    print(f"✓ Synthetic clip generated with {len(gt_data['notes'])} notes")


def test_naive_backend_on_synthetic():
    """Test that the naive backend can detect notes from the synthetic clip."""
    # First, generate the synthetic clip
    if not os.path.exists("out/synth/test.wav"):
        test_synthetic_generation()
    
    # Run the naive backend
    result = subprocess.run(
        [sys.executable, "backends/naive/run.py", "out/synth/test.wav", "out/synth/test.naive.json"],
        capture_output=True,
        text=True,
        check=True,
    )
    
    print(f"Naive backend output: {result.stdout}")
    
    # Load the detected notes
    est_data = load_json("out/synth/test.naive.json")
    
    # Load ground truth
    gt_data = load_json("out/synth/test.gt.json")
    
    # Evaluate
    metrics = evaluate_onset_only(
        gt_data["notes"],
        est_data["notes"],
        onset_tolerance=0.05,
    )
    
    print(f"Metrics: P={metrics['precision']:.3f}, R={metrics['recall']:.3f}, F1={metrics['f1']:.3f}")
    print(f"Detected {len(est_data['notes'])} notes (expected 16)")
    
    # The test requires precision 1.0 and recall 1.0 at 50ms tolerance
    assert metrics["precision"] == 1.0, f"Precision {metrics['precision']} != 1.0"
    assert metrics["recall"] == 1.0, f"Recall {metrics['recall']} != 1.0"
    
    # Also check that ground truth has exactly 16 notes and contains simultaneous notes
    assert len(gt_data["notes"]) == 16, f"Expected 16 ground truth notes, got {len(gt_data['notes'])}"
    
    # Check maximum polyphony (simultaneous notes)
    # Count how many notes are active at each time point
    max_polyphony = 0
    for note in gt_data["notes"]:
        # We'll check at the onset time of each note
        onset = note["onset"]
        count = sum(1 for n in gt_data["notes"] if n["onset"] <= onset < n["offset"])
        max_polyphony = max(max_polyphony, count)
    
    print(f"Maximum polyphony: {max_polyphony}")
    assert max_polyphony >= 4, f"Maximum polyphony {max_polyphony} < 4"


def test_cli_transcribe():
    """Test that the CLI can transcribe the synthetic clip."""
    # First, generate the synthetic clip
    if not os.path.exists("out/synth/test.wav"):
        test_synthetic_generation()
    
    # Create a temporary output directory
    with tempfile.TemporaryDirectory() as tmpdir:
        # Run the CLI
        result = subprocess.run(
            [
                sys.executable, "-m", "mt.cli", "transcribe",
                "out/synth/test.wav",
                "--backend", "naive",
                "--bpm", "120",
                "-o", tmpdir,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        
        print(f"CLI output: {result.stdout}")
        
        # Check that output files exist
        assert os.path.exists(os.path.join(tmpdir, "notes.json"))
        assert os.path.exists(os.path.join(tmpdir, "out.mid"))
        assert os.path.exists(os.path.join(tmpdir, "out.musicxml"))
        
        print("✓ CLI transcribe command works")


def test_musicxml_parses():
    """Test that the generated MusicXML can be parsed by music21."""
    # First, generate and transcribe
    if not os.path.exists("out/synth/test.wav"):
        test_synthetic_generation()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Run the CLI
        subprocess.run(
            [
                sys.executable, "-m", "mt.cli", "transcribe",
                "out/synth/test.wav",
                "--backend", "naive",
                "--bpm", "120",
                "-o", tmpdir,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        
        # Try to parse the MusicXML
        import music21
        musicxml_path = os.path.join(tmpdir, "out.musicxml")
        
        try:
            score = music21.converter.parse(musicxml_path)
            # Count notes by flattening the score
            flat_score = score.flatten()
            print(f"✓ MusicXML parsed successfully, found {len(flat_score.notes)} notes")
        except Exception as e:
            import pytest
            pytest.fail(f"Could not parse MusicXML: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
