"""Shared note-list -> WAV synthesis.

Used by scripts/make_test_wav.py (test clip generation) and compose/
(render composed notes to audio). Timbre: partials k = 1..6 at k*f0,
amplitude 1/k, decay exp(-t / (1.2 / k)), 5 ms attack, 30 ms release.
"""

import numpy as np
import soundfile as sf


def generate_note_waveform(
    pitch: int,
    duration: float,
    fs: int = 44100,
    velocity: int = 100,
) -> np.ndarray:
    """Generate a note with harmonic timbre.

    Args:
        pitch: MIDI note number
        duration: Duration in seconds
        fs: Sample rate
        velocity: MIDI velocity (1-127)

    Returns:
        Audio samples as numpy array
    """
    f0 = 440.0 * (2.0 ** ((pitch - 69) / 12.0))
    t = np.linspace(0, duration, int(fs * duration), endpoint=False)
    amplitude_scale = velocity / 127.0

    waveform = np.zeros_like(t)
    for k in range(1, 7):
        freq = k * f0
        amp = 1.0 / k
        decay = np.exp(-t / (1.2 / k))
        waveform += amp * decay * np.sin(2 * np.pi * freq * t)

    envelope = np.ones_like(t)
    attack_idx = int(0.005 * fs)
    if attack_idx > 0:
        envelope[:attack_idx] = np.linspace(0, 1, attack_idx)

    release_start = duration - 0.030
    release_idx = int(release_start * fs)
    if release_idx < len(t):
        envelope[release_idx:] = np.linspace(1, 0, len(t) - release_idx)

    return amplitude_scale * envelope * waveform


def render_notes(
    notes: list,
    fs: int = 44100,
    tail: float = 0.5,
    normalize: float = 0.8,
) -> np.ndarray:
    """Mix a note list (pitch/onset/offset/velocity, seconds) into mono audio."""
    end_time = max((n["offset"] for n in notes), default=0.0) + tail
    audio = np.zeros(int(fs * end_time))

    for n in notes:
        dur = n["offset"] - n["onset"]
        if dur <= 0:
            continue
        seg = generate_note_waveform(n["pitch"], dur, fs=fs, velocity=n["velocity"])
        start = int(n["onset"] * fs)
        end = start + len(seg)
        if end > len(audio):
            audio = np.pad(audio, (0, end - len(audio)))
        audio[start:end] += seg

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * normalize
    return audio


def render_to_wav(notes: list, wav_path: str, fs: int = 44100) -> str:
    """Render notes and write a PCM16 WAV file."""
    audio = render_notes(notes, fs=fs)
    sf.write(wav_path, audio, fs, subtype="PCM_16")
    return wav_path
