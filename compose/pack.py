"""Posting pack: draft title / description / tags / thumbnail for a song,
plus the ledger hook that feeds stats back into the next prompt.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from compose.dsl import load_song, midi_to_name, song_path
from compose.memo import load_memo
from compose.video import FONT_PATH, HEIGHT, WIDTH

DESCRIPTION_TEMPLATE = """\
{title}

気分: {mood}
場面: {scene}

— 自動作曲パイプライン —
key: {key} / bpm: {bpm} / style: {style}
生成: DSL -> validator -> MIDI/MusicXML
歌: (Synthesizer V / NEUTRINO へ流す場合はここに記載)
"""

FIXED_TAGS = ["オリジナル曲", "DTM", "自動作曲", "instrumental"]


def title_candidates(memo: Dict[str, Any], song_title: str = "") -> List[str]:
    """Draft 3 title candidates from the memo."""
    cands = []
    phrase = memo.get("phrase", "").strip()
    scene = memo.get("scene", "").strip()
    mood = memo.get("mood", "").strip()
    if song_title:
        cands.append(song_title)
    if phrase:
        cands.append(phrase)
        if scene:
            cands.append(f"{phrase} / {scene}")
    if scene and mood:
        cands.append(f"{scene}の{mood}")
    while len(cands) < 3:
        cands.append("(untitled)")
    return cands[:3]


def build_pack(song_dir: str) -> Dict[str, str]:
    """Write pack/{title,description,tags}.txt and pack/thumbnail.png."""
    d = Path(song_dir)
    pack_dir = d / "pack"
    pack_dir.mkdir(exist_ok=True)

    memo_path = d / "memo.md"
    memo = load_memo(str(memo_path)) if memo_path.exists() else {}
    dsl = song_path(song_dir)
    doc = load_song(str(dsl)) if dsl else {}
    meta = doc.get("meta", {}) if doc else {}
    song_title = meta.get("title", "")

    cands = title_candidates(memo, song_title)
    (pack_dir / "title.txt").write_text(
        "\n".join(f"{i + 1}. {t}" for i, t in enumerate(cands)) + "\n",
        encoding="utf-8")

    desc = DESCRIPTION_TEMPLATE.format(
        title=cands[0],
        mood=memo.get("mood", ""),
        scene=memo.get("scene", ""),
        key=doc.get("key", "?"),
        bpm=doc.get("bpm", "?"),
        style=meta.get("style", "?"),
    )
    (pack_dir / "description.txt").write_text(desc, encoding="utf-8")

    tags = list(FIXED_TAGS)
    if meta.get("style"):
        tags.insert(0, meta["style"])
    if memo.get("mood"):
        tags.append(memo["mood"])
    (pack_dir / "tags.txt").write_text(", ".join(tags) + "\n", encoding="utf-8")

    thumb = pack_dir / "thumbnail.png"
    render_thumbnail(cands[0], str(thumb))

    return {
        "title": str(pack_dir / "title.txt"),
        "description": str(pack_dir / "description.txt"),
        "tags": str(pack_dir / "tags.txt"),
        "thumbnail": str(thumb),
    }


def render_thumbnail(title: str, out_path: str) -> str:
    """Simple 1920x1080 thumbnail: dark gradient + centered title."""
    img = Image.new("RGB", (WIDTH, HEIGHT), (20, 20, 40))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        r = int(20 + 40 * y / HEIGHT)
        b = int(40 + 30 * y / HEIGHT)
        draw.line([(0, y), (WIDTH, y)], fill=(r, 20, b))
    try:
        font = ImageFont.truetype(FONT_PATH, 110)
    except Exception:
        font = ImageFont.load_default()
    text = title if title != "(untitled)" else "untitled"
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x, y = (WIDTH - w) / 2, (HEIGHT - h) / 2
    for dx in (-4, 0, 4):
        for dy in (-4, 0, 4):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=(255, 255, 255))
    img.save(out_path)
    return out_path
