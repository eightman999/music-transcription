# Stage 2: one learned detection backend

Working directory: `/Users/eightman/dev/tools/music-transcription`. Read `README.md`, `mt/schema.py`, `mt/backends.py`
and `backends/naive/run.py` first to see the backend contract that Stage 1 established.
Plan context is in `PLAN.md` (Japanese), sections 3.3, 3.4, 4.1, 4.2.

Other agents are adding other backends **at the same time** in sibling directories. Therefore:

- Create and edit files ONLY inside `backends/<NAME>/` (NAME is given at the bottom). Do not edit `mt/`, `scripts/`, `tests/`,
  `pyproject.toml`, `README.md` or any other backend directory. If you believe a shared file must change, do not change it:
  describe the needed change in your final report.
- Do NOT run any `git` command that writes (no add / commit / stash / checkout). Read-only git is fine.

## Hard rules

- No sudo. Never type or print credentials. If something asks for a password, a login or an account registration, stop and report.
- Do not invent numbers. Every number in the final report must come from a command you ran in this session.
- Model weights must end up under `data/models/<NAME>/` (`./data` is a symlink to a shared data directory; you may create that
  subdirectory and write only there). Nothing may be downloaded into the home directory. If a library insists on a default
  download location in `~`, pass an explicit path or download the file yourself with `curl -L` from the official source.
- Only use the official distribution (PyPI package, the official GitHub repository, the official weight URL referenced by the package).

## Deliverables in `backends/<NAME>/`

1. `setup.sh`: idempotent. Creates `backends/<NAME>/.venv` with `uv venv --python 3.11` (use 3.10 or 3.12 only if 3.11 provably
   cannot work, and say why), installs the dependencies with `uv pip install --python backends/<NAME>/.venv/bin/python ...`,
   fetches the weights. Running it twice must be harmless.
2. `requirements.lock`: the output of `uv pip freeze` for that venv.
3. `run.py <in.wav> <out.json>`: runs the model on one audio file and writes the note-event JSON of `mt/schema.py`
   (`backend` = `<NAME>`, notes with integer MIDI pitch, onset / offset in seconds, velocity 1-127, optional `pedal` list).
   It runs under `backends/<NAME>/.venv/bin/python`. It must not need the core `.venv`.
   Use Apple MPS if it works for this model, otherwise CPU; state which one actually ran.
4. `NOTES.md` (Japanese, short): package and version, weight file name / size / source URL / sha256, licence of code and weights
   as stated by the source, device used, anything that did not work.

## Install attempts

Try at most two different install approaches. If both fail, stop, write the reason into `NOTES.md` with the real error
messages, and report the backend as "not installable". Do not fake a `run.py`.

## Verification (do all, report real output)

- `bash backends/<NAME>/setup.sh` succeeds (run it a second time to show it is idempotent).
- Make sure the synthetic clip exists: `uv run python scripts/make_test_wav.py`.
- `backends/<NAME>/.venv/bin/python backends/<NAME>/run.py out/synth/test.wav out/synth/<NAME>.json` succeeds.
- `uv run python -c "from mt.schema import load; d = load('out/synth/<NAME>.json'); print(len(d['notes']))"` works
  (adapt the function name to what `mt/schema.py` really exports).
- `uv run python scripts/eval_detect.py --dataset synth --backends <NAME>` prints a table. If the registry in `mt/backends.py`
  does not pick up the new backend automatically, do not edit it: evaluate with a few lines of throwaway Python instead and
  say so in the report. The synthetic clip is not real piano, so low scores here are acceptable: report them as they are.

## Final report (print at the end)

Commands run and their real output, the device used, wall time for the synthetic clip, what failed or is unverified,
and any change you think is needed in shared files.

---

