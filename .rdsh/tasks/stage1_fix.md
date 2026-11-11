# Stage 1 fix: the first attempt did not meet the brief

Working directory: `/Users/eightman/dev/tools/music-transcription`. Read `.rdsh/tasks/stage1.md` (the original brief), then the
current code. A review of the first attempt found the problems below. Fix all of them.

## Environment (already prepared for you, do not rebuild)

- `.venv` is now Python 3.11 with the core dependencies installed. Run everything with `.venv/bin/python` (e.g. `.venv/bin/python -m pytest -q`).
- `UV_CACHE_DIR` points to `./.uv-cache`, so `uv` works inside the sandbox if you need it.
- Other agents may be working in `backends/basic_pitch`, `backends/kong`, `backends/transkun`. Do not touch those directories.

## Hard rules

- No sudo, no credentials. Work only inside this directory.
- Do not invent numbers. Do not weaken a test to make it pass. If a target cannot be reached, leave the strict test in place
  (failing) and report the real numbers.

## Problems to fix

### 1. Synthetic generator (`scripts/make_test_wav.py`) does not match the brief

It currently produces sequential pure sine tones. Replace it with exactly this (deterministic, no randomness):

- Mono, 44100 Hz, BPM 120 (one beat = 0.5 s). Total length = 12 beats + 0.5 s of silence = 6.5 s.
- Timbre of one note with fundamental f0: partials k = 1..6 at k*f0, amplitude 1/k, each with decay `exp(-t / (1.2 / k))`
  (t in seconds from the onset), 5 ms linear attack, 30 ms linear release ending exactly at the note offset,
  whole note scaled by velocity/127. Sum all notes, then peak-normalise the clip to 0.8.
- Notes (MIDI pitch, onset beat, duration in beats, velocity): 16 notes in total.
  - Chords, 3.5 beats long, velocity 80: beat 0: 48, 52, 55 (C3 E3 G3); beat 4: 53, 57, 60 (F3 A3 C4); beat 8: 55, 59, 62 (G3 B3 D4).
  - Melody, 0.9 beats long, velocity 100: beat 1: 69, beat 2: 62, beat 3: 81, beat 5: 74, beat 6: 67, beat 9: 76, beat 10: 69.
  (The melody pitches were chosen so that none of them equals, or is a semitone away from, the 2nd / 3rd / 4th harmonic of a chord
  tone sounding at the same time. Do not change the note list.)
- Writes `out/synth/test.wav` and `out/synth/test.gt.json` (ground truth = the list above converted to seconds).

### 2. Naive detector (`backends/naive/run.py`) reaches only F1 0.062

A 16384-sample window was used for both pitch and onset timing, so onsets are off by 70-100 ms. Use two resolutions.
Recommended design (you may deviate if you measure something better, but keep the same stages):

- Pitch salience: STFT with Hann window 8192, hop 441 (10 ms). For each MIDI pitch p in 36..96, `S[p, t]` = the maximum magnitude
  among the bins within +-0.3 semitone of the fundamental of p.
- Activity: a pitch is active in a frame when `S[p, t]` is above a threshold relative to the global maximum (start around -35 dB and tune).
- Harmonic suppression: p is not a note in frame t when one of p-12, p-19, p-24 (the pitch whose 2nd / 3rd / 4th harmonic is p)
  is active in that frame and stronger than p.
- Semitone-neighbour suppression: p is not a note in frame t when p-1 or p+1 has a larger salience (spectral leakage).
- Tracking: a note is a run of active frames of at least 80 ms; merge gaps shorter than 30 ms.
- Onset refinement: a second STFT with Hann window 1024, hop 220 (5 ms); onset strength = half-wave-rectified spectral flux;
  pick its peaks; move each note onset to the nearest flux peak within +-150 ms (the long window makes the raw onset early).
- Offset: correct the bias introduced by the long window; report what accuracy you get.
- Velocity: a monotonic mapping of the note's peak salience to 1-127.

Target: on the new synthetic clip, precision 1.0 and recall 1.0 (16/16) with the onset-only metric at 50 ms tolerance.
Report the onset+offset metric as measured (no target).

### 3. `tests/test_synthetic.py` was weakened to "metrics >= 0.0"

Restore the strict assertion: onset-only precision == 1.0 and recall == 1.0 for the naive backend on the synthetic clip.
Also assert that the ground truth has exactly 16 notes and contains simultaneous notes (maximum polyphony >= 4).

### 4. `mt/backends.py`

- Peak RSS is wrong (the table shows 291888 MB). Start the child with `subprocess.Popen` and reap it with `os.wait4(pid, 0)`
  to get that child's own `ru_maxrss`; on macOS the unit is bytes, on Linux kilobytes. Return megabytes.
- Resolve paths from the repository root (`Path(__file__).resolve().parents[1]`), not from the current working directory.
- Discover backends automatically: every `backends/<name>/run.py` is a backend called `<name>`. Remove the manual registry.
- When the child exits non-zero, raise an error that includes the last lines of its stderr.

### 5. `scripts/eval_detect.py`

- `--dataset` accepts `synth` or a directory path containing `<name>.wav` + `<name>.gt.json` pairs.
- A backend failure on one clip is recorded in the table / JSON as a failure with the error message; the run continues.
- The table shows the number of estimated and reference notes in separate, labelled columns, and peak RSS in MB.
- The JSON output of a backend may contain an optional `meta` object (`device`, `package`, `version`); add it to `mt/schema.py`
  as optional and show device / version in the result files when present.

### 6. Repository hygiene

- `.gitignore`: do NOT ignore `results/` (result tables are tracked). Do ignore `tmp/`, `.uv-cache/`, `backends/*/.uv_cache/`, `uv.lock` stays tracked.
  Keep ignoring `data`, `out/`, `.venv/`, `backends/*/.venv/`, `.rdsh/logs/`.
- Delete the stray `tmp/` directory.
- README: remove the statement that Python 3.15 is used; the project uses Python 3.11 via `uv venv --python 3.11 .venv`.
  State clearly that the naive backend and the generator are re-implementations, not the original prototype.

## Done means

- `.venv/bin/python -m pytest -q` passes with the strict synthetic test in place (or the strict test fails and you report why).
- `.venv/bin/python scripts/eval_detect.py --dataset synth --backends naive` prints the table; `results/detect_synth.md` and `.json` are updated and tracked.
- Commit with Conventional Commits messages. Stage only files you changed (do not `git add -A`; never add anything under `backends/basic_pitch`, `backends/kong`, `backends/transkun`, `.rdsh/logs`, `data`).

## Final report (print at the end)

The pytest summary line, the evaluation table, the per-note onset errors (max absolute error in ms), what failed or is unverified,
and every deviation from this brief.
