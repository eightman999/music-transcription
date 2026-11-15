"""Song DSL: load/save and normalization.

The DSL is the single source of truth for a composed song. An LLM (or the
rule-based drafter) writes this; humans and the validator fix it; the
compiler turns it into notes JSON -> MIDI/MusicXML.

Format (YAML or JSON, decided by file extension):

    meta: {title: str, style: str}          # optional
    key: "C major"                          # root name + mode
    bpm: 96
    time: "4/4"                             # numerator = beats per bar
    vocal_range: [55, 79]                   # MIDI, singable limits
    sections:                               # optional; sum(bars) must match
      - {name: intro, bars: 2}
      - {name: sabi,  bars: 8}
    bars:
      - chord: "C"                          # chord name for the whole bar
        notes:
          - {pitch: "E4", len: 1.0, lyric: "き"}
          - {rest: true, len: 0.5}
          - {pitch: "G4", len: "1/2", lyric: "み"}

pitch: note name ("C4", "F#3", "Bb4"), a MIDI int, or a rest
       ({rest: true} or pitch: null / "rest").
len:   beats (float). Fraction strings like "1/2" are allowed.
lyric: exactly one mora of lyric sung on that note (checked by validator).
"""

import json
import re
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

NOTE_NAME_TO_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]


class DSLError(ValueError):
    pass


def pitch_to_midi(value: Any) -> Optional[int]:
    """Normalize a pitch spec to a MIDI number, or None for a rest."""
    if value is None:
        return None
    if isinstance(value, int):
        if not (0 <= value <= 127):
            raise DSLError(f"pitch out of range: {value}")
        return value
    if isinstance(value, str):
        s = value.strip()
        if s.lower() in ("rest", "r", ""):
            return None
        if re.fullmatch(r"-?\d+", s):
            return pitch_to_midi(int(s))
        m = re.fullmatch(r"([A-Ga-g])([#b♯♭]?)(-?\d+)", s)
        if not m:
            raise DSLError(f"unparseable pitch: {value!r}")
        name, acc, octave = m.group(1).upper(), m.group(2), int(m.group(3))
        pc = NOTE_NAME_TO_PC[name]
        if acc in ("#", "♯"):
            pc += 1
        elif acc in ("b", "♭"):
            pc -= 1
        midi = (octave + 1) * 12 + pc  # C4 = 60
        if not (0 <= midi <= 127):
            raise DSLError(f"pitch out of range: {value!r}")
        return midi
    raise DSLError(f"unparseable pitch: {value!r}")


def midi_to_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[midi % 12]}{midi // 12 - 1}"


def len_to_beats(value: Any) -> float:
    """Normalize a length spec to beats (float)."""
    if isinstance(value, (int, float)):
        beats = float(value)
    elif isinstance(value, str):
        s = value.strip()
        if "/" in s:
            beats = float(Fraction(s))
        else:
            beats = float(s)
    else:
        raise DSLError(f"unparseable len: {value!r}")
    if beats <= 0:
        raise DSLError(f"len must be positive: {value!r}")
    return beats


def parse_key(key: str) -> Tuple[int, str]:
    """Parse 'C major' / 'A minor' -> (tonic pitch class, mode)."""
    m = re.fullmatch(r"\s*([A-Ga-g])([#b♯♭]?)\s*(major|minor|maj|min|m)?\s*", key)
    if not m:
        raise DSLError(f"unparseable key: {key!r}")
    name, acc, mode = m.group(1).upper(), m.group(2), (m.group(3) or "major").lower()
    pc = NOTE_NAME_TO_PC[name]
    if acc in ("#", "♯"):
        pc += 1
    elif acc in ("b", "♭"):
        pc -= 1
    pc %= 12
    if mode in ("m", "min", "minor"):
        mode = "minor"
    elif mode in ("maj", "major"):
        mode = "major"
    else:
        raise DSLError(f"unparseable mode in key: {key!r}")
    return pc, mode


def parse_time(sig: str) -> Tuple[int, int]:
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", str(sig))
    if not m:
        raise DSLError(f"unparseable time signature: {sig!r}")
    num, den = int(m.group(1)), int(m.group(2))
    if den != 4:
        raise DSLError(f"only x/4 time supported for now: {sig!r}")
    return num, den


def scale_pcs(key: str) -> List[int]:
    """Pitch classes of the key's scale."""
    tonic, mode = parse_key(key)
    intervals = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    return [(tonic + i) % 12 for i in intervals]


# ---- chord names ---------------------------------------------------------

_CHORD_QUALITIES = {
    "": (0, 4, 7),
    "m": (0, 3, 7),
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "M7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "m7b5": (0, 3, 6, 10),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "sus4": (0, 5, 7),
    "sus2": (0, 2, 7),
    "dim": (0, 3, 6),
    "dim7": (0, 3, 6, 9),
    "aug": (0, 4, 8),
    "add9": (0, 4, 7, 14),
}


def parse_chord(name: str) -> Tuple[int, List[int]]:
    """Parse a chord name -> (root pitch class, chord pitch classes)."""
    s = str(name).strip()
    m = re.match(r"^([A-Ga-g])([#b♯♭]?)(.*)$", s)
    if not m:
        raise DSLError(f"unparseable chord: {name!r}")
    root = NOTE_NAME_TO_PC[m.group(1).upper()]
    acc = m.group(2)
    if acc in ("#", "♯"):
        root += 1
    elif acc in ("b", "♭"):
        root -= 1
    root %= 12
    quality = m.group(3).strip()
    if quality not in _CHORD_QUALITIES:
        raise DSLError(f"unsupported chord quality: {name!r}")
    return root, [(root + i) % 12 for i in _CHORD_QUALITIES[quality]]


# ---- document load/save ---------------------------------------------------

def load_song(path: str) -> Dict[str, Any]:
    """Load a DSL file (.yaml/.yml/.json) and normalize the body."""
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".json":
        doc = json.loads(text)
    else:
        doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise DSLError(f"song file must be a mapping: {path}")
    return normalize_song(doc)


def normalize_song(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Validate top-level fields and normalize notes to (midi, beats, lyric)."""
    for req in ("key", "bpm", "bars"):
        if req not in doc:
            raise DSLError(f"missing required field: {req}")

    beats_per_bar, _ = parse_time(str(doc.get("time", "4/4")))
    bars = doc["bars"]
    if not isinstance(bars, list) or not bars:
        raise DSLError("bars must be a non-empty list")

    for i, bar in enumerate(bars):
        if not isinstance(bar, dict) or "notes" not in bar:
            raise DSLError(f"bar {i}: must be a mapping with 'notes'")
        if "chord" not in bar:
            raise DSLError(f"bar {i}: missing 'chord'")
        parse_chord(bar["chord"])  # raises early on bad names
        if not isinstance(bar["notes"], list):
            raise DSLError(f"bar {i}: notes must be a list")
        for j, note in enumerate(bar["notes"]):
            if not isinstance(note, dict):
                raise DSLError(f"bar {i} note {j}: must be a mapping")
            note["_midi"] = None if note.get("rest") else pitch_to_midi(note.get("pitch"))
            note["_beats"] = len_to_beats(note.get("len", 1.0))

    doc["_beats_per_bar"] = beats_per_bar
    return doc


def save_song(doc: Dict[str, Any], path: str) -> None:
    """Save a DSL doc (internal keys stripped) as YAML or JSON."""
    clean = {k: v for k, v in doc.items() if not k.startswith("_")}
    for bar in clean.get("bars", []):
        for note in bar.get("notes", []):
            for k in [k for k in note if k.startswith("_")]:
                del note[k]
    p = Path(path)
    if p.suffix.lower() == ".json":
        p.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        p.write_text(yaml.safe_dump(clean, allow_unicode=True, sort_keys=False), encoding="utf-8")


def vocal_range(doc: Dict[str, Any]) -> Tuple[int, int]:
    """Singable range in MIDI; default roughly G3..G5."""
    vr = doc.get("vocal_range", [55, 79])
    if isinstance(vr, list) and len(vr) == 2:
        return pitch_to_midi(vr[0]), pitch_to_midi(vr[1])
    raise DSLError(f"vocal_range must be [low, high]: {vr!r}")


def song_path(song_dir: str) -> Optional[Path]:
    """Locate the DSL file in a song directory."""
    d = Path(song_dir)
    for name in ("song.yaml", "song.yml", "song.json"):
        if (d / name).exists():
            return d / name
    return None
