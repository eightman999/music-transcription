"""Tests for scripts/eval_detect.py fixes."""

import os
import sys
import json
import tempfile
import shutil
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.eval_detect import (
    load_dataset,
    evaluate_backend_on_clip,
    print_markdown_table,
    sort_notes_by_onset_pitch,
)
from mt.schema import save_json, create_empty


class TestSortNotesByOnsetPitch:
    """Test the note sorting function."""
    
    def test_empty_notes(self):
        """Empty list should return empty list."""
        assert sort_notes_by_onset_pitch([]) == []
    
    def test_single_note(self):
        """Single note should return as-is."""
        notes = [{"pitch": 60, "onset": 1.0, "offset": 2.0, "velocity": 100}]
        assert sort_notes_by_onset_pitch(notes) == notes
    
    def test_sorts_by_onset(self):
        """Notes should be sorted by onset time."""
        notes = [
            {"pitch": 60, "onset": 2.0, "offset": 3.0, "velocity": 100},
            {"pitch": 64, "onset": 1.0, "offset": 2.0, "velocity": 100},
            {"pitch": 67, "onset": 3.0, "offset": 4.0, "velocity": 100},
        ]
        sorted_notes = sort_notes_by_onset_pitch(notes)
        assert sorted_notes[0]["pitch"] == 64  # onset 1.0
        assert sorted_notes[1]["pitch"] == 60  # onset 2.0
        assert sorted_notes[2]["pitch"] == 67  # onset 3.0
    
    def test_sorts_by_pitch_when_onset_equal(self):
        """Notes with same onset should be sorted by pitch."""
        notes = [
            {"pitch": 67, "onset": 1.0, "offset": 2.0, "velocity": 100},
            {"pitch": 60, "onset": 1.0, "offset": 2.0, "velocity": 100},
            {"pitch": 64, "onset": 1.0, "offset": 2.0, "velocity": 100},
        ]
        sorted_notes = sort_notes_by_onset_pitch(notes)
        assert sorted_notes[0]["pitch"] == 60
        assert sorted_notes[1]["pitch"] == 64
        assert sorted_notes[2]["pitch"] == 67
    
    def test_reverse_time_order(self):
        """Test that notes in reverse time order are sorted correctly."""
        # This simulates the basic_pitch issue where notes are in reverse time order
        notes = [
            {"pitch": 60, "onset": 3.0, "offset": 4.0, "velocity": 100},
            {"pitch": 64, "onset": 2.0, "offset": 3.0, "velocity": 100},
            {"pitch": 67, "onset": 1.0, "offset": 2.0, "velocity": 100},
        ]
        sorted_notes = sort_notes_by_onset_pitch(notes)
        assert sorted_notes[0]["onset"] == 1.0
        assert sorted_notes[1]["onset"] == 2.0
        assert sorted_notes[2]["onset"] == 3.0


class TestLoadDataset:
    """Test dataset loading."""
    
    def test_load_synth_dataset(self):
        """Test loading the synth dataset."""
        clips = load_dataset("out/synth")
        assert len(clips) == 1
        assert clips[0][0] == "test"
        assert "test.wav" in clips[0][1]
        assert "test.gt.json" in clips[0][2]
    
    def test_load_dataset_with_path(self):
        """Test loading a dataset given as a path."""
        # Create a temporary dataset
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test clip
            wav_path = os.path.join(tmpdir, "test.wav")
            gt_path = os.path.join(tmpdir, "test.gt.json")
            
            # Create minimal WAV file
            import numpy as np
            import soundfile as sf
            audio = np.zeros(44100, dtype=np.float32)
            sf.write(wav_path, audio, 44100)
            
            # Create ground truth
            gt_data = create_empty(wav_path, "ground_truth")
            gt_data["notes"] = [
                {"pitch": 60, "onset": 0.0, "offset": 1.0, "velocity": 100}
            ]
            save_json(gt_data, gt_path)
            
            # Load dataset
            clips = load_dataset(tmpdir)
            assert len(clips) == 1
            assert clips[0][0] == "test"


class TestPrintMarkdownTable:
    """Test markdown table generation."""
    
    def test_mean_row_per_backend(self):
        """Test that mean row is computed per backend, not across all backends."""
        # Create test results with two backends
        results = [
            {
                "clip": "clip1",
                "backend": "backend_a",
                "num_gt_notes": 10,
                "num_est_notes": 8,
                "onset_only": {"precision": 0.8, "recall": 0.8, "f1": 0.8},
                "onset_offset": {"precision": 0.7, "recall": 0.7, "f1": 0.7},
                "onset_offset_sustained": {"precision": 0.75, "recall": 0.75, "f1": 0.75},
                "onset_dev_median_ms": 5.0,
                "wall_time": 1.0,
                "real_time_factor": 1.0,
                "peak_rss_mb": 100.0,
                "device": "",
                "version": "",
                "failed": False,
                "error": None,
            },
            {
                "clip": "clip2",
                "backend": "backend_a",
                "num_gt_notes": 10,
                "num_est_notes": 9,
                "onset_only": {"precision": 0.9, "recall": 0.9, "f1": 0.9},
                "onset_offset": {"precision": 0.8, "recall": 0.8, "f1": 0.8},
                "onset_offset_sustained": {"precision": 0.85, "recall": 0.85, "f1": 0.85},
                "onset_dev_median_ms": 6.0,
                "wall_time": 1.0,
                "real_time_factor": 1.0,
                "peak_rss_mb": 100.0,
                "device": "",
                "version": "",
                "failed": False,
                "error": None,
            },
            {
                "clip": "clip1",
                "backend": "backend_b",
                "num_gt_notes": 10,
                "num_est_notes": 5,
                "onset_only": {"precision": 0.5, "recall": 0.5, "f1": 0.5},
                "onset_offset": {"precision": 0.4, "recall": 0.4, "f1": 0.4},
                "onset_offset_sustained": {"precision": 0.45, "recall": 0.45, "f1": 0.45},
                "onset_dev_median_ms": 10.0,
                "wall_time": 1.0,
                "real_time_factor": 1.0,
                "peak_rss_mb": 200.0,
                "device": "",
                "version": "",
                "failed": False,
                "error": None,
            },
        ]
        
        table = print_markdown_table(results, "test_dataset")
        
        # Check that we have mean rows for each backend
        assert "**mean** | backend_a" in table
        assert "**mean** | backend_b" in table
        
        # Check that backend_a mean onset_offset is 0.75 (average of 0.7 and 0.8)
        # and backend_b mean onset_offset is 0.4
        # The table should show these values
        assert "0.750/0.750/0.750" in table  # backend_a mean onset_offset
        assert "0.400/0.400/0.400" in table  # backend_b mean onset_offset


class TestDatasetPathBasename:
    """Test that dataset paths use basename for result filenames."""
    
    def test_basename_in_filename(self):
        """Test that result filename uses basename of dataset path."""
        # This is tested implicitly by the save_results functions
        # We'll test it by checking the actual behavior
        from scripts.eval_detect import save_results_json, save_results_md
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test with a path that contains separators
            dataset_name = "data/sanity"
            
            # Save results
            results = []
            json_path = save_results_json(results, dataset_name, tmpdir)
            md_path = save_results_md("", dataset_name, tmpdir)
            
            # Check that the filename uses basename
            assert "detect_sanity.json" in json_path
            assert "detect_sanity.md" in md_path
            
            # Verify files were created with correct names
            assert os.path.exists(os.path.join(tmpdir, "detect_sanity.json"))
            assert os.path.exists(os.path.join(tmpdir, "detect_sanity.md"))


class TestBackendFailureHandling:
    """Test that backend failures are handled gracefully."""
    
    def test_failed_backend_result(self):
        """Test that a failed backend returns a proper error result."""
        # Create a temporary dataset
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test clip
            wav_path = os.path.join(tmpdir, "test.wav")
            gt_path = os.path.join(tmpdir, "test.gt.json")
            
            # Create minimal WAV file
            import numpy as np
            import soundfile as sf
            audio = np.zeros(44100, dtype=np.float32)
            sf.write(wav_path, audio, 44100)
            
            # Create ground truth
            gt_data = create_empty(wav_path, "ground_truth")
            gt_data["notes"] = [
                {"pitch": 60, "onset": 0.0, "offset": 1.0, "velocity": 100}
            ]
            save_json(gt_data, gt_path)
            
            # Try to evaluate with a non-existent backend
            # This should return a failed result, not crash
            result = evaluate_backend_on_clip(
                "nonexistent_backend",
                wav_path,
                gt_path,
                "test_dataset",
            )
            
            assert result["failed"] is True
            assert result["backend"] == "nonexistent_backend"
            assert result["error"] is not None
