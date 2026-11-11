#!/usr/bin/env python3
"""Command-line interface for music transcription.

Usage:
    uv run python -m mt.cli transcribe <in.wav> --backend naive --bpm 120 -o <outdir>
"""

import os
import sys
import argparse
from pathlib import Path

# Import from mt package
from mt.backends import run_backend
from mt.score_naive import score_notes


def main():
    parser = argparse.ArgumentParser(description="Music Transcription CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Transcribe command
    transcribe_parser = subparsers.add_parser("transcribe", help="Transcribe audio to sheet music")
    transcribe_parser.add_argument("input_wav", type=str, help="Input WAV file")
    transcribe_parser.add_argument("--backend", type=str, default="naive", 
                                   help="Backend to use (default: naive)")
    transcribe_parser.add_argument("--bpm", type=float, default=120.0,
                                   help="BPM for quantization (default: 120)")
    transcribe_parser.add_argument("-o", "--output", type=str, required=True,
                                   help="Output directory")
    transcribe_parser.add_argument("--hand-split", type=int, default=60,
                                   help="MIDI pitch to split hands (default: 60 = C4)")
    
    args = parser.parse_args()
    
    if args.command == "transcribe":
        transcribe(args)
    else:
        parser.print_help()
        sys.exit(1)


def transcribe(args):
    """Transcribe audio to sheet music."""
    input_wav = args.input_wav
    backend = args.backend
    bpm = args.bpm
    output_dir = args.output
    hand_split = args.hand_split
    
    print(f"Transcribing {input_wav} with backend {backend}...")
    
    # Create output directory
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate temporary JSON output path
    tmp_json = os.path.join(output_dir, "tmp_notes.json")
    
    # Run backend
    print(f"Running backend {backend}...")
    wall_time, peak_rss = run_backend(backend, input_wav, tmp_json)
    print(f"Backend completed in {wall_time:.2f}s, peak RSS: {peak_rss/1024:.1f} MB")
    
    # Score the notes
    print(f"Scoring notes with BPM {bpm}...")
    output_files = score_notes(
        tmp_json,
        output_dir,
        bpm=bpm,
        hand_split_pitch=hand_split,
    )
    
    # Clean up temporary file
    if os.path.exists(tmp_json):
        os.remove(tmp_json)
    
    print(f"\nOutput files:")
    for name, path in output_files.items():
        if path:
            print(f"  {name}: {path}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
