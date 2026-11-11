#!/usr/bin/env python3
"""Transkun backend for piano transcription.

Uses the transkun package to transcribe piano audio to MIDI,
then converts MIDI to note-event JSON format.

Usage: python run.py <in.wav> <out.json>
"""

import sys
import os
import json
import subprocess
import tempfile
import pretty_midi

# Add parent directory to path to import mt.schema
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mt.schema import save_json, create_empty


def convert_midi_to_notes(midi_path: str) -> tuple:
    """Convert MIDI file to notes and pedal events.
    
    Args:
        midi_path: Path to MIDI file
        
    Returns:
        Tuple of (notes, pedal_events)
    """
    # Load MIDI with pretty_midi
    midi_data = pretty_midi.PrettyMIDI(midi_path)
    
    notes = []
    pedal_events = []
    
    # Process all instruments (transkun typically outputs one instrument)
    for instrument in midi_data.instruments:
        for note in instrument.notes:
            notes.append({
                "pitch": int(note.pitch),
                "onset": float(note.start),
                "offset": float(note.end),
                "velocity": int(note.velocity),
            })
    
    # Collect all CC64 events from all instruments
    cc64_events = []
    for instrument in midi_data.instruments:
        for cc in instrument.control_changes:
            if cc.number == 64:
                cc64_events.append((cc.time, cc.value))
    
    # Sort by time
    cc64_events.sort(key=lambda x: x[0])
    
    # Track pedal state and create pedal events
    pedal_pressed = False
    pedal_start = None
    
    for time, value in cc64_events:
        if value >= 64 and not pedal_pressed:
            # Pedal pressed
            pedal_pressed = True
            pedal_start = time
        elif value < 64 and pedal_pressed:
            # Pedal released
            pedal_pressed = False
            if pedal_start is not None:
                pedal_events.append({
                    "onset": float(pedal_start),
                    "offset": float(time),
                })
                pedal_start = None
    
    # If pedal is still pressed at the end, create an event to the end of the audio
    if pedal_pressed and pedal_start is not None:
        # Get the end time from the last note or use a reasonable default
        max_end = max([n["offset"] for n in notes]) if notes else 0
        pedal_events.append({
            "onset": float(pedal_start),
            "offset": float(max_end),
        })
    
    return notes, pedal_events


def get_weight_paths():
    """Get paths to transkun pretrained weights and config.
    
    Uses importlib_resources to find the weight files in the venv.
    Returns (weight_path, conf_path).
    """
    import importlib_resources
    import transkun
    
    weight_path = importlib_resources.files(transkun).joinpath("pretrained/2.0.pt")
    conf_path = importlib_resources.files(transkun).joinpath("pretrained/2.0.conf")
    
    return str(weight_path), str(conf_path)


def transcribe_audio(input_wav: str, output_mid: str, device: str = "cpu") -> None:
    """Run transkun transcription.
    
    Args:
        input_wav: Input WAV file path
        output_mid: Output MIDI file path
        device: Device to use (cpu, cuda, mps)
    """
    weight_path, conf_path = get_weight_paths()
    
    # Build command
    cmd = [
        sys.executable,
        "-m",
        "transkun.transcribe",
        input_wav,
        output_mid,
        "--weight",
        weight_path,
        "--conf",
        conf_path,
        "--device",
        device,
    ]
    
    # Run transkun
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True,
    )
    
    # Print output for debugging
    if result.stdout:
        print(f"transkun stdout: {result.stdout}", file=sys.stderr)
    if result.stderr:
        print(f"transkun stderr: {result.stderr}", file=sys.stderr)


def get_device_info():
    """Get device information for meta object."""
    device = "cpu"
    package = "transkun"
    version = "2.0.1"
    
    try:
        import torch
        if torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
    except ImportError:
        pass
    
    try:
        import transkun
        version = transkun.__version__
    except (ImportError, AttributeError):
        pass
    
    return device, package, version


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <in.wav> <out.json>", file=sys.stderr)
        sys.exit(1)
    
    input_wav = sys.argv[1]
    output_json = sys.argv[2]
    
    # Determine device
    device, package, version = get_device_info()
    print(f"Using {device} device", file=sys.stderr)
    
    # Create temporary MIDI file
    with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp_mid:
        tmp_mid_path = tmp_mid.name
    
    try:
        # Run transkun transcription
        print(f"Transcribing {input_wav} with device={device}...", file=sys.stderr)
        transcribe_audio(input_wav, tmp_mid_path, device)
        
        # Convert MIDI to notes
        print(f"Converting MIDI to notes...", file=sys.stderr)
        notes, pedal_events = convert_midi_to_notes(tmp_mid_path)
        
        # Create output dict
        output = create_empty(input_wav, backend="transkun")
        output["notes"] = notes
        if pedal_events:
            output["pedal"] = pedal_events
        
        # Add meta information
        output["meta"] = {
            "device": device,
            "package": package,
            "version": version,
        }
        
        # Save output
        save_json(output, output_json)
        
        print(f"Detected {len(notes)} notes, {len(pedal_events)} pedal events, saved to {output_json}", file=sys.stderr)
        
    finally:
        # Clean up temporary MIDI file
        if os.path.exists(tmp_mid_path):
            os.unlink(tmp_mid_path)


if __name__ == "__main__":
    main()
