#!/usr/bin/env python3
"""Fetch a subset of MAESTRO v3 test split for evaluation.

Selection criteria:
- Rows with split == "test"
- Duration between 90 and 420 seconds
- Sorted by audio_filename
- Greedy pick of rows whose composer has not been picked yet
- Until 5 pieces are selected
- Total duration must stay <= 30 minutes (1800 seconds)

Output:
- data/maestro_test5/<slug>.wav
- data/maestro_test5/<slug>.midi
- data/maestro_test5/<slug>.gt.json
- data/maestro_test5/manifest.json

The slug is a sanitized version of the audio filename (without extension).

Ground truth from MIDI:
- Note onsets/velocities as recorded
- For offsets: extend a note to the sustain-pedal release (CC64 >= 64) or to the next
  onset of the same pitch, whichever comes first.
- Pedal intervals are stored in the 'pedal' field.
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

# MAESTRO v3 base URL
MAESTRO_BASE_URL = "https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/"
MAESTRO_CSV_URL = MAESTRO_BASE_URL + "maestro-v3.0.0.csv"


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


def download_csv() -> List[Dict]:
    """Download and parse the MAESTRO v3 CSV file."""
    print("Downloading MAESTRO v3 CSV...")
    response = urllib.request.urlopen(MAESTRO_CSV_URL)
    csv_data = response.read().decode('utf-8')
    
    reader = csv.DictReader(io.StringIO(csv_data))
    rows = list(reader)
    print(f"Loaded {len(rows)} rows from CSV")
    return rows


def select_test_subset(rows: List[Dict]) -> List[Dict]:
    """Select a subset of test split rows.
    
    Criteria:
    - split == "test"
    - 90 <= duration <= 420
    - Greedy pick by composer (first occurrence of each composer)
    - Max 5 pieces
    - Total duration <= 1800 seconds (30 minutes)
    
    Returns:
        List of selected rows
    """
    # Filter test split with duration in range
    test_rows = [
        row for row in rows 
        if row['split'] == 'test' and 
           90 <= float(row['duration']) <= 420
    ]
    
    # Sort by audio_filename
    test_rows.sort(key=lambda r: r['audio_filename'])
    
    # Greedy pick by composer
    selected = []
    seen_composers = set()
    total_duration = 0.0
    
    for row in test_rows:
        composer = row['canonical_composer']
        if composer in seen_composers:
            continue
        
        duration = float(row['duration'])
        if total_duration + duration > 1800:
            print(f"Skipping {row['audio_filename']}: would exceed 30 minute limit")
            continue
        
        selected.append(row)
        seen_composers.add(composer)
        total_duration += duration
        
        if len(selected) >= 5:
            break
    
    print(f"Selected {len(selected)} pieces, total duration: {total_duration:.1f}s")
    
    # Assert all selected rows have split == "test"
    for row in selected:
        assert row['split'] == 'test', f"Row {row['audio_filename']} has split {row['split']}"
    
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
                print(f"  ERROR: {member_name} not found in zip")
                return False
    except ImportError:
        print("  ERROR: remotezip not installed")
        return False
    except Exception as e:
        print(f"  ERROR: Failed to extract {member_name}: {e}")
        return False


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
    # For each note, find if it's held by pedal
    extended_notes = []
    
    for note in all_notes:
        original_offset = note['offset']
        
        # Find pedal intervals that cover this note's onset
        # A note is extended by pedal if:
        # 1. There's an active pedal at the note's onset
        # 2. The pedal is released after the note's original offset
        
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
    
    parser = argparse.ArgumentParser(description="Fetch MAESTRO v3 test subset")
    parser.add_argument("--out", type=str, default="_staging/maestro_test5",
                        help="Output directory (default: _staging/maestro_test5)")
    parser.add_argument("--zip-url", type=str, default=MAESTRO_BASE_URL + "maestro-v3.0.0.zip",
                        help="URL to MAESTRO zip file")
    parser.add_argument("--force", action="store_true",
                        help="Force re-download even if files exist")
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")
    
    # Download CSV
    rows = download_csv()
    
    # Select subset
    selected_rows = select_test_subset(rows)
    
    if not selected_rows:
        print("ERROR: No suitable rows found")
        sys.exit(1)
    
    print(f"\nSelected {len(selected_rows)} pieces:")
    for row in selected_rows:
        print(f"  {row['canonical_composer']} - {row['canonical_title']} ({row['duration']}s)")
    
    # Download and process each piece
    manifest = []
    
    for row in selected_rows:
        midi_filename = row['midi_filename']
        audio_filename = row['audio_filename']
        composer = row['canonical_composer']
        title = row['canonical_title']
        year = row['year']
        duration = float(row['duration'])
        
        # Create slug
        slug = sanitize_filename(audio_filename)
        
        # Output paths
        wav_path = output_dir / f"{slug}.wav"
        midi_path = output_dir / f"{slug}.midi"
        gt_json_path = output_dir / f"{slug}.gt.json"
        
        # Skip if files exist and not forcing
        if not args.force and wav_path.exists() and midi_path.exists() and gt_json_path.exists():
            print(f"\nSkipping {slug}: files already exist")
            # Still add to manifest
            sha256 = compute_sha256(str(wav_path))
            manifest.append({
                "slug": slug,
                "composer": composer,
                "title": title,
                "year": year,
                "duration": duration,
                "original_midi_filename": midi_filename,
                "original_audio_filename": audio_filename,
                "wav_path": str(wav_path),
                "midi_path": str(midi_path),
                "gt_json_path": str(gt_json_path),
                "sha256": sha256,
            })
            continue
        
        print(f"\nProcessing {slug}...")
        
        # Download WAV
        wav_member = f"{audio_filename}"
        if not extract_member_from_zip(args.zip_url, wav_member, str(wav_path)):
            print(f"  ERROR: Failed to download WAV")
            continue
        
        # Download MIDI
        midi_member = f"{midi_filename}"
        if not extract_member_from_zip(args.zip_url, midi_member, str(midi_path)):
            print(f"  ERROR: Failed to download MIDI")
            continue
        
        # Create ground truth JSON
        gt_data = create_ground_truth_json(
            str(wav_path),
            str(midi_path),
            composer,
            title,
            year,
            midi_filename,
            audio_filename,
        )
        save_json(gt_data, str(gt_json_path))
        print(f"  Saved ground truth to {gt_json_path}")
        
        # Compute SHA256
        sha256 = compute_sha256(str(wav_path))
        
        # Add to manifest
        manifest.append({
            "slug": slug,
            "composer": composer,
            "title": title,
            "year": year,
            "duration": duration,
            "original_midi_filename": midi_filename,
            "original_audio_filename": audio_filename,
            "wav_path": str(wav_path),
            "midi_path": str(midi_path),
            "gt_json_path": str(gt_json_path),
            "sha256": sha256,
        })
    
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


if __name__ == "__main__":
    main()
