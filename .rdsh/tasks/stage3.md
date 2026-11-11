# Stage 3: real-recording evaluation sets and the backend comparison

Working directory: `/Users/eightman/dev/tools/music-transcription`. Read `README.md`, `PLAN.md` (Japanese; sections 3.3, 3.4, 4.3-4.6),
`mt/`, `scripts/eval_detect.py` and each `backends/*/NOTES.md` first.

## Hard rules

- No sudo. Never type or print credentials. If something asks for a login or registration, stop that item and report it.
- Do not invent numbers. Every number in a result file or in the report must come from a command run in this session.
  Anything not measured is written as "未測定".
- Data goes only under `data/` (a symlink to a shared data directory). Before downloading, run `df -h ~` and keep the total
  you add in this stage under 5 GB. Never download `maestro-v3.0.0.zip` as a whole (it is 108 GB).
- Datasets are CC BY-NC-SA: evaluation use only. Never add audio / MIDI from them to git. Do not change `.gitignore` to allow it.
- Do not edit the backends' `run.py` to improve their scores. If a backend crashes on a real file, report the error; a minimal
  robustness fix (e.g. resampling, stereo to mono) is allowed and must be listed in the report.

## 0. Known defects in `scripts/eval_detect.py` / `mt/backends.py` to fix first

Reproduce each with `.venv/bin/python scripts/eval_detect.py --dataset data/sanity --backends naive,basic_pitch,transkun`
(`data/sanity/` holds one real clip with ground truth), fix, and add a test for each (use a tiny temporary dataset built in the test,
with the naive backend only).

1. A dataset given as a path crashes at the end: the result file name is built from the raw path
   (`results/detect_data/sanity.md`). Use the directory's base name (`results/detect_sanity.md`).
2. The "mean" row averages over all rows of all backends. It must be one mean row **per backend** (mean over that backend's clips).
3. `mt/backends.py` has a tangle of fallbacks for peak RSS (psutil, RUSAGE_CHILDREN). Keep exactly one mechanism:
   `subprocess.Popen` + `os.wait4(pid, 0)`, bytes on macOS and kilobytes on Linux, returned in MB.
4. `backends/basic_pitch/run.py` writes notes in reverse time order: every backend's notes must be sorted by (onset, pitch)
   — enforce this once in the harness after loading rather than in each backend.

## Environment notes

- Run everything with `.venv/bin/python` (Python 3.11). `UV_CACHE_DIR` is set, so `uv pip install --python .venv/bin/python <pkg>` works;
  add new core dependencies to `pyproject.toml` as well.
- The sandbox allows writes only inside the working directory. `./data` is a symlink that points outside: **you can read it but not
  write to it.** Therefore every fetch / generate script takes `--out <dir>`; while developing and testing, write to `_staging/<set>/`
  (add `_staging/` to `.gitignore`) and run the evaluations on `_staging/<set>`. The operator will re-run the scripts with
  `--out data/<set>` afterwards. Wherever this brief says `data/<set>`, use `_staging/<set>` for your own runs.
- Shell commands may run up to 15 minutes. Start long downloads so that they can resume (skip files that already exist with the right size).

## A. MAESTRO v3 test subset (in-distribution)

- Official base URL: `https://storage.googleapis.com/magentadata/datasets/maestro/v3.0.0/` (`maestro-v3.0.0.csv`, `maestro-v3.0.0.zip`).
  The server supports HTTP Range requests (verified). Use the `remotezip` package (add it to the core dependencies) to extract
  single members from the remote zip.
- `scripts/fetch_maestro_subset.py`: selection must be a coded, deterministic rule, not hand-picked:
  rows with `split == "test"` and `90 <= duration <= 420` seconds, sorted by `audio_filename`, greedy pick of rows whose
  composer has not been picked yet, until 5 pieces; total duration must stay <= 30 minutes.
  Assert in code that every selected row has `split == "test"` (two of the candidate models were trained on the train split).
- Output `data/maestro_test5/<slug>.wav`, `<slug>.midi`, `<slug>.gt.json` and `manifest.json`
  (composer, title, year, duration, original filenames, sha256 of the wav).
- Ground truth from MIDI: note onsets / velocities as recorded. For offsets, follow the common MAESTRO evaluation practice:
  extend a note to the sustain-pedal release (CC64 >= 64) or to the next onset of the same pitch, whichever comes first.
  Also store the pedal intervals in `pedal`. Document this choice in the README.

## B. Out-of-distribution set: SMD (Saarland Music Data)

- Zenodo record 13753319, "Saarland Music Data: MIDI-Audio Piano Music", open access, CC BY-NC-SA 3.0, one file
  `SMD-piano_v2.zip` (3.2 GB). No model here was trained on it and it is a different piano and room.
- `scripts/fetch_smd_subset.py`: try `remotezip` on the Zenodo file URL first; if Range requests do not work there, download the
  zip once into `data/_downloads/` (check free space first), extract what is needed, and delete the zip afterwards.
- Select 5 pieces by a coded rule: sort by file name, greedy pick of pieces with a new composer and duration between 90 and 420 s.
  Check that audio and MIDI of a piece are aligned (same recording, not a score MIDI): compare durations and report them.
- Output `data/smd5/` in the same layout as A (convert mp3 to wav with ffmpeg if needed).
- If this set cannot be obtained without registration or does not contain aligned MIDI, stop this item and report "未測定" with the reason.

## C. Degraded MAESTRO set (robustness only, not a substitute for B)

- `scripts/make_degraded.py`: from `data/maestro_test5/` create `data/maestro_test5_degraded/` deterministically with ffmpeg:
  added room reverb, pink noise at 30 dB SNR, and an MP3 96 kbps round trip. Ground truth is copied unchanged
  (make sure the processing adds no time offset: measure and correct or report it).

## D. Comparison

- Run `scripts/eval_detect.py` for the datasets `synth`, `data/maestro_test5`, `data/smd5`, `data/maestro_test5_degraded`
  with every backend that is installed (`naive`, `basic_pitch`, `kong`, `transkun`). Extend the script if needed so that a dataset
  can be given as a path and so that a backend failure on one clip is recorded as a failure instead of aborting the run.
- Result files `results/detect_<dataset>.md` / `.json`: per clip and mean, P / R / F1 onset-only and onset+offset,
  real-time factor, peak RSS, device, backend package version.
- Also report note velocity accuracy: add to `mt/evaluate.py` an onset+velocity metric using
  `mir_eval.transcription_velocity.precision_recall_f1_overlap` (onset tolerance 0.05, `offset_ratio=None`, default velocity tolerance 0.1)
  and show its P / R / F1 as an extra column. Velocities are compared after mir_eval's own linear rescaling, so this measures
  relative dynamics, not absolute loudness.
- `results/phase1a_summary.md` (Japanese): the mean onset F1 of every backend on every dataset in one table,
  the adoption decision according to PLAN.md 4.5 (compare on B first; if B is "未測定" the decision is "暫定採用"),
  and a list of everything that failed or is "未測定".
- Add tests that do not need the datasets or learned backends (e.g. the MIDI -> ground-truth conversion with pedal extension on a
  tiny MIDI built in the test). Dataset-dependent tests must skip when the data is absent.

## Done means

- `uv run pytest -q` passes.
- The four evaluations were run and the result files exist (or the item is recorded as "未測定" with the reason).
- One command re-runs each evaluation and reproduces the same P / R / F1.
- Changes are committed with Conventional Commits messages. No dataset file is tracked by git (`git ls-files | grep -E '\.(wav|midi?|mp3)$'` prints nothing).

## Final report (print at the end)

The summary table, the exact commands, what failed, what is "未測定", and any deviation from this brief.
