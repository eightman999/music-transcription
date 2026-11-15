"""LLM prompt builder: the instruction sheet that makes a model emit the DSL.

The prompt pins everything the validator enforces, so the LLM output is
checkable and fixable rather than free-form MusicXML.
"""

from typing import Any, Dict

PROMPT_TEMPLATE = """\
あなたは作曲アシスタントです。下記の仕様に **厳密に** 従い、曲を DSL (YAML) で出力してください。
MusicXML は書かないでください。YAML コードブロック 1 つだけを出力します。

# 曲の条件 (固定済み — 変えないこと)
- key: {key}
- bpm: {bpm}
- 拍子: {time_sig} (各小節の len 合計は必ず {beats_per_bar} にする)
- 歌える音域 (vocal_range): {vocal_lo}〜{vocal_hi} (MIDI {vocal_lo_midi}〜{vocal_hi_midi})
- 構成: {sections}
- コード進行 (小節ごと): {chords}
- サビの小節は音を高め・密度を上げて盛り上げる

# 素材 (メモより)
- 気分: {mood}
- 刺さった一言: {phrase}
- 場面: {scene}
- NGワード (歌詞に使わない): {ng_words}

# DSL フォーマット
```yaml
meta:
  title: "曲タイトル"
  style: "{style}"
key: "{key}"
bpm: {bpm}
time: "{time_sig}"
vocal_range: [{vocal_lo_midi}, {vocal_hi_midi}]
sections:
{sections_yaml}
bars:
  - chord: "C"                    # その小節のコード名
    notes:
      - {{pitch: "E4", len: 1.0, lyric: "き"}}   # pitch は音名かMIDI値
      - {{rest: true, len: 0.5}}                  # 休符
      - {{pitch: "G4", len: 0.5, lyric: "み"}}    # len は拍数 (4分=1.0)
```

# 機械検証ルール (違反は自動修正 or エラーになります)
1. 各小節の len 合計 == {beats_per_bar}
2. メロディは vocal_range 内に収める
3. 各小節の 1 拍目と 3 拍目に始まる音はコード構成音にする (強拍のぶつかりは修正対象)
4. lyric は 1 音符につき 1 モーラ (「きゃ」は 1、「きょう」は 3)
5. bars の数 == sections の bars 合計 == {total_bars} 小節
6. 歌詞は素材から連想して書く。サビ → Aメロ → Bメロ の順に内容を決めるのが推奨

# 出力
- YAML 1 ブロックのみ。説明文は不要。
"""


def build_prompt(doc_or_style: Dict[str, Any], memo: Dict[str, Any]) -> str:
    """Render the LLM instruction sheet from a style preset (+ memo)."""
    st = doc_or_style
    bpb = int(st.get("beats_per_bar", 4))
    sections = st.get("sections", [])
    total = sum(int(s.get("bars", 0)) for s in sections)
    vr = st.get("vocal_range", [55, 79])
    from compose.dsl import midi_to_name

    return PROMPT_TEMPLATE.format(
        key=st["key"],
        bpm=st["bpm"],
        time_sig=f"{bpb}/4",
        beats_per_bar=bpb,
        vocal_lo=midi_to_name(vr[0]),
        vocal_hi=midi_to_name(vr[1]),
        vocal_lo_midi=vr[0],
        vocal_hi_midi=vr[1],
        sections=" / ".join(f"{s.get('name')}:{s.get('bars')}小節" for s in sections),
        sections_yaml="\n".join(
            f"  - {{name: {s.get('name')}, bars: {s.get('bars')}}}" for s in sections),
        chords="-".join(st.get("chords", [])),
        style=st.get("name", ""),
        mood=memo.get("mood", ""),
        phrase=memo.get("phrase", ""),
        scene=memo.get("scene", ""),
        ng_words=", ".join(memo.get("ng_words", [])) or "(なし)",
        total_bars=total,
    )
