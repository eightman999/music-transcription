#!/usr/bin/env python3
"""Compose harness CLI.

Usage:
    python -m compose.cli new <slug>                 # today's memo
    python -m compose.cli styles [--memo memo.md]    # list / suggest presets
    python -m compose.cli prompt <song_dir>          # LLM instruction sheet
    python -m compose.cli draft <song_dir> [--style ballad] [--seed N]
    python -m compose.cli check <song_dir> [--fix]   # validator
    python -m compose.cli build <song_dir>           # DSL -> MIDI/XML/WAV
    python -m compose.cli lyrics-init <song_dir>
    python -m compose.cli lyrics-check <lyrics.md>
    python -m compose.cli video <song_dir> [--bg bg.png]
    python -m compose.cli pack <song_dir>
    python -m compose.cli post <song_dir> --url URL
    python -m compose.cli stats <song_dir> --views N [--retention P]
    python -m compose.cli feedback
"""

import argparse
import sys
from pathlib import Path

from compose.dsl import DSLError, load_song, save_song, song_path
from compose.memo import load_memo, new_song_dir
from compose.styles import format_styles, get_style, suggest_style


def _load_doc(song_dir: str):
    p = song_path(song_dir)
    if p is None:
        sys.exit(f"no song.yaml/song.json in {song_dir} (run draft or prompt first)")
    return load_song(str(p)), p


def main() -> None:
    ap = argparse.ArgumentParser(prog="compose", description="Compose harness")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("new", help="create songs/<date>-<slug>/ with memo")
    p.add_argument("slug")

    p = sub.add_parser("styles", help="list presets / suggest from a memo")
    p.add_argument("--memo", help="memo.md to match against")

    p = sub.add_parser("prompt", help="emit the LLM instruction sheet")
    p.add_argument("song_dir")
    p.add_argument("--style", help="style preset name (default: suggest or ballad)")

    p = sub.add_parser("draft", help="rule-based DSL scaffold")
    p.add_argument("song_dir")
    p.add_argument("--style")
    p.add_argument("--seed", type=int)

    p = sub.add_parser("check", help="validate the DSL")
    p.add_argument("song_dir")
    p.add_argument("--fix", action="store_true", help="autofix in place")

    p = sub.add_parser("build", help="compile DSL to MIDI/MusicXML/WAV")
    p.add_argument("song_dir")
    p.add_argument("--no-audio", action="store_true")

    p = sub.add_parser("lyrics-init", help="write lyrics.md template")
    p.add_argument("song_dir")

    p = sub.add_parser("lyrics-check", help="line-length + rhyme report")
    p.add_argument("lyrics_md")
    p.add_argument("--range", nargs=2, type=int, default=[4, 16],
                   metavar=("MIN", "MAX"))

    p = sub.add_parser("video", help="assemble telop video")
    p.add_argument("song_dir")
    p.add_argument("--bg", help="background image or loop video")
    p.add_argument("-o", "--output")

    p = sub.add_parser("pack", help="posting pack drafts + thumbnail")
    p.add_argument("song_dir")

    p = sub.add_parser("post", help="record a post in the ledger")
    p.add_argument("song_dir")
    p.add_argument("--url", required=True)
    p.add_argument("--platform", default="youtube")

    p = sub.add_parser("stats", help="record views/retention")
    p.add_argument("song_dir")
    p.add_argument("--views", type=int, required=True)
    p.add_argument("--retention", type=float)
    p.add_argument("--likes", type=int)

    sub.add_parser("feedback", help="ledger -> hints for next prompt")

    args = ap.parse_args()
    if args.cmd is None:
        ap.print_help()
        sys.exit(1)

    if args.cmd == "new":
        d = new_song_dir(args.slug)
        print(f"created {d}/memo.md — fill in 気分/刺さった一言/場面/NGワード")

    elif args.cmd == "styles":
        if args.memo:
            memo = load_memo(args.memo)
            pick = suggest_style(memo)
            print(f"suggested: {pick or '(no match — pick manually)'}")
        print(format_styles())

    elif args.cmd == "prompt":
        from compose.prompt import build_prompt

        memo_path = Path(args.song_dir) / "memo.md"
        memo = load_memo(str(memo_path)) if memo_path.exists() else {}
        style_name = args.style or suggest_style(memo) or "ballad"
        print(build_prompt(get_style(style_name), memo))

    elif args.cmd == "draft":
        from compose.draft import draft_song, write_draft

        memo_path = Path(args.song_dir) / "memo.md"
        memo = load_memo(str(memo_path)) if memo_path.exists() else {}
        style_name = args.style or suggest_style(memo) or "ballad"
        doc = draft_song(get_style(style_name), slug=Path(args.song_dir).name,
                         seed=args.seed)
        path = write_draft(doc, args.song_dir)
        print(f"wrote {path} (style={style_name}) — run `check` then `build`")

    elif args.cmd == "check":
        from compose.validate import format_report, has_errors, validate_song

        doc, path = _load_doc(args.song_dir)
        issues = validate_song(doc, fix=args.fix)
        print(format_report(issues))
        if args.fix:
            save_song(doc, str(path))
            print(f"-- fixed doc saved to {path}")
        sys.exit(1 if has_errors(issues) else 0)

    elif args.cmd == "build":
        from compose.compile import compile_song
        from compose.validate import format_report, has_errors, validate_song

        doc, path = _load_doc(args.song_dir)
        issues = validate_song(doc, fix=True)
        report = format_report(issues)
        if issues:
            print(report)
        if has_errors(issues):
            save_song(doc, str(path))
            sys.exit("errors remain after autofix; DSL saved, fix by hand")
        if any(i["level"] == "fixed" for i in issues):
            save_song(doc, str(path))
            print(f"-- autofixed DSL saved to {path}")
        files = compile_song(doc, args.song_dir, render_audio=not args.no_audio)
        for k, v in files.items():
            if v:
                print(f"  {k}: {v}")

    elif args.cmd == "lyrics-init":
        from compose.lyrics import init_lyrics

        print(f"wrote {init_lyrics(args.song_dir)}")

    elif args.cmd == "lyrics-check":
        from compose.lyrics import check_lyrics

        _, report = check_lyrics(args.lyrics_md, tuple(args.range))
        print(report)

    elif args.cmd == "video":
        from compose.video import build_video

        print(build_video(args.song_dir, bg=args.bg, out_path=args.output))

    elif args.cmd == "pack":
        from compose.pack import build_pack

        for k, v in build_pack(args.song_dir).items():
            print(f"  {k}: {v}")

    elif args.cmd == "post":
        from compose.ledger import record_post

        print(f"recorded: {record_post(args.song_dir, args.url, args.platform)}")

    elif args.cmd == "stats":
        from compose.ledger import record_stats

        print(f"recorded: {record_stats(args.song_dir, args.views, args.retention, args.likes)}")

    elif args.cmd == "feedback":
        from compose.ledger import feedback

        print(feedback())


if __name__ == "__main__":
    main()
