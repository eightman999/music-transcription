"""Schema for note-event JSON.

Schema:
{
    "backend": str,
    "audio": str,
    "notes": [
        {
            "pitch": int (MIDI note number, 0-127),
            "onset": float (seconds),
            "offset": float (seconds),
            "velocity": int (1-127)
        }
    ],
    "pedal": [
        {
            "onset": float (seconds),
            "offset": float (seconds)
        }
    ] (optional),
    "meta": {
        "device": str (optional),
        "package": str (optional),
        "version": str (optional)
    } (optional)
}
"""

import json
from typing import Any, Dict, List, Optional


def validate_note(note: Dict[str, Any]) -> bool:
    """Validate a single note dict."""
    required_keys = {"pitch", "onset", "offset", "velocity"}
    if not required_keys.issubset(note.keys()):
        return False
    
    # Validate types
    if not isinstance(note["pitch"], int):
        return False
    if not isinstance(note["onset"], (int, float)):
        return False
    if not isinstance(note["offset"], (int, float)):
        return False
    if not isinstance(note["velocity"], int):
        return False
    
    # Validate ranges
    if not (0 <= note["pitch"] <= 127):
        return False
    if not (0 <= note["velocity"] <= 127):
        return False
    if note["velocity"] < 1:  # velocity must be 1-127
        return False
    if note["onset"] < 0:
        return False
    if note["offset"] < 0:
        return False
    if note["offset"] < note["onset"]:
        return False
    
    return True


def validate_pedal(pedal: Dict[str, Any]) -> bool:
    """Validate a single pedal dict."""
    required_keys = {"onset", "offset"}
    if not required_keys.issubset(pedal.keys()):
        return False
    
    if not isinstance(pedal["onset"], (int, float)):
        return False
    if not isinstance(pedal["offset"], (int, float)):
        return False
    
    if pedal["onset"] < 0:
        return False
    if pedal["offset"] < 0:
        return False
    if pedal["offset"] < pedal["onset"]:
        return False
    
    return True


def validate_schema(data: Dict[str, Any]) -> bool:
    """Validate the full note-event JSON schema."""
    required_keys = {"backend", "audio", "notes"}
    if not required_keys.issubset(data.keys()):
        return False
    
    # Validate types
    if not isinstance(data["backend"], str):
        return False
    if not isinstance(data["audio"], str):
        return False
    if not isinstance(data["notes"], list):
        return False
    
    # Validate each note
    for note in data["notes"]:
        if not isinstance(note, dict):
            return False
        if not validate_note(note):
            return False
    
    # Validate pedal if present
    if "pedal" in data:
        if not isinstance(data["pedal"], list):
            return False
        for pedal in data["pedal"]:
            if not isinstance(pedal, dict):
                return False
            if not validate_pedal(pedal):
                return False

    # Validate meta if present
    if "meta" in data:
        if not isinstance(data["meta"], dict):
            return False
        meta = data["meta"]
        # All meta fields are optional
        for key in meta:
            if not isinstance(meta[key], str):
                return False

    return True


def load_json(filepath: str) -> Dict[str, Any]:
    """Load and validate a note-event JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if not validate_schema(data):
        raise ValueError(f"Invalid schema in {filepath}")
    
    return data


def save_json(data: Dict[str, Any], filepath: str) -> None:
    """Save a note-event JSON file."""
    if not validate_schema(data):
        raise ValueError("Invalid schema")
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def create_empty(audio_path: str, backend: str = "") -> Dict[str, Any]:
    """Create an empty note-event dict with the given audio path and backend."""
    return {
        "backend": backend,
        "audio": audio_path,
        "notes": [],
    }
