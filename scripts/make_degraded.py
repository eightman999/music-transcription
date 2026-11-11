#!/usr/bin/env python3
"""Create a degraded version of a dataset with room reverb, pink noise, and MP3 compression.

CLI: make_degraded.py --input <dir> --output <dir> [--force]

Processing:
1. Room reverb by convolution with synthetic impulse response
2. Pink noise at 30 dB SNR
3. Peak normalization to 0.99
4. MP3 96 kbps round trip with delay compensation
5. Write output as 16-bit PCM WAV

Ground truth files (.midi, .mid, .gt.json) are always copied.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve, correlate, correlation_lags


def get_ffmpeg_version():
    """Get ffmpeg version string."""
    result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg not found or failed")
    # ffmpeg outputs version info to stdout
    output = result.stdout.strip()
    if not output:
        output = result.stderr.strip()
    return output.split('\n')[0]


def compute_sha256(filepath):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def make_impulse_response(sr, rng):
    """Create synthetic room impulse response.
    
    Args:
        sr: sample rate in Hz
        rng: numpy random generator
        
    Returns:
        ir: impulse response as numpy array, length 0.6s at sr
    """
    duration = 0.6  # seconds
    n_samples = int(duration * sr)
    
    ir = np.zeros(n_samples, dtype=np.float64)
    
    # Direct sound at t=0
    ir[0] = 1.0
    
    # 5 ms in samples
    t_5ms = int(0.005 * sr)
    
    # RT60 = 0.5 seconds
    # Decay constant: 6.908 / RT60
    decay = 6.908 / 0.5
    
    # Direct-to-reverberant ratio = 6 dB
    # sum(tail^2) should equal 10^(-6/10)
    target_tail_energy = 10 ** (-6 / 10)
    
    # Generate tail from 5ms onwards
    tail_start = t_5ms
    tail_length = n_samples - tail_start
    
    if tail_length > 0:
        # Time array for tail (in seconds)
        t = np.arange(tail_start, n_samples) / sr
        
        # Generate Gaussian noise for the tail
        tail = rng.standard_normal(tail_length)
        
        # Apply exponential decay
        tail *= np.exp(-decay * t)
        
        # Scale tail to have the correct energy
        tail_energy = np.sum(tail ** 2)
        if tail_energy > 0:
            scale = np.sqrt(target_tail_energy / tail_energy)
            tail *= scale
        
        ir[tail_start:] = tail
    
    return ir


def apply_reverb(audio, ir, sr):
    """Apply reverb by convolution.
    
    Args:
        audio: input audio (n_samples,) or (n_samples, n_channels)
        ir: impulse response
        sr: sample rate
        
    Returns:
        reverbed audio with same shape as input
    """
    if audio.ndim == 1:
        # Mono
        result = fftconvolve(audio, ir)[:len(audio)]
    else:
        # Multi-channel: convolve each channel separately
        result = np.zeros_like(audio)
        for c in range(audio.shape[1]):
            result[:, c] = fftconvolve(audio[:, c], ir)[:len(audio)]
    
    return result


def generate_pink_noise(length, n_channels, rng):
    """Generate pink noise (1/f spectrum).
    
    Args:
        length: number of samples
        n_channels: number of channels
        rng: numpy random generator
        
    Returns:
        noise: (length, n_channels) array of pink noise
    """
    # Generate white Gaussian noise
    white = rng.standard_normal((length, n_channels))
    
    # Apply 1/f filtering in frequency domain
    n = length
    freqs = np.fft.rfftfreq(n)
    
    # Avoid division by zero at DC
    with np.errstate(divide='ignore', invalid='ignore'):
        filter_ = 1.0 / np.sqrt(np.maximum(freqs, 1))
    filter_[0] = 0  # DC bin set to 0
    
    # Apply filter to each channel
    noise = np.zeros((length, n_channels))
    for c in range(n_channels):
        fft_signal = np.fft.rfft(white[:, c])
        filtered = fft_signal * filter_
        noise[:, c] = np.fft.irfft(filtered, n=n)
    
    return noise


def add_noise_at_snr(signal, noise, target_snr_db):
    """Scale and add noise to achieve target SNR.
    
    Args:
        signal: clean signal (n_samples,) or (n_samples, n_channels)
        noise: noise signal (same shape as signal)
        target_snr_db: target SNR in dB
        
    Returns:
        noisy_signal: signal + scaled noise
        measured_snr_db: actual SNR achieved
    """
    # Compute signal power (mean of squares across all samples and channels)
    signal_power = np.mean(signal ** 2)
    noise_power = np.mean(noise ** 2)
    
    # Compute required scaling
    # SNR_db = 10 * log10(signal_power / noise_power)
    # target_snr_db = 10 * log10(signal_power / (noise_power * scale^2))
    # scale^2 = signal_power / (noise_power * 10^(target_snr_db/10))
    if noise_power > 0:
        scale = np.sqrt(signal_power / (noise_power * (10 ** (target_snr_db / 10))))
    else:
        scale = 0.0
    
    scaled_noise = noise * scale
    noisy_signal = signal + scaled_noise
    
    # Compute actual SNR
    actual_noise_power = np.mean(scaled_noise ** 2)
    if actual_noise_power > 0:
        measured_snr_db = 10 * np.log10(signal_power / actual_noise_power)
    else:
        measured_snr_db = float('inf')
    
    return noisy_signal, measured_snr_db


def normalize_peak(audio, max_peak=0.99):
    """Normalize audio to maximum peak value.
    
    Args:
        audio: input audio
        max_peak: maximum allowed peak (default 0.99)
        
    Returns:
        normalized audio, gain applied (1.0 if no scaling needed)
    """
    current_peak = np.max(np.abs(audio))
    if current_peak > max_peak:
        gain = max_peak / current_peak
        audio = audio * gain
    else:
        gain = 1.0
    return audio, gain


def measure_lag(signal1, signal2, sr, max_lag_seconds=0.2, window_seconds=30):
    """Measure lag between two signals using cross-correlation.
    
    Uses FFT-based correlation for speed. Sign convention: measure_lag(ref, delayed)
    returns +k when delayed[n] == ref[n - k] (i.e., delayed is ref shifted later by k samples).
    
    Args:
        signal1: reference signal (mono)
        signal2: delayed signal (mono)
        sr: sample rate
        max_lag_seconds: maximum lag to search (default 0.2s)
        window_seconds: duration of window to use (default 30s)
        
    Returns:
        lag in samples (positive if signal2 is delayed relative to signal1)
    """
    # Take a window from the beginning
    window_samples = min(len(signal1), len(signal2), int(window_seconds * sr))
    
    s1 = signal1[:window_samples]
    s2 = signal2[:window_samples]
    
    # Normalize both signals
    s1 = s1 - np.mean(s1)
    s2 = s2 - np.mean(s2)
    
    if np.std(s1) > 0:
        s1 = s1 / np.std(s1)
    if np.std(s2) > 0:
        s2 = s2 / np.std(s2)
    
    # Maximum lag in samples
    max_lag_samples = int(max_lag_seconds * sr)
    
    # Cross-correlation using FFT for speed
    # scipy.signal.correlate(a, b) computes sum_n a[n+k] * conj(b[n])
    # The lag where correlation peaks is the offset needed to align b with a
    # We want: if signal2 is delayed by k (signal2[n] = signal1[n-k]), return +k
    # scipy returns -k for this case, so we negate
    corr = correlate(s1, s2, mode='full', method='fft')
    
    # Get the lags array
    lags = correlation_lags(len(s1), len(s2), mode='full')
    
    # Restrict to +- max_lag_samples
    valid_indices = (np.abs(lags) <= max_lag_samples)
    valid_lags = lags[valid_indices]
    valid_corr = corr[valid_indices]
    
    if len(valid_corr) == 0:
        return 0
    
    best_index = np.argmax(valid_corr)
    best_lag = valid_lags[best_index]
    
    # Negate to get our sign convention: +k means signal2 is delayed by k
    return -best_lag


def mp3_roundtrip(input_path, sr, tmpdir):
    """Perform MP3 roundtrip: WAV -> MP3 96kbps -> WAV.
    
    Args:
        input_path: path to input WAV file
        sr: sample rate to use for output
        tmpdir: temporary directory for intermediate files
        
    Returns:
        path to output WAV file after roundtrip
    """
    tmpdir = Path(tmpdir)
    
    # Write temporary 16-bit WAV
    wav_a = tmpdir / "a.wav"
    
    # Encode to MP3
    mp3_path = tmpdir / "a.mp3"
    cmd_encode = [
        'ffmpeg', '-y', '-i', str(input_path),
        '-codec:a', 'libmp3lame', '-b:a', '96k',
        str(mp3_path)
    ]
    result = subprocess.run(cmd_encode, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"MP3 encoding failed: {result.stderr}")
    
    # Decode back to WAV
    wav_b = tmpdir / "b.wav"
    cmd_decode = [
        'ffmpeg', '-y', '-i', str(mp3_path),
        '-ar', str(sr),
        str(wav_b)
    ]
    result = subprocess.run(cmd_decode, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"MP3 decoding failed: {result.stderr}")
    
    return wav_b


def process_clip(input_path, output_path, sr, n_channels, rng, ffmpeg_version):
    """Process a single audio clip through the degradation pipeline.
    
    Args:
        input_path: path to input WAV file
        output_path: path to output WAV file
        sr: sample rate
        n_channels: number of channels
        rng: numpy random generator
        ffmpeg_version: ffmpeg version string
        
    Returns:
        dict with processing metadata for manifest
    """
    # Load audio as float64
    audio, loaded_sr = sf.read(input_path, dtype='float64')
    
    if loaded_sr != sr:
        raise ValueError(f"Sample rate mismatch: expected {sr}, got {loaded_sr}")
    
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
    
    if audio.shape[1] != n_channels:
        raise ValueError(f"Channel count mismatch: expected {n_channels}, got {audio.shape[1]}")
    
    original_samples = audio.shape[0]
    
    # Step 1: Room reverb
    ir = make_impulse_response(sr, rng)
    reverbed = apply_reverb(audio, ir, sr)
    
    # Step 2: Pink noise at 30 dB SNR
    noise = generate_pink_noise(original_samples, n_channels, rng)
    noisy, measured_snr_db = add_noise_at_snr(reverbed, noise, 30.0)
    
    # Step 3: Peak normalization
    noisy, peak_gain = normalize_peak(noisy, 0.99)
    
    # Write temporary WAV for MP3 roundtrip
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        # Write temporary 16-bit WAV
        temp_wav = tmpdir / "temp.wav"
        sf.write(str(temp_wav), noisy, sr, subtype='PCM_16')
        
        # Step 4: MP3 roundtrip
        wav_b = mp3_roundtrip(temp_wav, sr, tmpdir)
        
        # Load the MP3-decoded audio
        mp3_audio, mp3_sr = sf.read(str(wav_b), dtype='float64')
        
        if mp3_sr != sr:
            raise RuntimeError(f"MP3 decoding changed sample rate: {mp3_sr} != {sr}")
        
        if mp3_audio.ndim == 1:
            mp3_audio = mp3_audio.reshape(-1, 1)
        
        # Step 5: Delay compensation
        # Measure lag between temp_wav (a.wav) and wav_b (b.wav)
        # Use mono mixes
        a_mono = np.mean(noisy, axis=1)
        b_mono = np.mean(mp3_audio, axis=1)
        
        mp3_lag_samples = measure_lag(a_mono, b_mono, sr, max_lag_seconds=0.2, window_seconds=30)
        
        # Shift b by the lag
        if mp3_lag_samples > 0:
            # b is delayed: remove samples from beginning
            shifted = mp3_audio[mp3_lag_samples:]
            # Pad with zeros at the end if needed
            if len(shifted) < original_samples:
                padding = np.zeros((original_samples - len(shifted), n_channels))
                shifted = np.vstack([shifted, padding])
            elif len(shifted) > original_samples:
                shifted = shifted[:original_samples]
        elif mp3_lag_samples < 0:
            # b is ahead: add samples at beginning
            lag_abs = abs(mp3_lag_samples)
            padding = np.zeros((lag_abs, n_channels))
            shifted = np.vstack([padding, mp3_audio])
            shifted = shifted[:original_samples]
        else:
            shifted = mp3_audio[:original_samples]
        
        # Trim/pad to exact original length
        if len(shifted) < original_samples:
            padding = np.zeros((original_samples - len(shifted), n_channels))
            shifted = np.vstack([shifted, padding])
        elif len(shifted) > original_samples:
            shifted = shifted[:original_samples]
        
        # Measure residual lag
        shifted_mono = np.mean(shifted, axis=1)
        residual_lag_samples = measure_lag(a_mono, shifted_mono, sr, max_lag_seconds=0.001, window_seconds=30)
        
        # Check residual lag is within +-1 ms
        max_residual_samples = sr / 1000  # 1 ms in samples
        if abs(residual_lag_samples) > max_residual_samples:
            raise RuntimeError(
                f"Residual lag {residual_lag_samples} samples ({residual_lag_samples / sr * 1000:.3f} ms) "
                f"exceeds 1 ms tolerance"
            )
        
        # Write final output as 16-bit PCM
        sf.write(str(output_path), shifted, sr, subtype='PCM_16')
    
    # Compute SHA256 of output
    sha256 = compute_sha256(output_path)
    
    # Get duration
    duration = original_samples / sr
    
    return {
        'measured_snr_db': float(measured_snr_db),
        'mp3_lag_samples': int(mp3_lag_samples),
        'residual_lag_samples': int(residual_lag_samples),
        'peak_gain': float(peak_gain),
        'sha256': sha256,
        'duration': float(duration),
    }


def main():
    parser = argparse.ArgumentParser(description="Create degraded dataset")
    parser.add_argument("--input", type=str, required=True,
                        help="Input directory")
    parser.add_argument("--output", type=str, required=True,
                        help="Output directory")
    parser.add_argument("--force", action="store_true",
                        help="Force re-processing even if files exist")
    args = parser.parse_args()
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    
    # Check inputs
    if not input_dir.exists():
        print(f"ERROR: Input directory {input_dir} does not exist")
        sys.exit(1)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check ffmpeg
    try:
        ffmpeg_version = get_ffmpeg_version()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    # Get list of WAV files
    wav_files = sorted(input_dir.glob("*.wav"))
    if not wav_files:
        print(f"ERROR: No WAV files found in {input_dir}")
        sys.exit(1)
    
    print(f"Found {len(wav_files)} WAV files")
    print(f"Using ffmpeg: {ffmpeg_version}")
    
    # Fixed random seed for reproducibility
    rng = np.random.default_rng(20261111)
    
    # Processing parameters
    params = {
        'seed': 20261111,
        'rt60': 0.5,
        'direct_to_reverberant_ratio_db': 6,
        'target_snr_db': 30.0,
        'mp3_bitrate': '96k',
        'ffmpeg_version': ffmpeg_version,
    }
    
    # Process each clip
    clip_metadata = {}
    
    for wav_file in wav_files:
        slug = wav_file.stem
        output_wav = output_dir / f"{slug}.wav"
        
        print(f"\nProcessing {slug}...")
        
        # Check if already processed and --force is not set
        if not args.force and output_wav.exists():
            print(f"  Skipping: {output_wav} already exists")
        else:
            # Get audio info
            info = sf.info(str(wav_file))
            sr = info.samplerate
            n_channels = info.channels
            
            print(f"  Sample rate: {sr}, Channels: {n_channels}")
            
            # Process the clip
            try:
                start_time = time.time()
                metadata = process_clip(
                    str(wav_file), str(output_wav),
                    sr, n_channels, rng, ffmpeg_version
                )
                elapsed = time.time() - start_time
                clip_metadata[slug] = metadata
                print(f"  SNR: {metadata['measured_snr_db']:.2f} dB")
                print(f"  MP3 lag: {metadata['mp3_lag_samples']} samples")
                print(f"  Residual lag: {metadata['residual_lag_samples']} samples")
                print(f"  Peak gain: {metadata['peak_gain']:.4f}")
                print(f"  SHA256: {metadata['sha256']}")
                print(f"  Elapsed: {elapsed:.2f}s")
            except Exception as e:
                print(f"  ERROR processing {slug}: {e}")
                raise
        
        # Always copy ground truth files
        for ext in ['.midi', '.mid', '.gt.json']:
            src = input_dir / f"{slug}{ext}"
            if src.exists():
                dst = output_dir / f"{slug}{ext}"
                import shutil
                shutil.copy2(str(src), str(dst))
                print(f"  Copied {ext}")
    
    # Write manifest
    manifest = {
        'parameters': params,
        'clips': clip_metadata,
    }
    
    manifest_path = output_dir / "manifest.json"
    with open(str(manifest_path), 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\nManifest written to {manifest_path}")
    print(f"Done! Degraded set created in {output_dir}")


if __name__ == "__main__":
    main()
