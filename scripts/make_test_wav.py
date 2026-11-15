#!/usr/bin/env python3
"""Generate a piano-like synthetic test clip.

Creates exactly 16 notes: 3 chords (3.5 beats each) + 7 melody notes (0.9 beats each).
Fixed BPM 120, mono 44.1 kHz.
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
from mt.synth import generate_note_waveform, render_notes


def generate_test_clip(
    fs: int = 44100,
    bpm: int = 120,
) -> tuple:
    """Generate the test clip with exactly 16 notes.
    
    Notes:
    - Chords, 3.5 beats long, velocity 80:
      - beat 0: 48, 52, 55 (C3 E3 G3)
      - beat 4: 53, 57, 60 (F3 A3 C4)
      - beat 8: 55, 59, 62 (G3 B3 D4)
    - Melody, 0.9 beats long, velocity 100:
      - beat 1: 69
      - beat 2: 62
      - beat 3: 81
      - beat 5: 74
      - beat 6: 67
      - beat 9: 76
      - beat 10: 69
    
    Total length = 12 beats + 0.5 s of silence = 6.5 s.
    
    Args:
        fs: Sample rate
        bpm: Beats per minute
    
    Returns:
        Tuple of (audio, notes)
    """
    beat_duration = 60.0 / bpm  # seconds per beat
    
    # Chord notes: (pitch, onset_beat, duration_beats, velocity)
    chord_notes = [
        (48, 0, 3.5, 80), (52, 0, 3.5, 80), (55, 0, 3.5, 80),  # C3 E3 G3 at beat 0
        (53, 4, 3.5, 80), (57, 4, 3.5, 80), (60, 4, 3.5, 80),  # F3 A3 C4 at beat 4
        (55, 8, 3.5, 80), (59, 8, 3.5, 80), (62, 8, 3.5, 80),  # G3 B3 D4 at beat 8
    ]
    
    # Melody notes: (pitch, onset_beat, duration_beats, velocity)
    melody_notes = [
        (69, 1, 0.9, 100),  # A4 at beat 1
        (62, 2, 0.9, 100),  # D4 at beat 2
        (81, 3, 0.9, 100),  # A5 at beat 3
        (74, 5, 0.9, 100),  # E5 at beat 5
        (67, 6, 0.9, 100),  # G4 at beat 6
        (76, 9, 0.9, 100),  # E5 at beat 9
        (69, 10, 0.9, 100), # A4 at beat 10
    ]
    
    all_notes = chord_notes + melody_notes
    
    # Generate audio for each note
    audio_segments = []
    notes = []
    
    for pitch, onset_beat, duration_beats, velocity in all_notes:
        onset_time = onset_beat * beat_duration
        duration_time = duration_beats * beat_duration
        
        # Generate note waveform
        note_audio = generate_note_waveform(
            pitch=pitch,
            duration=duration_time,
            fs=fs,
            velocity=velocity,
        )
        
        # Store note info
        notes.append({
            "pitch": pitch,
            "onset": onset_time,
            "offset": onset_time + duration_time,
            "velocity": velocity,
        })
        
        # We'll mix all notes together
        audio_segments.append((onset_time, note_audio))
    
    # Create the full audio by mixing all notes
    # Find the total duration
    total_duration = 12 * beat_duration + 0.5  # 12 beats + 0.5 s silence
    total_samples = int(fs * total_duration)
    
    # Initialize audio with silence
    audio = np.zeros(total_samples)
    
    # Mix all notes
    for onset_time, note_audio in audio_segments:
        start_idx = int(onset_time * fs)
        end_idx = start_idx + len(note_audio)
        
        if end_idx > total_samples:
            # Extend audio if needed
            new_samples = end_idx - total_samples
            audio = np.pad(audio, (0, new_samples), mode='constant')
            total_samples = len(audio)
        
        audio[start_idx:end_idx] += note_audio
    
    # Add 0.5 s of silence at the end (if not already there)
    silence_duration = 0.5
    silence_samples = int(silence_duration * fs)
    current_duration = total_samples / fs
    
    if current_duration < 12 * beat_duration + silence_duration:
        additional_silence = int((12 * beat_duration + silence_duration - current_duration) * fs)
        if additional_silence > 0:
            audio = np.pad(audio, (0, additional_silence), mode='constant')
    
    # Peak-normalise the clip to 0.8
    max_amplitude = np.max(np.abs(audio))
    if max_amplitude > 0:
        audio = audio / max_amplitude * 0.8
    
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
    
    # Print note details for debugging
    print("\nNote details:")
    for i, note in enumerate(notes):
        print(f"  {i+1}. Pitch {note['pitch']}: onset={note['onset']:.3f}s, offset={note['offset']:.3f}s, velocity={note['velocity']}")


if __name__ == "__main__":
    main()
