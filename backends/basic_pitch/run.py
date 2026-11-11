#!/usr/bin/env python3
"""Basic Pitch backend for note detection.

Usage: python run.py <in.wav> <out.json>

Uses the basic-pitch library from Spotify for piano transcription.
API: from basic_pitch.inference import predict
Returns: model_output, midi_data, note_events = predict(path)
Note events: (start_s, end_s, midi_pitch, amplitude, pitch_bends)
Amplitude (0-1) is mapped to velocity (1-127).
"""

import sys
import os
import json
import time
import numpy as np

# Add parent directory to path to import mt.schema
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mt.schema import save_json, create_empty


def amplitude_to_velocity(amplitude: float) -> int:
    """Map amplitude (0-1) to MIDI velocity (1-127)."""
    # Clamp amplitude to [0, 1]
    amplitude = max(0.0, min(1.0, amplitude))
    # Scale to 1-127 range
    velocity = int(amplitude * 126) + 1
    # Ensure it's within valid range
    velocity = max(1, min(127, velocity))
    return velocity


def detect_notes(audio_path: str) -> tuple:
    """Detect notes using basic-pitch.
    
    Args:
        audio_path: Path to input WAV file
        
    Returns:
        Tuple of (notes, device, package_version)
    """
    try:
        from basic_pitch.inference import predict
        from basic_pitch import build_icassp_2022_model_path, FilenameSuffix
        import basic_pitch
    except ImportError as e:
        print(f"ERROR: Cannot import basic_pitch: {e}")
        print("Please run: bash backends/basic_pitch/setup.sh")
        sys.exit(1)
    
    # Get package version
    try:
        from importlib.metadata import version
        package_version = version('basic-pitch')
    except Exception:
        try:
            import pkg_resources
            package_version = pkg_resources.get_distribution('basic-pitch').version
        except Exception:
            package_version = "unknown"
    
    # Determine which runtime to use
    device = "CPU"
    model_path = None
    
    # Try ONNX first (more reliable in sandboxed environments)
    try:
        model_path = build_icassp_2022_model_path(FilenameSuffix.onnx)
        print(f"Using ONNX model: {model_path}")
        device = "ONNX Runtime (CPU)"
        # Try to detect if MPS is available
        try:
            import onnxruntime as ort
            providers = ort.get_available_providers()
            if 'CoreMLExecutionProvider' in providers:
                device = "ONNX Runtime (CoreML)"
            elif any('Metal' in str(p) for p in providers):
                device = "ONNX Runtime (MPS)"
        except Exception:
            pass
    except Exception as e:
        print(f"ONNX model not available: {e}")
        try:
            # Fall back to CoreML
            model_path = build_icassp_2022_model_path(FilenameSuffix.coreml)
            print(f"Using CoreML model: {model_path}")
            device = "CoreML (Apple MPS)"
        except Exception as e:
            print(f"CoreML model not available: {e}")
            # Fall back to default model
            print("Using default model")
    
    # Run prediction with tuned parameters
    # Using default thresholds from the ICASSP 2022 paper
    # predict returns: model_output, midi_data, note_events
    # note_events is a list of tuples: (start_s, end_s, midi_pitch, amplitude, pitch_bends)
    try:
        if model_path:
            model_output, midi_data, note_events = predict(
                audio_path, 
                model_or_model_path=model_path,
                onset_threshold=0.5,  # Default from paper
                frame_threshold=0.3,   # Default from paper
                minimum_note_length=127.7  # Default from paper in ms
            )
        else:
            model_output, midi_data, note_events = predict(
                audio_path,
                onset_threshold=0.5,
                frame_threshold=0.3,
                minimum_note_length=127.7
            )
    except Exception as e:
        print(f"ERROR: Prediction failed: {e}")
        sys.exit(1)
    
    notes = []
    
    for event in note_events:
        start_s, end_s, midi_pitch, amplitude, pitch_bends = event
        
        # Convert amplitude to velocity
        velocity = amplitude_to_velocity(amplitude)
        
        # Create note dict
        note = {
            "pitch": int(midi_pitch),
            "onset": float(start_s),
            "offset": float(end_s),
            "velocity": velocity,
        }
        
        notes.append(note)
    
    return notes, device, package_version


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <in.wav> <out.json>")
        sys.exit(1)
    
    input_wav = sys.argv[1]
    output_json = sys.argv[2]
    
    # Check if input file exists
    if not os.path.exists(input_wav):
        print(f"ERROR: Input file not found: {input_wav}")
        sys.exit(1)
    
    # Detect notes
    print(f"Running Basic Pitch on {input_wav}...")
    start_time = time.time()
    notes, device, package_version = detect_notes(input_wav)
    wall_time = time.time() - start_time
    
    # Create output dict
    output = create_empty(input_wav, backend="basic_pitch")
    output["notes"] = notes
    
    # Add meta information
    output["meta"] = {
        "device": device,
        "package": "basic-pitch",
        "version": package_version,
        "wall_time": wall_time
    }
    
    # Save output
    save_json(output, output_json)
    
    print(f"Detected {len(notes)} notes, saved to {output_json}")
    print(f"Wall time: {wall_time:.2f} seconds")
    print(f"Device: {device}")


if __name__ == "__main__":
    main()
