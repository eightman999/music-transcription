# Stage 3d: correct the ground-truth conversion and the evaluation harness

Working directory: `/Users/eightman/dev/tools/music-transcription`. Read `mt/evaluate.py`, `mt/schema.py`, `scripts/eval_detect.py`,
`scripts/fetch_maestro_subset.py` and `tests/` first.

A review of the last run found that the onset+offset numbers are wrong because the MIDI -> ground-truth conversion is wrong.
Fix exactly what is listed here. Do not "improve" anything else.

## You own (may edit / create)

`mt/gt.py` (new), `mt/evaluate.py`, `mt/schema.py`, `scripts/eval_detect.py`, `scripts/fetch_maestro_subset.py`,
`tests/test_gt.py` (new), other existing files under `tests/`, `README.md`, `results/detect_synth.*`, `results/detect_maestro_test5.*`.

Another agent is rewriting `scripts/make_degraded.py` at the same time. **Do not touch** `scripts/make_degraded.py`,
`scripts/fetch_smd_subset.py`, `tests/test_degraded.py`, `backends/`, `_staging/maestro_test5_degraded/`.
When you commit, stage only the files you own by explicit path (never `git add -A` / `git add .` / `git commit -a`).

## Hard rules

- No sudo, no credentials. No downloads in this stage (everything needed is already on disk).
- Do not invent numbers. Do not weaken or delete an existing test to make it pass.
- Run everything with `.venv/bin/python`. `./data` is read-only for you; write only inside the working directory.

## What was wrong

`midi_to_ground_truth()` in `scripts/fetch_maestro_subset.py`:

1. Pedal intervals are built with a stack: every CC64 event with value >= 64 pushes a time, every event < 64 pops one.
   A real pedal sends many consecutive values (70, 100, 120, 90, 40, 10, ...), so stale entries stay on the stack and later
   releases create bogus intervals that are minutes long.
2. A note is extended only when the pedal was already down at the note onset. Pressing the pedal while the key is held is missed.
3. The models do not agree on the convention (one reports key-release offsets, another pedal-extended offsets), so a single
   onset+offset number against one convention is unfair. We will store the raw data and report both.

## A. `mt/gt.py` (new, shared by all dataset scripts)

```python
def pedal_intervals(cc64: list[tuple[float, int]], end_time: float, threshold: int = 64) -> list[dict]:
    """cc64 = (time, value) pairs. State machine: sort by time; when the state is 'up' and value >= threshold the pedal
    goes down at that time; when the state is 'down' and value < threshold it goes up at that time and one interval
    {"onset": down_time, "offset": up_time} is emitted. Repeated values on the same side change nothing.
    If the pedal is still down at the end, close the interval at end_time. Intervals of zero length are dropped."""

def midi_to_gt(midi_path) -> dict:
    """Returns {"notes": [...], "pedal": [...]}. Notes are exactly as recorded: onset = note.start, offset = note.end
    (key release), velocity = note.velocity, pitch = note.pitch, all instruments merged, sorted by (onset, pitch).
    pedal = pedal_intervals() over the CC64 events of all instruments, end_time = pm.get_end_time()."""

def sustain_extended(notes: list[dict], pedal: list[dict]) -> list[dict]:
    """Returns a new list in the same order; only "offset" may change. For each note:
    1. off = note["offset"]. If a pedal interval satisfies onset <= off < offset (pedal is down at the key release), off = that
       interval's offset.
    2. nxt = the onset of the next note of the same pitch with onset > this note's onset. If it exists and nxt < off, off = nxt.
    3. off is never smaller than the raw offset unless rule 2 applied, and never <= the note onset
       (if it would be, keep the raw offset)."""
```

Use `bisect` / per-pitch lists so that this is not quadratic (a clip has ~4000 notes and ~1000 pedal intervals).

`tests/test_gt.py` builds tiny MIDI objects with `pretty_midi` in the test (no dataset needed) and checks:

- CC64 values `70, 100, 120, 30, 10, 90, 20` at times 1..7 give exactly two intervals: (1, 4) and (6, 7).
- Pedal still down at the end is closed at the end time.
- Key held 2.0-3.0, pedal 2.5-5.0: raw offset 3.0, extended offset 5.0.
- Key 2.0-3.0, pedal 1.0-2.5 (released before the key): extended offset stays 3.0.
- Two notes of the same pitch at 2.0-2.2 and 3.0-3.2 with pedal 1.9-6.0: extended offsets 3.0 and 6.0.
- A note without any pedal is unchanged; `sustain_extended` does not modify its input list.

## B. Ground-truth files

- A `*.gt.json` now stores the **raw** notes of `midi_to_gt` plus `"pedal"`. No extension is baked in.
- `scripts/fetch_maestro_subset.py`: delete its own conversion code and use `mt.gt.midi_to_gt`. When the wav and midi of a piece
  already exist in `--out`, it must not touch the network for that piece but must **always rewrite** `<slug>.gt.json` from the
  midi. Running `.venv/bin/python scripts/fetch_maestro_subset.py --out _staging/maestro_test5` therefore regenerates the five
  ground-truth files offline (if the CSV is needed for the manifest and is not cached, keep the existing manifest instead of failing).

## C. `mt/evaluate.py` and `scripts/eval_detect.py`

1. Two onset+offset results per clip, same mir_eval settings as now (onset 0.05, offset_ratio 0.2, offset_min_tolerance 0.05):
   - `onset_offset`: reference = raw key-release offsets.
   - `onset_offset_sustained`: reference = `sustain_extended(notes, pedal)`. If the ground truth has no `pedal` key, this is `null`
     (shown as `n/a`).
   Table columns: `On+Off key (P/R/F1)` and `On+Off sustained (P/R/F1)`.
2. Onset timing diagnostic per clip and backend: with `mir_eval.transcription.match_notes` (onset 0.05, `offset_ratio=None`),
   over the matched pairs compute `est_onset - ref_onset`; store `onset_dev_median_ms` and `onset_dev_mean_abs_ms`; show the
   median in a column `Onset dev (ms)`. `null` when there are no matches.
3. A failed clip currently gets P/R/F1 = 0.0, which silently lowers the mean. Store `null` metrics plus `"error"`; exclude failed
   clips from the mean; the mean row shows `ok/total` clips in a new column `Clips`.
4. Output cache, so that a re-score after a ground-truth change does not re-run the models:
   after a successful backend run, keep its JSON at `out/detect/<dataset_name>/<backend>/<clip>.json` and a sidecar
   `<clip>.run.json` with `wav_sha256`, wall time, real-time factor, peak RSS. On the next run, when both files exist and
   `wav_sha256` equals the current wav's sha256, reuse them instead of running the backend (print `cached`).
   `--no-cache` forces a real run. (`out/` is already git-ignored.)
5. Keep everything else (file naming by directory base name, one mean row per backend, sort notes by (onset, pitch) after loading).

Add tests (naive backend only, tiny temporary dataset built in the test): the cache is used on the second run and ignored with
`--no-cache`; a failing clip is excluded from the mean; `onset_offset_sustained` is `null` without pedal and differs from
`onset_offset` on a case with pedal.

## D. Run (each as its own command, in this order)

1. `.venv/bin/python -m pytest -q`
2. `.venv/bin/python scripts/fetch_maestro_subset.py --out _staging/maestro_test5` (offline regeneration of the gt files)
3. `.venv/bin/python scripts/eval_detect.py --dataset synth --backends naive`
4. `.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5 --backends naive,basic_pitch,transkun`
5. `.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5 --backends naive,basic_pitch,kong,transkun`
   (step 4 warms the cache so that step 5 only has to run `kong`, which takes about 10 minutes; if a command is cut off by the
   time limit, run it again: finished clips come from the cache)

Then commit (Conventional Commits, explicit paths only).

## Final report (print at the end)

The pytest summary line, the mean rows of `results/detect_maestro_test5.md` copied verbatim, the number of pedal intervals per
piece, anything that failed, and every deviation from this brief. Do not write prose that contains numbers you did not copy
from a command output.
