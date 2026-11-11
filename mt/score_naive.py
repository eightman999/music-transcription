"""Naive scoring: fixed-BPM grid quantization, MIDI and MusicXML output."""

import os
from pathlib import Path
from typing import Dict, List, Optional
import numpy as np
import pretty_midi
import music21
from mt.schema import load_json, save_json


def quantize_notes(
    notes: List[Dict],
    bpm: float = 120.0,
    grid_size: int = 16,
) -> List[Dict]:
    """Quantize note onsets and offsets to a fixed BPM grid.
    
    Args:
        notes: List of note dicts with onset, offset in seconds
        bpm: Beats per minute
        grid_size: Number of divisions per beat (e.g., 16 for 16th notes)
    
    Returns:
        List of quantized note dicts
    """
    if not notes:
        return []
    
    # Calculate time per grid division
    beats_per_second = bpm / 60.0
    seconds_per_beat = 1.0 / beats_per_second
    seconds_per_grid = seconds_per_beat / grid_size
    
    quantized = []
    for note in notes:
        # Quantize onset and offset
        onset_grid = round(note["onset"] / seconds_per_grid)
        offset_grid = round(note["offset"] / seconds_per_grid)
        
        # Ensure offset >= onset
        if offset_grid < onset_grid:
            offset_grid = onset_grid + 1
        
        quantized_note = {
            "pitch": note["pitch"],
            "onset": onset_grid * seconds_per_grid,
            "offset": offset_grid * seconds_per_grid,
            "velocity": note["velocity"],
        }
        quantized.append(quantized_note)
    
    return quantized


def notes_to_pretty_midi(
    notes: List[Dict],
    hand_split_pitch: int = 60,  # C4 = MIDI 60
) -> pretty_midi.PrettyMIDI:
    """Convert notes to PrettyMIDI object with hand splitting.
    
    Args:
        notes: List of note dicts
        hand_split_pitch: MIDI pitch to split hands (notes >= this go to right hand)
    
    Returns:
        PrettyMIDI object
    """
    pm = pretty_midi.PrettyMIDI()
    
    # Create two instruments: left hand (piano, program 0) and right hand (piano, program 0)
    left_instrument = pretty_midi.Instrument(program=0)
    right_instrument = pretty_midi.Instrument(program=0)
    
    for note in notes:
        midi_note = pretty_midi.Note(
            velocity=note["velocity"],
            pitch=note["pitch"],
            start=note["onset"],
            end=note["offset"],
        )
        
        if note["pitch"] >= hand_split_pitch:
            right_instrument.notes.append(midi_note)
        else:
            left_instrument.notes.append(midi_note)
    
    # Add instruments to PrettyMIDI
    if left_instrument.notes:
        pm.instruments.append(left_instrument)
    if right_instrument.notes:
        pm.instruments.append(right_instrument)
    
    return pm


def notes_to_music21_stream(
    notes: List[Dict],
    bpm: float = 120.0,
    hand_split_pitch: int = 60,
) -> music21.stream.Stream:
    """Convert notes to Music21 stream with two staves (left and right hand).
    
    Args:
        notes: List of note dicts
        bpm: Beats per minute for tempo
        hand_split_pitch: MIDI pitch to split hands
    
    Returns:
        Music21 Stream with PianoStaff
    """
    from music21 import note, stream, instrument, tempo
    
    # Create streams for each hand
    left_stream = stream.Stream()
    right_stream = stream.Stream()
    
    # Set tempo
    metronome_mark = tempo.MetronomeMark(number=bpm)
    
    for n in notes:
        # Create music21 note
        n_duration = n["offset"] - n["onset"]
        
        # Convert MIDI pitch to music21 pitch
        m21_pitch = music21.pitch.Pitch()
        m21_pitch.midi = n["pitch"]
        
        # Create note with duration
        m21_note = note.Note(pitch=m21_pitch)
        m21_note.duration.quarterLength = n_duration * bpm / 60.0 * 4  # Convert seconds to quarter notes
        m21_note.volume.velocity = n["velocity"]
        
        if n["pitch"] >= hand_split_pitch:
            right_stream.append(m21_note)
        else:
            left_stream.append(m21_note)
    
    # Create piano staff
    left_piano = instrument.Piano()
    left_piano.partId = "left"
    left_stream.insert(0, left_piano)
    left_stream.insert(0, metronome_mark)
    
    right_piano = instrument.Piano()
    right_piano.partId = "right"
    right_stream.insert(0, right_piano)
    right_stream.insert(0, metronome_mark)
    
    # Create score with two staves
    score = stream.Score()
    score.insert(0, left_stream)
    score.insert(0, right_stream)
    
    return score


def score_notes(
    input_json: str,
    output_dir: str,
    bpm: float = 120.0,
    hand_split_pitch: int = 60,
) -> Dict[str, str]:
    """Score notes from JSON to MIDI and MusicXML.
    
    Args:
        input_json: Path to input JSON file
        output_dir: Output directory
        bpm: Beats per minute
        hand_split_pitch: MIDI pitch to split hands
    
    Returns:
        Dict with paths to output files
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Load notes
    data = load_json(input_json)
    notes = data["notes"]
    
    # Quantize
    quantized_notes = quantize_notes(notes, bpm=bpm)
    
    # Save quantized JSON
    quantized_data = {
        "backend": data.get("backend", ""),
        "audio": data.get("audio", ""),
        "notes": quantized_notes,
    }
    if "pedal" in data:
        quantized_data["pedal"] = data["pedal"]
    
    notes_json_path = os.path.join(output_dir, "notes.json")
    save_json(quantized_data, notes_json_path)
    
    # Save MIDI
    pm = notes_to_pretty_midi(quantized_notes, hand_split_pitch=hand_split_pitch)
    midi_path = os.path.join(output_dir, "out.mid")
    pm.write(midi_path)
    
    # Save MusicXML
    try:
        m21_stream = notes_to_music21_stream(quantized_notes, bpm=bpm, hand_split_pitch=hand_split_pitch)
        musicxml_path = os.path.join(output_dir, "out.musicxml")
        m21_stream.write("musicxml", fp=musicxml_path)
    except Exception as e:
        print(f"Warning: Could not generate MusicXML: {e}")
        musicxml_path = None
    
    return {
        "notes_json": notes_json_path,
        "midi": midi_path,
        "musicxml": musicxml_path,
    }
