"""Posting ledger: append-only jsonl of posts and metrics, plus a feedback
summary that turns views/retention into hints for the next prompt.

ledger.jsonl lives at the repo root (gitignored — it's personal data).
"""

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

LEDGER_PATH = Path(__file__).resolve().parent.parent / "ledger.jsonl"


def _append(entry: Dict[str, Any], path: Optional[str] = None) -> Path:
    p = Path(path) if path else LEDGER_PATH
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return p


def _load(path: Optional[str] = None) -> List[Dict[str, Any]]:
    p = Path(path) if path else LEDGER_PATH
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def record_post(song_dir: str, url: str, platform: str = "youtube",
                path: Optional[str] = None) -> Path:
    return _append({
        "kind": "post",
        "date": datetime.date.today().isoformat(),
        "song": Path(song_dir).name,
        "url": url,
        "platform": platform,
    }, path)


def record_stats(song_dir: str, views: int, retention: Optional[float] = None,
                 likes: Optional[int] = None, path: Optional[str] = None) -> Path:
    return _append({
        "kind": "stats",
        "date": datetime.date.today().isoformat(),
        "song": Path(song_dir).name,
        "views": views,
        "retention": retention,
        "likes": likes,
    }, path)


def feedback(path: Optional[str] = None) -> str:
    """Aggregate the ledger into 'hints for the next song'."""
    entries = _load(path)
    stats = [e for e in entries if e.get("kind") == "stats"]
    posts = {e["song"]: e for e in entries if e.get("kind") == "post"}
    if not stats:
        return "ledger is empty — post a song and record stats first"

    by_song: Dict[str, List[Dict[str, Any]]] = {}
    for e in stats:
        by_song.setdefault(e["song"], []).append(e)

    lines = ["# feedback", ""]
    best_song, best_ret = None, -1.0
    for song, rows in sorted(by_song.items()):
        views = max(r["views"] for r in rows)
        rets = [r["retention"] for r in rows if r.get("retention") is not None]
        ret = max(rets) if rets else None
        url = posts.get(song, {}).get("url", "")
        lines.append(
            f"- {song}: views={views}"
            + (f" retention={ret:.1f}%" if ret is not None else "")
            + (f" {url}" if url else ""))
        if ret is not None and ret > best_ret:
            best_song, best_ret = song, ret

    lines.append("")
    if best_song:
        lines.append(
            f"best retention: {best_song} ({best_ret:.1f}%) "
            "— reuse its style/mood for the next prompt")
    return "\n".join(lines)
