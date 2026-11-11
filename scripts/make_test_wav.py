#!/usr/bin/env python3
"""Generate a piano-like synthetic test clip.

Creates exactly 16 notes: a simple C major scale played sequentially.
Fixed BPM 120, mono 44.1 kHz or 22.05 kHz.
Writes out/synth/test.wav and out/synth/test.gt.json.

Usage: python scripts/make_test_wav.py [--sr 44100]
"""

import os
import sys
import json
import numpy as np
import soundfile as sf

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mt.schema import save_json


def generate_sine_note(
    pitch: int,
    duration: float,
    fs: int = 44100,
    velocity: int = 100,
) -> np.ndarray:
    """Generate a pure sine wave note.
    
    Args:
        pitch: MIDI note number
        duration: Duration in seconds
        fs: Sample rate
        velocity: MIDI velocity (1-127)
    
    Returns:
        Audio samples as numpy array
    """
    # Convert MIDI pitch to frequency
    freq = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
    
    # Generate time array
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    
    # Generate sine wave with simple envelope
    amplitude = velocity / 127.0
    
    # Simple envelope: attack and release
    attack_time = 0.01
    release_time = 0.05
    
    envelope = np.ones_like(t)
    
    # Attack
    attack_idx = int(attack_time * fs)
    if attack_idx > 0:
        envelope[:attack_idx] = np.linspace(0, 1, attack_idx)
    
    # Release
    release_start = duration - release_time
    release_idx = int(release_start * fs)
    if release_idx < len(t):
        envelope[release_idx:] = np.linspace(1, 0, len(t) - release_idx)
    
    # Generate sine wave
    audio = amplitude * envelope * np.sin(2 * np.pi * freq * t)
    
    return audio


def generate_test_clip(
    fs: int = 44100,
    bpm: int = 120,
) -> Tuple[np.ndarray, List[Dict]]:
    """Generate the test clip with exactly 16 notes.
    
    Pattern: C major scale played 2 times (C4, D4, E4, F4, G4, A4, B4, C5)
    Each note is 0.8 seconds long, with 0.2 seconds gap between notes.
    Total duration: 16 * (0.8 + 0.2) = 16 seconds.
    
    Args:
        fs: Sample rate
        bpm: Beats per minute (used for quantization, not for timing)
    
    Returns:
        Tuple of (audio, notes)
    """
    # C major scale: C, D, E, F, G, A, B, C
    scale_pitches = [60, 62, 64, 65, 67, 69, 71, 72]
    
    # Repeat 2 times to get 16 notes
    note_pitches = scale_pitches * 2
    
    note_duration = 0.8  # seconds
    gap_duration = 0.2  # seconds
    
    notes = []
    audio_segments = []
    
    for i, pitch in enumerate(note_pitches):
        start_time = i * (note_duration + gap_duration)
        
        # Generate note
        note_audio = generate_sine_note(
            pitch=pitch,
            duration=note_duration,
            fs=fs,
            velocity=100,
        )
        
        # Add gap (silence)
        gap_audio = np.zeros(int(fs * gap_duration))
        audio_segments.append(note_audio)
        audio_segments.append(gap_audio)
        
        # Add to notes list
        notes.append({
            "pitch": pitch,
            "onset": start_time,
            "offset": start_time + note_duration,
            "velocity": 100,
        })
    
    # Concatenate audio
    audio = np.concatenate(audio_segments)
    
    return audio, notes


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate synthetic test clip")
    parser.add_argument("--sr", type=int, default=44100, help="Sample rate (default: 44100)")
    parser.add_argument("--bpm", type=int, default=120, help="BPM (default: 120)")
    parser.add_argument("--output-dir", type=str, default="out/synth", help="Output directory")
    args = parser.parse_args()
    
    # Generate test clip
    audio, notes = generate_test_clip(fs=args.sr, bpm=args.bpm)
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Save WAV
    wav_path = os.path.join(args.output_dir, "test.wav")
    sf.write(wav_path, audio, args.sr, subtype='PCM_16')
    print(f"Saved WAV to {wav_path}")
    
    # Save ground truth JSON
    gt_data = {
        "backend": "ground_truth",
        "audio": wav_path,
        "notes": notes,
    }
    gt_path = os.path.join(args.output_dir, "test.gt.json")
    save_json(gt_data, gt_path)
    print(f"Saved ground truth to {gt_path} with {len(notes)} notes")
    
    # Verify we have exactly 16 notes
    assert len(notes) == 16, f"Expected 16 notes, got {len(notes)}"
    print("✓ Generated exactly 16 notes")


if __name__ == "__main__":
    main()
