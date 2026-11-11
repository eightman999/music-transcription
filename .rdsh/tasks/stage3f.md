# Stage 3f: SMD evaluation set, generated summary, final Phase 1a runs

Working directory: `/Users/eightman/dev/tools/music-transcription`. Read `mt/gt.py`, `mt/evaluate.py`, `scripts/eval_detect.py`,
`scripts/fetch_maestro_subset.py`, `PLAN.md` section 4.5 (Japanese) first. You are the only agent working now.

## Hard rules

- No sudo, no credentials. Do not invent numbers. Do not weaken or delete an existing test.
- Run everything with `.venv/bin/python`. `./data` is read-only for you; write only inside the working directory (`_staging/`, `results/`, ...).
- Never add audio / MIDI of a dataset to git. Stage files by explicit path only.
- Do not edit `backends/`, `mt/gt.py`, `scripts/make_degraded.py`.

## 0. Two defects left by the previous stage (fix first, in `scripts/eval_detect.py` and its tests)

1. The Markdown table lost two columns. The JSON still has `onset_only` and `onset_velocity`, but `results/detect_*.md` only
   shows the two On+Off columns. The table columns must be, in this order:
   `Clip | Backend | GT | Est | Onset-only (P/R/F1) | On+Off key (P/R/F1) | On+Off sustained (P/R/F1) | Onset+Velocity (P/R/F1) | Onset dev (ms) | RT | RSS | Device | Version | Clips`
   (onset-only is the primary metric of the whole project). Add a test that the header contains all of these names and that the
   mean row carries the onset-only mean.
2. A test writes into the real cache (`out/detect/test_dataset/nonexistent_backend/`). Tests must use a temporary directory for
   the cache (add a `--cache-dir` option / function argument defaulting to `out/detect`), and delete `out/detect/test_dataset`.

The already cached model outputs in `out/detect/maestro_test5/` are valid: do not delete them and do not use `--no-cache`.

## A. `scripts/fetch_smd_subset.py` (replace the file completely; target under 220 lines)

Source: Zenodo record 13753319, `SMD-piano_v2.zip`
(`https://zenodo.org/records/13753319/files/SMD-piano_v2.zip?download=1`, CC BY-NC-SA 3.0, evaluation use only).
The zip contains `midi/<stem>.mid`, `csv/<stem>.csv`, `wav_44100_stereo/<stem>.wav` (and two other wav folders that we do not use)
for 50 pieces. Stems look like `Bach_BWV849-01_001_20090916-SMD`; the composer is the text before the first `_`.

CLI: `fetch_smd_subset.py --out <dir> [--cache <dir>] [--n 5]`, `--cache` defaults to `data/_downloads/smd`.

1. Open the zip with `remotezip.RemoteZip` (only the central directory is read, a few kB) and take `infolist()`.
2. Selection rule (coded, deterministic): stems of `wav_44100_stereo/*.wav` sorted by name; duration in seconds =
   `(file_size - 44) / (44100 * 2 * 2)`; walk the sorted list and pick a stem when its composer has not been picked yet and
   `90 <= duration <= 420`; stop at `--n`.
   The operator has already checked that this rule yields, in this order:
   `Bach_BWV849-01_001_20090916-SMD`, `Bartok_SZ080-01_002_20110315-SMD`, `Beethoven_Op027No1-02_003_20090916-SMD`,
   `Brahms_Op010No1_003_20090916-SMD`, `Chopin_Op010-03_007_20100611-SMD`. If you get anything else, stop and report.
3. For every needed member (`midi/`, `csv/`, `wav_44100_stereo/` of each selected stem): if `<cache>/<member path>` exists with
   exactly the size in the zip directory, use it. Otherwise download that member into `<cache>/<member path>` through the open
   `RemoteZip` (write to `*.part`, verify the size, rename). The operator has pre-filled the cache with all 15 members, so in
   your runs nothing should be downloaded; if a member is missing, do **not** try to download 3 GB: stop and report.
4. Write into `--out` in the same layout as the MAESTRO set: `<stem>.wav` (copy, unchanged: 44.1 kHz stereo), `<stem>.mid` (copy),
   `<stem>.gt.json` (`mt.gt.midi_to_gt`, schema fields `backend: "ground_truth"`, `audio: "<stem>.wav"`, `notes`, `pedal`).
5. Consistency check per piece, stored in `manifest.json` and printed:
   - the csv (`Start;Duration;Pitch;Velocity;Instrument`, `;`-separated, times in seconds) has the same number of notes as the
     MIDI; after sorting both by (onset, pitch): maximum absolute onset difference in ms (`csv_max_onset_diff_ms`);
   - wav duration (soundfile) and MIDI end time in seconds.
   If the note counts differ, raise.
6. `manifest.json`: source URL, licence, selection rule, and per piece: stem, composer, duration, number of notes, number of
   pedal intervals, sha256 of the wav, the check values above.

`tests/test_smd.py`: test the selection rule as a pure function on a hand-made list of (name, size) tuples (composer uniqueness,
duration window, order, stops at n); test the csv parser on a small string. No network in tests.

## B. `scripts/make_summary.py` (new): the summary is generated, never hand-written

`make_summary.py` reads `results/detect_<name>.json` for the names `synth`, `maestro_test5`, `smd5`, `maestro_test5_degraded`
(a missing file means that set is "未測定") and writes `results/phase1a_summary.md` in Japanese. Every number in the file comes
from those JSON files; the script contains no literal measurement.

Content:

1. One table per dataset: per backend the mean over clips of onset-only P / R / F1, On+Off key F1, On+Off sustained F1,
   onset+velocity F1, median onset deviation (ms), real-time factor, peak RSS (MB), and `ok/total` clips. The package version and device per backend.
2. One overview table: mean onset-only F1, rows = backends, columns = the four datasets ("未測定" where absent).
3. Decision according to PLAN.md 4.5, computed in code:
   - candidates = learned backends (everything except `naive`) whose mean onset F1 is above `naive` on `maestro_test5` and on `smd5`;
   - rank candidates by mean onset F1 on `smd5`; `tied` = candidates within 1.0 point (0.010) of the best;
   - adopted = the member of `tied` with the lowest mean real-time factor on `smd5`;
   - if `smd5` is absent: do the same on `maestro_test5` and label the result "暫定採用"; otherwise "採用".
   Print the values that led to the decision (the F1 of each candidate, the tie set, the real-time factors).
4. A fixed section "注意" (text only, no numbers):
   - MAESTRO の test split は kong / transkun の学習データと同じ分布（同じコンクール・同じ系統のピアノ）であり、SMD が分布外の確認である。
   - On+Off は基準が 2 通りある（鍵を離した時刻／サステインペダルで延長した時刻）。モデルごとに出力の流儀が違うため両方を載せ、主指標は onset-only とする。
   - 劣化版（残響・ピンクノイズ・MP3）は頑健性の参考であり、実環境の録音の代わりではない。
   - onset+velocity は mir_eval の線形再スケーリング後の比較で、相対的な強弱の一致を見ている。
5. A list of failed clips (backend, clip, error) taken from the JSON files, and the list of "未測定" sets.

`tests/test_summary.py`: with small hand-made result JSON files in a temporary directory, check the decision logic
(clear winner; two candidates within 1.0 point -> the faster one; `smd5` missing -> "暫定採用") and that a missing dataset is shown as "未測定".

## C. Run (each as its own command, in this order; evaluations are cached per clip, so a command cut off by the time limit can simply be run again)

1. `.venv/bin/python -m pytest -q`
2. `.venv/bin/python scripts/fetch_smd_subset.py --out _staging/smd5`
3. `.venv/bin/python scripts/eval_detect.py --dataset synth --backends naive`
4. `.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5 --backends naive,basic_pitch,kong,transkun` (should be fully cached)
5. `.venv/bin/python scripts/eval_detect.py --dataset _staging/smd5 --backends naive,basic_pitch,transkun`
6. `.venv/bin/python scripts/eval_detect.py --dataset _staging/smd5 --backends naive,basic_pitch,kong,transkun`
7. `.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5_degraded --backends naive,basic_pitch,transkun`
8. `.venv/bin/python scripts/eval_detect.py --dataset _staging/maestro_test5_degraded --backends naive,basic_pitch,kong,transkun`
9. `.venv/bin/python scripts/make_summary.py`
10. `.venv/bin/python -m pytest -q`

If a backend crashes on a clip, do not patch the backend: the failure is recorded by the harness; report it.

## D. Repository

- README (Japanese, short): how to rebuild each dataset and re-run each evaluation, the two offset conventions, the cache
  (`out/detect/`, `--no-cache`). Remove statements that are no longer true.
- Commit with Conventional Commits, explicit paths. Include `scripts/make_degraded.py` and `tests/test_degraded.py`
  (written by another agent, not committed yet) and `.rdsh/tasks/`, `.rdsh/mistral.patch.yml`, `.rdsh/run.sh` (not `.rdsh/logs`).
  `git ls-files | grep -E '\.(wav|midi?|mp3)$'` must print nothing.

## Final report (print at the end)

The pytest summary line, the overview table and the decision section copied verbatim from `results/phase1a_summary.md`,
the manifest check values of the SMD pieces, anything that failed, and every deviation from this brief.
