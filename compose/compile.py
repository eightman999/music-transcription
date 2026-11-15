"""Compiler: validated DSL -> notes JSON -> MIDI + MusicXML + WAV + meta.

Melody becomes its own track; each bar's chord becomes a backing track
(block chord by default, 8th-note arpeggio when the style says so).
Section boundaries are exported to song.meta.json so the video step can
time lyric overlays to real note onsets.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pretty_midi
from compose.dsl import DSLError, parse_chord, parse_key, vocal_range
from mt.synth import render_to_wav


def _chord_midis(bar: Dict[str, Any], base_octave: int = 3) -> List[int]:
    """Chord tones of a bar, voiced around the given octave."""
    root_pc, pcs = parse_chord(bar["chord"])
    base = (base_octave + 1) * 12  # C3 = 48
    return sorted(base + pc for pc in pcs)


def song_to_tracks(doc: Dict[str, Any]) -> Tuple[List[Dict], List[Dict], Dict[str, Any]]:
    """DSL -> (melody_notes, backing_notes, meta). Times in seconds."""
    bpm = float(doc["bpm"])
    bpb = doc["_beats_per_bar"]
    spb = 60.0 / bpm
    style = doc.get("meta", {}).get("style", "")
    accompaniment = doc.get("accompaniment", "block")

    melody: List[Dict] = []
    backing: List[Dict] = []
    sections_meta: List[Dict] = []

    bar_index = 0
    section_iter = iter(doc.get("sections", []))
    current = next(section_iter, None)
    section_start_bar = 0

    for i, bar in enumerate(doc["bars"]):
        bar_onset = i * bpb * spb
        pos = 0.0
        for note in bar["notes"]:
            onset = bar_onset + pos * spb
            offset = onset + note["_beats"] * spb
            if note["_midi"] is not None:
                melody.append({
                    "pitch": note["_midi"],
                    "onset": round(onset, 6),
                    "offset": round(offset, 6),
                    "velocity": int(note.get("velocity", 92)),
                    **({"lyric": note["lyric"]} if note.get("lyric") else {}),
                })
            pos += note["_beats"]

        chord = _chord_midis(bar)
        if accompaniment == "arp":
            step = 0.5 * spb  # 8th notes
            n_steps = int(round(bpb * 2))
            pattern = chord + chord[::-1]
            for k in range(n_steps):
                backing.append({
                    "pitch": pattern[k % len(pattern)],
                    "onset": round(bar_onset + k * step, 6),
                    "offset": round(bar_onset + (k + 1) * step, 6),
                    "velocity": 55,
                })
        else:
            for p in chord:
                backing.append({
                    "pitch": p,
                    "onset": round(bar_onset, 6),
                    "offset": round(bar_onset + bpb * spb, 6),
                    "velocity": 50,
                })

        # section tracking
        if current is not None and i - section_start_bar >= int(current.get("bars", 0)):
            section_start_bar = i
            current = next(section_iter, None)
        if current is not None and i == section_start_bar:
            sections_meta.append({
                "name": current.get("name", f"section{len(sections_meta)}"),
                "start_bar": i,
                "start_sec": round(bar_onset, 6),
            })

    for k, s in enumerate(sections_meta):
        nxt = sections_meta[k + 1]["start_sec"] if k + 1 < len(sections_meta) else None
        s["end_sec"] = nxt if nxt is not None else round(
            len(doc["bars"]) * bpb * spb, 6)
        s["end_bar"] = (sections_meta[k + 1]["start_bar"]
                        if k + 1 < len(sections_meta) else len(doc["bars"]))

    meta = {
        "bpm": bpm,
        "key": doc["key"],
        "time": doc.get("time", "4/4"),
        "style": style,
        "sections": sections_meta,
        "total_sec": round(len(doc["bars"]) * bpb * spb, 6),
    }
    return melody, backing, meta


def _to_pretty_midi(melody: List[Dict], backing: List[Dict], bpm: float) -> pretty_midi.PrettyMIDI:
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    mel = pretty_midi.Instrument(program=0, name="melody")
    for n in melody:
        mel.notes.append(pretty_midi.Note(
            velocity=n["velocity"], pitch=n["pitch"],
            start=n["onset"], end=n["offset"]))
    pm.instruments.append(mel)
    if backing:
        ac = pretty_midi.Instrument(program=0, name="chords")
        for n in backing:
            ac.notes.append(pretty_midi.Note(
                velocity=n["velocity"], pitch=n["pitch"],
                start=n["onset"], end=n["offset"]))
        pm.instruments.append(ac)
    return pm


def _to_music21(doc: Dict[str, Any], melody: List[Dict], backing: List[Dict]):
    """Build a music21 Score: melody part (with lyrics) + chord part."""
    from music21 import chord as m21chord
    from music21 import instrument, key, meter, note, stream, tempo

    bpm = float(doc["bpm"])
    tonic_pc, mode = parse_key(doc["key"])
    key_sig = key.Key(
        key.pitch.Pitch(midi=60 + tonic_pc).name.replace("-", "b"), mode)
    time_sig = meter.TimeSignature(str(doc.get("time", "4/4")))
    mm = tempo.MetronomeMark(number=bpm)

    mel_part = stream.Part()
    mel_part.insert(0, instrument.Piano())
    mel_part.insert(0, key_sig)
    mel_part.insert(0, time_sig)
    mel_part.insert(0, mm)
    for n in melody:
        m21n = note.Note()
        m21n.pitch.midi = n["pitch"]
        m21n.offset = n["onset"] * bpm / 60.0
        m21n.duration.quarterLength = n["offset"] * bpm / 60.0 - m21n.offset
        m21n.volume.velocity = n["velocity"]
        if n.get("lyric"):
            m21n.addLyric(n["lyric"])
        mel_part.insert(m21n.offset, m21n)

    chd_part = stream.Part()
    chd_part.insert(0, instrument.Piano())
    chd_part.insert(0, key.Key(key_sig.tonic.name, mode))
    chd_part.insert(0, meter.TimeSignature(str(doc.get("time", "4/4"))))
    bpb = doc["_beats_per_bar"]
    for i, bar in enumerate(doc["bars"]):
        midis = _chord_midis(bar)
        c = m21chord.Chord(midis)
        c.offset = i * bpb
        c.duration.quarterLength = bpb
        chd_part.insert(c.offset, c)

    score = stream.Score()
    score.insert(0, mel_part)
    score.insert(0, chd_part)
    return score


def compile_song(doc: Dict[str, Any], out_dir: str, render_audio: bool = True) -> Dict[str, Any]:
    """Compile a validated DSL doc into notes.json / out.mid / out.musicxml /
    song.wav / song.meta.json inside out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    bpm = float(doc["bpm"])

    melody, backing, meta = song_to_tracks(doc)
    all_notes = sorted(
        ({k: v for k, v in n.items() if k != "lyric"} for n in melody + backing),
        key=lambda n: (n["onset"], n["pitch"]))

    notes_json = os.path.join(out_dir, "notes.json")
    with open(notes_json, "w", encoding="utf-8") as f:
        json.dump({
            "backend": "compose",
            "audio": "",
            "notes": all_notes,
            "meta": {"package": "compose", "version": "0.1.0"},
        }, f, ensure_ascii=False, indent=2)

    midi_path = os.path.join(out_dir, "out.mid")
    _to_pretty_midi(melody, backing, bpm).write(midi_path)

    musicxml_path = None
    try:
        score = _to_music21(doc, melody, backing)
        musicxml_path = os.path.join(out_dir, "out.musicxml")
        score.write("musicxml", fp=musicxml_path)
    except Exception as e:
        print(f"Warning: MusicXML generation failed: {e}")

    wav_path = None
    if render_audio:
        wav_path = os.path.join(out_dir, "song.wav")
        render_to_wav(all_notes, wav_path)

    meta_path = os.path.join(out_dir, "song.meta.json")
    meta["melody_note_count"] = len(melody)
    meta["lyric_mora_count"] = sum(1 for n in melody if n.get("lyric"))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    return {
        "notes_json": notes_json,
        "midi": midi_path,
        "musicxml": musicxml_path,
        "wav": wav_path,
        "meta": meta_path,
    }
