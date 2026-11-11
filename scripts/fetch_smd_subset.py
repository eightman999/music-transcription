#!/usr/bin/env python3
"""Fetch a subset of SMD (Saarland Music Data) for evaluation.

SMD-piano_v2.zip from Zenodo record 13753319.

Selection criteria:
- Sort by file name
- Greedy pick of pieces with a new composer
- Duration between 90 and 420 seconds
- 5 pieces total
- Check that audio and MIDI of a piece are aligned (same recording, not a score MIDI)

Output:
- _staging/smd5/<slug>.wav (converted from wav_44100_stereo if needed)
- _staging/smd5/<slug>.midi
- _staging/smd5/<slug>.gt.json
- _staging/smd5/manifest.json

The SMD zip structure:
- midi/<basename>.mid - MIDI files
- wav_44100_stereo/<basename>.wav - WAV files at 44100 Hz stereo
- midi_wav_22050_mono/<basename>.wav - WAV files at 22050 Hz mono
- wav_22050_mono/<basename>.wav - WAV files at 22050 Hz mono
- csv/<basename>.csv - Note-level CSV data

Composer is extracted from the filename (e.g., "Bach_BWV849-01_..." -> "Bach").
Duration is extracted from the WAV file header.
"""

import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt.schema import save_json

# SMD Zenodo record
SMD_ZENODO_RECORD = "13753319"
SMD_ZIP_URL = f"https://zenodo.org/record/{SMD_ZENODO_RECORD}/files/SMD-piano_v2.zip?download=1"


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to be used as a slug."""
    # Remove path separators and extension
    basename = os.path.basename(filename)
    slug = os.path.splitext(basename)[0]
    # Replace problematic characters
    slug = slug.replace(" ", "_").replace("-", "_").replace(".", "_")
    # Remove any remaining special characters
    slug = "".join(c for c in slug if c.isalnum() or c in "_-")
    return slug


def extract_composer_from_filename(filename: str) -> str:
    """Extract composer name from SMD filename.
    
    Example: "Bach_BWV849-01_001_20090916-SMD.mid" -> "Bach"
    """
    basename = os.path.basename(filename)
    # Remove extension
    basename_no_ext = os.path.splitext(basename)[0]
    # Split by underscore and take the first part
    parts = basename_no_ext.split("_")
    if parts:
        # Handle special cases like "Rachmaninoff" vs "Rachmaninov"
        composer = parts[0]
        # Normalize known variations
        if composer == "Rachmaninov":
            return "Sergei Rachmaninoff"
        return composer
    return "Unknown"


def get_wav_duration_from_remote(zip_url: str, wav_member: str, rz=None) -> Optional[float]:
    """Get WAV duration by estimating from file size.
    
    For wav_44100_stereo WAV files: 44100 Hz * 2 channels * 16 bits = 176400 bytes/second
    Subtract 44 bytes for the WAV header.
    """
    try:
        import remotezip
        
        if rz is None:
            with remotezip.RemoteZip(zip_url) as rz:
                return get_wav_duration_from_remote(zip_url, wav_member, rz)
        
        if wav_member not in rz.namelist():
            return None
        
        # Get file size from zip info
        file_size = rz.getinfo(wav_member).file_size
        
        # For wav_44100_stereo: 44100 Hz, 2 channels, 16 bits = 176400 bytes/second
        # Subtract 44 bytes for WAV header
        data_size = file_size - 44
        bytes_per_second = 44100 * 2 * 2  # 176400
        
        if bytes_per_second > 0 and data_size > 0:
            duration = data_size / bytes_per_second
            return duration
        
        return None
    except Exception as e:
        print(f"  WARNING: Could not get duration for {wav_member}: {e}")
        return None


def list_smd_pieces(zip_url: str) -> List[Dict]:
    """List all SMD pieces with their metadata.
    
    Uses remotezip to list files and get sizes.
    
    Returns:
        List of dicts with filename, composer, duration
    """
    try:
        import remotezip
        
        print("Listing SMD pieces using remotezip...")
        with remotezip.RemoteZip(zip_url) as rz:
            namelist = rz.namelist()
            
            # Get all WAV files from wav_44100_stereo
            wav_files = [n for n in namelist if n.startswith('wav_44100_stereo/') and n.endswith('.wav')]
            
            # Get all MIDI files from midi/
            midi_files = [n for n in namelist if n.startswith('midi/') and n.endswith('.mid')]
            
            print(f"Found {len(wav_files)} WAV files and {len(midi_files)} MIDI files")
            
            # Build a set of MIDI basenames for quick lookup
            midi_basenames = set()
            for midi_file in midi_files:
                basename = os.path.basename(midi_file)
                base_no_ext = os.path.splitext(basename)[0]
                midi_basenames.add(base_no_ext)
            
            # Build a mapping from basename to WAV file info
            pieces = []
            for wav_file in wav_files:
                basename = os.path.basename(wav_file)
                base_no_ext = os.path.splitext(basename)[0]
                
                # Check if corresponding MIDI file exists
                if base_no_ext not in midi_basenames:
                    print(f"  WARNING: No MIDI file for {wav_file}")
                    continue
                
                # Get file size to estimate duration - do this lazily only when needed
                # For now, just store the wav_file and we'll get the size later when selecting
                # Extract composer
                composer = extract_composer_from_filename(wav_file)
                
                pieces.append({
                    'filename': base_no_ext,
                    'wav_path': wav_file,
                    'midi_path': f'midi/{base_no_ext}.mid',
                    'composer': composer,
                    'duration': None,  # Will be filled in later
                })
            
            print(f"Found {len(pieces)} valid pieces with both WAV and MIDI")
            return pieces
    except Exception as e:
        print(f"ERROR: Failed to list SMD pieces: {e}")
        return []


def select_smd_subset(pieces: List[Dict], zip_url: str) -> List[Dict]:
    """Select a subset of SMD pieces.
    
    Criteria:
    - Sort by filename
    - Greedy pick by composer
    - Duration between 90 and 420 seconds
    - 5 pieces total
    
    Args:
        pieces: List of all pieces (without duration)
        zip_url: URL to the SMD zip file
    
    Returns:
        List of selected pieces with duration
    """
    import remotezip
    
    # First, get durations for all pieces
    print("Getting durations for all pieces...")
    try:
        with remotezip.RemoteZip(zip_url) as rz:
            for piece in pieces:
                wav_file = piece['wav_path']
                try:
                    file_size = rz.getinfo(wav_file).file_size
                    # For wav_44100_stereo: 44100 Hz, 2 channels, 16 bits = 176400 bytes/second
                    data_size = file_size - 44
                    bytes_per_second = 44100 * 2 * 2  # 176400
                    
                    if bytes_per_second > 0 and data_size > 0:
                        duration = data_size / bytes_per_second
                        piece['duration'] = duration
                    else:
                        piece['duration'] = None
                except Exception as e:
                    print(f"  WARNING: Could not get duration for {wav_file}: {e}")
                    piece['duration'] = None
    except Exception as e:
        print(f"ERROR: Failed to get durations: {e}")
        return []
    
    # Filter by duration
    filtered = [p for p in pieces if p.get('duration') is not None and 90 <= p['duration'] <= 420]
    print(f"Filtered to {len(filtered)} pieces with duration 90-420s")
    
    # Sort by filename
    filtered.sort(key=lambda p: p['filename'])
    
    # Greedy pick by composer
    selected = []
    seen_composers = set()
    
    for piece in filtered:
        composer = piece['composer']
        if composer in seen_composers:
            continue
        
        selected.append(piece)
        seen_composers.add(composer)
        
        if len(selected) >= 5:
            break
    
    print(f"Selected {len(selected)} pieces")
    return selected


def compute_sha256(filepath: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_member_from_zip(zip_url: str, member_name: str, output_path: str) -> bool:
    """Extract a single member from a remote zip file using remotezip."""
    try:
        import remotezip
        
        print(f"  Downloading {member_name}...")
        with remotezip.RemoteZip(zip_url) as rz:
            if member_name in rz.namelist():
                data = rz.read(member_name)
                with open(output_path, 'wb') as f:
                    f.write(data)
                print(f"  Saved to {output_path}")
                return True
            else:
                print(f"  ERROR: {member_name} not found in zip")
                return False
    except ImportError:
        print("  ERROR: remotezip not installed")
        return False
    except Exception as e:
        print(f"  ERROR: Failed to extract {member_name}: {e}")
        return False


def convert_wav_sample_rate(input_path: str, output_path: str, target_rate: int = 44100) -> bool:
    """Convert WAV to target sample rate using ffmpeg."""
    try:
        # Check current sample rate
        import soundfile as sf
        info = sf.info(input_path)
        current_rate = info.samplerate
        
        if current_rate == target_rate:
            # Already at target rate, just copy
            import shutil
            shutil.copy(input_path, output_path)
            return True
        
        # Convert sample rate
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-ar', str(target_rate),
            '-ac', '2',  # stereo
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"  Converted sample rate from {current_rate} to {target_rate}")
            return True
        else:
            print(f"  ERROR: ffmpeg failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ERROR: Could not convert sample rate: {e}")
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


def get_midi_duration(midi_path: str) -> Optional[float]:
    """Get MIDI duration in seconds."""
    try:
        import pretty_midi
        pm = pretty_midi.PrettyMIDI(midi_path)
        if pm.instruments:
            # Get max end time across all notes
            max_end = 0.0
            for instrument in pm.instruments:
                for note in instrument.notes:
                    if note.end > max_end:
                        max_end = note.end
            return max_end
        return 0.0
    except Exception as e:
        print(f"  WARNING: Could not get MIDI duration: {e}")
        return None


def midi_to_ground_truth(midi_path: str) -> Tuple[List[Dict], List[Dict]]:
    """Convert MIDI file to ground truth notes with pedal extension.
    
    For offsets: extend a note to the sustain-pedal release (CC64 >= 64) or to the
    next onset of the same pitch, whichever comes first.
    
    Returns:
        Tuple of (notes, pedal_intervals)
    """
    import pretty_midi
    
    # Load MIDI
    pm = pretty_midi.PrettyMIDI(midi_path)
    
    # Get all notes from all instruments
    all_notes = []
    for instrument in pm.instruments:
        for note in instrument.notes:
            all_notes.append({
                'pitch': note.pitch,
                'onset': note.start,
                'offset': note.end,
                'velocity': note.velocity,
            })
    
    # Sort notes by onset, then pitch
    all_notes.sort(key=lambda n: (n['onset'], n['pitch']))
    
    # Get pedal (sustain) events from control changes
    pedal_intervals = []
    pedal_on_times = []
    
    for instrument in pm.instruments:
        for cc in instrument.control_changes:
            if cc.number == 64:  # Sustain pedal
                if cc.value >= 64:
                    pedal_on_times.append(cc.time)
                else:
                    # Pedal off - match with most recent on
                    if pedal_on_times:
                        onset = pedal_on_times.pop()
                        pedal_intervals.append({
                            'onset': onset,
                            'offset': cc.time,
                        })
    
    # Sort pedal intervals
    pedal_intervals.sort(key=lambda p: p['onset'])
    
    # Extend note offsets based on pedal
    extended_notes = []
    
    for note in all_notes:
        original_offset = note['offset']
        
        # Find pedal intervals that cover this note's onset
        max_extension = original_offset
        
        for pedal in pedal_intervals:
            # Pedal must start before or at note onset and end after note offset
            if pedal['onset'] <= note['onset'] and pedal['offset'] > max_extension:
                max_extension = pedal['offset']
        
        # Also check for next onset of same pitch
        for other_note in all_notes:
            if other_note['pitch'] == note['pitch'] and other_note['onset'] > note['onset']:
                if other_note['onset'] < max_extension:
                    max_extension = other_note['onset']
                break  # Only need the next one
        
        extended_notes.append({
            'pitch': note['pitch'],
            'onset': note['onset'],
            'offset': max_extension,
            'velocity': note['velocity'],
        })
    
    return extended_notes, pedal_intervals


def create_ground_truth_json(
    wav_path: str,
    midi_path: str,
    composer: str,
    title: str,
    original_midi_filename: str,
    original_audio_filename: str,
) -> Dict:
    """Create ground truth JSON from MIDI file."""
    notes, pedal = midi_to_ground_truth(midi_path)
    
    gt_data = {
        "backend": "ground_truth",
        "audio": wav_path,
        "notes": notes,
        "pedal": pedal,
        "meta": {
            "composer": composer,
            "title": title,
            "original_midi_filename": original_midi_filename,
            "original_audio_filename": original_audio_filename,
        }
    }
    
    return gt_data


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Fetch SMD subset")
    parser.add_argument("--out", type=str, default="_staging/smd5",
                        help="Output directory (default: _staging/smd5)")
    parser.add_argument("--zip-url", type=str, default=SMD_ZIP_URL,
                        help="URL to SMD zip file")
    parser.add_argument("--force", action="store_true",
                        help="Force re-download even if files exist")
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    # List all pieces
    pieces = list_smd_pieces(args.zip_url)
    
    if not pieces:
        print("ERROR: Could not list SMD pieces")
        print("未測定: SMD dataset cannot be obtained")
        sys.exit(1)
    
    # Select subset
    selected_pieces = select_smd_subset(pieces, args.zip_url)
    
    if not selected_pieces:
        print("ERROR: No suitable pieces found")
        print("未測定: No suitable SMD pieces found")
        sys.exit(1)
    
    print(f"\nSelected {len(selected_pieces)} pieces:")
    for piece in selected_pieces:
        print(f"  {piece['composer']} - {piece['filename']} ({piece['duration']:.1f}s)")
    
    # Download and process each piece
    manifest = []
    success_count = 0
    
    for piece in selected_pieces:
        filename = piece['filename']
        wav_member = piece['wav_path']
        midi_member = piece['midi_path']
        composer = piece['composer']
        duration = piece['duration']
        
        # Create slug
        slug = sanitize_filename(filename)
        
        # Output paths
        wav_path = output_dir / f"{slug}.wav"
        midi_path = output_dir / f"{slug}.midi"
        gt_json_path = output_dir / f"{slug}.gt.json"
        
        # Skip if files exist and not forcing
        if not args.force and wav_path.exists() and midi_path.exists() and gt_json_path.exists():
            print(f"\nSkipping {slug}: files already exist")
            sha256 = compute_sha256(str(wav_path))
            manifest.append({
                "slug": slug,
                "composer": composer,
                "title": filename,
                "duration": duration,
                "original_midi_filename": midi_member,
                "original_audio_filename": wav_member,
                "wav_path": str(wav_path),
                "midi_path": str(midi_path),
                "gt_json_path": str(gt_json_path),
                "sha256": sha256,
            })
            success_count += 1
            continue
        
        print(f"\nProcessing {slug}...")
        
        # Download WAV
        if not extract_member_from_zip(args.zip_url, wav_member, str(wav_path)):
            print(f"  ERROR: Failed to download WAV")
            continue
        
        # Download MIDI
        if not extract_member_from_zip(args.zip_url, midi_member, str(midi_path)):
            print(f"  ERROR: Failed to download MIDI")
            continue
        
        # Convert WAV to 44100 Hz stereo if needed
        temp_wav = wav_path
        target_wav = output_dir / f"{slug}_converted.wav"
        if not convert_wav_sample_rate(str(wav_path), str(target_wav)):
            print(f"  WARNING: Could not convert WAV, using original")
            target_wav = wav_path
        else:
            # Replace the original with the converted
            os.unlink(str(wav_path))
            os.rename(str(target_wav), str(wav_path))
        
        # Check alignment: compare WAV and MIDI durations
        wav_duration = get_audio_duration(str(wav_path))
        midi_duration = get_midi_duration(str(midi_path))
        
        if wav_duration and midi_duration:
            diff = abs(wav_duration - midi_duration)
            print(f"  WAV duration: {wav_duration:.2f}s, MIDI duration: {midi_duration:.2f}s, diff: {diff:.2f}s")
            if diff > 5.0:  # More than 5 seconds difference
                print(f"  WARNING: Large duration mismatch - audio and MIDI may not be aligned")
        
        # Create ground truth JSON
        gt_data = create_ground_truth_json(
            str(wav_path),
            str(midi_path),
            composer,
            filename,
            midi_member,
            wav_member,
        )
        save_json(gt_data, str(gt_json_path))
        print(f"  Saved ground truth to {gt_json_path}")
        
        # Compute SHA256
        sha256 = compute_sha256(str(wav_path))
        
        # Add to manifest
        manifest.append({
            "slug": slug,
            "composer": composer,
            "title": filename,
            "duration": duration,
            "original_midi_filename": midi_member,
            "original_audio_filename": wav_member,
            "wav_path": str(wav_path),
            "midi_path": str(midi_path),
            "gt_json_path": str(gt_json_path),
            "sha256": sha256,
        })
        success_count += 1
    
    # Save manifest
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nSaved manifest to {manifest_path}")
    
    # Print summary
    total_duration = sum(m['duration'] for m in manifest)
    print(f"\nSummary:")
    print(f"  Total pieces: {len(manifest)}")
    print(f"  Total duration: {total_duration:.1f}s ({total_duration/60:.1f} minutes)")
    print(f"  Output directory: {output_dir}")
    
    # Exit non-zero if we didn't get all requested pieces
    if success_count < len(selected_pieces):
        print(f"\nERROR: Only obtained {success_count}/{len(selected_pieces)} pieces")
        sys.exit(1)


if __name__ == "__main__":
    main()
