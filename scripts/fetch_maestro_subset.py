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
- Note onsets/velocities/offsets as recorded (raw key-release offsets)
- Pedal intervals are stored in the 'pedal' field.
- sustain_extended() can be used to compute pedal-extended offsets.
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
from mt.gt import midi_to_gt

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
    - Greedy pick by composer AND year (first occurrence of each composer+year combination)
    - Max 5 pieces
    - Total duration <= 1800 seconds (30 minutes)
    
    Selection rule: Sort by audio_filename, then greedily pick rows whose
    canonical_composer has not been picked yet AND whose year has not been picked yet.
    This ensures different composers AND different recording years when possible.
    
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
    
    # Greedy pick by composer AND year
    selected = []
    seen_composers = set()
    seen_years = set()
    total_duration = 0.0
    
    for row in test_rows:
        composer = row['canonical_composer']
        year = row['year']
        
        # Skip if we've already seen this composer OR this year
        if composer in seen_composers or year in seen_years:
            continue
        
        duration = float(row['duration'])
        if total_duration + duration > 1800:
            print(f"Skipping {row['audio_filename']}: would exceed 30 minute limit")
            continue
        
        selected.append(row)
        seen_composers.add(composer)
        seen_years.add(year)
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
    """Extract a single member from a remote zip file using remotezip.
    
    The member_name from the CSV is relative (e.g., '2004/...'), but in the zip
    it's stored with the prefix 'maestro-v3.0.0/'. This function handles that.
    """
    try:
        import remotezip
        
        print(f"  Downloading {member_name} from {zip_url}...")
        with remotezip.RemoteZip(zip_url) as rz:
            # The CSV has relative paths like '2004/...', but the zip has 'maestro-v3.0.0/2004/...'
            # Try both with and without the prefix
            possible_names = [
                f"maestro-v3.0.0/{member_name}",
                member_name,
            ]
            
            found = False
            for name in possible_names:
                if name in rz.namelist():
                    data = rz.read(name)
                    with open(output_path, 'wb') as f:
                        f.write(data)
                    print(f"  Saved to {output_path}")
                    found = True
                    break
            
            if not found:
                # Debug: show what's actually in the zip
                print(f"  ERROR: {member_name} not found in zip")
                print(f"  Available files matching pattern: {[n for n in rz.namelist() if member_name.split('/')[-1] in n][:5]}")
                return False
            
            return True
    except ImportError:
        print("  ERROR: remotezip not installed")
        return False
    except Exception as e:
        print(f"  ERROR: Failed to extract {member_name}: {e}")
        return False


def midi_to_ground_truth(midi_path: str) -> Tuple[List[Dict], List[Dict]]:
    """Convert MIDI file to ground truth notes with pedal extension.
    
    This function is deprecated. Use mt.gt.midi_to_gt instead.
    """
    gt = midi_to_gt(midi_path)
    return gt["notes"], gt["pedal"]




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
    gt = midi_to_gt(midi_path)
    
    gt_data = {
        "backend": "ground_truth",
        "audio": wav_path,
        "notes": gt["notes"],
        "pedal": gt["pedal"],
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
        
        # Skip download if files exist and not forcing
        if not args.force and wav_path.exists() and midi_path.exists():
            print(f"\nSkipping {slug}: files already exist")
            # Still regenerate gt.json from midi
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
            print(f"  Re-generated ground truth to {gt_json_path}")
            sha256 = compute_sha256(str(wav_path))
            manifest.append({
                "slug": slug,
                "composer": composer,
                "title": title,
                "year": year,
                "split": "test",
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
            "split": "test",
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
    
    # Exit non-zero if we didn't get all requested pieces
    if len(manifest) < len(selected_rows):
        print(f"\nERROR: Only obtained {len(manifest)}/{len(selected_rows)} pieces")
        sys.exit(1)


if __name__ == "__main__":
    main()
