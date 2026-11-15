"""Song validator: mechanical checks + autofix before compiling.

LLM-written melodies break in predictable ways:
  - bar note lengths don't sum to the time signature
  - melody wanders out of the singable range
  - strong-beat notes clash with the bar's chord
  - a lyric carries more than one mora on a single note

This module flags each of those (error / warn / fixed) and can repair
the fixable ones in place (validate_song(..., fix=True)).

Rules:
  BAR_LEN      sum(len) must equal beats_per_bar.
               fix: shortfall -> append a rest; overflow -> trim/drop the tail.
  RANGE        melody pitches must be inside vocal_range.
               fix: transpose by octaves until inside; error if unreachable.
  STRONG_BEAT  notes starting on beats 0 and bpb/2 should be chord tones.
               warn when outside the chord but inside the scale,
               error when outside the scale.
               fix: move to the nearest chord tone (same octave first).
  MORA         one note carries exactly one mora of lyric.
               fix: split the note into equal-length notes, one mora each.
  BARS_COUNT   len(bars) must equal sum(sections[].bars) when sections exist.
  SCALE        non-scale tones produce a warn (chromaticism is legal-ish).
"""

from typing import Any, Dict, List, Optional

from compose.dsl import DSLError, midi_to_name, parse_chord, scale_pcs, vocal_range

SMALL_KANA = set("ゃゅょぁぃぅぇぉゎャュヨァィゥェォヮ")


def split_mora(s: str) -> List[str]:
    """Split a string into morae; small kana attach to the previous mora."""
    morae: List[str] = []
    for ch in s:
        if morae and ch in SMALL_KANA:
            morae[-1] += ch
        else:
            morae.append(ch)
    return morae


def _issue(rule: str, level: str, bar: int, note_idx: Optional[int], msg: str,
           before: Any = None, after: Any = None) -> Dict[str, Any]:
    return {
        "rule": rule, "level": level, "bar": bar, "note": note_idx,
        "msg": msg, "before": before, "after": after,
    }


def _strong_positions(beats_per_bar: int) -> List[int]:
    if beats_per_bar == 4:
        return [0, 2]
    if beats_per_bar % 2 == 0:
        return [0, beats_per_bar // 2]
    return [0]


def validate_song(doc: Dict[str, Any], fix: bool = False) -> List[Dict[str, Any]]:
    """Run all rules over a normalized DSL doc. Returns the issue list."""
    issues: List[Dict[str, Any]] = []
    bpb = doc["_beats_per_bar"]
    lo, hi = vocal_range(doc)
    scale = set(scale_pcs(doc["key"]))
    strong = _strong_positions(bpb)
    bars = doc["bars"]

    if "sections" in doc:
        declared = sum(int(s.get("bars", 0)) for s in doc["sections"])
        if declared != len(bars):
            issues.append(_issue(
                "BARS_COUNT", "error", -1, None,
                f"sections declare {declared} bars but {len(bars)} exist"))

    for i, bar in enumerate(bars):
        notes = bar["notes"]
        root_pc, chord_pcs = parse_chord(bar["chord"])

        # --- MORA (fix first so length math uses final notes) ---
        j = 0
        while j < len(notes):
            note = notes[j]
            lyric = note.get("lyric")
            if isinstance(lyric, str) and lyric.strip():
                morae = split_mora(lyric.strip())
                if len(morae) > 1:
                    if fix:
                        each = note["_beats"] / len(morae)
                        new_notes = []
                        for m in morae:
                            nn = dict(note)
                            nn["lyric"] = m
                            nn["len"] = each
                            nn["_beats"] = each
                            new_notes.append(nn)
                        notes[j:j + 1] = new_notes
                        issues.append(_issue(
                            "MORA", "fixed", i, j,
                            f"lyric {lyric!r} had {len(morae)} morae on one note",
                            before=lyric, after=morae))
                        j += len(new_notes)
                        continue
                    issues.append(_issue(
                        "MORA", "error", i, j,
                        f"lyric {lyric!r} is {len(morae)} morae; one note = one mora"))
            j += 1

        if not notes:
            issues.append(_issue("BAR_LEN", "error", i, None, "bar has no notes"))
            continue

        # --- BAR_LEN ---
        total = sum(n["_beats"] for n in notes)
        if abs(total - bpb) > 1e-6:
            if fix:
                if total < bpb:
                    notes.append({
                        "rest": True, "len": bpb - total, "_beats": bpb - total,
                        "_midi": None,
                    })
                    issues.append(_issue(
                        "BAR_LEN", "fixed", i, None,
                        f"bar length {total:.3g} < {bpb}; appended a rest",
                        before=total, after=bpb))
                else:
                    overflow = total - bpb
                    before = total
                    while overflow > 1e-6 and notes:
                        last = notes[-1]
                        if last["_beats"] <= overflow + 1e-6:
                            overflow -= last["_beats"]
                            notes.pop()
                        else:
                            last["_beats"] -= overflow
                            last["len"] = last["_beats"]
                            overflow = 0.0
                    issues.append(_issue(
                        "BAR_LEN", "fixed", i, None,
                        f"bar length {before:.3g} > {bpb}; trimmed the tail",
                        before=before, after=bpb))
            else:
                issues.append(_issue(
                    "BAR_LEN", "error", i, None,
                    f"bar length {total:.3g} beats != {bpb}"))

        # --- per-note checks ---
        pos = 0.0
        for j, note in enumerate(notes):
            midi = note["_midi"]
            if midi is not None:
                # RANGE
                if not (lo <= midi <= hi):
                    fixed_to = None
                    if fix:
                        for shift in (12, -12, 24, -24):
                            if lo <= midi + shift <= hi:
                                fixed_to = midi + shift
                                break
                    if fixed_to is not None:
                        issues.append(_issue(
                            "RANGE", "fixed", i, j,
                            f"{midi_to_name(midi)} outside vocal range "
                            f"[{midi_to_name(lo)}..{midi_to_name(hi)}]",
                            before=midi_to_name(midi), after=midi_to_name(fixed_to)))
                        note["_midi"] = fixed_to
                        note["pitch"] = midi_to_name(fixed_to)
                        midi = fixed_to
                    else:
                        issues.append(_issue(
                            "RANGE", "error", i, j,
                            f"{midi_to_name(midi)} outside vocal range "
                            f"[{midi_to_name(lo)}..{midi_to_name(hi)}]"))

                pc = midi % 12
                # SCALE
                if pc not in scale:
                    issues.append(_issue(
                        "SCALE", "warn", i, j,
                        f"{midi_to_name(midi)} is outside the key scale"))

                # STRONG_BEAT
                beat_in_bar = round(pos, 6)
                if any(abs(beat_in_bar - s) < 1e-6 for s in strong):
                    if pc not in chord_pcs:
                        if pc not in scale:
                            issues.append(_issue(
                                "STRONG_BEAT", "error", i, j,
                                f"beat {beat_in_bar:g}: {midi_to_name(midi)} "
                                f"clashes with {bar['chord']} and is off-scale"))
                        elif fix:
                            candidates = sorted(
                                chord_pcs,
                                key=lambda c: min(abs(pc - c), 12 - abs(pc - c)))
                            target_pc = candidates[0]
                            base = midi - pc
                            cand = [base + target_pc, base + target_pc - 12,
                                    base + target_pc + 12]
                            cand = [c for c in cand if lo <= c <= hi]
                            if cand:
                                new_midi = min(cand, key=lambda c: abs(c - midi))
                                issues.append(_issue(
                                    "STRONG_BEAT", "fixed", i, j,
                                    f"beat {beat_in_bar:g}: {midi_to_name(midi)} "
                                    f"-> chord tone {midi_to_name(new_midi)} "
                                    f"of {bar['chord']}",
                                    before=midi_to_name(midi),
                                    after=midi_to_name(new_midi)))
                                note["_midi"] = new_midi
                                note["pitch"] = midi_to_name(new_midi)
                            else:
                                issues.append(_issue(
                                    "STRONG_BEAT", "warn", i, j,
                                    f"beat {beat_in_bar:g}: {midi_to_name(midi)} "
                                    f"is a non-chord tone on {bar['chord']}"))
                        else:
                            issues.append(_issue(
                                "STRONG_BEAT", "warn", i, j,
                                f"beat {beat_in_bar:g}: {midi_to_name(midi)} "
                                f"is a non-chord tone on {bar['chord']}"))
            pos += note["_beats"]

    return issues


def format_report(issues: List[Dict[str, Any]]) -> str:
    """Render issues as a plain-text report."""
    if not issues:
        return "OK: no issues"
    counts = {"error": 0, "warn": 0, "fixed": 0}
    lines = []
    for it in issues:
        counts[it["level"]] += 1
        loc = f"bar {it['bar']}" + (f" note {it['note']}" if it["note"] is not None else "")
        lines.append(f"[{it['level']:5s}] {it['rule']:12s} {loc}: {it['msg']}")
    lines.append(
        f"-- {counts['error']} error(s), {counts['warn']} warning(s), "
        f"{counts['fixed']} fixed")
    return "\n".join(lines)


def has_errors(issues: List[Dict[str, Any]]) -> bool:
    return any(i["level"] == "error" for i in issues)
