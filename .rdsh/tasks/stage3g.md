# Stage 3g: `scripts/fetch_smd_subset.py` does not run

Working directory: `/Users/eightman/dev/tools/music-transcription`. Run everything with `.venv/bin/python`.
The operator is running a long evaluation at the same time: do not run `scripts/eval_detect.py`, do not touch `results/`,
`out/`, `data/`, `backends/`, `mt/`. You own only `scripts/fetch_smd_subset.py`, `tests/test_smd.py`, `scripts/make_summary.py`,
`tests/test_summary.py`. Stage files by explicit path when committing.

## What was found

The committed script crashes on the first piece when the operator runs it:

```
$ .venv/bin/python scripts/fetch_smd_subset.py --out data/smd5
  File "scripts/fetch_smd_subset.py", line 45, in <listcomp>
    'pitch': int(r['Pitch']), 'velocity': int(r['Velocity'])} for r in reader]
ValueError: invalid literal for int() with base 10: '000.273'
Processing Bach_BWV849-01_001_20090916-SMD...
ERROR: invalid literal for int() with base 10: '000.273'
```

The real csv looks like this (velocity is a float between 0 and 1, numbers are zero-padded):

```
Start;Duration;Pitch;Velocity;Instrument
002.549;000.476;68;000.273;MIDI 01
003.061;000.251;64;000.273;MIDI 01
```

So the previous report ("SMD dataset fetched and processed") did not come from this script, and no `manifest.json` was written.
Also the script names the MIDI copy `<stem>.midi` while the brief said `<stem>.mid`; keep `.mid`.

## Fix

1. `parse_csv`: velocity is `float`. Update `tests/test_smd.py` to use the three real lines above as its sample.
2. The script must exit non-zero when a piece fails (now it prints `ERROR` and goes on). No `try/except` that swallows errors.
3. `manifest.json` must be written (source URL, licence, selection rule, per piece: stem, composer, duration, number of notes,
   number of pedal intervals, sha256 of the wav, `csv_max_onset_diff_ms`, wav duration, MIDI end time).
4. Add an end-to-end test that is skipped when `data/_downloads/smd/wav_44100_stereo` is absent: run the script as a subprocess
   with `--out <tmp dir> --n 1` (the cache is complete, so no download happens; the central directory read needs the network,
   skip the test when that request fails) and assert exit code 0 and that `<stem>.wav`, `<stem>.mid`, `<stem>.gt.json`,
   `manifest.json` exist and the gt has the same number of notes as the manifest says.
5. `scripts/make_summary.py`: the line under "実行日" prints the literal text "自動生成". Replace it with the newest modification
   date (YYYY-MM-DD) among the result JSON files it read. Do not run `make_summary.py` against `results/` (the operator will);
   only run its tests.

## Run

1. `.venv/bin/python -m pytest -q tests/test_smd.py tests/test_summary.py`
2. `.venv/bin/python scripts/fetch_smd_subset.py --out _staging/smd5_check` and print `_staging/smd5_check/manifest.json`.
3. Commit (Conventional Commits, explicit paths).

## Final report

The pytest summary line, the exit code and last lines of step 2, the per-piece `csv_max_onset_diff_ms`, and anything that failed.
Report only what a command in this session printed.
