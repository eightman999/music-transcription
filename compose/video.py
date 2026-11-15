"""Video assembly: background + waveform + lyric telops -> mp4 via ffmpeg.

Lyrics come straight from the DSL (one mora per note), so telop timing is
the real note onsets — no manual alignment. Each telop is a transparent
PNG rendered with Pillow; ffmpeg overlays them with enable=between(t,a,b).

Score-scroll videos need MuseScore or LilyPond (not installed); when
`mscore` exists we could add a scrolling-score track later.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from compose.dsl import load_song, song_path

WIDTH, HEIGHT = 1920, 1080
FONT_PATH = "/System/Library/Fonts/Hiragino Sans GB.ttc"
TELOP_FONT_SIZE = 80
BARS_PER_LINE = 2  # lyric telop = this many bars of lyrics joined


def lyric_lines(doc: Dict[str, Any], bars_per_line: int = BARS_PER_LINE) -> List[Dict[str, Any]]:
    """Group DSL melody lyrics into timed telop lines.

    A line starts at its first lyric-bearing note's onset and ends at the
    next line's onset (or +4s for the last line).
    """
    bpm = float(doc["bpm"])
    bpb = doc["_beats_per_bar"]
    spb = 60.0 / bpm

    lines: List[Dict[str, Any]] = []
    for g in range(0, len(doc["bars"]), bars_per_line):
        text_parts: List[str] = []
        onset = None
        for i in range(g, min(g + bars_per_line, len(doc["bars"]))):
            pos = 0.0
            for note in doc["bars"][i]["notes"]:
                lyric = (note.get("lyric") or "").strip()
                if lyric and note["_midi"] is not None:
                    if onset is None:
                        onset = (i * bpb + pos) * spb
                    text_parts.append(lyric)
                pos += note["_beats"]
        lines.append({"text": "".join(text_parts), "onset": onset})

    timed = [ln for ln in lines if ln["onset"] is not None and ln["text"]]
    for i, ln in enumerate(timed):
        nxt = timed[i + 1]["onset"] if i + 1 < len(timed) else None
        ln["end"] = nxt if nxt is not None else ln["onset"] + 4.0
    return timed


def render_telop(text: str, out_path: str) -> str:
    """Render one telop line to a transparent 1920x1080 PNG."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, TELOP_FONT_SIZE)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (WIDTH - w) / 2
    y = HEIGHT - 220
    for dx in (-3, 0, 3):
        for dy in (-3, 0, 3):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    img.save(out_path)
    return out_path


def audio_duration(wav_path: str) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", wav_path],
        capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def build_video(
    song_dir: str,
    bg: Optional[str] = None,
    out_path: Optional[str] = None,
) -> str:
    """Assemble the video for a song dir (needs song.wav + DSL file)."""
    d = Path(song_dir)
    wav = d / "song.wav"
    if not wav.exists():
        raise FileNotFoundError(f"{wav} not found; run `compose build` first")
    dsl = song_path(song_dir)
    if dsl is None:
        raise FileNotFoundError(f"no song.yaml/json in {song_dir}")
    doc = load_song(str(dsl))

    dur = audio_duration(str(wav))
    out = out_path or str(d / "video.mp4")
    lines = lyric_lines(doc)

    with tempfile.TemporaryDirectory() as tmp:
        telops = []
        for i, ln in enumerate(lines):
            p = os.path.join(tmp, f"telop_{i:03d}.png")
            render_telop(ln["text"], p)
            telops.append((p, ln["onset"], ln["end"]))

        cmd = ["ffmpeg", "-y"]
        # background
        if bg and Path(bg).suffix.lower() in (".mp4", ".mov", ".m4v"):
            cmd += ["-stream_loop", "-1", "-i", bg]
        elif bg:
            cmd += ["-loop", "1", "-i", bg]
        else:
            cmd += ["-f", "lavfi", "-i",
                    f"color=c=0x141428:s={WIDTH}x{HEIGHT}:d={dur:.3f}:r=30"]
        cmd += ["-i", str(wav)]
        for p, _, _ in telops:
            cmd += ["-i", p]

        filters = [
            f"[1:a]showwaves=s={WIDTH}x260:mode=cline:colors=0x7aa2f7:rate=30[w]",
            f"[0:v]scale={WIDTH}x{HEIGHT},setsar=1[bg]",
            f"[bg][w]overlay=0:{HEIGHT - 460}[v0]",
        ]
        prev = "v0"
        for i, (_, onset, end) in enumerate(telops):
            idx = i + 2
            cur = f"v{i + 1}"
            filters.append(
                f"[{prev}][{idx}:v]overlay=0:0:enable='between(t,{onset:.3f},{end:.3f})'[{cur}]")
            prev = cur
        cmd += ["-filter_complex", ";".join(filters),
                "-map", f"[{prev}]", "-map", "1:a",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-t", f"{dur:.3f}", out]

        subprocess.run(cmd, check=True)
    return out
