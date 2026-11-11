#!/usr/bin/env python3
"""Fetch SMD piano dataset subset. Zenodo 13753319, CC BY-NC-SA 3.0."""
import os, sys, json, csv, io, hashlib, argparse, shutil
from pathlib import Path
from typing import List, Tuple, Dict
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mt.schema import save_json
from mt.gt import midi_to_gt
import remotezip, soundfile as sf, pretty_midi

SMD_ZIP_URL = "https://zenodo.org/records/13753319/files/SMD-piano_v2.zip?download=1"
SMD_LICENCE = "CC BY-NC-SA 3.0"

def compute_sha256(fp):
    h = hashlib.sha256()
    with open(fp, 'rb') as f:
        while True:
            c = f.read(8192)
            if not c: break
            h.update(c)
    return h.hexdigest()

def duration_from_size(sz):
    return (sz - 44) / (44100 * 2 * 2) if sz > 44 else 0.0

def select_smd(members, n=5):
    wavs = []
    for path, sz in members:
        if path.startswith("wav_44100_stereo/") and path.endswith(".wav"):
            stem = Path(path).stem
            wavs.append((path, stem, sz, duration_from_size(sz)))
    wavs.sort(key=lambda x: x[0])
    selected, seen = [], set()
    for _, stem, _, dur in wavs:
        comp = stem.split('_')[0]
        if comp in seen or dur < 90 or dur > 420: continue
        selected.append(stem)
        seen.add(comp)
        if len(selected) >= n: break
    return selected

def parse_csv(csv_str):
    reader = csv.DictReader(io.StringIO(csv_str), delimiter=';')
    return [{'onset': float(r['Start']), 'duration': float(r['Duration']),
             'pitch': int(r['Pitch']), 'velocity': float(r['Velocity'])} for r in reader]

def check_consistency(wav_path, midi_path, csv_path):
    audio, fs_val = sf.read(wav_path)
    wav_dur = len(audio) / fs_val
    pm = pretty_midi.PrettyMIDI(midi_path)
    midi_end = pm.get_end_time()
    midi_notes = []
    for inst in pm.instruments:
        for note in inst.notes:
            midi_notes.append({'onset': note.start, 'pitch': int(note.pitch)})
    midi_notes.sort(key=lambda n: (n['onset'], n['pitch']))
    with open(csv_path, 'r') as f:
        csv_notes = parse_csv(f.read())
    csv_notes.sort(key=lambda n: (n['onset'], n['pitch']))
    if len(midi_notes) != len(csv_notes):
        raise ValueError(f"Note count mismatch: MIDI={len(midi_notes)}, CSV={len(csv_notes)}")
    max_diff = max(abs(m['onset'] - c['onset']) for m, c in zip(midi_notes, csv_notes))
    return {'csv_max_onset_diff_ms': max_diff * 1000.0, 'wav_duration': wav_dur,
            'midi_end_time': midi_end, 'num_notes': len(midi_notes)}

def download_member(rz, member, out_path, exp_size):
    out_path = Path(out_path)
    if out_path.exists() and out_path.stat().st_size == exp_size: return True
    if out_path.exists(): out_path.unlink()
    part = Path(str(out_path) + ".part")
    try:
        data = rz.read(member)
        with open(part, 'wb') as f: f.write(data)
        if part.stat().st_size == exp_size:
            part.rename(out_path)
            return True
        part.unlink()
        return False
    except Exception:
        if part.exists():
            part.unlink()
        return False

def main():
    parser = argparse.ArgumentParser(description="Fetch SMD subset")
    parser.add_argument("--out", default="_staging/smd5")
    parser.add_argument("--cache", default="data/_downloads/smd")
    parser.add_argument("--n", type=int, default=5)
    args = parser.parse_args()
    out_dir = Path(args.out)
    cache_dir = Path(args.cache)
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    expected = ["Bach_BWV849-01_001_20090916-SMD", "Bartok_SZ080-01_002_20110315-SMD",
                "Beethoven_Op027No1-02_003_20090916-SMD", "Brahms_Op010No1_003_20090916-SMD",
                "Chopin_Op010-03_007_20100611-SMD"]
    try:
        with remotezip.RemoteZip(SMD_ZIP_URL) as rz:
            members = [(i.filename, i.file_size) for i in rz.infolist()]
            selected = select_smd(members, args.n)
            if args.n == 5 and selected != expected:
                print(f"ERROR: Got {selected}, expected {expected}")
                sys.exit(1)
            manifest = []
            for stem in selected:
                print(f"Processing {stem}...")
                midi_m = f"midi/{stem}.mid"
                csv_m = f"csv/{stem}.csv"
                wav_m = f"wav_44100_stereo/{stem}.wav"
                sizes = {m: s for m, s in members}
                for m in [midi_m, csv_m, wav_m]:
                    if m not in sizes:
                        print(f"ERROR: Missing {m}")
                        sys.exit(1)
                midi_cache = cache_dir / midi_m
                csv_cache = cache_dir / csv_m
                wav_cache = cache_dir / wav_m
                for m, c, s in [(midi_m, midi_cache, sizes[midi_m]),
                                  (csv_m, csv_cache, sizes[csv_m]),
                                  (wav_m, wav_cache, sizes[wav_m])]:
                    if not download_member(rz, m, str(c), s):
                        print(f"ERROR: Failed to download {m}")
                        sys.exit(1)
                shutil.copy2(str(wav_cache), str(out_dir / f"{stem}.wav"))
                shutil.copy2(str(midi_cache), str(out_dir / f"{stem}.mid"))
                gt = midi_to_gt(str(out_dir / f"{stem}.mid"))
                save_json({"backend": "ground_truth", "audio": f"{stem}.wav",
                           "notes": gt["notes"], "pedal": gt["pedal"]},
                          str(out_dir / f"{stem}.gt.json"))
                checks = check_consistency(str(out_dir / f"{stem}.wav"),
                                           str(out_dir / f"{stem}.mid"), str(csv_cache))
                num_pedal = len(gt["pedal"])
                wav_sha = compute_sha256(str(out_dir / f"{stem}.wav"))
                composer = stem.split('_')[0]
                manifest.append({"stem": stem, "composer": composer,
                                 "duration": checks['wav_duration'], "num_notes": checks['num_notes'],
                                 "num_pedal_intervals": num_pedal, "wav_sha256": wav_sha,
                                 "csv_max_onset_diff_ms": checks['csv_max_onset_diff_ms'],
                                 "midi_end_time": checks['midi_end_time']})
                print(f"  {composer}, {checks['wav_duration']:.1f}s, {checks['num_notes']} notes")
            with open(out_dir / "manifest.json", 'w') as f:
                json.dump({"source_url": SMD_ZIP_URL, "licence": SMD_LICENCE,
                           "selection_rule": "wav_44100_stereo/*.wav sorted, duration=(sz-44)/(44100*2*2), unique composer, 90<=dur<=420, stop at n",
                           "pieces": manifest}, f, indent=2, ensure_ascii=False)
            print(f"Done. {len(manifest)} pieces, {sum(p['duration'] for p in manifest):.1f}s total")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
