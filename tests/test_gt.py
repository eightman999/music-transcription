"""Tests for mt/gt.py."""

import os
import sys
import tempfile

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt.gt import pedal_intervals, midi_to_gt, sustain_extended

import pretty_midi


class TestPedalIntervals:
    """Test pedal_intervals function."""

    def test_basic_interval(self):
        """Test basic pedal on/off creates one interval."""
        cc64 = [(1.0, 100), (2.0, 0)]
        intervals = pedal_intervals(cc64, 10.0)
        assert len(intervals) == 1
        assert intervals[0]["onset"] == 1.0
        assert intervals[0]["offset"] == 2.0

    def test_multiple_values_on_same_side(self):
        """CC64 values 70, 100, 120, 30, 10, 90, 20 at times 1..7 give exactly two intervals: (1, 4) and (6, 7)."""
        cc64 = [
            (1.0, 70),
            (2.0, 100),
            (3.0, 120),
            (4.0, 30),
            (5.0, 10),
            (6.0, 90),
            (7.0, 20),
        ]
        intervals = pedal_intervals(cc64, 10.0)
        assert len(intervals) == 2
        assert intervals[0]["onset"] == 1.0
        assert intervals[0]["offset"] == 4.0
        assert intervals[1]["onset"] == 6.0
        assert intervals[1]["offset"] == 7.0

    def test_pedal_still_down_at_end(self):
        """Pedal still down at the end is closed at the end time."""
        cc64 = [(1.0, 100)]
        intervals = pedal_intervals(cc64, 5.0)
        assert len(intervals) == 1
        assert intervals[0]["onset"] == 1.0
        assert intervals[0]["offset"] == 5.0

    def test_empty_cc64(self):
        """Empty CC64 list returns empty intervals."""
        intervals = pedal_intervals([], 10.0)
        assert intervals == []

    def test_zero_length_intervals_dropped(self):
        """Zero-length intervals are dropped."""
        cc64 = [(1.0, 100), (1.0, 0)]
        intervals = pedal_intervals(cc64, 10.0)
        assert intervals == []

    def test_threshold_parameter(self):
        """Test custom threshold parameter."""
        cc64 = [(1.0, 50), (2.0, 0)]
        # With default threshold 64, 50 < 64 so no interval
        intervals = pedal_intervals(cc64, 10.0)
        assert intervals == []
        
        # With threshold 40, 50 >= 40 so interval is created
        intervals = pedal_intervals(cc64, 10.0, threshold=40)
        assert len(intervals) == 1
        assert intervals[0]["onset"] == 1.0
        assert intervals[0]["offset"] == 2.0


class TestMidiToGt:
    """Test midi_to_gt function."""

    def _create_test_midi(self, notes_data, cc64_events=None):
        """Create a test MIDI file with specified notes and CC64 events."""
        pm = pretty_midi.PrettyMIDI()
        instrument = pretty_midi.Instrument(0)
        
        for pitch, start, end, velocity in notes_data:
            note = pretty_midi.Note(
                velocity=velocity,
                pitch=pitch,
                start=start,
                end=end,
            )
            instrument.notes.append(note)
        
        if cc64_events:
            for time, value in cc64_events:
                cc = pretty_midi.ControlChange(
                    number=64,
                    value=value,
                    time=time,
                )
                instrument.control_changes.append(cc)
        
        pm.instruments.append(instrument)
        return pm

    def test_basic_notes(self):
        """Test basic note extraction."""
        with tempfile.NamedTemporaryFile(suffix='.midi', delete=False) as f:
            midi_path = f.name
        
        try:
            notes_data = [(60, 0.0, 1.0, 100), (64, 0.5, 1.5, 80)]
            pm = self._create_test_midi(notes_data)
            pm.write(midi_path)
            
            gt = midi_to_gt(midi_path)
            
            assert len(gt["notes"]) == 2
            assert gt["notes"][0]["pitch"] == 60
            assert gt["notes"][0]["onset"] == 0.0
            assert gt["notes"][0]["offset"] == 1.0
            assert gt["notes"][0]["velocity"] == 100
            assert gt["notes"][1]["pitch"] == 64
            assert gt["notes"][1]["onset"] == 0.5
            assert gt["notes"][1]["offset"] == 1.5
            assert gt["notes"][1]["velocity"] == 80
        finally:
            os.unlink(midi_path)

    def test_notes_sorted_by_onset_pitch(self):
        """Test that notes are sorted by (onset, pitch)."""
        with tempfile.NamedTemporaryFile(suffix='.midi', delete=False) as f:
            midi_path = f.name
        
        try:
            # Create notes in non-sorted order
            notes_data = [(64, 0.5, 1.5, 80), (60, 0.0, 1.0, 100), (60, 0.0, 1.0, 100)]
            pm = self._create_test_midi(notes_data)
            pm.write(midi_path)
            
            gt = midi_to_gt(midi_path)
            
            # Should be sorted by onset, then pitch
            assert gt["notes"][0]["pitch"] == 60
            assert gt["notes"][1]["pitch"] == 60
            assert gt["notes"][2]["pitch"] == 64
        finally:
            os.unlink(midi_path)

    def test_pedal_extraction(self):
        """Test pedal interval extraction from MIDI."""
        with tempfile.NamedTemporaryFile(suffix='.midi', delete=False) as f:
            midi_path = f.name
        
        try:
            notes_data = [(60, 0.0, 2.0, 100)]
            cc64_events = [(0.5, 100), (1.5, 0)]
            pm = self._create_test_midi(notes_data, cc64_events)
            pm.write(midi_path)
            
            gt = midi_to_gt(midi_path)
            
            assert len(gt["pedal"]) == 1
            assert gt["pedal"][0]["onset"] == 0.5
            assert gt["pedal"][0]["offset"] == 1.5
        finally:
            os.unlink(midi_path)


class TestSustainExtended:
    """Test sustain_extended function."""

    def test_no_pedal_no_change(self):
        """A note without any pedal is unchanged."""
        notes = [
            {"pitch": 60, "onset": 2.0, "offset": 3.0, "velocity": 100}
        ]
        pedal = []
        result = sustain_extended(notes, pedal)
        
        # Should not modify input list
        assert result is not notes
        assert len(result) == 1
        assert result[0]["offset"] == 3.0

    def test_pedal_down_at_key_release(self):
        """Key held 2.0-3.0, pedal 2.5-5.0: raw offset 3.0, extended offset 5.0."""
        notes = [
            {"pitch": 60, "onset": 2.0, "offset": 3.0, "velocity": 100}
        ]
        pedal = [{"onset": 2.5, "offset": 5.0}]
        result = sustain_extended(notes, pedal)
        
        assert len(result) == 1
        assert result[0]["offset"] == 5.0

    def test_pedal_released_before_key(self):
        """Key 2.0-3.0, pedal 1.0-2.5 (released before the key): extended offset stays 3.0."""
        notes = [
            {"pitch": 60, "onset": 2.0, "offset": 3.0, "velocity": 100}
        ]
        pedal = [{"onset": 1.0, "offset": 2.5}]
        result = sustain_extended(notes, pedal)
        
        assert len(result) == 1
        assert result[0]["offset"] == 3.0

    def test_two_notes_same_pitch_with_pedal(self):
        """Two notes of the same pitch at 2.0-2.2 and 3.0-3.2 with pedal 1.9-6.0: extended offsets 3.0 and 6.0."""
        notes = [
            {"pitch": 60, "onset": 2.0, "offset": 2.2, "velocity": 100},
            {"pitch": 60, "onset": 3.0, "offset": 3.2, "velocity": 100},
        ]
        pedal = [{"onset": 1.9, "offset": 6.0}]
        result = sustain_extended(notes, pedal)
        
        assert len(result) == 2
        # First note: pedal extends to 6.0, but next note at 3.0 is earlier
        assert result[0]["offset"] == 3.0
        # Second note: pedal extends to 6.0, no next note
        assert result[1]["offset"] == 6.0

    def test_offset_never_smaller_than_onset(self):
        """Ensure offset is never <= onset."""
        notes = [
            {"pitch": 60, "onset": 2.0, "offset": 2.1, "velocity": 100}
        ]
        pedal = [{"onset": 1.0, "offset": 1.5}]  # Pedal ends before note starts
        result = sustain_extended(notes, pedal)
        
        assert result[0]["offset"] >= result[0]["onset"]
        # Should keep raw offset since pedal doesn't cover it
        assert result[0]["offset"] == 2.1

    def test_empty_notes(self):
        """Empty notes list returns empty list."""
        result = sustain_extended([], [])
        assert result == []

    def test_empty_pedal(self):
        """Empty pedal list means no extension."""
        notes = [
            {"pitch": 60, "onset": 2.0, "offset": 3.0, "velocity": 100}
        ]
        result = sustain_extended(notes, [])
        assert result[0]["offset"] == 3.0

    def test_multiple_pedal_intervals(self):
        """Test with multiple pedal intervals."""
        notes = [
            {"pitch": 60, "onset": 1.0, "offset": 2.0, "velocity": 100},
            {"pitch": 64, "onset": 3.0, "offset": 4.0, "velocity": 100},
        ]
        pedal = [
            {"onset": 0.5, "offset": 2.5},
            {"onset": 3.5, "offset": 5.0},
        ]
        result = sustain_extended(notes, pedal)
        
        # First note: pedal 0.5-2.5 covers offset 2.0, extends to 2.5
        assert result[0]["offset"] == 2.5
        # Second note: pedal 3.5-5.0 covers offset 4.0 (3.5 <= 4.0 < 5.0), extends to 5.0
        assert result[1]["offset"] == 5.0

    def test_input_not_modified(self):
        """sustain_extended does not modify its input list."""
        notes = [
            {"pitch": 60, "onset": 2.0, "offset": 3.0, "velocity": 100}
        ]
        pedal = [{"onset": 2.5, "offset": 5.0}]
        original_offset = notes[0]["offset"]
        
        result = sustain_extended(notes, pedal)
        
        # Input should be unchanged
        assert notes[0]["offset"] == original_offset
        # Result should be different
        assert result[0]["offset"] != original_offset
