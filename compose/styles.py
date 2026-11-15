"""Style presets: genre / tempo / key / progression / vocal range, fixed upfront.

Loaded from config/styles.toml. A memo's 気分 can auto-suggest a preset via
keyword matching, but the chosen style then locks key/BPM/progression so the
LLM (or drafter) only has to fill in melody + lyrics.
"""

import re
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "styles.toml"


def load_styles(config_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def get_style(name: str, config_path: Optional[str] = None) -> Dict[str, Any]:
    styles = load_styles(config_path)
    if name not in styles:
        raise KeyError(f"unknown style {name!r}; available: {', '.join(styles)}")
    return dict(styles[name], name=name)


def suggest_style(memo: Dict[str, Any], config_path: Optional[str] = None) -> Optional[str]:
    """Pick a preset by matching memo mood/scene keywords against each
    preset's `mood_keywords` list. Returns a style name or None."""
    text = " ".join(str(memo.get(k, "")) for k in ("mood", "phrase", "scene"))
    best: Optional[str] = None
    best_hits = 0
    for name, st in load_styles(config_path).items():
        hits = sum(1 for kw in st.get("mood_keywords", []) if kw and kw in text)
        if hits > best_hits:
            best, best_hits = name, hits
    return best


def format_styles(config_path: Optional[str] = None) -> str:
    """Human-readable preset list."""
    lines = []
    for name, st in load_styles(config_path).items():
        lines.append(
            f"{name:10s} {st.get('label', ''):20s} "
            f"bpm={st.get('bpm')} key={st.get('key')} "
            f"chords={'-'.join(st.get('chords', []))}")
    return "\n".join(lines)
