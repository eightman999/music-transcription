"""Rule-based DSL drafter: fills a style skeleton with a seeded melody.

`compose draft` writes song.yaml with chords/sections taken from the style
preset and a random-walk melody (no lyrics). It exists so that:
  - the pipeline smokes end-to-end without an LLM
  - an LLM gets a concrete scaffold to rewrite instead of a blank file

Melody: scale-tone random walk biased toward chord tones on strong beats,
seeded deterministically from the song slug + date.
"""

import hashlib
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

from compose.dsl import MAJOR_SCALE, MINOR_SCALE, parse_chord, parse_key


def _scale_midis(key: str, lo: int, hi: int) -> List[int]:
    tonic, mode = parse_key(key)
    intervals = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    out = []
    for midi in range(lo, hi + 1):
        if (midi - tonic) % 12 in intervals:
            out.append(midi)
    return out


def _seed_for(slug: str, extra: Optional[int] = None) -> int:
    h = hashlib.sha256(f"{slug}:{extra if extra is not None else ''}".encode())
    return int.from_bytes(h.digest()[:8], "big")


def draft_song(
    style: Dict[str, Any],
    slug: str = "song",
    seed: Optional[int] = None,
    title: str = "",
) -> Dict[str, Any]:
    """Generate a DSL doc from a style preset."""
    rng = random.Random(_seed_for(slug, seed))
    chords: List[str] = list(style["chords"])
    sections = [dict(s) for s in style["sections"]]
    total_bars = sum(int(s["bars"]) for s in sections)
    bpb = int(style.get("beats_per_bar", 4))
    lo, hi = style.get("vocal_range", [55, 79])
    density = float(style.get("density", 0.6))          # prob. an 8th slot sounds
    scale = _scale_midis(style["key"], lo, hi)
    tonic_pc, _ = parse_key(style["key"])

    # mark sabi bars for register/density boost
    sabi_bars = set()
    idx = 0
    for s in sections:
        if str(s.get("name", "")).lower() in ("sabi", "chorus", "サビ"):
            sabi_bars.update(range(idx, idx + int(s["bars"])))
        idx += int(s["bars"])

    bars = []
    pos = len(scale) // 2
    for i in range(total_bars):
        chord_name = chords[i % len(chords)]
        _, chord_pcs = parse_chord(chord_name)
        is_sabi = i in sabi_bars
        notes = []
        slot = 0.5
        n_slots = int(bpb / slot)
        for k in range(n_slots):
            strong = k * slot in (0.0, bpb / 2)
            sound = rng.random() < (density * (1.3 if is_sabi else 1.0)) or strong
            if not sound:
                if notes and notes[-1]["_midi"] is not None:
                    notes[-1]["len"] += slot
                    notes[-1]["_beats"] += slot
                else:
                    notes.append({"rest": True, "len": slot, "_beats": slot,
                                  "_midi": None})
                continue
            # random walk on the scale; land on chord tones at strong beats
            pos += rng.choice([-2, -1, -1, 0, 1, 1, 2])
            pos = max(0, min(len(scale) - 1, pos))
            midi = scale[pos]
            if is_sabi and midi + 12 <= hi:
                midi += 12
            if strong and (midi % 12) not in chord_pcs:
                nearest = min(
                    range(max(lo, midi - 4), min(hi, midi + 4) + 1),
                    key=lambda m: (0 if (m % 12) in chord_pcs else 1, abs(m - midi)))
                midi = nearest
            notes.append({"pitch": midi, "len": slot, "_beats": slot,
                          "_midi": midi, "velocity": 96 if is_sabi else 88})
        bars.append({"chord": chord_name, "notes": notes})

    return {
        "meta": {"title": title or slug, "style": style.get("name", "")},
        "key": style["key"],
        "bpm": style["bpm"],
        "time": f"{bpb}/4",
        "vocal_range": [lo, hi],
        "accompaniment": style.get("accompaniment", "block"),
        "sections": sections,
        "bars": bars,
    }


def write_draft(doc: Dict[str, Any], song_dir: str) -> Path:
    """Serialize a drafted DSL doc as YAML (internal keys stripped)."""
    from compose.dsl import save_song

    clean = {
        k: v for k, v in doc.items() if not k.startswith("_")
    }
    for bar in clean["bars"]:
        for note in bar["notes"]:
            for k in [k for k in note if k.startswith("_")]:
                del note[k]
    path = Path(song_dir) / "song.yaml"
    save_song(clean, str(path))
    return path
