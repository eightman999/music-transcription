#!/usr/bin/env python3
"""Kong backend for piano transcription.

Uses piano-transcription-inference package (Kong et al., 2020)
"High-resolution Piano Transcription with Pedals by Regressing Onsets and Offsets Times"

Usage: python run.py <in.wav> <out.json>
"""

import sys
import os
import json
import time
import numpy as np

# Add repo root to path to import mt.schema
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mt.schema import save_json, create_empty


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <in.wav> <out.json>")
        sys.exit(1)

    input_wav = sys.argv[1]
    output_json = sys.argv[2]

    # Import piano-transcription-inference
    try:
        from piano_transcription_inference import PianoTranscription, sample_rate
    except ImportError as e:
        print(f"Error importing piano-transcription-inference: {e}")
        print("Please run: bash backends/kong/setup.sh")
        sys.exit(1)

    # Determine device - try MPS first, fall back to CPU
    import torch
    device_str = 'mps'
    device = torch.device(device_str)
    
    # Test if MPS actually works with a small tensor operation
    try:
        test_tensor = torch.tensor([1.0], device=device)
        test_tensor * 2
        print(f"Using device: {device_str}")
    except Exception as e:
        print(f"MPS test failed ({e}), falling back to CPU")
        device_str = 'cpu'
        device = torch.device(device_str)
        print(f"Using device: {device_str}")

    # Checkpoint path - use MT_MODELS_DIR if set, otherwise repo data/models
    model_dir = os.path.join(
        os.environ.get('MT_MODELS_DIR', 
                       os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
        'data', 'models', 'kong'
    )
    checkpoint_path = os.path.join(model_dir, 'CRNN_note_F1=0.9677_pedal_F1=0.9186.pth')
    
    if not os.path.exists(checkpoint_path):
        print(f"Checkpoint not found at: {checkpoint_path}")
        print("Please run: bash backends/kong/setup.sh")
        sys.exit(1)

    print(f"Loading checkpoint: {checkpoint_path}")

    # Load audio using soundfile
    # The model expects mono 16 kHz float32 audio
    import soundfile as sf
    audio, fs_actual = sf.read(input_wav, dtype='float32')
    
    # Convert to mono if stereo by averaging channels
    if len(audio.shape) > 1:
        audio = np.mean(audio, axis=1)
    
    # Resample if needed to match the expected sample_rate (16000)
    if fs_actual != sample_rate:
        from scipy import signal
        num_samples = int(len(audio) * sample_rate / fs_actual)
        audio = signal.resample(audio, num_samples)
        fs_actual = sample_rate
    
    print(f"Audio loaded: {len(audio)} samples at {fs_actual} Hz, mono={audio.ndim == 1}")

    # Create transcriptor
    start_time = time.time()
    transcriptor = PianoTranscription(
        device=device,
        checkpoint_path=checkpoint_path
    )

    # Transcribe
    # The transcribe method expects audio as numpy array
    transcribed_dict = transcriptor.transcribe(audio, midi_path=None)
    
    elapsed_time = time.time() - start_time

    # Extract note events and pedal events
    est_note_events = transcribed_dict['est_note_events']
    est_pedal_events = transcribed_dict['est_pedal_events']

    print(f"Detected {len(est_note_events)} note events")
    print(f"Detected {len(est_pedal_events)} pedal events")
    print(f"Inference time: {elapsed_time:.2f}s")

    # Convert to our schema
    notes = []
    for event in est_note_events:
        note = {
            "pitch": int(event['midi_note']),
            "onset": float(event['onset_time']),
            "offset": float(event['offset_time']),
            "velocity": int(event['velocity']),
        }
        # Ensure velocity is in range 1-127
        note['velocity'] = max(1, min(127, note['velocity']))
        notes.append(note)

    # Convert pedal events to our schema
    pedal = []
    for event in est_pedal_events:
        pedal.append({
            "onset": float(event['onset_time']),
            "offset": float(event['offset_time']),
        })

    # Create output dict
    output = create_empty(input_wav, backend="kong")
    output["notes"] = notes
    if pedal:
        output["pedal"] = pedal
    
    # Add meta information
    output["meta"] = {
        "device": device_str,
        "package": "piano-transcription-inference",
        "version": "0.0.6",
    }

    # Save output
    save_json(output, output_json)

    print(f"Saved {len(notes)} notes to {output_json}")
    if pedal:
        print(f"Saved {len(pedal)} pedal events")


if __name__ == "__main__":
    main()
