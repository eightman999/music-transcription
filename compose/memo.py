"""Input memo: one fixed-format sheet per song.

    # 入力メモ 2026-11-15
    - 気分: ...
    - 刺さった一言: ...
    - 場面: ...
    - NGワード: a, b

`compose new <slug>` creates songs/<date>-<slug>/memo.md; everything
downstream reads this file.
"""

import datetime
import re
from pathlib import Path
from typing import Any, Dict, Optional

MEMO_TEMPLATE = """# 入力メモ {date}
- 気分:
- 刺さった一言:
- 場面:
- NGワード:
"""

_FIELD_MAP = {
    "気分": "mood",
    "刺さった一言": "phrase",
    "場面": "scene",
    "NGワード": "ng_words",
}


def new_song_dir(slug: str, date: Optional[str] = None, root: str = "songs") -> Path:
    """Create songs/<date>-<slug>/ with the fixed-format memo."""
    date = date or datetime.date.today().isoformat()
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", slug).strip("-") or "untitled"
    d = Path(root) / f"{date}-{slug}"
    d.mkdir(parents=True, exist_ok=True)
    memo = d / "memo.md"
    if not memo.exists():
        memo.write_text(MEMO_TEMPLATE.format(date=date), encoding="utf-8")
    return d


def load_memo(path: str) -> Dict[str, Any]:
    """Parse a memo file into {mood, phrase, scene, ng_words}."""
    memo: Dict[str, Any] = {"mood": "", "phrase": "", "scene": "", "ng_words": []}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*-\s*(.+?)\s*[:：]\s*(.*)$", line)
        if not m:
            continue
        label, value = m.group(1).strip(), m.group(2).strip()
        key = _FIELD_MAP.get(label)
        if key == "ng_words":
            memo[key] = [w for w in re.split(r"[,、\s]+", value) if w]
        elif key:
            memo[key] = value
    return memo
