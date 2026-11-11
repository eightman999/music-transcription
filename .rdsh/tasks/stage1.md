# Stage 1: scaffold, naive backend, synthetic test, evaluation harness

You are implementing Phase 1a (first part) of the plan in `PLAN.md` (Japanese; read sections 3, 4 and 9 first).
Working directory: `/Users/eightman/dev/tools/music-transcription`. Work only inside it.

## Hard rules

- No sudo. Never type or print credentials. If something asks for a password, stop and report.
- Do not touch any other repository or directory. `./data` is a symlink to a shared data directory: do not write to it in this stage.
- Do not invent numbers. Every number in your final report must come from a command you ran in this session.
- The original prototype (`transcribe.py`, `make_test_wav.py`) is NOT available on this machine. You re-implement it from the description below. Say so in the README.

## Environment

- macOS, Apple Silicon. The default `python3` is 3.15 and must NOT be used.
- Use `uv`. Create the core environment with `uv venv --python 3.11 .venv` and a `pyproject.toml`
  (core deps: numpy, scipy, soundfile, mir_eval, pretty_midi, music21, pytest). Run things with `uv run`.

## Deliverables

1. `git init` (if not already a repo), `.gitignore` covering `.venv/`, `backends/*/.venv/`, `data`, `out/`, `.rdsh/logs/`, `__pycache__/`, `*.wav` under `out/`.
2. Package `mt/`:
   - `mt/schema.py`: load / save / validate the note-event JSON. Schema:
     `{"backend": str, "audio": str, "notes": [{"pitch": int (MIDI), "onset": float sec, "offset": float sec, "velocity": int 1-127}], "pedal": [{"onset": float, "offset": float}] (optional)}`.
     Ground-truth files use the same schema.
   - `mt/backends.py`: a registry `name -> command` and `run_backend(name, wav_path, out_json)` that runs the backend as a
     **separate process** (`<python> backends/<name>/run.py <in.wav> <out.json>`), and returns wall time and peak RSS of the child.
     The python for a backend is `backends/<name>/.venv/bin/python` if it exists, otherwise the core `.venv`.
   - `mt/evaluate.py`: note-level metrics with `mir_eval.transcription.precision_recall_f1_overlap`
     (pitches converted to Hz). Report two settings: onset-only (`onset_tolerance=0.05, offset_ratio=None`)
     and onset+offset (`onset_tolerance=0.05, offset_ratio=0.2, offset_min_tolerance=0.05`).
   - `mt/score_naive.py`: fixed-BPM grid quantisation of note events, then MIDI (pretty_midi) and MusicXML (music21) output,
     splitting hands at C4 (two staves). This is the baseline for later stages; keep it simple.
3. `backends/naive/run.py`: the naive detector, a CLI `run.py <in.wav> <out.json>`:
   STFT -> per-MIDI-pitch fundamental energy -> harmonic suppression (a pitch is suppressed when it is explained as the
   2nd/3rd/4th harmonic of a stronger lower pitch) -> semitone-neighbour suppression -> onset / sustain tracking -> note events.
   It may only import numpy / scipy / soundfile and `mt.schema`.
4. `scripts/make_test_wav.py`: generates a piano-like synthetic test clip (additive synthesis with several decaying harmonics):
   C, F, G major chords plus a melody, **exactly 16 notes in total**, fixed BPM 120, mono 44.1 kHz or 22.05 kHz.
   Writes `out/synth/test.wav` and the ground truth `out/synth/test.gt.json` (same schema). Deterministic (no randomness, or fixed seed).
5. `scripts/eval_detect.py --dataset synth --backends naive`: runs each backend on each clip of the dataset, evaluates,
   prints a Markdown table (per clip and mean: P / R / F1 onset-only, P / R / F1 onset+offset, real-time factor, peak RSS MB)
   and writes `results/detect_<dataset>.md` and `results/detect_<dataset>.json`.
   Design the dataset loader so that a dataset is just a directory of `<name>.wav` + `<name>.gt.json` pairs.
6. `mt/cli.py`: `uv run python -m mt.cli transcribe <in.wav> --backend naive --bpm 120 -o <outdir>` writes
   `notes.json`, `out.mid`, `out.musicxml`.
7. `tests/` (pytest):
   - synthetic clip: the naive backend reaches precision 1.0 and recall 1.0 (16/16) at onset tolerance 50 ms.
     If you cannot reach this honestly by improving the detector, do NOT loosen the test or tune the generator to
     make it trivially easy (e.g. pure sines); report the real numbers instead.
   - evaluation sanity: identical reference and estimate give F1 = 1.0; an empty estimate gives 0.
   - schema validation rejects malformed input.
   - the MusicXML written by `mt.cli transcribe` on the synthetic clip parses with music21.
8. `README.md` (short, Japanese): what exists, how to run the tests and the evaluation.

## Done means

- `uv run pytest -q` passes.
- `uv run python scripts/eval_detect.py --dataset synth --backends naive` prints the table and writes the result files.
- Changes are committed with Conventional Commits messages (e.g. `feat: scaffold project and naive backend`).

## Final report (print at the end)

- The exact commands you ran for verification and their real output (pytest summary line, the evaluation table).
- Anything that failed, is unverified, or that you changed relative to this brief.
