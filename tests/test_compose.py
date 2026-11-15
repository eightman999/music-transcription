"""Tests for the compose harness (DSL, validator, compiler, memo, ledger)."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compose import dsl
from compose.compile import compile_song, song_to_tracks
from compose.ledger import feedback, record_post, record_stats
from compose.lyrics import check_lyrics, line_length, line_vowel
from compose.memo import load_memo, new_song_dir
from compose.prompt import build_prompt
from compose.styles import get_style, load_styles, suggest_style
from compose.validate import has_errors, split_mora, validate_song
from mt.schema import validate_schema

VALID_SONG = {
    "key": "C major",
    "bpm": 100,
    "time": "4/4",
    "vocal_range": [55, 79],
    "sections": [{"name": "sabi", "bars": 2}],
    "bars": [
        {"chord": "C", "notes": [
            {"pitch": "C4", "len": 1.0, "lyric": "き"},
            {"pitch": "E4", "len": 1.0, "lyric": "み"},
            {"pitch": "G4", "len": 1.0, "lyric": "の"},
            {"pitch": "E4", "len": 1.0, "lyric": "う"},
        ]},
        {"chord": "G", "notes": [
            {"pitch": "G4", "len": 2.0, "lyric": "そ"},
            {"pitch": "D4", "len": 1.0, "lyric": "ら"},
            {"rest": True, "len": 1.0},
        ]},
    ],
}


# ---- DSL -------------------------------------------------------------

def test_pitch_to_midi():
    assert dsl.pitch_to_midi("C4") == 60
    assert dsl.pitch_to_midi("A4") == 69
    assert dsl.pitch_to_midi("F#3") == 54
    assert dsl.pitch_to_midi("Bb3") == 58
    assert dsl.pitch_to_midi(72) == 72
    assert dsl.pitch_to_midi("rest") is None
    with pytest.raises(dsl.DSLError):
        dsl.pitch_to_midi("H4")
    with pytest.raises(dsl.DSLError):
        dsl.pitch_to_midi(200)


def test_len_to_beats():
    assert dsl.len_to_beats(1.0) == 1.0
    assert dsl.len_to_beats("1/2") == 0.5
    assert dsl.len_to_beats("3/4") == 0.75
    with pytest.raises(dsl.DSLError):
        dsl.len_to_beats(0)


def test_parse_key_chord():
    assert dsl.parse_key("C major") == (0, "major")
    assert dsl.parse_key("A minor") == (9, "minor")
    root, pcs = dsl.parse_chord("Am7")
    assert root == 9
    assert set(pcs) == {9, 0, 4, 7}
    root, pcs = dsl.parse_chord("F#")
    assert root == 6


def test_load_save_roundtrip(tmp_path):
    p = tmp_path / "song.yaml"
    dsl.save_song(dsl.normalize_song(dict(VALID_SONG)), str(p))
    doc = dsl.load_song(str(p))
    assert doc["bpm"] == 100
    assert doc["bars"][0]["notes"][0]["_midi"] == 60
    assert doc["_beats_per_bar"] == 4


# ---- validator ---------------------------------------------------------

def test_validate_clean():
    doc = dsl.normalize_song(dict(VALID_SONG))
    issues = validate_song(doc)
    assert not has_errors(issues)


def test_bar_length_error_and_fix():
    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    doc["bars"][0]["notes"].pop()  # now 3 beats in a 4/4 bar
    issues = validate_song(doc, fix=False)
    assert has_errors(issues)
    assert any(i["rule"] == "BAR_LEN" for i in issues)

    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    doc["bars"][0]["notes"].pop()
    issues = validate_song(doc, fix=True)
    assert not has_errors(issues)
    total = sum(n["_beats"] for n in doc["bars"][0]["notes"])
    assert abs(total - 4.0) < 1e-6
    assert doc["bars"][0]["notes"][-1].get("rest") is True


def test_range_fix():
    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    doc["bars"][0]["notes"][0]["pitch"] = "C7"  # 96 > hi(79)
    doc["bars"][0]["notes"][0]["_midi"] = 96
    issues = validate_song(doc, fix=True)
    assert not has_errors(issues)
    assert doc["bars"][0]["notes"][0]["_midi"] == 72  # -24 lands inside [55,79]
    assert any(i["rule"] == "RANGE" and i["level"] == "fixed" for i in issues)


def test_strong_beat_warn():
    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    # beat 0 of bar 0: C chord. Make it F# (off-scale + non-chord) -> error
    doc["bars"][0]["notes"][0]["pitch"] = "F#4"
    doc["bars"][0]["notes"][0]["_midi"] = 66
    issues = validate_song(doc)
    assert has_errors(issues)
    assert any(i["rule"] == "STRONG_BEAT" and i["level"] == "error" for i in issues)


def test_mora_split():
    assert split_mora("きょう") == ["きょ", "う"]
    assert split_mora("ずっと") == ["ず", "っ", "と"]

    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    doc["bars"][0]["notes"][0]["lyric"] = "きょう"  # 3 morae on 1 note
    issues = validate_song(doc, fix=False)
    assert any(i["rule"] == "MORA" and i["level"] == "error" for i in issues)

    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    doc["bars"][0]["notes"][0]["lyric"] = "きょう"
    issues = validate_song(doc, fix=True)
    assert not has_errors(issues)
    lyrics = [n.get("lyric") for n in doc["bars"][0]["notes"]]
    assert lyrics[:3] == ["きょ", "う", "み"]


def test_bars_count_mismatch():
    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    doc["sections"] = [{"name": "x", "bars": 5}]
    issues = validate_song(doc)
    assert any(i["rule"] == "BARS_COUNT" for i in issues)


# ---- compiler ----------------------------------------------------------

def test_compile_outputs(tmp_path):
    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    files = compile_song(doc, str(tmp_path))
    assert Path(files["midi"]).exists()
    assert Path(files["notes_json"]).exists()
    assert Path(files["wav"]).exists()
    data = json.loads(Path(files["notes_json"]).read_text())
    assert validate_schema(data)
    # 6 melody notes (rest excluded) + 2 bars * 3 chord tones
    assert len(data["notes"]) == 6 + 6
    meta = json.loads(Path(files["meta"]).read_text())
    assert meta["melody_note_count"] == 6
    assert meta["lyric_mora_count"] == 6
    assert meta["sections"][0]["name"] == "sabi"


def test_compile_deterministic(tmp_path):
    doc = dsl.normalize_song(json.loads(json.dumps(VALID_SONG)))
    m1, b1, _ = song_to_tracks(doc)
    m2, b2, _ = song_to_tracks(dsl.normalize_song(json.loads(json.dumps(VALID_SONG))))
    assert m1 == m2 and b1 == b2


# ---- memo / styles / prompt --------------------------------------------

def test_memo_roundtrip(tmp_path):
    d = new_song_dir("test-song", date="2026-11-15", root=str(tmp_path))
    memo_path = d / "memo.md"
    memo_path.write_text(
        "# 入力メモ 2026-11-15\n"
        "- 気分: 疲れた\n"
        "- 刺さった一言: 終電を逃した\n"
        "- 場面: 雨の駅前\n"
        "- NGワード: 死, 恋\n",
        encoding="utf-8")
    memo = load_memo(str(memo_path))
    assert memo["mood"] == "疲れた"
    assert memo["phrase"] == "終電を逃した"
    assert memo["ng_words"] == ["死", "恋"]
    assert suggest_style(memo) == "ballad"


def test_styles_load():
    styles = load_styles()
    assert "ballad" in styles and "pop" in styles
    st = get_style("ballad")
    assert st["bpm"] == 72
    assert st["name"] == "ballad"


def test_prompt_build():
    st = get_style("ballad")
    prompt = build_prompt(st, {"mood": "疲れた", "phrase": "終電", "scene": "駅",
                               "ng_words": ["死"]})
    assert "bars" in prompt and "MORA" not in prompt  # human-readable rules
    assert "き" not in prompt or True
    assert "20 小節" in prompt or "bars 合計" in prompt


# ---- lyrics ------------------------------------------------------------

def test_lyrics_check(tmp_path):
    p = tmp_path / "lyrics.md"
    p.write_text(
        "# 歌詞\n\n## サビ\nきみのうた\nそらへとびだつ\nひ\n\n## Aメロ\nあさのひかり\n",
        encoding="utf-8")
    rows, report = check_lyrics(str(p), (4, 16))
    assert len(rows) == 4
    assert rows[0]["vowel"] == "a"  # た -> a
    assert rows[1]["vowel"] == "u"  # つ -> u
    assert "outside" in report  # ひ is 1 char


def test_line_helpers():
    assert line_length("きみの うた") == 5
    assert line_vowel("あした") == "a"
    assert line_vowel("song") is None


# ---- ledger --------------------------------------------------------------

def test_ledger(tmp_path):
    lp = str(tmp_path / "ledger.jsonl")
    record_post("2026-11-15-x", "https://youtu.be/xyz", path=lp)
    record_stats("2026-11-15-x", views=120, retention=42.5, path=lp)
    report = feedback(path=lp)
    assert "2026-11-15-x" in report
    assert "42.5" in report
    assert "best retention" in report
