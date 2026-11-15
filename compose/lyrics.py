"""Lyrics form: write freely, the form checks only two things — line length
and end-rhyme (last-mora vowel). Sections are ordered サビ -> Aメロ -> Bメロ.

`compose lyrics-init` writes the template; `compose lyrics-check` reports
each line's char count and trailing vowel, flagging lines outside the
style's lyric_line_range.
"""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from compose.validate import split_mora

LYRICS_TEMPLATE = """# 歌詞

## サビ
(先にサビを書く。1行 {lo}〜{hi} 文字目安)

## Aメロ

## Bメロ

## サビ (くり返し)

"""

# last kana -> vowel (あ/か/さ... = a, etc.). Katakana maps via -0x60.
_VOWEL_TABLE = {}
_GROUPS = {
    "a": "あかさたなはまやらわがざだばぱいきしちにひみりぎじぢびぴいうくすつぬふむゆるぐずづぶぷうえけせてねへめれげぜでべぺえおこそとのほもよろをごぞどぼぽおんっー",
}
# build explicit table: あ行->a, い段->i, う段->u, え段->e, お段->o, ん->n
for _vowel, _chars in {
    "a": "あかさたなはまやらわがざだばぱ",
    "i": "いきしちにひみりぎじぢびぴ",
    "u": "うくすつぬふむゆるぐずづぶぷ",
    "e": "えけせてねへめれげぜでべぺ",
    "o": "おこそとのほもよろをごぞどぼぽ",
    "n": "ん",
    "": "っー",
}.items():
    for _c in _chars:
        _VOWEL_TABLE[_c] = _vowel


def _katakana_to_hiragana(ch: str) -> str:
    o = ord(ch)
    if 0x30A1 <= o <= 0x30F6:
        return chr(o - 0x60)
    return ch


def line_vowel(line: str) -> Optional[str]:
    """Vowel of the line's final mora (a/i/u/e/o/n), or None if unknown."""
    text = re.sub(r"[\s、。!?！?…・~〜]", "", line)
    if not text:
        return None
    morae = split_mora(text)
    last = _katakana_to_hiragana(morae[-1][-1])
    return _VOWEL_TABLE.get(last)


def line_length(line: str) -> int:
    """Char count ignoring whitespace and punctuation."""
    return len(re.sub(r"[\s、。!?！?…・~〜]", "", line))


def check_lyrics(
    path: str,
    line_range: Tuple[int, int] = (4, 16),
) -> Tuple[List[Dict[str, Any]], str]:
    """Check a lyrics file. Returns (rows, report_text)."""
    rows: List[Dict[str, Any]] = []
    section = "(no section)"
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            section = line.lstrip("#").strip()
            continue
        if line.startswith("(") and line.endswith(")"):
            continue
        length = line_length(line)
        vowel = line_vowel(line)
        flag = ""
        if not (line_range[0] <= length <= line_range[1]):
            flag = f"  <- outside {line_range[0]}..{line_range[1]} chars"
        rows.append({
            "section": section, "line": line,
            "length": length, "vowel": vowel or "?",
        })

    lines = []
    cur = None
    for r in rows:
        if r["section"] != cur:
            cur = r["section"]
            lines.append(f"\n[{cur}]")
        warn = ""
        if not (line_range[0] <= r["length"] <= line_range[1]):
            warn = f"  <- outside {line_range[0]}..{line_range[1]}"
        lines.append(f"  {r['length']:3d}字 韻:{r['vowel']}  {r['line']}{warn}")

    # rhyme summary per section
    lines.append("\n-- rhyme map --")
    cur = None
    vowels: List[str] = []
    for r in rows:
        if r["section"] != cur:
            if cur is not None:
                lines.append(f"  [{cur}] {' '.join(vowels)}")
            cur = r["section"]
            vowels = []
        vowels.append(r["vowel"])
    if cur is not None:
        lines.append(f"  [{cur}] {' '.join(vowels)}")

    return rows, "\n".join(lines)


def init_lyrics(song_dir: str, line_range: Tuple[int, int] = (4, 16)) -> Path:
    path = Path(song_dir) / "lyrics.md"
    if not path.exists():
        path.write_text(
            LYRICS_TEMPLATE.format(lo=line_range[0], hi=line_range[1]),
            encoding="utf-8")
    return path
