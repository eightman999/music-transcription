# Resume note (read first)

A previous run of the brief below died with a network transport error in the middle of step 3. State on disk right now:

- Step 1 is done: `_staging/maestro_test5/` holds 5 wav + 5 midi + 5 gt.json + `manifest.json` (5 composers, years 2004-2011,
  about 24 minutes in total). Do not download these again. Still do the checks of step 1 (in particular, record `split` in the
  manifest: the current manifest has no split field) by re-running the script, which must skip existing files.
- `scripts/fetch_maestro_subset.py` and `scripts/fetch_smd_subset.py` have uncommitted modifications from that run: review them
  (`git diff`) and keep going from there.
- `_staging/smd5/` is empty. No evaluation of step 2 has been saved yet (`results/` has only `detect_synth` and `detect_sanity`).

Continue with step 1 (checks only), then steps 2 to 6. Run long evaluations one dataset at a time.

---

# Stage 3b: the Stage 3 scripts were never run. Run them, fix them, and produce the real numbers.

Working directory: `/Users/eightman/dev/tools/music-transcription`. Read `.rdsh/tasks/stage3.md` again: all of its rules and
definitions of done still apply. The previous attempt wrote `scripts/fetch_maestro_subset.py`, `scripts/fetch_smd_subset.py` and
`scripts/make_degraded.py` but executed none of them and reported everything as "未測定". That is not acceptable: "未測定" is only for
items that were attempted and are impossible (registration required, no aligned MIDI, ...), with the real error message.

Downloading is permitted and expected here. Network access works from the sandbox. Sizes are small: five MAESTRO wav files are
roughly 150-300 MB in total; SMD is one 3.2 GB zip (40 GB of disk are free). Write to `_staging/` (inside the working directory).

## Observed failure (the operator ran your script)

`.venv/bin/python scripts/fetch_maestro_subset.py --out data/maestro_test5` selected 5 rows and then failed for every one with
`ERROR: 2004/MIDI-Unprocessed_..._wav.wav not found in zip` and wrote an empty manifest, exiting with status 0.

- Members of `maestro-v3.0.0.zip` are stored with a directory prefix: `maestro-v3.0.0/2004/....wav`. Look at `RemoteZip(...).namelist()`
  instead of assuming names.
- A fetch script that obtained fewer pieces than requested must exit non-zero.
- All five selected pieces came from 2004. Keep the coded rule deterministic, but prefer different recording years as well as
  different composers when possible (state the final rule in the README).

## What to do, in this order. Do not stop after writing code: run each step and look at the output.

1. Fix and run `scripts/fetch_maestro_subset.py --out _staging/maestro_test5`. Check: 5 wav + 5 midi + 5 gt.json + manifest;
   every row is `split == "test"`; total duration <= 30 min; each gt.json has a plausible number of notes; the wav duration matches the CSV duration.
2. Run the evaluation on it with all four backends:
   `.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5 --backends naive,basic_pitch,kong,transkun`.
   Sanity reference from the operator on one MAESTRO test clip: onset F1 naive 0.27, basic_pitch 0.65, kong 0.97, transkun 0.99.
   If your numbers for kong / transkun are far below that, your ground-truth conversion or the dataset is wrong: find the cause.
3. Fix and run `scripts/fetch_smd_subset.py --out _staging/smd5` (Zenodo record 13753319, file `SMD-piano_v2.zip`).
   Try `remotezip` on the Zenodo file URL; if Range requests fail, download the zip once to `_staging/_downloads/` with `curl -L -C -`
   (resumable), extract the selected pieces, then delete the zip. Inspect the archive listing first to learn its real layout
   (which folders hold audio and which hold the performance-aligned MIDI) instead of assuming it.
   Then evaluate all four backends on `_staging/smd5`.
4. Run `scripts/make_degraded.py --input _staging/maestro_test5 --output _staging/maestro_test5_degraded`, verify that the degraded audio has
   no time offset against the original (cross-correlate one clip and report the lag in ms), then evaluate all four backends on it.
5. Write `results/phase1a_summary.md` (Japanese) from the measured result files only, with the adoption decision per PLAN.md 4.5.
6. `.venv/bin/python -m pytest -q` passes. Commit with Conventional Commits; stage only the files you changed; `results/*.md` and
   `results/*.json` are tracked; nothing under `_staging/` or `data` is tracked. Also fix `.gitignore`: the entry `data/` does not match
   the symlink `data` (git shows it as untracked): use `data` without the slash. Track `uv.lock`.

## Hard rules (unchanged)

No sudo, no credentials, no registration. No invented numbers: every number in a result file comes from a command run in this
session. Do not modify the backends' `run.py` to improve scores. Keep this stage's downloads under 5 GB and delete the SMD zip afterwards.

## Final report

For each of the four datasets: the per-backend mean table (onset, onset+offset, onset+velocity F1; real-time factor), copied from the
result files. Then: the selected pieces, the measured lag of the degraded set, what failed with the real error text, deviations.
