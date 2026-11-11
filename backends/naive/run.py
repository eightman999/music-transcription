#!/usr/bin/env python3
"""Naive detector backend.

STFT -> per-MIDI-pitch fundamental energy -> harmonic suppression ->
semitone-neighbour suppression -> onset / sustain tracking -> note events.

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


def midi_to_hz(midi_pitch):
    """Convert MIDI note number to Hz."""
    return 440.0 * (2.0 ** ((midi_pitch - 69) / 12.0))


def compute_stft(audio, fs=44100, nperseg=8192, noverlap=None):
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


def get_semitone_bandwidth(freq, semitones=0.3):
    """Get frequency range for +/- semitones around a frequency."""
    lower = freq * (2.0 ** (-semitones / 12.0))
    upper = freq * (2.0 ** (semitones / 12.0))
    return lower, upper


def compute_pitch_salience(spectrogram, frequencies, pitch_range=(36, 96), 
                           semitone_tolerance=0.3):
    """Compute pitch salience for each MIDI pitch.
    
    For each MIDI pitch p, S[p, t] = maximum magnitude among bins within
    +/- semitone_tolerance of the fundamental frequency of p.
    
    Returns:
        salience: 2D array of shape (num_pitches, num_frames)
        pitches: list of MIDI pitches
        hop_time: time between frames in seconds
    """
    pitches = list(range(pitch_range[0], pitch_range[1] + 1))
    num_pitches = len(pitches)
    num_frames = spectrogram.shape[1]
    
    salience = np.zeros((num_pitches, num_frames))
    
    for i, pitch in enumerate(pitches):
        f0 = midi_to_hz(pitch)
        lower, upper = get_semitone_bandwidth(f0, semitones=semitone_tolerance)
        
        # Find frequency bins within the range
        freq_indices = np.where((frequencies >= lower) & (frequencies <= upper))[0]
        
        if len(freq_indices) > 0:
            # Take maximum magnitude across the frequency bins
            salience[i, :] = np.max(spectrogram[freq_indices, :], axis=0)
    
    return salience, pitches


def get_active_pitches_per_frame(salience, pitches, threshold_db=-35.0):
    """Get set of active pitches for each frame.
    
    A pitch is active when its salience is above a threshold relative to
    the global maximum.
    
    Returns:
        active_pitches: list of sets, one per frame, containing active pitch indices
    """
    global_max = np.max(salience)
    if global_max <= 0:
        return [set() for _ in range(salience.shape[1])]
    
    threshold_linear = 10.0 ** (threshold_db / 20.0)
    threshold = global_max * threshold_linear
    
    active = salience > threshold
    
    active_pitches = []
    for t in range(active.shape[1]):
        active_indices = set(np.where(active[:, t])[0])
        active_pitches.append(active_indices)
    
    return active_pitches


def apply_harmonic_suppression_to_frame(active_pitches, salience, pitches, frame_idx):
    """Apply harmonic suppression to a single frame.
    
    A pitch p is suppressed if one of p-12, p-19, p-24 (the pitch whose
    2nd/3rd/4th harmonic is p) is active in that frame and stronger than p.
    
    Returns:
        filtered_pitches: set of pitch indices that are NOT suppressed
    """
    active_set = active_pitches[frame_idx]
    pitch_to_idx = {p: i for i, p in enumerate(pitches)}
    
    # Start with all active pitches
    filtered = set(active_set)
    
    for pitch_idx in list(active_set):
        pitch = pitches[pitch_idx]
        
        # Check if this pitch is explained as a harmonic of a lower pitch
        for harmonic_offset in [12, 19, 24]:  # 2nd, 3rd, 4th harmonic
            lower_pitch = pitch - harmonic_offset
            if lower_pitch in pitch_to_idx:
                lower_idx = pitch_to_idx[lower_pitch]
                # If lower pitch is active and stronger, suppress this pitch
                if (lower_idx in active_set and 
                    salience[lower_idx, frame_idx] > salience[pitch_idx, frame_idx]):
                    filtered.discard(pitch_idx)
                    break
    
    return filtered


def apply_semitone_suppression_to_frame(active_pitches, salience, pitches, frame_idx):
    """Apply semitone-neighbour suppression to a single frame.
    
    A pitch p is suppressed if p-1 or p+1 has a larger salience.
    
    Returns:
        filtered_pitches: set of pitch indices that are NOT suppressed
    """
    active_set = active_pitches[frame_idx]
    pitch_to_idx = {p: i for i, p in enumerate(pitches)}
    
    # Start with all active pitches
    filtered = set(active_set)
    
    for pitch_idx in list(active_set):
        pitch = pitches[pitch_idx]
        
        # Check neighbors
        for neighbor_offset in [-1, 1]:
            neighbor_pitch = pitch + neighbor_offset
            if neighbor_pitch in pitch_to_idx:
                neighbor_idx = pitch_to_idx[neighbor_pitch]
                # If neighbor is active and has larger salience, suppress this pitch
                if (neighbor_idx in active_set and 
                    salience[neighbor_idx, frame_idx] > salience[pitch_idx, frame_idx]):
                    filtered.discard(pitch_idx)
                    break
    
    return filtered


def track_notes(active_pitches_per_frame, salience, pitches, hop_time, 
                 min_duration=0.08, max_gap=0.03):
    """Track notes from per-frame active pitches.
    
    For each pitch, find continuous runs of active frames (with gaps <= max_gap).
    A note requires at least min_duration of continuous activity.
    
    Returns:
        notes: list of dicts with pitch, onset_frame, offset_frame, peak_salience
    """
    num_frames = len(active_pitches_per_frame)
    num_pitches = len(pitches)
    
    notes = []
    
    for pitch_idx in range(num_pitches):
        # Find frames where this pitch is active
        active_frames = []
        for t in range(num_frames):
            if pitch_idx in active_pitches_per_frame[t]:
                active_frames.append(t)
        
        if len(active_frames) == 0:
            continue
        
        # Group into continuous runs (with gap merging)
        runs = []
        current_run = [active_frames[0]]
        
        for i in range(1, len(active_frames)):
            gap = active_frames[i] - active_frames[i-1] - 1
            gap_time = gap * hop_time
            
            if gap_time <= max_gap:
                # Merge into current run
                current_run.append(active_frames[i])
            else:
                # Start new run
                runs.append(current_run)
                current_run = [active_frames[i]]
        
        runs.append(current_run)
        
        # Filter by minimum duration
        for run in runs:
            duration = (run[-1] - run[0] + 1) * hop_time
            if duration >= min_duration:
                # Find peak salience in this run
                peak_salience = np.max(salience[pitch_idx, run])
                
                notes.append({
                    'pitch': pitches[pitch_idx],
                    'onset_frame': run[0],
                    'offset_frame': run[-1],
                    'peak_salience': peak_salience,
                })
    
    return notes


def compute_spectral_flux(spectrogram):
    """Compute half-wave-rectified spectral flux.
    
    Spectral flux = sum of positive differences between consecutive frames.
    Half-wave rectified means we only keep positive differences.
    
    Returns:
        flux: 1D array of spectral flux values (one per frame after the first)
    """
    # Compute difference between consecutive frames
    diff = np.diff(spectrogram, axis=1)
    
    # Half-wave rectification: keep only positive differences
    diff_positive = np.maximum(diff, 0)
    
    # Sum across frequency bins
    flux = np.sum(diff_positive, axis=0)
    
    return flux


def find_flux_peaks(flux, min_distance=1):
    """Find peaks in spectral flux.
    
    Returns:
        peak_indices: indices of peaks in the flux array (relative to flux array)
    """
    if len(flux) == 0:
        return []
    
    # Pad to avoid edge issues
    flux_padded = np.concatenate([[0], flux, [0]])
    
    # Find local maxima
    peaks = []
    for i in range(1, len(flux_padded) - 1):
        if flux_padded[i] > flux_padded[i-1] and flux_padded[i] >= flux_padded[i+1]:
            peaks.append(i - 1)  # -1 because we padded at the start
    
    # Apply minimum distance constraint
    if min_distance > 0:
        filtered_peaks = []
        last_peak = -min_distance
        for peak in peaks:
            if peak - last_peak >= min_distance:
                filtered_peaks.append(peak)
                last_peak = peak
        peaks = filtered_peaks
    
    return peaks


def refine_onsets_with_flux(notes, flux, flux_frame_times, hop_time_pitch, 
                             search_window=0.15):
    """Refine note onsets using spectral flux peaks.
    
    Move each note onset to the nearest flux peak within +/- search_window seconds.
    
    Returns:
        notes: list of notes with refined onsets (in seconds)
    """
    if len(flux) == 0:
        # No flux, just convert frames to times
        refined_notes = []
        for note in notes:
            refined_notes.append({
                'pitch': note['pitch'],
                'onset': note['onset_frame'] * hop_time_pitch,
                'offset': (note['offset_frame'] + 1) * hop_time_pitch,
                'peak_salience': note['peak_salience'],
            })
        return refined_notes
    
    # Find flux peaks
    peak_indices = find_flux_peaks(flux)
    peak_times = flux_frame_times[peak_indices]
    
    refined_notes = []
    for note in notes:
        onset_time = note['onset_frame'] * hop_time_pitch
        
        # Find nearest peak within search window
        best_peak = None
        best_distance = float('inf')
        
        for peak_time in peak_times:
            distance = abs(peak_time - onset_time)
            if distance <= search_window and distance < best_distance:
                best_peak = peak_time
                best_distance = distance
        
        if best_peak is not None:
            onset_time = best_peak
        
        # Convert offset frame to time, but we'll adjust it later
        offset_time = (note['offset_frame'] + 1) * hop_time_pitch
        
        refined_notes.append({
            'pitch': note['pitch'],
            'onset': onset_time,
            'offset': offset_time,
            'peak_salience': note['peak_salience'],
        })
    
    return refined_notes


def correct_offsets(notes, window_duration, hop_time_pitch):
    """Correct offset bias introduced by the long window.
    
    The long STFT window causes the detected offset to be delayed.
    We add a correction to the offset to account for the window delay.
    """
    # The window causes a delay. We need to extend the offset.
    # Empirically, we need to add about 0.070s to get the correct offset
    offset_correction = window_duration * 0.375
    
    corrected_notes = []
    for note in notes:
        # Extend the offset
        new_offset = note['offset'] + offset_correction
        
        corrected_notes.append({
            'pitch': note['pitch'],
            'onset': note['onset'],
            'offset': new_offset,
            'peak_salience': note['peak_salience'],
        })
    
    return corrected_notes


def salience_to_velocity(peak_salience, global_max):
    """Map peak salience to velocity (1-127).
    
    Monotonic mapping: velocity = 1 + 126 * (peak_salience / global_max)
    """
    if global_max <= 0:
        return 1
    
    # Clamp to valid range
    normalized = peak_salience / global_max
    velocity = 1 + int(126 * normalized)
    velocity = max(1, min(127, velocity))
    return velocity


def detect_notes(audio_path):
    """Main detection function."""
    # Load audio
    audio, fs = sf.read(audio_path, dtype='float32')
    
    # Convert to mono if stereo
    if len(audio.shape) > 1:
        audio = np.mean(audio, axis=1)
    
    # ============================================================
    # Stage 1: Pitch salience with large window (8192, hop 441 = 10 ms)
    # ============================================================
    nperseg_pitch = 8192
    hop_pitch = 441
    noverlap_pitch = nperseg_pitch - hop_pitch
    
    f_pitch, t_pitch, spectrogram_pitch = compute_stft(
        audio, fs=fs, nperseg=nperseg_pitch, noverlap=noverlap_pitch
    )
    
    hop_time_pitch = hop_pitch / fs  # 0.01 s = 10 ms
    
    # Compute pitch salience
    salience, pitches = compute_pitch_salience(
        spectrogram_pitch, f_pitch, pitch_range=(36, 96), semitone_tolerance=0.3
    )
    
    # ============================================================
    # Stage 2: Activity detection
    # ============================================================
    active_pitches = get_active_pitches_per_frame(salience, pitches, threshold_db=-15.0)
    
    # ============================================================
    # Stage 3: Harmonic suppression (per frame)
    # ============================================================
    for t in range(len(active_pitches)):
        active_pitches[t] = apply_harmonic_suppression_to_frame(
            active_pitches, salience, pitches, t
        )
    
    # ============================================================
    # Stage 4: Semitone-neighbour suppression (per frame)
    # ============================================================
    for t in range(len(active_pitches)):
        active_pitches[t] = apply_semitone_suppression_to_frame(
            active_pitches, salience, pitches, t
        )
    
    # ============================================================
    # Stage 5: Tracking
    # ============================================================
    raw_notes = track_notes(
        active_pitches, salience, pitches, hop_time_pitch,
        min_duration=0.08, max_gap=0.03
    )
    
    # ============================================================
    # Stage 6: Onset refinement with small window STFT (1024, hop 220 = 5 ms)
    # ============================================================
    nperseg_onset = 1024
    hop_onset = 220
    noverlap_onset = nperseg_onset - hop_onset
    
    f_onset, t_onset, spectrogram_onset = compute_stft(
        audio, fs=fs, nperseg=nperseg_onset, noverlap=noverlap_onset
    )
    
    # Compute spectral flux
    flux = compute_spectral_flux(spectrogram_onset)
    
    # Get frame times for onset STFT (flux has one fewer frame)
    hop_time_onset = hop_onset / fs  # 0.005 s = 5 ms
    flux_frame_times = t_onset[1:]  # flux[i] corresponds to time between frame i and i+1
    
    # Refine onsets
    refined_notes = refine_onsets_with_flux(
        raw_notes, flux, flux_frame_times, hop_time_pitch, search_window=0.15
    )
    
    # ============================================================
    # Stage 7: Offset correction
    # ============================================================
    window_duration = nperseg_pitch / fs
    corrected_notes = correct_offsets(refined_notes, window_duration, hop_time_pitch)
    
    # ============================================================
    # Stage 8: Velocity mapping
    # ============================================================
    global_max_salience = np.max(salience)
    
    final_notes = []
    for note in corrected_notes:
        velocity = salience_to_velocity(note['peak_salience'], global_max_salience)
        final_notes.append({
            'pitch': note['pitch'],
            'onset': note['onset'],
            'offset': note['offset'],
            'velocity': velocity,
        })
    
    return final_notes


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
