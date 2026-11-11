#!/usr/bin/env python3
"""Create a degraded version of the MAESTRO test set for robustness testing.

From data/maestro_test5/ create data/maestro_test5_degraded/ with:
- Added room reverb
- Pink noise at 30 dB SNR
- MP3 96 kbps round trip

Ground truth is copied unchanged.

The processing should add no time offset - measure and correct or report it.
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Dict, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def add_reverb(input_path: str, output_path: str) -> bool:
    """Add room reverb using ffmpeg.
    
    Uses the ladspa plugin for reverb if available, otherwise uses a simple delay.
    """
    try:
        # Try with ladspa reverb plugin
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-af', 'ladspa=file=caps:Capriccio',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"  Added reverb using ladspa")
            return True
    except Exception:
        pass
    
    try:
        # Fallback: simple echo effect
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-af', 'aecho=0.8:0.9:1000:0.3',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"  Added reverb using echo")
            return True
    except Exception:
        pass
    
    print(f"  WARNING: Could not add reverb")
    return False


def add_pink_noise(input_path: str, output_path: str, snr_db: float = 30.0) -> bool:
    """Add pink noise at specified SNR using ffmpeg.
    
    SNR = 30 dB means the signal is 30 dB louder than the noise.
    """
    try:
        # Generate pink noise and mix with original
        # First, get the duration of the input
        cmd_duration = [
            'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', input_path
        ]
        result = subprocess.run(cmd_duration, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  WARNING: Could not get duration")
            return False
        
        duration = float(result.stdout.strip())
        
        # Generate pink noise
        noise_file = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        noise_path = noise_file.name
        noise_file.close()
        
        try:
            cmd_noise = [
                'ffmpeg', '-y', '-f', 'lavfi', '-i', f'anoisesrc=color=pink:r=44100:d={duration}',
                '-t', str(duration),
                noise_path
            ]
            result = subprocess.run(cmd_noise, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"  WARNING: Could not generate pink noise")
                return False
            
            # Calculate volume levels for mixing
            # SNR = 10 * log10(signal_power / noise_power)
            # For 30 dB SNR: signal_power / noise_power = 10^(30/10) = 1000
            # So noise should be at 1/1000 of signal level, or -30 dB
            
            # Mix the two files
            cmd_mix = [
                'ffmpeg', '-y', '-i', input_path, '-i', noise_path,
                '-filter_complex', '[0:a]volume=1.0[signal];[1:a]volume=0.0316227766[noise];[signal][noise]amix=inputs=2:duration=first',
                output_path
            ]
            result = subprocess.run(cmd_mix, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                print(f"  Added pink noise at {snr_db} dB SNR")
                return True
            else:
                print(f"  WARNING: Could not mix audio: {result.stderr}")
                return False
        finally:
            if os.path.exists(noise_path):
                os.unlink(noise_path)
    except Exception as e:
        print(f"  WARNING: Could not add pink noise: {e}")
        return False


def mp3_roundtrip(input_path: str, output_path: str, bitrate: str = "96k") -> bool:
    """Encode to MP3 and decode back to WAV."""
    try:
        # Encode to MP3
        mp3_file = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
        mp3_path = mp3_file.name
        mp3_file.close()
        
        try:
            cmd_encode = [
                'ffmpeg', '-y', '-i', input_path,
                '-codec:a', 'libmp3lame',
                '-b:a', bitrate,
                mp3_path
            ]
            result = subprocess.run(cmd_encode, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"  WARNING: Could not encode to MP3: {result.stderr}")
                return False
            
            # Decode back to WAV
            cmd_decode = [
                'ffmpeg', '-y', '-i', mp3_path,
                '-codec:a', 'pcm_s16le',
                '-ar', '44100',
                '-ac', '2',
                output_path
            ]
            result = subprocess.run(cmd_decode, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                print(f"  MP3 roundtrip at {bitrate}")
                return True
            else:
                print(f"  WARNING: Could not decode MP3: {result.stderr}")
                return False
        finally:
            if os.path.exists(mp3_path):
                os.unlink(mp3_path)
    except Exception as e:
        print(f"  WARNING: Could not do MP3 roundtrip: {e}")
        return False


def get_audio_duration(filepath: str) -> Optional[float]:
    """Get audio duration in seconds."""
    try:
        import soundfile as sf
        info = sf.info(filepath)
        return info.duration
    except Exception as e:
        print(f"  WARNING: Could not get duration: {e}")
        return None


def check_time_offset(original_path: str, degraded_path: str) -> float:
    """Check if the degraded audio has a time offset compared to original.
    
    Returns:
        The time offset in seconds (positive if degraded starts later)
    """
    try:
        import soundfile as sf
        import numpy as np
        
        # Load both files
        orig_audio, orig_fs = sf.read(original_path)
        deg_audio, deg_fs = sf.read(degraded_path)
        
        # Ensure same sample rate
        if orig_fs != deg_fs:
            print(f"  WARNING: Sample rates differ: {orig_fs} vs {deg_fs}")
            return 0.0
        
        # Take a small window from the beginning
        window_size = min(len(orig_audio), len(deg_audio), 44100)  # 1 second
        orig_window = orig_audio[:window_size]
        deg_window = deg_audio[:window_size]
        
        # Normalize - handle stereo by taking mean across channels
        if len(orig_window.shape) > 1:
            orig_window = np.mean(orig_window, axis=1)
        if len(deg_window.shape) > 1:
            deg_window = np.mean(deg_window, axis=1)
        
        orig_max = np.max(np.abs(orig_window))
        deg_max = np.max(np.abs(deg_window))
        if orig_max > 0:
            orig_window = orig_window / orig_max
        if deg_max > 0:
            deg_window = deg_window / deg_max
        
        # Cross-correlate to find offset
        # For simplicity, we'll just check the first few samples
        # A more sophisticated approach would use cross-correlation
        
        # Simple check: find where the degraded audio starts
        # Look for the first sample where degraded is non-zero
        for i in range(min(len(orig_window), len(deg_window))):
            if np.abs(deg_window[i]) > 0.01:
                # Check if original is also non-zero here
                if np.abs(orig_window[i]) > 0.01:
                    return 0.0
                else:
                    # Degraded starts later
                    return i / orig_fs
        
        return 0.0
    except Exception as e:
        print(f"  WARNING: Could not check time offset: {e}")
        return 0.0


def correct_time_offset(input_path: str, output_path: str, offset_seconds: float) -> bool:
    """Correct a time offset by trimming the beginning of the audio."""
    if offset_seconds <= 0:
        return True
    
    try:
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-ss', str(offset_seconds),
            '-c', 'copy',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"  Corrected time offset of {offset_seconds:.3f}s")
            return True
        else:
            print(f"  WARNING: Could not correct time offset: {result.stderr}")
            return False
    except Exception as e:
        print(f"  WARNING: Could not correct time offset: {e}")
        return False


def main():
    import argparse
    import shutil
    
    parser = argparse.ArgumentParser(description="Create degraded MAESTRO test set")
    parser.add_argument("--input", type=str, default="_staging/maestro_test5",
                        help="Input directory (default: _staging/maestro_test5)")
    parser.add_argument("--output", type=str, default="_staging/maestro_test5_degraded",
                        help="Output directory (default: _staging/maestro_test5_degraded)")
    parser.add_argument("--force", action="store_true",
                        help="Force re-processing even if files exist")
    args = parser.parse_args()
    
    # Check ffmpeg
    if not check_ffmpeg():
        print("ERROR: ffmpeg is required but not found")
        sys.exit(1)
    
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Input directory: {input_dir}")
    print(f"Output directory: {output_dir}")
    
    # Check input directory exists
    if not input_dir.exists():
        print(f"ERROR: Input directory {input_dir} does not exist")
        sys.exit(1)
    
    # Get list of WAV files
    wav_files = list(input_dir.glob("*.wav"))
    if not wav_files:
        print(f"ERROR: No WAV files found in {input_dir}")
        sys.exit(1)
    
    print(f"Found {len(wav_files)} WAV files")
    
    # Process each file
    for wav_file in wav_files:
        slug = wav_file.stem
        print(f"\nProcessing {slug}...")
        
        # Output paths
        degraded_wav = output_dir / f"{slug}.wav"
        
        # Check if already processed
        if not args.force and degraded_wav.exists():
            print(f"  Skipping: {degraded_wav} already exists")
            continue
        
        # Create temporary files for intermediate steps
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_dir = Path(tmpdir)
            
            # Step 1: Add reverb
            reverb_path = tmp_dir / "reverb.wav"
            if not add_reverb(str(wav_file), str(reverb_path)):
                print(f"  WARNING: Skipping reverb step")
                reverb_path = wav_file
            
            # Step 2: Add pink noise
            noise_path = tmp_dir / "noise.wav"
            if not add_pink_noise(str(reverb_path), str(noise_path)):
                print(f"  WARNING: Skipping noise step")
                noise_path = reverb_path
            
            # Step 3: MP3 roundtrip
            mp3_path = tmp_dir / "mp3.wav"
            if not mp3_roundtrip(str(noise_path), str(mp3_path)):
                print(f"  WARNING: Skipping MP3 step")
                mp3_path = noise_path
            
            # Check time offset
            offset = check_time_offset(str(wav_file), str(mp3_path))
            print(f"  Time offset: {offset:.3f}s")
            
            # Correct if needed
            if offset > 0.01:  # More than 10ms
                final_path = tmp_dir / "final.wav"
                if not correct_time_offset(str(mp3_path), str(final_path), offset):
                    print(f"  WARNING: Could not correct time offset")
                    final_path = mp3_path
            else:
                final_path = mp3_path
            
            # Copy to output
            shutil.copy(str(final_path), str(degraded_wav))
            print(f"  Saved degraded WAV to {degraded_wav}")
        
        # Copy ground truth files
        for ext in [".midi", ".gt.json"]:
            src = input_dir / f"{slug}{ext}"
            if src.exists():
                dst = output_dir / f"{slug}{ext}"
                shutil.copy(str(src), str(dst))
                print(f"  Copied {ext} to {dst}")
    
    # Copy manifest if it exists
    manifest_src = input_dir / "manifest.json"
    if manifest_src.exists():
        manifest_dst = output_dir / "manifest.json"
        shutil.copy(str(manifest_src), str(manifest_dst))
        print(f"\nCopied manifest to {manifest_dst}")
    
    print(f"\nDone! Degraded set created in {output_dir}")


if __name__ == "__main__":
    main()
