#!/usr/bin/env python3
"""Fetch a subset of SMD (Saarland Music Data) for evaluation.

SMD-piano_v2.zip from Zenodo record 13753319.

Selection criteria:
- Sort by file name
- Greedy pick of pieces with a new composer
- Duration between 90 and 420 seconds
- 5 pieces total
- Check that audio and MIDI of a piece are aligned (same duration)

Output:
- data/smd5/<slug>.wav (converted from mp3 if needed)
- data/smd5/<slug>.midi
- data/smd5/<slug>.gt.json
- data/smd5/manifest.json

If the set cannot be obtained without registration or does not contain aligned MIDI,
stop and report "未測定" with the reason.
"""

import os
import sys
import json
import csv
import io
import hashlib
import urllib.request
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mt.schema import save_json

# SMD Zenodo record
SMD_ZENODO_RECORD = "13753319"
SMD_ZIP_URL = f"https://zenodo.org/record/{SMD_ZENODO_RECORD}/files/SMD-piano_v2.zip?download=1"
SMD_CSV_URL = f"https://zenodo.org/record/{SMD_ZENODO_RECORD}/files/metadata.csv?download=1"


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


def download_csv() -> Optional[List[Dict]]:
    """Download and parse the SMD metadata CSV file."""
    try:
        print("Downloading SMD metadata CSV...")
        response = urllib.request.urlopen(SMD_CSV_URL, timeout=30)
        csv_data = response.read().decode('utf-8')
        
        reader = csv.DictReader(io.StringIO(csv_data))
        rows = list(reader)
        print(f"Loaded {len(rows)} rows from CSV")
        return rows
    except Exception as e:
        print(f"ERROR: Failed to download SMD CSV: {e}")
        return None


def select_smd_subset(rows: List[Dict]) -> List[Dict]:
    """Select a subset of SMD pieces.
    
    Criteria:
    - Sort by file name
    - Greedy pick by composer
    - Duration between 90 and 420 seconds
    - 5 pieces total
    
    Returns:
        List of selected rows
    """
    # Filter rows with duration in range
    # The CSV might have different column names, we need to check
    filtered_rows = []
    for row in rows:
        # Try to find duration column
        duration = None
        for key in row:
            if 'duration' in key.lower():
                try:
                    duration = float(row[key])
                    break
                except ValueError:
                    pass
        
        if duration is None:
            print(f"WARNING: Could not find duration in row: {row}")
            continue
        
        if 90 <= duration <= 420:
            filtered_rows.append(row)
    
    # Sort by filename
    # Try different column names for filename
    filename_key = None
    for key in filtered_rows[0] if filtered_rows else []:
        if 'filename' in key.lower() or 'audio' in key.lower():
            filename_key = key
            break
    
    if filename_key:
        filtered_rows.sort(key=lambda r: r.get(filename_key, ''))
    
    # Greedy pick by composer
    selected = []
    seen_composers = set()
    
    # Try different column names for composer
    composer_key = None
    for key in filtered_rows[0] if filtered_rows else []:
        if 'composer' in key.lower():
            composer_key = key
            break
    
    for row in filtered_rows:
        if not composer_key:
            break
            
        composer = row.get(composer_key, '')
        if composer in seen_composers:
            continue
        
        selected.append(row)
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
        
        print(f"  Downloading {member_name} from {zip_url}...")
        with remotezip.RemoteZip(zip_url) as rz:
            if member_name in rz.namelist():
                data = rz.read(member_name)
                with open(output_path, 'wb') as f:
                    f.write(data)
                print(f"  Saved to {output_path}")
                return True
            else:
                print(f"  WARNING: {member_name} not found in zip")
                return False
    except ImportError:
        print("  ERROR: remotezip not installed")
        return False
    except Exception as e:
        print(f"  ERROR: Failed to extract {member_name}: {e}")
        return False


def convert_mp3_to_wav(mp3_path: str, wav_path: str) -> bool:
    """Convert MP3 to WAV using ffmpeg."""
    try:
        import subprocess
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', mp3_path, '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', wav_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            print(f"  Converted {mp3_path} to {wav_path}")
            return True
        else:
            print(f"  ERROR: ffmpeg failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ERROR: Could not convert MP3: {e}")
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
            if pedal['onset'] <= note['onset'] and pedal['offset'] > max_extension:
                max_extension = pedal['offset']
        
        # Also check for next onset of same pitch
        for other_note in all_notes:
            if other_note['pitch'] == note['pitch'] and other_note['onset'] > note['onset']:
                if other_note['onset'] < max_extension:
                    max_extension = other_note['onset']
                break
        
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
    year: str,
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
            "year": year,
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
    
    # Try to download CSV first
    rows = download_csv()
    
    if rows is None:
        print("ERROR: Could not download SMD metadata")
        print("This might require registration or the URL might have changed.")
        print("未測定: SMD dataset cannot be obtained without registration")
        sys.exit(1)
    
    # Select subset
    selected_rows = select_smd_subset(rows)
    
    if not selected_rows:
        print("ERROR: No suitable rows found")
        print("未測定: No suitable SMD pieces found")
        sys.exit(1)
    
    print(f"\nSelected {len(selected_rows)} pieces:")
    for row in selected_rows:
        print(f"  {row}")
    
    # Try to extract from remote zip first
    # If that doesn't work, we'll need to download the full zip
    
    # For now, let's try remotezip
    manifest = []
    
    # We need to know the structure of the zip file
    # Let's try to list the contents
    try:
        import remotezip
        print("\nTrying to list SMD zip contents...")
        with remotezip.RemoteZip(args.zip_url) as rz:
            namelist = rz.namelist()
            print(f"Found {len(namelist)} files in zip")
            # Print first 20 files
            for name in namelist[:20]:
                print(f"  {name}")
    except Exception as e:
        print(f"ERROR: Could not list SMD zip: {e}")
        print("This might mean Range requests are not supported.")
        print("未測定: SMD dataset cannot be obtained without downloading full zip")
        sys.exit(1)
    
    # For now, we'll report as 未測定 since we need to understand the structure
    print("\n未測定: SMD dataset structure needs to be verified")
    print("The script needs to be updated with the correct file paths in the SMD zip.")


if __name__ == "__main__":
    main()
