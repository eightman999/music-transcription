"""Tests for scripts/fetch_smd_subset.py."""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.fetch_smd_subset import (
    duration_from_size,
    select_smd,
    parse_csv,
)


class TestDurationCalculation:
    """Test duration calculation from file size."""
    
    def test_duration_formula(self):
        """Test that duration is calculated correctly."""
        # For 44.1 kHz stereo 16-bit WAV:
        # bytes_per_second = 44100 * 2 * 2 = 176400
        # duration = (file_size - 44) / 176400
        
        # 1 second of audio: 176400 + 44 = 176444 bytes
        assert abs(duration_from_size(176444) - 1.0) < 0.001
        
        # 2 seconds: 176400 * 2 + 44 = 352844 bytes
        assert abs(duration_from_size(352844) - 2.0) < 0.001
        
        # 0 bytes: should return 0
        assert duration_from_size(0) == 0.0
        
        # Less than header: should return 0
        assert duration_from_size(44) == 0.0


class TestComposerExtraction:
    """Test composer extraction from stem."""
    
    def test_simple_composer(self):
        """Test extraction of simple composer name."""
        # The composer extraction is done inline in select_smd
        # Test the logic directly
        stem = "Bach_BWV849-01_001_20090916-SMD"
        composer = stem.split('_')[0]
        assert composer == "Bach"
        
        stem = "Beethoven_Op027No1-02_003_20090916-SMD"
        composer = stem.split('_')[0]
        assert composer == "Beethoven"
    
    def test_composer_with_underscore(self):
        """Test that only the first part is taken."""
        stem = "Johann_Sebastian_Bach_Something"
        composer = stem.split('_')[0]
        assert composer == "Johann"


class TestSelectionRule:
    """Test the SMD selection rule as a pure function."""
    
    def test_selection_basic(self):
        """Test basic selection with hand-made member list."""
        # Create test members: (path, size)
        # We need to create sizes that give durations in the 90-420 range
        # bytes_per_second = 44100 * 2 * 2 = 176400
        
        def make_wav_size(duration):
            return int(duration * 176400 + 44)
        
        members = [
            # Use the expected order from the brief
            ("wav_44100_stereo/Bach_BWV849-01_001_20090916-SMD.wav", make_wav_size(100)),
            # Bartok - duration 150s
            ("wav_44100_stereo/Bartok_SZ080-01_002_20110315-SMD.wav", make_wav_size(150)),
            # Beethoven - duration 200s
            ("wav_44100_stereo/Beethoven_Op027No1-02_003_20090916-SMD.wav", make_wav_size(200)),
            # Brahms - duration 250s
            ("wav_44100_stereo/Brahms_Op010No1_003_20090916-SMD.wav", make_wav_size(250)),
            # Chopin - duration 300s
            ("wav_44100_stereo/Chopin_Op010-03_007_20100611-SMD.wav", make_wav_size(300)),
            # Another composer - should be skipped (composer already picked if we add another)
            ("wav_44100_stereo/Debussy_Something_001_20090916-SMD.wav", make_wav_size(120)),
            # Short piece - should be skipped (duration < 90)
            ("wav_44100_stereo/Short_Piece_001_20090916-SMD.wav", make_wav_size(50)),
            # Long piece - should be skipped (duration > 420)
            ("wav_44100_stereo/Long_Piece_001_20090916-SMD.wav", make_wav_size(500)),
        ]
        
        selected = select_smd(members, n=5)
        
        # Should pick the first 5 unique composers in sorted order
        expected = [
            "Bach_BWV849-01_001_20090916-SMD",
            "Bartok_SZ080-01_002_20110315-SMD",
            "Beethoven_Op027No1-02_003_20090916-SMD",
            "Brahms_Op010No1_003_20090916-SMD",
            "Chopin_Op010-03_007_20100611-SMD",
        ]
        
        assert selected == expected, f"Expected {expected}, got {selected}"
    
    def test_selection_order(self):
        """Test that selection respects sorted order."""
        def make_wav_size(duration):
            return int(duration * 176400 + 44)
        
        # Members in reverse order
        members = [
            ("wav_44100_stereo/Chopin_Op010-03_007_20100611-SMD.wav", make_wav_size(300)),
            ("wav_44100_stereo/Brahms_Op010No1_003_20090916-SMD.wav", make_wav_size(250)),
            ("wav_44100_stereo/Beethoven_Op027No1-02_003_20090916-SMD.wav", make_wav_size(200)),
            ("wav_44100_stereo/Bartok_SZ080-01_002_20110315-SMD.wav", make_wav_size(150)),
            ("wav_44100_stereo/Bach_BWV849-01_001_20090916-SMD.wav", make_wav_size(100)),
        ]
        
        selected = select_smd(members, n=5)
        
        # Should be sorted by filename
        expected = [
            "Bach_BWV849-01_001_20090916-SMD",
            "Bartok_SZ080-01_002_20110315-SMD",
            "Beethoven_Op027No1-02_003_20090916-SMD",
            "Brahms_Op010No1_003_20090916-SMD",
            "Chopin_Op010-03_007_20100611-SMD",
        ]
        
        assert selected == expected, f"Expected {expected}, got {selected}"
    
    def test_selection_stops_at_n(self):
        """Test that selection stops when n pieces are selected."""
        def make_wav_size(duration):
            return int(duration * 176400 + 44)
        
        members = [
            ("wav_44100_stereo/Bach_BWV849-01_001_20090916-SMD.wav", make_wav_size(100)),
            ("wav_44100_stereo/Bartok_SZ080-01_002_20110315-SMD.wav", make_wav_size(150)),
            ("wav_44100_stereo/Beethoven_Op027No1-02_003_20090916-SMD.wav", make_wav_size(200)),
            ("wav_44100_stereo/Brahms_Op010No1_003_20090916-SMD.wav", make_wav_size(250)),
            ("wav_44100_stereo/Chopin_Op010-03_007_20100611-SMD.wav", make_wav_size(300)),
            ("wav_44100_stereo/Debussy_Something_001_20090916-SMD.wav", make_wav_size(120)),
        ]
        
        selected = select_smd(members, n=3)
        
        # Should stop at 3
        assert len(selected) == 3
        assert selected == [
            "Bach_BWV849-01_001_20090916-SMD",
            "Bartok_SZ080-01_002_20110315-SMD",
            "Beethoven_Op027No1-02_003_20090916-SMD",
        ]


class TestCSVParser:
    """Test the CSV parser on a small string."""
    
    def test_parse_csv_basic(self):
        """Test parsing basic CSV content with real SMD format."""
        csv_content = """Start;Duration;Pitch;Velocity;Instrument
002.549;000.476;68;000.273;MIDI 01
003.061;000.251;64;000.273;MIDI 01
003.312;000.251;60;000.273;MIDI 01"""
        
        notes = parse_csv(csv_content)
        
        assert len(notes) == 3
        assert notes[0]['onset'] == 2.549
        assert notes[0]['duration'] == 0.476
        assert notes[0]['pitch'] == 68
        assert notes[0]['velocity'] == 0.273
        assert notes[1]['onset'] == 3.061
        assert notes[1]['pitch'] == 64
        assert notes[2]['onset'] == 3.312
        assert notes[2]['pitch'] == 60
    
    def test_parse_csv_empty(self):
        """Test parsing empty CSV."""
        csv_content = "Start;Duration;Pitch;Velocity;Instrument"
        notes = parse_csv(csv_content)
        assert len(notes) == 0
    
    def test_parse_csv_with_header_only(self):
        """Test parsing CSV with only header."""
        csv_content = "Start;Duration;Pitch;Velocity;Instrument\n"
        notes = parse_csv(csv_content)
        assert len(notes) == 0


class TestEndToEnd:
    """End-to-end test for fetch_smd_subset.py."""

    def test_fetch_smd_subset_e2e(self):
        """Test the full script as a subprocess."""
        import subprocess
        import json
        from pathlib import Path

        # Check if cache directory exists
        cache_dir = Path("data/_downloads/smd/wav_44100_stereo")
        if not cache_dir.exists():
            import pytest
            pytest.skip("SMD cache directory not found")

        # Run the script with --out to a temp dir and --n 1
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir) / "smd_test"
            result = subprocess.run(
                [sys.executable, "scripts/fetch_smd_subset.py",
                 "--out", str(out_dir), "--n", "1"],
                capture_output=True, text=True
            )

            # Check exit code
            assert result.returncode == 0, f"Script failed with: {result.stderr}"

            # Check that output files exist
            assert out_dir.exists(), "Output directory not created"

            # Find the stem from the first piece
            manifest_path = out_dir / "manifest.json"
            assert manifest_path.exists(), "manifest.json not created"

            with open(manifest_path, 'r') as f:
                manifest = json.load(f)

            assert "pieces" in manifest, "manifest.json missing 'pieces' key"
            assert len(manifest["pieces"]) == 1, f"Expected 1 piece, got {len(manifest['pieces'])}"

            piece = manifest["pieces"][0]
            stem = piece["stem"]

            # Check that all required files exist
            assert (out_dir / f"{stem}.wav").exists(), f"{stem}.wav not found"
            assert (out_dir / f"{stem}.mid").exists(), f"{stem}.mid not found"
            assert (out_dir / f"{stem}.gt.json").exists(), f"{stem}.gt.json not found"

            # Check that manifest has all required fields
            required_fields = ["stem", "composer", "duration", "num_notes",
                             "num_pedal_intervals", "wav_sha256",
                             "csv_max_onset_diff_ms", "midi_end_time"]
            for field in required_fields:
                assert field in piece, f"Missing field: {field}"

            # Check that gt.json has the same number of notes as manifest
            with open(out_dir / f"{stem}.gt.json", 'r') as f:
                gt = json.load(f)
            assert len(gt["notes"]) == piece["num_notes"], \
                f"Note count mismatch: gt={len(gt['notes'])}, manifest={piece['num_notes']}"

            # Check manifest.json has source_url, licence, selection_rule
            assert "source_url" in manifest, "Missing source_url in manifest"
            assert "licence" in manifest, "Missing licence in manifest"
            assert "selection_rule" in manifest, "Missing selection_rule in manifest"
