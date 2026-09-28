#!/usr/bin/env python3
"""
/home/z/my-project/scripts/brag_audio.py

Synthesizes music + SFX, then mixes with the 5 TTS voiceover lines
into a single 18.0s 48kHz stereo track for brag.mp4.

Deadpan yc-parody register: a single sustained A-minor pad, very low volume,
slow tremolo. SFX are soft, short, sit under the music.
"""

import os
import sys
import wave
import struct
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

BRAG_OUT = os.environ.get("BRAG_OUT")
if not BRAG_OUT:
    print("Set BRAG_OUT env var", file=sys.stderr); sys.exit(1)

AUDIO_DIR = os.path.join(BRAG_OUT, "work", "audio")
SR = 48000       # final sample rate (ffmpeg will resample if needed)
DUR = 18.0
N = int(SR * DUR)
T = np.linspace(0, DUR, N, endpoint=False)

# ----------------------------------------------------------------------------
# 1. MUSIC — sustained A-minor pad (A2 + E3 + A3 + C4), low-passed, slow tremolo
#    A2=110, E3=164.81, A3=220, C4=261.63
# ----------------------------------------------------------------------------
def pad(freqs, dur_arr):
    out = np.zeros_like(dur_arr)
    for f in freqs:
        out += np.sin(2*np.pi*f*dur_arr) * 0.5
        # add a tiny detune for warmth
        out += np.sin(2*np.pi*(f*1.003)*dur_arr) * 0.25
    return out

music_mono = pad([110.0, 164.81, 220.0, 261.63], T)
# normalize to safe range
music_mono = music_mono / np.max(np.abs(music_mono)) * 0.6
# low-pass at ~800 Hz for that muffled, deadpan pad sound
b, a = butter(4, 800/(SR/2), btype='low')
music_mono = lfilter(b, a, music_mono)
# slow tremolo — 0.3 Hz, depth 0.4
tremolo = 1.0 + 0.4 * np.sin(2*np.pi*0.3*T)
music_mono = music_mono * tremolo
# soft fade in/out (1s in, 1.5s out)
fade_in = np.minimum(T/1.0, 1.0)
fade_out = np.minimum((DUR - T)/1.5, 1.0)
music_mono = music_mono * fade_in * fade_out
# music sits low in the mix
music_mono = music_mono * 0.18   # ≈ -15 dB

# ----------------------------------------------------------------------------
# 2. SFX — short soft bursts at specific timecodes
#    Each one is a sine burst with exponential decay, very low volume.
# ----------------------------------------------------------------------------
def click_synth(t_start, freq=900.0, dur_s=0.06, gain=0.25):
    """Soft click — 60ms sine burst with exp decay."""
    out = np.zeros(N, dtype=np.float32)
    s = int(t_start * SR)
    e = min(int((t_start + dur_s) * SR), N)
    if e <= s: return out
    local_t = np.arange(e - s) / SR
    env = np.exp(-local_t * 35)  # fast decay
    wave_ = np.sin(2*np.pi*freq*local_t) * env
    out[s:e] = wave_ * gain
    return out

def tick_synth(t_start, freq=2200.0, dur_s=0.035, gain=0.18):
    """Short tick — 35ms high-freq burst."""
    return click_synth(t_start, freq=freq, dur_s=dur_s, gain=gain)

def pop_synth(t_start, freq=380.0, dur_s=0.18, gain=0.22):
    """Soft pop — 180ms low sine with slower decay."""
    out = np.zeros(N, dtype=np.float32)
    s = int(t_start * SR)
    e = min(int((t_start + dur_s) * SR), N)
    if e <= s: return out
    local_t = np.arange(e - s) / SR
    env = np.exp(-local_t * 12)
    wave_ = np.sin(2*np.pi*freq*local_t) * env
    out[s:e] = wave_ * gain
    return out

def draw_synth(t_start, dur_s=1.5, gain=0.10):
    """Pencil-draw tick — high-freq bursts every 80ms over dur_s, very low gain."""
    out = np.zeros(N, dtype=np.float32)
    n_bursts = int(dur_s / 0.08)
    for i in range(n_bursts):
        t = t_start + i * 0.08
        out += tick_synth(t, freq=1800 + 200*np.sin(i*0.6), dur_s=0.03, gain=gain)
    return out

# SFX timeline (matches brag-plan.md)
sfx = np.zeros(N, dtype=np.float32)
# 6 hard-cut clicks (start of each scene + start of punchline)
for t in [0.0, 2.5, 5.5, 9.0, 12.0, 15.0]:
    sfx += click_synth(t, freq=900.0, dur_s=0.05, gain=0.22)
# 3 list-row ticks (scene 3)
for t in [5.8, 6.0, 6.2]:
    sfx += tick_synth(t, freq=2200.0, dur_s=0.03, gain=0.16)
# 1 toast pop (scene 4)
sfx += pop_synth(10.5, freq=420.0, dur_s=0.18, gain=0.24)
# pencil-draw ticks (scene 5, 12.0–14.5s)
sfx += draw_synth(12.2, dur_s=2.2, gain=0.08)

# light low-pass on SFX so they sit in the same space as music
b2, a2 = butter(2, 3500/(SR/2), btype='low')
sfx = lfilter(b2, a2, sfx)

# ----------------------------------------------------------------------------
# 3. VOICEOVER — place 5 TTS clips on the timeline with deadpan gaps
#    Load each wav (24kHz mono), resample to 48kHz, place at the right time.
# ----------------------------------------------------------------------------
def load_and_resample(path, target_sr=SR):
    src_sr, src = wavfile.read(path)
    if src.dtype == np.int16:
        src = src.astype(np.float32) / 32768.0
    elif src.dtype == np.int32:
        src = src.astype(np.float32) / 2147483648.0
    # convert to mono if stereo
    if src.ndim == 2:
        src = src.mean(axis=1)
    # linear resample to target_sr
    if src_sr != target_sr:
        n_out = int(len(src) * target_sr / src_sr)
        idx_out = np.arange(n_out) * (len(src) - 1) / (n_out - 1)
        i0 = idx_out.astype(np.int64)
        i1 = np.minimum(i0 + 1, len(src) - 1)
        frac = idx_out - i0
        src = src[i0] * (1 - frac) + src[i1] * frac
    return src

vo_starts = [0.8, 4.5, 9.5, 13.0, 14.7]   # seconds
vo_gains  = [0.9, 0.9, 0.9, 0.85, 0.9]    # slightly under music-bed level

vo_track = np.zeros(N, dtype=np.float32)
for i in range(1, 6):
    path = os.path.join(AUDIO_DIR, f"vo_{i}.wav")
    clip = load_and_resample(path, SR)
    start = int(vo_starts[i-1] * SR)
    end = min(start + len(clip), N)
    # tiny fade in/out on each clip to avoid clicks at boundaries
    fade = min(int(0.02 * SR), len(clip)//2)
    clip[:fade] *= np.linspace(0, 1, fade)
    clip[-fade:] *= np.linspace(1, 0, fade)
    vo_track[start:end] += clip[:end-start] * vo_gains[i-1]

# simple sidechain duck: reduce music gain by 4 dB when VO is present
# (approximate sidechain via VO envelope)
def simple_duck(music, vo, reduction_db=4.0, attack=0.05, release=0.2):
    env = np.abs(vo)
    # smooth the envelope with a moving average (attack/release)
    win = max(int(attack * SR), 1)
    kernel = np.ones(win) / win
    env_smooth = np.convolve(env, kernel, mode='same')
    env_smooth = env_smooth / max(env_smooth.max(), 1e-9)
    # additional slow release
    win2 = max(int(release * SR), 1)
    kernel2 = np.ones(win2) / win2
    env_smooth = np.convolve(env_smooth, kernel2, mode='same')
    gain_lin = 1.0 - env_smooth * (1 - 10**(-reduction_db/20))
    return music * gain_lin

music_ducked = simple_duck(music_mono.astype(np.float32), vo_track, reduction_db=5.0)

# ----------------------------------------------------------------------------
# 4. FINAL MIX — mono → stereo (slightly pan music left/right for width)
# ----------------------------------------------------------------------------
mono_mix = music_ducked + sfx + vo_track
mono_mix = mono_mix / np.max(np.abs(mono_mix)) * 0.85  # normalize to -1.4 dBFS

# stereo: tiny pan on music for width, VO + SFX center
left  = music_ducked * 0.85 + sfx + vo_track
right = music_ducked * 1.15 + sfx + vo_track
stereo = np.stack([left, right], axis=1)
stereo = stereo / np.max(np.abs(stereo)) * 0.85

# write final mix
out_path = os.path.join(AUDIO_DIR, "mix.wav")
wavfile.write(out_path, SR, (stereo * 32767).astype(np.int16))
print(f"Wrote mix → {out_path}  ({DUR:.1f}s, {SR}Hz stereo)")

# also write individual stems for debugging
wavfile.write(os.path.join(AUDIO_DIR, "music.wav"), SR, (music_mono * 32767 * 0.18 / 0.18).astype(np.int16))
wavfile.write(os.path.join(AUDIO_DIR, "sfx.wav"), SR, (sfx * 32767).astype(np.int16))
wavfile.write(os.path.join(AUDIO_DIR, "vo.wav"), SR, (vo_track * 32767).astype(np.int16))
print("Stems: music.wav, sfx.wav, vo.wav")
