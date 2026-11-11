"""Tests for mt/schema.py."""

import pytest
import json
import os
import tempfile
from mt.schema import (
    validate_schema,
    validate_note,
    validate_pedal,
    load_json,
    save_json,
    create_empty,
)


class TestValidateNote:
    def test_valid_note(self):
        note = {
            "pitch": 60,
            "onset": 0.0,
            "offset": 1.0,
            "velocity": 100,
        }
        assert validate_note(note) is True
    
    def test_invalid_pitch_range(self):
        note = {
            "pitch": 128,  # Invalid: max is 127
            "onset": 0.0,
            "offset": 1.0,
            "velocity": 100,
        }
        assert validate_note(note) is False
    
    def test_invalid_velocity_range(self):
        note = {
            "pitch": 60,
            "onset": 0.0,
            "offset": 1.0,
            "velocity": 0,  # Invalid: min is 1
        }
        assert validate_note(note) is False
    
    def test_offset_before_onset(self):
        note = {
            "pitch": 60,
            "onset": 1.0,
            "offset": 0.0,
            "velocity": 100,
        }
        assert validate_note(note) is False
    
    def test_missing_keys(self):
        note = {
            "pitch": 60,
            "onset": 0.0,
            # Missing offset and velocity
        }
        assert validate_note(note) is False


class TestValidatePedal:
    def test_valid_pedal(self):
        pedal = {
            "onset": 0.0,
            "offset": 1.0,
        }
        assert validate_pedal(pedal) is True
    
    def test_offset_before_onset(self):
        pedal = {
            "onset": 1.0,
            "offset": 0.0,
        }
        assert validate_pedal(pedal) is False


class TestValidateSchema:
    def test_valid_schema(self):
        data = {
            "backend": "test",
            "audio": "test.wav",
            "notes": [
                {"pitch": 60, "onset": 0.0, "offset": 1.0, "velocity": 100},
            ],
        }
        assert validate_schema(data) is True
    
    def test_valid_schema_with_pedal(self):
        data = {
            "backend": "test",
            "audio": "test.wav",
            "notes": [
                {"pitch": 60, "onset": 0.0, "offset": 1.0, "velocity": 100},
            ],
            "pedal": [
                {"onset": 0.0, "offset": 1.0},
            ],
        }
        assert validate_schema(data) is True
    
    def test_missing_required_keys(self):
        data = {
            "backend": "test",
            # Missing audio and notes
        }
        assert validate_schema(data) is False
    
    def test_invalid_note_in_list(self):
        data = {
            "backend": "test",
            "audio": "test.wav",
            "notes": [
                {"pitch": 60, "onset": 0.0, "offset": 1.0, "velocity": 100},
                {"pitch": 200, "onset": 0.0, "offset": 1.0, "velocity": 100},  # Invalid pitch
            ],
        }
        assert validate_schema(data) is False


class TestLoadSaveJson:
    def test_save_and_load(self):
        data = {
            "backend": "test",
            "audio": "test.wav",
            "notes": [
                {"pitch": 60, "onset": 0.0, "offset": 1.0, "velocity": 100},
            ],
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            save_json(data, filepath)
            loaded = load_json(filepath)
            
            assert loaded["backend"] == data["backend"]
            assert loaded["audio"] == data["audio"]
            assert len(loaded["notes"]) == 1
            assert loaded["notes"][0]["pitch"] == 60
    
    def test_save_invalid_schema_raises(self):
        data = {
            "backend": "test",
            "audio": "test.wav",
            "notes": [
                {"pitch": 200, "onset": 0.0, "offset": 1.0, "velocity": 100},  # Invalid
            ],
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            with pytest.raises(ValueError):
                save_json(data, filepath)
    
    def test_load_invalid_schema_raises(self):
        data = {
            "backend": "test",
            "audio": "test.wav",
            "notes": [
                {"pitch": 200, "onset": 0.0, "offset": 1.0, "velocity": 100},  # Invalid
            ],
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = os.path.join(tmpdir, "test.json")
            with open(filepath, "w") as f:
                json.dump(data, f)
            
            with pytest.raises(ValueError):
                load_json(filepath)


class TestCreateEmpty:
    def test_create_empty(self):
        data = create_empty("test.wav", "test_backend")
        assert data["backend"] == "test_backend"
        assert data["audio"] == "test.wav"
        assert data["notes"] == []
