# Resume note (read first)

A previous run of the brief below wrote `scripts/make_degraded.py` and `tests/test_degraded.py` (7 tests pass) and then died on an
API timeout before the real run. The operator then ran step 2 of "Run": it did not finish within 10 minutes for 24 minutes of audio.

Cause: `measure_lag()` uses `np.correlate(s1, s2, mode='full')` on 30 s of audio (1.3 million samples). That is O(n^2),
about 10^12 operations per call, and it is called twice per clip. Fix exactly this:

- Use `scipy.signal.correlate(s1, s2, mode='full', method='fft')` with `scipy.signal.correlation_lags`, then restrict to +-0.2 s.
- Make the sign convention explicit and tested: `measure_lag(ref, delayed)` returns `+k` when `delayed[n] == ref[n - k]`
  (i.e. `delayed` is `ref` shifted later by k samples). Add a test with a noise burst shifted by +441 and by -441 samples at
  44.1 kHz that checks the returned value exactly, and a test that after compensation the residual is 0.
- Add a test that `measure_lag` on two 30 s signals at 44.1 kHz finishes in under 5 seconds.
- The whole test file must run in under 30 seconds (it takes 70 s now); the full run on the five real clips should take
  about a minute or two. Print the elapsed time per clip.

Do not restructure the rest of the script. Then do the "Run" section of the brief (steps 1 to 3) and the final report.
The same ownership rules apply: only `scripts/make_degraded.py`, `tests/test_degraded.py`, `_staging/maestro_test5_degraded/`;
no git command that writes.

---

# Stage 3e: rewrite `scripts/make_degraded.py`

Working directory: `/Users/eightman/dev/tools/music-transcription`.

## You own (may edit / create)

Only `scripts/make_degraded.py`, `tests/test_degraded.py` (new) and the directory `_staging/maestro_test5_degraded/`.
Another agent is editing `mt/`, `scripts/eval_detect.py`, `scripts/fetch_maestro_subset.py` and other tests at the same time:
do not touch any other file. **Do not run any git command that writes** (no add / commit / stash / checkout / restore).

## Hard rules

- No sudo, no credentials, no downloads. Run everything with `.venv/bin/python`. Write only inside the working directory.
- Do not invent numbers: every number you report must be printed by a command you ran.

## What was wrong

The current script "adds room reverb" with `aecho=0.8:0.9:1000:0.3`: a single echo **one second** later. Every note is played
twice, the models correctly transcribe the echo, and precision drops to 0.6. That is not a room. Also: the noise level is a
fixed gain (the SNR was never measured), and every step silently falls back to "skip" on error.

## New implementation (replace the file completely; target under 200 lines)

CLI: `make_degraded.py --input <dir> --output <dir> [--force]`, both directories required.
Processing is done with numpy / scipy / soundfile; ffmpeg is used only for the MP3 round trip. Deterministic. Any failing step
raises and the script exits non-zero: no fallbacks, no skipping.

For each `<input>/<slug>.wav` (keep sample rate and channel count; process in float64):

1. **Room reverb** by convolution with a synthetic impulse response, the same for every clip and channel:
   - `rng = numpy.random.default_rng(20261111)`, length 0.6 s at the clip's sample rate.
   - `ir[0] = 1.0` (direct sound, so no delay is introduced).
   - Tail: for t >= 5 ms, `gaussian_noise(t) * exp(-6.908 * t / 0.5)` (RT60 = 0.5 s); zero between sample 1 and 5 ms.
     Scale the tail so that `sum(tail**2) == 10 ** (-6 / 10)` (direct-to-reverberant ratio 6 dB).
   - `scipy.signal.fftconvolve(x, ir)[:len(x)]` per channel.
2. **Pink noise at 30 dB SNR**: white Gaussian noise from the same generator (independent per channel), shaped to 1/f power in
   the frequency domain (`rfft`, divide by `sqrt(f)`, DC bin set to 0, `irfft`), scaled so that
   `10 * log10(mean(signal**2) / mean(noise**2)) == 30.0` where `signal` is the reverberated clip (all channels, whole clip).
   Add it. Compute and store the measured SNR.
3. If `max(abs(y)) > 0.99`, scale the whole clip down to peak 0.99 (store the gain).
4. **MP3 96 kbps round trip**: write a temporary 16-bit wav, `ffmpeg -y -i a.wav -codec:a libmp3lame -b:a 96k a.mp3`, then
   `ffmpeg -y -i a.mp3 -ar <sr> b.wav`. Check both return codes.
5. **Delay compensation**: measure the lag of `b.wav` against `a.wav` (mono mixes, first 30 s, cross-correlation restricted to
   +-0.2 s, result in samples). Shift `b` by that lag, then trim / zero-pad to exactly the length of the input clip.
   Measure the lag again: the residual must be within +-1 ms, otherwise raise.
6. Write `<output>/<slug>.wav` as 16-bit PCM.

Regardless of whether the wav was re-created or skipped (it is skipped when it exists and `--force` is absent), **always copy
again** `<slug>.midi`, `<slug>.mid` (whichever exists) and `<slug>.gt.json` from the input directory, because the ground truth
there may have been regenerated.

Write `<output>/manifest.json`: the processing parameters (seed, RT60, direct-to-reverberant ratio, target SNR, MP3 bitrate,
ffmpeg version line) and per clip: `measured_snr_db`, `mp3_lag_samples`, `residual_lag_samples`, `peak_gain`, `sha256` of the
output wav, duration in seconds of input and output.

## Tests (`tests/test_degraded.py`)

Build a 3-second synthetic stereo clip in a temporary directory (a few decaying sine notes with sharp attacks) plus a dummy
`.gt.json`, run the script on it, and assert: same sample rate, channel count and number of samples as the input; measured SNR
within 30.0 +- 0.1 dB; `abs(residual_lag_samples) <= sr / 1000`; the lag of the output against the input (measured again in the
test by cross-correlation) within +-2 ms; running twice gives the identical sha256; the gt file is copied; a corrupt input
wav makes the script exit non-zero. Skip the test when ffmpeg is not installed.

## Run

1. `.venv/bin/python -m pytest -q tests/test_degraded.py`
2. `.venv/bin/python scripts/make_degraded.py --input _staging/maestro_test5 --output _staging/maestro_test5_degraded --force`
3. Print `_staging/maestro_test5_degraded/manifest.json`.

Do not run the evaluation; the operator will.

## Final report (print at the end)

The pytest summary line, the per-clip measured SNR / MP3 lag / residual lag copied from the manifest, anything that failed,
and every deviation from this brief.
