"""Tests for the make_degraded.py script."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import correlate, correlation_lags


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


def measure_lag(signal1, signal2, sr, max_lag_seconds=0.002, window_seconds=30):
    """Measure lag between two signals using cross-correlation.
    
    Uses FFT-based correlation for speed. Sign convention: measure_lag(ref, delayed)
    returns +k when delayed[n] == ref[n - k] (i.e., delayed is ref shifted later by k samples).
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


def create_synthetic_clip(sr=44100, duration=3.0, n_channels=2):
    """Create a synthetic stereo audio clip with decaying sine notes."""
    n_samples = int(sr * duration)
    t = np.arange(n_samples) / sr
    
    # Create a few decaying sine notes with sharp attacks
    audio = np.zeros((n_samples, n_channels))
    
    # Note 1: 440 Hz (A4), starts at 0.1s, decays over 0.5s
    start_idx = int(0.1 * sr)
    decay_length = int(0.5 * sr)
    note_t = np.arange(decay_length) / sr
    envelope = np.exp(-5 * note_t)  # Sharp attack, exponential decay
    note = envelope * np.sin(2 * np.pi * 440 * note_t)
    audio[start_idx:start_idx+decay_length, :] = note.reshape(-1, 1)
    
    # Note 2: 660 Hz (E5), starts at 0.8s, decays over 0.4s
    start_idx = int(0.8 * sr)
    decay_length = int(0.4 * sr)
    note_t = np.arange(decay_length) / sr
    envelope = np.exp(-5 * note_t)
    note = envelope * np.sin(2 * np.pi * 660 * note_t)
    audio[start_idx:start_idx+decay_length, :] = note.reshape(-1, 1)
    
    # Note 3: 880 Hz (A5), starts at 1.5s, decays over 0.3s
    start_idx = int(1.5 * sr)
    decay_length = int(0.3 * sr)
    note_t = np.arange(decay_length) / sr
    envelope = np.exp(-5 * note_t)
    note = envelope * np.sin(2 * np.pi * 880 * note_t)
    audio[start_idx:start_idx+decay_length, :] = note.reshape(-1, 1)
    
    # Normalize to 0.5 peak to leave room for processing
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.5
    
    return audio, sr, n_channels


@pytest.fixture
def temp_dir():
    """Create a temporary directory for testing."""
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def synthetic_dataset(temp_dir):
    """Create a synthetic dataset with WAV and ground truth files."""
    input_dir = temp_dir / "input"
    input_dir.mkdir()
    
    # Create synthetic audio
    audio, sr, n_channels = create_synthetic_clip()
    
    # Write WAV file
    wav_path = input_dir / "test_clip.wav"
    sf.write(str(wav_path), audio, sr, subtype='PCM_16')
    
    # Write dummy ground truth
    gt_path = input_dir / "test_clip.gt.json"
    gt_data = {"notes": [{"time": 0.1, "pitch": 69, "duration": 0.5}]}
    with open(str(gt_path), 'w') as f:
        json.dump(gt_data, f)
    
    return input_dir, wav_path, audio, sr, n_channels


def check_ffmpeg():
    """Check if ffmpeg is available."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not check_ffmpeg(), reason="ffmpeg not installed")
class TestMakeDegraded:
    """Tests for make_degraded.py script."""
    
    def test_basic_processing(self, synthetic_dataset, temp_dir):
        """Test basic processing of a synthetic clip."""
        input_dir, wav_path, original_audio, sr, n_channels = synthetic_dataset
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        # Run the script
        script_path = Path(__file__).parent.parent / "scripts" / "make_degraded.py"
        cmd = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Check script succeeded
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        
        # Check output WAV exists
        output_wav = output_dir / "test_clip.wav"
        assert output_wav.exists(), "Output WAV not created"
        
        # Load output audio
        output_audio, output_sr, output_channels = load_audio_info(output_wav)
        
        # Check sample rate and channels match
        assert output_sr == sr, f"Sample rate mismatch: {output_sr} != {sr}"
        assert output_channels == n_channels, f"Channel count mismatch: {output_channels} != {n_channels}"
        
        # Check number of samples matches
        assert output_audio.shape[0] == original_audio.shape[0], \
            f"Sample count mismatch: {output_audio.shape[0]} != {original_audio.shape[0]}"
    
    def test_manifest(self, synthetic_dataset, temp_dir):
        """Test that manifest is created with correct metadata."""
        input_dir, wav_path, original_audio, sr, n_channels = synthetic_dataset
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        script_path = Path(__file__).parent.parent / "scripts" / "make_degraded.py"
        cmd = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        
        # Check manifest exists
        manifest_path = output_dir / "manifest.json"
        assert manifest_path.exists(), "Manifest not created"
        
        # Load and validate manifest
        with open(str(manifest_path), 'r') as f:
            manifest = json.load(f)
        
        # Check parameters
        assert 'parameters' in manifest
        params = manifest['parameters']
        assert params['seed'] == 20261111
        assert params['rt60'] == 0.5
        assert params['direct_to_reverberant_ratio_db'] == 6
        assert params['target_snr_db'] == 30.0
        assert params['mp3_bitrate'] == '96k'
        assert 'ffmpeg_version' in params
        
        # Check clip metadata
        assert 'clips' in manifest
        assert 'test_clip' in manifest['clips']
        clip = manifest['clips']['test_clip']
        
        # Check measured SNR is within tolerance
        assert abs(clip['measured_snr_db'] - 30.0) < 0.1, \
            f"SNR out of tolerance: {clip['measured_snr_db']}"
        
        # Check residual lag is within 1 ms
        max_residual = sr / 1000
        assert abs(clip['residual_lag_samples']) <= max_residual, \
            f"Residual lag too large: {clip['residual_lag_samples']} samples"
        
        # Check other fields exist
        assert 'mp3_lag_samples' in clip
        assert 'peak_gain' in clip
        assert 'sha256' in clip
        assert 'duration' in clip
    
    def test_ground_truth_copied(self, synthetic_dataset, temp_dir):
        """Test that ground truth files are copied."""
        input_dir, wav_path, original_audio, sr, n_channels = synthetic_dataset
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        script_path = Path(__file__).parent.parent / "scripts" / "make_degraded.py"
        cmd = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        
        # Check ground truth file was copied
        gt_path = output_dir / "test_clip.gt.json"
        assert gt_path.exists(), "Ground truth file not copied"
        
        # Verify content matches
        with open(str(input_dir / "test_clip.gt.json"), 'r') as f:
            original_gt = json.load(f)
        with open(str(gt_path), 'r') as f:
            copied_gt = json.load(f)
        assert original_gt == copied_gt, "Ground truth content mismatch"
    
    def test_lag_compensation(self, synthetic_dataset, temp_dir):
        """Test that MP3 lag is properly compensated."""
        input_dir, wav_path, original_audio, sr, n_channels = synthetic_dataset
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        script_path = Path(__file__).parent.parent / "scripts" / "make_degraded.py"
        cmd = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        
        # Load original and degraded audio
        output_wav = output_dir / "test_clip.wav"
        degraded_audio, _, _ = load_audio_info(output_wav)
        
        # Measure lag between original and degraded
        # Use mono mixes
        original_mono = np.mean(original_audio, axis=1)
        degraded_mono = np.mean(degraded_audio, axis=1)
        
        lag_samples = measure_lag(original_mono, degraded_mono, sr, max_lag_seconds=0.002)
        
        # Lag should be within +-2 ms
        max_lag_samples = int(0.002 * sr)
        assert abs(lag_samples) <= max_lag_samples, \
            f"Lag too large: {lag_samples} samples ({lag_samples / sr * 1000:.3f} ms)"
    
    def test_deterministic(self, synthetic_dataset, temp_dir):
        """Test that running twice gives identical results."""
        input_dir, wav_path, original_audio, sr, n_channels = synthetic_dataset
        
        script_path = Path(__file__).parent.parent / "scripts" / "make_degraded.py"
        
        # First run
        output_dir1 = temp_dir / "output1"
        output_dir1.mkdir()
        cmd1 = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir1),
            "--force",
        ]
        result1 = subprocess.run(cmd1, capture_output=True, text=True)
        assert result1.returncode == 0, f"First run failed: {result1.stderr}"
        
        # Second run
        output_dir2 = temp_dir / "output2"
        output_dir2.mkdir()
        cmd2 = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir2),
            "--force",
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        assert result2.returncode == 0, f"Second run failed: {result2.stderr}"
        
        # Compare SHA256 hashes
        output_wav1 = output_dir1 / "test_clip.wav"
        output_wav2 = output_dir2 / "test_clip.wav"
        
        sha1 = compute_sha256(str(output_wav1))
        sha2 = compute_sha256(str(output_wav2))
        
        assert sha1 == sha2, f"SHA256 mismatch: {sha1} != {sha2}"
    
    def test_skip_without_force(self, synthetic_dataset, temp_dir):
        """Test that existing files are skipped without --force."""
        input_dir, wav_path, original_audio, sr, n_channels = synthetic_dataset
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        script_path = Path(__file__).parent.parent / "scripts" / "make_degraded.py"
        
        # First run with --force
        cmd1 = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ]
        result1 = subprocess.run(cmd1, capture_output=True, text=True)
        assert result1.returncode == 0, f"First run failed: {result1.stderr}"
        
        # Get SHA256 of first run
        output_wav = output_dir / "test_clip.wav"
        sha1 = compute_sha256(str(output_wav))
        
        # Second run without --force (should skip)
        cmd2 = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir),
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        assert result2.returncode == 0, f"Second run failed: {result2.stderr}"
        
        # Check that file was not modified
        sha2 = compute_sha256(str(output_wav))
        assert sha1 == sha2, "File was modified when it should have been skipped"
        
        # But ground truth should still be copied
        gt_path = output_dir / "test_clip.gt.json"
        mtime_before = os.path.getmtime(str(gt_path))
        
        # Touch the input gt file
        input_gt = input_dir / "test_clip.gt.json"
        with open(str(input_gt), 'a') as f:
            f.write('\n')
        
        # Run again without --force
        subprocess.run(cmd2, capture_output=True, text=True)
        
        # Check that gt file was updated
        mtime_after = os.path.getmtime(str(gt_path))
        assert mtime_after >= mtime_before, "Ground truth was not copied"
    
    def test_corrupt_input_fails(self, temp_dir):
        """Test that corrupt input WAV makes script exit non-zero."""
        input_dir = temp_dir / "input"
        input_dir.mkdir()
        
        # Create a corrupt WAV file (just random bytes)
        wav_path = input_dir / "corrupt.wav"
        with open(str(wav_path), 'wb') as f:
            f.write(b'RIFF' + os.urandom(100))
        
        output_dir = temp_dir / "output"
        output_dir.mkdir()
        
        script_path = Path(__file__).parent.parent / "scripts" / "make_degraded.py"
        cmd = [
            str(Path(__file__).parent.parent / ".venv" / "bin" / "python"),
            str(script_path),
            "--input", str(input_dir),
            "--output", str(output_dir),
            "--force",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        # Should fail
        assert result.returncode != 0, "Script should have failed on corrupt input"

    def test_measure_lag_sign_convention(self):
        """Test that measure_lag sign convention is correct.
        
        measure_lag(ref, delayed) returns +k when delayed[n] == ref[n - k].
        """
        sr = 44100
        
        # Create a noise burst
        rng = np.random.default_rng(42)
        n_samples = 10000
        ref = rng.standard_normal(n_samples)
        
        # Test +441 sample delay: delayed[n] = ref[n - 441]
        delayed_pos = np.zeros(n_samples)
        delayed_pos[441:] = ref[:-441]
        
        lag_pos = measure_lag(ref, delayed_pos, sr, max_lag_seconds=0.01)
        assert lag_pos == 441, f"Expected +441, got {lag_pos}"
        
        # Test -441 sample delay: delayed[n] = ref[n + 441]
        delayed_neg = np.zeros(n_samples)
        delayed_neg[:-441] = ref[441:]
        
        lag_neg = measure_lag(ref, delayed_neg, sr, max_lag_seconds=0.01)
        assert lag_neg == -441, f"Expected -441, got {lag_neg}"
        
        # Test residual is 0 after compensation
        # For +441 case: shift delayed_pos back by 441
        compensated = delayed_pos[441:]
        ref_trimmed = ref[:-441]
        residual_lag = measure_lag(ref_trimmed, compensated, sr, max_lag_seconds=0.001)
        assert abs(residual_lag) <= 1, f"Residual lag should be ~0, got {residual_lag}"

    def test_measure_lag_performance(self):
        """Test that measure_lag on 30s signals at 44.1kHz finishes in under 5 seconds."""
        sr = 44100
        n_samples = int(30 * sr)  # 1.3M samples
        
        # Create random signals
        rng = np.random.default_rng(42)
        s1 = rng.standard_normal(n_samples)
        s2 = rng.standard_normal(n_samples)
        
        start = time.time()
        lag = measure_lag(s1, s2, sr, max_lag_seconds=0.2, window_seconds=30)
        elapsed = time.time() - start
        
        assert elapsed < 5.0, f"measure_lag took {elapsed:.2f}s (must be < 5s)"
        # Also check it returns a valid result
        assert isinstance(lag, (int, float, np.integer, np.floating))


def load_audio_info(wav_path):
    """Load audio file and return (audio, sample_rate, channels)."""
    audio, sr = sf.read(str(wav_path), dtype='float64')
    if audio.ndim == 1:
        audio = audio.reshape(-1, 1)
        channels = 1
    else:
        channels = audio.shape[1]
    return audio, sr, channels
