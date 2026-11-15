"""Compose harness: memo -> style -> DSL -> validate -> score/video/pack.

Pipeline (the reverse direction of the transcription side):
  songs/<date>-<slug>/memo.md      fixed-format input memo
  song.yaml / song.json            DSL source of truth (key/bpm/chords/bars)
  -> validator                     mechanical checks + autofix
  -> compiler                      notes JSON -> MIDI + MusicXML + WAV
  -> lyrics/video/pack/ledger      telop video, posting pack, metrics ledger
"""

__version__ = "0.1.0"
