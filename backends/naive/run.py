#!/usr/bin/env python3
"""Naive detector backend.

STFT -> per-MIDI-pitch fundamental energy -> thresholding ->
onset / sustain tracking -> note events.

Usage: python run.py <in.wav> <out.json>
"""

import sys
import os
import json
import numpy as np
import scipy.signal
import soundfile as sf

# Add parent directory to path to import mt.schema
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from mt.schema import save_json, create_empty


def compute_stft(audio, fs=44100, nperseg=4096, noverlap=None):
    """Compute STFT magnitude spectrum."""
    if noverlap is None:
        noverlap = nperseg // 4
    
    f, t, Zxx = scipy.signal.stft(
        audio,
        fs=fs,
        nperseg=nperseg,
        noverlap=noverlap,
        window='hann',
    )
    return f, t, np.abs(Zxx)


def midi_to_hz(midi_pitch):
    """Convert MIDI note number to Hz."""
    return 440.0 * (2.0 ** ((midi_pitch - 69) / 12.0))


def get_pitch_energy(spectrogram, frequencies, target_hz, bin_width_hz=10.0):
    """Get energy around a target frequency from spectrogram."""
    lower = target_hz - bin_width_hz / 2
    upper = target_hz + bin_width_hz / 2
    
    freq_indices = np.where((frequencies >= lower) & (frequencies <= upper))[0]
    
    if len(freq_indices) == 0:
        return np.zeros(spectrogram.shape[1])
    
    energy = np.sum(spectrogram[freq_indices, :], axis=0)
    return energy


def detect_onsets(energy, fs=44100, nperseg=4096, noverlap=None, threshold=0.2, min_distance=3):
    """Detect onsets from energy time series."""
    if noverlap is None:
        noverlap = nperseg // 4
    
    hop_length = nperseg - noverlap
    hop_time = hop_length / fs
    
    # Normalize energy
    energy_norm = energy / (np.max(energy) + 1e-10)
    
    # Find the first time energy rises above threshold
    onset_frames = []
    in_note = False
    for i in range(len(energy_norm)):
        if energy_norm[i] > threshold and not in_note:
            # Found onset
            onset_frames.append(i)
            in_note = True
        elif energy_norm[i] < threshold * 0.5:
            in_note = False
    
    onsets = [f * hop_time for f in onset_frames]
    return onsets


def track_notes(energy_dict, fs=44100, nperseg=4096, noverlap=None):
    """Track notes from pitch energies."""
    if noverlap is None:
        noverlap = nperseg // 4
    
    hop_length = nperseg - noverlap
    hop_time = hop_length / fs
    
    notes = []
    
    for pitch in sorted(energy_dict.keys()):
        if pitch not in energy_dict:
            continue
        
        energy = energy_dict[pitch]
        
        if np.max(energy) < 1e-10:
            continue
        
        # Detect onsets
        onsets = detect_onsets(energy, fs=fs, nperseg=nperseg, noverlap=noverlap, threshold=0.05, min_distance=10)
        
        # For each onset, find the offset
        for onset_time in onsets:
            onset_idx = int(onset_time / hop_time)
            
            # Find offset
            offset_idx = len(energy) - 1
            for j in range(onset_idx + 1, len(energy)):
                if energy[j] < np.max(energy) * 0.25:
                    offset_idx = j
                    break
            
            offset_time = offset_idx * hop_time
            
            # Calculate velocity
            peak_energy = np.max(energy[onset_idx:offset_idx])
            velocity = min(127, int(peak_energy * 127))
            
            notes.append({
                "pitch": pitch,
                "onset": onset_time,
                "offset": offset_time,
                "velocity": max(1, velocity),
            })
    
    return notes


def merge_overlapping_notes(notes, merge_threshold=0.05):
    """Merge notes that are very close in time."""
    if not notes:
        return []
    
    notes = sorted(notes, key=lambda n: n["onset"])
    
    merged = []
    current_note = notes[0]
    
    for note in notes[1:]:
        if (note["onset"] - current_note["onset"] < merge_threshold and 
            note["pitch"] == current_note["pitch"]):
            current_note["offset"] = max(current_note["offset"], note["offset"])
            current_note["velocity"] = max(current_note["velocity"], note["velocity"])
        else:
            merged.append(current_note)
            current_note = note
    
    merged.append(current_note)
    return merged


def remove_duplicates(notes):
    """Remove duplicate notes."""
    unique = []
    seen = set()
    
    for note in notes:
        key = (note["pitch"], round(note["onset"], 4), round(note["offset"], 4))
        if key not in seen:
            seen.add(key)
            unique.append(note)
    
    return unique


def detect_notes(audio_path):
    """Main detection function."""
    # Load audio
    audio, fs = sf.read(audio_path, dtype='float32')
    
    # Convert to mono if stereo
    if len(audio.shape) > 1:
        audio = np.mean(audio, axis=1)
    
    # Compute STFT with large window and high overlap for better frequency resolution
    nperseg = 16384
    noverlap = nperseg * 7 // 8  # 87.5% overlap
    f, t, Zxx = compute_stft(audio, fs=fs, nperseg=nperseg, noverlap=noverlap)
    
    # Compute energy for each MIDI pitch
    energy_dict = {}
    for midi_pitch in range(20, 109):
        target_hz = midi_to_hz(midi_pitch)
        energy = get_pitch_energy(Zxx, f, target_hz, bin_width_hz=3.0)
        energy_dict[midi_pitch] = energy
    
    # Apply threshold to keep only significant pitches
    all_energies = np.concatenate([energy_dict[p] for p in energy_dict])
    global_max = np.max(all_energies)
    threshold = global_max * 0.05
    
    thresholded_dict = {}
    for pitch in energy_dict:
        energy = energy_dict[pitch]
        if np.max(energy) > threshold:
            thresholded_dict[pitch] = energy
    
    # Track notes
    notes = track_notes(thresholded_dict, fs=fs, nperseg=nperseg, noverlap=noverlap)
    
    # Merge overlapping notes
    notes = merge_overlapping_notes(notes, merge_threshold=0.05)
    
    # Remove duplicates
    notes = remove_duplicates(notes)
    
    return notes


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <in.wav> <out.json>")
        sys.exit(1)
    
    input_wav = sys.argv[1]
    output_json = sys.argv[2]
    
    # Detect notes
    notes = detect_notes(input_wav)
    
    # Create output dict
    output = create_empty(input_wav, backend="naive")
    output["notes"] = notes
    
    # Save output
    save_json(output, output_json)
    
    print(f"Detected {len(notes)} notes, saved to {output_json}")


if __name__ == "__main__":
    main()
