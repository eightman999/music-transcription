# Stage 2 fix: rebuild one learned backend cleanly

Working directory: `/Users/eightman/dev/tools/music-transcription`. Read `.rdsh/tasks/stage2_common.md` (the original brief; all its
rules still apply, including: edit ONLY inside `backends/<NAME>/`, no writing git commands) and the current `backends/<NAME>/`.
A review of the first attempt found the problems listed below.

## What changed in the environment

- Python 3.11 is now installed for uv. `uv venv --python 3.11 <dir>` works. The earlier excuse "3.11 is not available" no longer holds.
- `UV_CACHE_DIR` is set to a shared cache inside the workspace, so `uv pip install` works in the sandbox. Do not create your own cache directory.
- The sandbox only allows writes inside the working directory. `./data` points outside, so you cannot write there; reading works.
- Shell commands may now run up to 15 minutes.
- A real piano clip for verification exists: `data/sanity/scarlatti_k525.wav` (MAESTRO test split, 67 s, stereo 44.1 kHz) with ground truth
  `data/sanity/scarlatti_k525.gt.json` (882 notes, same schema). Do not copy it into the repository.
- The synthetic clip is being rewritten by another agent right now. Do not use `out/synth/` for verification in this task.

## Required for every backend

1. Delete `backends/<NAME>/.venv` and rebuild it only by running `bash backends/<NAME>/setup.sh`. The venv must be Python 3.11,
   created with `uv venv --python 3.11`, packages installed with `uv pip install --python <venv python>` using pinned versions.
2. No manual edits of files inside `.venv` (site-packages). If the library needs a workaround, it lives in `run.py`.
   With Python 3.11 most of the earlier workarounds should be unnecessary: remove the ones that are no longer needed.
3. No absolute paths such as `/Users/...` in `setup.sh` or `run.py`: derive paths from the script location.
4. `run.py` writes an optional `meta` object into the JSON: `{"device": "...", "package": "...", "version": "..."}` with the device that
   really ran the model.
5. Remove ad hoc files that are not deliverables (throwaway evaluation scripts, patch scripts).
6. `NOTES.md` is updated to the real state (Python version, device, what was removed).

## Verification (report real output)

- `rm -rf backends/<NAME>/.venv && bash backends/<NAME>/setup.sh && bash backends/<NAME>/setup.sh` (second run proves idempotence).
- `backends/<NAME>/.venv/bin/python --version` prints 3.11.x.
- `backends/<NAME>/.venv/bin/python backends/<NAME>/run.py data/sanity/scarlatti_k525.wav out/sanity/<NAME>.json` and its wall time.
- Evaluate against the ground truth with the core environment:
  `.venv/bin/python -c "import json; from mt.evaluate import evaluate_onset_only as f; g=json.load(open('data/sanity/scarlatti_k525.gt.json')); e=json.load(open('out/sanity/<NAME>.json')); print(len(e['notes']), f(g['notes'], e['notes'], 0.05))"`
  (adapt to the real function signature in `mt/evaluate.py`; do not edit that file).
  On this real piano clip a piano-specific model is expected to reach an onset F1 well above 0.9, and Basic Pitch clearly above the
  naive detector. A result near 0 means the audio loading (sample rate, channel layout, scaling) or the conversion is broken: find and
  fix the cause in `run.py`, do not just report it as "expected".

## Final report

Commands and real output, the device, the wall time, the onset-only P / R / F1 on the real clip, what failed or is unverified.

---

## Your backend: NAME = `transkun`

Problems found:
- The venv is Python 3.13, which forced a manual patch of `transkun/transcribe.py` inside site-packages (`audioop` is gone in 3.13).
  That patch is not applied by `setup.sh`, so the backend is not reproducible. With Python 3.11 `audioop` exists and `pydub` works:
  remove the patch (`patch_transcribe.py`) and the throwaway `eval_transkun.py`.
- `setup.sh` falls back to `python3` (3.15 on this machine) and created a private 1 GB uv cache (already deleted). Use the shared cache.
- The first report measured 0 notes on a 2 second clip and called it expected. Verify on the real piano clip. If you use MPS,
  also run on CPU once and confirm the note counts agree; otherwise use CPU.
- `pydub` needs `ffmpeg` only for non-wav input; wav input must work. ffmpeg is installed at `/opt/homebrew/bin/ffmpeg`.
