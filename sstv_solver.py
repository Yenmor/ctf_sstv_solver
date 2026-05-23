#!/usr/bin/env python3
"""
CTF SSTV Solver — Automated Slow-Scan Television decoder for CTF challenges.

Decodes SSTV audio (WAV) into images. Auto-detects VIS codes for
standard modes; falls back to multi-strategy brute-force for unknown
or corrupted signals.

Usage:
    python sstv_solver.py signal.wav              # single file
    python sstv_solver.py signal.wav -o out/      # custom output dir
    python sstv_solver.py ./captures/             # batch: all WAVs in dir
    python sstv_solver.py a.wav b.wav             # batch: multiple files
    python sstv_solver.py --list-modes            # show supported modes

Output:
    For standard VIS:  out/<name>_001.png
    For unknown VIS:   out/<name>_001_01_Martin_M1_GBR_light.png ...
                       (6 strategy variants)
    For batch:         out/<file1>/...  out/<file2>/...
"""

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, sosfilt, hilbert, medfilt
from PIL import Image
import os, sys, argparse
from pathlib import Path

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════
# SSTV Mode Registry
# ═══════════════════════════════════════════════════════════════

MODE_REGISTRY = {
    1:  ("Robot 8 (B&W)",   "gray",   160, 120, 44.0,   9.0, 2.0),
    2:  ("Robot 12 (B&W)",  "gray",   160, 120, 66.0,   9.0, 2.0),
    4:  ("Martin M1",       "rgb",    320, 256, 146.432, 4.862, 0.572),
    5:  ("Martin M2",       "rgb",    320, 256, 73.216,  4.862, 0.572),
    8:  ("Robot 36",        "ycc",    320, 240, 88.0,   9.0, 3.0),
    12: ("Robot 72",        "ycc",    320, 240, 138.0,  9.0, 3.0),
    44: ("Martin M3",       "ycc",    320, 256, 146.432, 4.862, 0.572),
    45: ("Martin M4",       "ycc",    320, 256, 73.216,  4.862, 0.572),
    56: ("Scottie S2",      "rgb",    320, 256, 73.216,  9.0, 1.5),
    60: ("Scottie S1",      "rgb",    320, 256, 146.432, 9.0, 1.5),
    76: ("Scottie DX",      "rgb",    320, 256, 293.0,   9.0, 1.5),
    93: ("PD50",            "ycc",    320, 256, 80.0,    20.0, 2.08),
    94: ("PD90",            "ycc",    320, 256, 144.0,   20.0, 2.08),
    95: ("PD120",           "ycc",    640, 496, 190.0,   20.0, 2.08),
    96: ("PD160",           "ycc",    512, 400, 256.0,   20.0, 2.08),
    97: ("PD180",           "ycc",    640, 496, 288.0,   20.0, 2.08),
    98: ("PD240",           "ycc",    640, 496, 384.0,   20.0, 2.08),
    99: ("PD290",           "ycc",    800, 616, 464.0,   20.0, 2.08),
}

BLACK_FREQ = 1500
WHITE_FREQ = 2300

# Multi-strategy fallback for unknown VIS codes
FALLBACK_STRATEGIES = [
    ("Martin_M1_GBR",       "rgb",       4,  320, 256, 146.432, 4.862, 0.572),
    ("Martin_M1_heavy",     "rgb-heavy", 4,  320, 256, 146.432, 4.862, 0.572),
    ("RGB_Serial_320x255",  "rgb_serial",83, 320, 255, 441.0,  5.2,   1.0),
    ("Scottie_S1_GRB",      "rgb-grb",   60, 320, 256, 146.432, 9.0,   1.5),
    ("Robot_36_YCC",        "ycc",       8,  320, 256, 88.0,    9.0,   3.0),
    ("Gray_320x255",        "gray",      1,  320, 255, 441.0,  5.2,   1.0),
]


def list_modes():
    """Print supported SSTV modes."""
    print("\nSupported SSTV modes:\n")
    print(f"  {'VIS':<6} {'Name':<20} {'Encoding':<8} {'Resolution':<12}")
    print(f"  {'-'*6} {'-'*20} {'-'*8} {'-'*12}")
    for vis, (name, enc, w, h, scan, sync, porch) in sorted(MODE_REGISTRY.items()):
        print(f"  {vis:<6} {name:<20} {enc:<8} {w}x{h}")
    print()


# ═══════════════════════════════════════════════════════════════
# Signal Processing
# ═══════════════════════════════════════════════════════════════

def load_audio(filepath):
    """Load WAV, return (sample_rate, mono_float32_samples)."""
    sample_rate, data = wavfile.read(filepath)
    if data.ndim == 2:
        data = data.mean(axis=1)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128) / 128.0
    elif data.dtype == np.float32 or data.dtype == np.float64:
        data = data.astype(np.float32)
    else:
        data = data.astype(np.float32)
        mx = np.max(np.abs(data))
        if mx > 0:
            data /= mx
    return sample_rate, data


def bandpass_filter(data, sample_rate, low=800, high=2600, order=4):
    """Butterworth bandpass filter."""
    nyq = sample_rate / 2
    sos = butter(order, [low/nyq, high/nyq], btype='band', output='sos')
    return sosfilt(sos, data)


def compute_ifreq(signal, sample_rate):
    """FM demodulate via Hilbert transform -> instantaneous frequency (Hz)."""
    analytic = hilbert(signal)
    phase = np.unwrap(np.angle(analytic))
    ifreq = np.diff(phase) * sample_rate / (2.0 * np.pi)
    return np.append(ifreq, ifreq[-1])


def freq_to_pixel(freq):
    """Map frequency (Hz) to 0-255 pixel value."""
    return int(np.clip((freq - BLACK_FREQ) / (WHITE_FREQ - BLACK_FREQ) * 255.0, 0, 255))


def smooth_ifreq(ifreq, sample_rate, kernel_size=0):
    """Median-filter IF signal. Default kernel ~1ms."""
    if kernel_size <= 0:
        kernel_size = max(3, int(0.001 * sample_rate)) | 1
    return medfilt(ifreq, kernel_size)


# ═══════════════════════════════════════════════════════════════
# VIS Detection
# ═══════════════════════════════════════════════════════════════

def detect_vis(ifreq, sample_rate):
    """
    Scan IF for SSTV VIS codes. Handles variable-length leaders.

    Returns list of (vis_code, leader_start_sample) tuples.
    """
    vis_list = []
    n = len(ifreq)
    bit30 = int(0.030 * sample_rate)
    bit10 = int(0.010 * sample_rate)
    leader_min = int(0.300 * sample_rate)
    edge_skip = int(0.050 * sample_rate)

    i = edge_skip

    while i < n - leader_min - int(0.500 * sample_rate):
        if not (1850 < np.mean(ifreq[i:i + leader_min]) < 2050):
            i += bit10
            continue

        leader_end = i + leader_min
        while (leader_end + bit30 <= n
               and 1800 < np.mean(ifreq[leader_end:leader_end + bit30]) < 2050):
            leader_end += bit30

        search_limit = min(leader_end + int(0.150 * sample_rate), n - bit10)
        break_pos = None
        for k in range(leader_end, search_limit, bit10 // 2):
            if k + bit10 > n:
                break
            if 1000 < np.mean(ifreq[k:k + bit10]) < 1400:
                break_pos = k
                break

        if break_pos is None:
            i += bit10
            continue

        p = break_pos + bit10

        if p + bit30 > n:
            break
        if not (1000 < np.mean(ifreq[p:p + bit30]) < 1400):
            i += bit10
            continue
        p += bit30

        bits = []
        ok = True
        for _ in range(8):
            if p + bit30 > n:
                ok = False
                break
            avg = np.mean(ifreq[p:p + bit30])
            if 900 < avg < 1200:
                bits.append(0)
            elif 1200 <= avg < 1500:
                bits.append(1)
            else:
                ok = False
                break
            p += bit30

        if not ok or len(bits) != 8:
            i += bit10
            continue

        if p + bit30 > n:
            break
        if not (1000 < np.mean(ifreq[p:p + bit30]) < 1400):
            i += bit10
            continue
        p += bit30

        vis_code = sum(b << idx for idx, b in enumerate(bits))
        vis_list.append((vis_code, i))
        i = p

    return vis_list


def find_sync_pulses(ifreq, sample_rate):
    """Find 1200 Hz sync pulses. Returns [(start, end), ...]."""
    in_sync = (ifreq > 1000) & (ifreq < 1400)
    min_samples = int(0.0015 * sample_rate)
    edges = np.diff(np.concatenate([[0], in_sync.astype(int), [0]]))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]
    return [(s, e) for s, e in zip(starts, ends) if e - s >= min_samples]


def extract_line_pixels(ifreq, data_start, scan_duration_ms, num_pixels, sample_rate):
    """Extract pixel values from a scan line."""
    total_samples = int(scan_duration_ms * sample_rate / 1000.0)
    samples_per_px = total_samples / num_pixels
    pixels = []
    for i in range(num_pixels):
        center = int(data_start + (i + 0.5) * samples_per_px)
        half_win = max(1, int(samples_per_px / 2))
        start = max(0, center - half_win)
        end = min(len(ifreq), center + half_win)
        if start >= end:
            pixels.append(0)
            continue
        pixels.append(freq_to_pixel(np.mean(ifreq[start:end])))
    return pixels


# ═══════════════════════════════════════════════════════════════
# Decoders
# ═══════════════════════════════════════════════════════════════

def decode_rgb(ifreq, sample_rate, start_idx, width, height,
               scan_ms, sync_ms, porch_ms):
    """Decode line-sequential RGB (Martin/Scottie). G-B-R line order."""
    total_line_ms = sync_ms + porch_ms + scan_ms
    total_line_samp = int(total_line_ms * sample_rate / 1000.0)
    sync_samp = int(sync_ms * sample_rate / 1000.0)
    porch_samp = int(porch_ms * sample_rate / 1000.0)
    scan_samp = int(scan_ms * sample_rate / 1000.0)

    r_plane = np.zeros((height, width), dtype=np.uint8)
    g_plane = np.zeros((height, width), dtype=np.uint8)
    b_plane = np.zeros((height, width), dtype=np.uint8)

    pos = start_idx
    line_idx = 0

    while line_idx < height * 3 and pos + total_line_samp < len(ifreq):
        data_start = pos + sync_samp + porch_samp
        data_end = data_start + scan_samp
        if data_end > len(ifreq):
            break

        pixels = extract_line_pixels(ifreq, data_start, scan_ms, width, sample_rate)

        channel = line_idx % 3
        row = line_idx // 3
        if row < height:
            if channel == 0:
                g_plane[row] = pixels
            elif channel == 1:
                b_plane[row] = pixels
            else:
                r_plane[row] = pixels

        pos += total_line_samp
        line_idx += 1

    for row in range(height):
        if np.all(r_plane[row] == 0):
            r_plane[row] = r_plane[max(0, row - 1)]
        if np.all(g_plane[row] == 0):
            g_plane[row] = g_plane[max(0, row - 1)]
        if np.all(b_plane[row] == 0):
            b_plane[row] = b_plane[max(0, row - 1)]

    return np.stack([r_plane, g_plane, b_plane], axis=2)


def decode_rgb_serial(ifreq, sample_rate, start_idx, width, height,
                      total_scan_ms, sync_ms, porch_ms):
    """Decode serial RGB (all 3 channels in one line, ~3ms gaps)."""
    chan_gap_ms = 3.0
    chan_scan_ms = (total_scan_ms - 2 * chan_gap_ms) / 3.0

    sync_samp = int(sync_ms * sample_rate / 1000.0)
    porch_samp = int(porch_ms * sample_rate / 1000.0)
    chan_scan_samp = int(chan_scan_ms * sample_rate / 1000.0)
    chan_gap_samp = int(chan_gap_ms * sample_rate / 1000.0)

    r_plane = np.zeros((height, width), dtype=np.uint8)
    g_plane = np.zeros((height, width), dtype=np.uint8)
    b_plane = np.zeros((height, width), dtype=np.uint8)

    pos = start_idx
    line_idx = 0

    while line_idx < height and pos < len(ifreq):
        if pos + sync_samp > len(ifreq):
            break
        pos += sync_samp
        if pos + porch_samp > len(ifreq):
            break
        pos += porch_samp

        for plane, _name in [(r_plane, 'R'), (g_plane, 'G'), (b_plane, 'B')]:
            ch_end = pos + chan_scan_samp
            if ch_end > len(ifreq):
                break
            plane[line_idx] = extract_line_pixels(
                ifreq, pos, chan_scan_ms, width, sample_rate)
            pos = ch_end + chan_gap_samp

        line_idx += 1

    return np.stack([r_plane, g_plane, b_plane], axis=2)


def decode_ycc_robot(ifreq, sample_rate, start_idx, width, height,
                     y_scan_ms, sync_ms, porch_ms):
    """Decode YCrCb Robot-mode (Robot 36/72)."""
    sync_samp = int(sync_ms * sample_rate / 1000.0)
    porch_samp = int(porch_ms * sample_rate / 1000.0)
    y_scan_samp = int(y_scan_ms * sample_rate / 1000.0)
    c_porch_ms = 1.5
    c_scan_ms = y_scan_ms / 2.0
    c_porch_samp = int(c_porch_ms * sample_rate / 1000.0)
    c_scan_samp = int(c_scan_ms * sample_rate / 1000.0)

    y_plane = np.zeros((height, width), dtype=np.uint8)
    cr_plane = np.zeros((height, width), dtype=np.uint8)
    cb_plane = np.zeros((height, width), dtype=np.uint8)

    pos = start_idx
    line_idx = 0

    while line_idx < height and pos < len(ifreq):
        if pos + sync_samp > len(ifreq):
            break
        pos += sync_samp
        if pos + porch_samp > len(ifreq):
            break
        pos += porch_samp

        y_end = pos + y_scan_samp
        if y_end > len(ifreq):
            break
        y_plane[line_idx] = extract_line_pixels(ifreq, pos, y_scan_ms, width, sample_rate)
        pos = y_end

        if pos + c_porch_samp > len(ifreq):
            break
        pos += c_porch_samp

        c_end = pos + c_scan_samp
        if c_end > len(ifreq):
            break
        c_pixels = extract_line_pixels(ifreq, pos, c_scan_ms, width, sample_rate)
        if line_idx % 2 == 0:
            cr_plane[line_idx] = c_pixels
        else:
            cb_plane[line_idx] = c_pixels
        pos = c_end
        line_idx += 1

    for row in range(height):
        if row > 0 and np.all(cr_plane[row] == 0):
            cr_plane[row] = cr_plane[row - 1]
        if row > 0 and np.all(cb_plane[row] == 0):
            cb_plane[row] = cb_plane[row - 1]
    for row in range(height - 1, -1, -1):
        if row < height - 1 and np.all(cr_plane[row] == 0):
            cr_plane[row] = cr_plane[row + 1]
        if row < height - 1 and np.all(cb_plane[row] == 0):
            cb_plane[row] = cb_plane[row + 1]

    return _ycc_to_rgb(y_plane, cr_plane, cb_plane)


def decode_ycc_pd(ifreq, sample_rate, start_idx, width, height,
                  scan_ms, sync_ms, porch_ms):
    """Decode YCrCb PD-mode (PD50-PD290)."""
    sync_samp = int(sync_ms * sample_rate / 1000.0)
    porch_samp = int(porch_ms * sample_rate / 1000.0)
    y_scan_samp = int(scan_ms * sample_rate / 1000.0)
    c_porch_ms = 1.5
    c_scan_ms = scan_ms / 2.0
    c_porch_samp = int(c_porch_ms * sample_rate / 1000.0)
    c_scan_samp = int(c_scan_ms * sample_rate / 1000.0)

    y_plane = np.zeros((height, width), dtype=np.uint8)
    cr_plane = np.zeros((height, width), dtype=np.uint8)
    cb_plane = np.zeros((height, width), dtype=np.uint8)

    pos = start_idx
    line_idx = 0

    while line_idx < height and pos < len(ifreq):
        if pos + sync_samp > len(ifreq):
            break
        pos += sync_samp
        if pos + porch_samp > len(ifreq):
            break
        pos += porch_samp

        y_end = pos + y_scan_samp
        if y_end > len(ifreq):
            break
        y_plane[line_idx] = extract_line_pixels(ifreq, pos, scan_ms, width, sample_rate)
        pos = y_end

        if pos + c_porch_samp > len(ifreq):
            break
        pos += c_porch_samp

        c_end = pos + c_scan_samp
        if c_end > len(ifreq):
            break
        c_pixels = extract_line_pixels(ifreq, pos, c_scan_ms, width, sample_rate)
        if line_idx % 2 == 0:
            cr_plane[line_idx] = c_pixels
        else:
            cb_plane[line_idx] = c_pixels
        pos = c_end
        line_idx += 1

    for row in range(height):
        if row > 0 and np.all(cr_plane[row] == 0):
            cr_plane[row] = cr_plane[row - 1]
        if row > 0 and np.all(cb_plane[row] == 0):
            cb_plane[row] = cb_plane[row - 1]
    for row in range(height - 1, -1, -1):
        if row < height - 1 and np.all(cr_plane[row] == 0):
            cr_plane[row] = cr_plane[row + 1]
        if row < height - 1 and np.all(cb_plane[row] == 0):
            cb_plane[row] = cb_plane[row + 1]

    return _ycc_to_rgb(y_plane, cr_plane, cb_plane)


def decode_gray(ifreq, sample_rate, start_idx, width, height,
                scan_ms, sync_ms, porch_ms):
    """Decode grayscale SSTV."""
    sync_samp = int(sync_ms * sample_rate / 1000.0)
    porch_samp = int(porch_ms * sample_rate / 1000.0)
    scan_samp = int(scan_ms * sample_rate / 1000.0)

    gray_plane = np.zeros((height, width), dtype=np.uint8)
    pos = start_idx
    line_idx = 0

    while line_idx < height and pos < len(ifreq):
        if pos + sync_samp > len(ifreq):
            break
        pos += sync_samp
        if pos + porch_samp > len(ifreq):
            break
        pos += porch_samp

        data_end = pos + scan_samp
        if data_end > len(ifreq):
            break
        gray_plane[line_idx] = extract_line_pixels(ifreq, pos, scan_ms, width, sample_rate)
        pos = data_end
        line_idx += 1

    return np.stack([gray_plane] * 3, axis=2)


def _ycc_to_rgb(y, cr, cb):
    """ITU-R BT.601 YCrCb -> RGB."""
    y = y.astype(np.float32)
    cr = cr.astype(np.float32) - 128.0
    cb = cb.astype(np.float32) - 128.0
    r = y + 1.402 * cr
    g = y - 0.34414 * cb - 0.71414 * cr
    b = y + 1.772 * cb
    return np.stack([
        np.clip(r, 0, 255).astype(np.uint8),
        np.clip(g, 0, 255).astype(np.uint8),
        np.clip(b, 0, 255).astype(np.uint8),
    ], axis=2)


# ═══════════════════════════════════════════════════════════════
# Decode Orchestrator
# ═══════════════════════════════════════════════════════════════

def decode_sstv(ifreq, sample_rate, vis_code, start_idx):
    """
    Decode one SSTV image. Returns [(PIL.Image, variant_name), ...].
    Known VIS -> single result; unknown -> 6-strategy fallback.
    """
    search_start = start_idx + int(1.0 * sample_rate)
    sync_pulses = find_sync_pulses(ifreq[search_start:], sample_rate)
    if sync_pulses:
        data_start = search_start + sync_pulses[0][0]
    else:
        data_start = start_idx + int(0.500 * sample_rate)

    results = []

    if vis_code in MODE_REGISTRY:
        name, enc, w, h, scan_ms, sync_ms, porch_ms = MODE_REGISTRY[vis_code]
        try:
            img_array = _decode_one(ifreq, sample_rate, data_start,
                                    enc, vis_code, w, h, scan_ms, sync_ms, porch_ms)
            results.append((Image.fromarray(img_array, mode='RGB'), name))
        except Exception as e:
            print(f"  [!] {name}: {e}")
    else:
        for variant, enc, vis_ref, w, h, scan_ms, sync_ms, porch_ms in FALLBACK_STRATEGIES:
            try:
                img_array = _decode_one(ifreq, sample_rate, data_start,
                                        enc, vis_ref, w, h, scan_ms, sync_ms, porch_ms)
                results.append((Image.fromarray(img_array, mode='RGB'), variant))
            except Exception as e:
                print(f"  [!] {variant}: {e}")

    return results


def _decode_one(ifreq, sample_rate, data_start, enc, vis_code,
                w, h, scan_ms, sync_ms, porch_ms):
    """Single strategy decode. Returns (H, W, 3) uint8 array."""
    if enc == "rgb":
        return decode_rgb(ifreq, sample_rate, data_start,
                          w, h, scan_ms, sync_ms, porch_ms)
    elif enc == "rgb-heavy":
        kernel = max(3, int(0.005 * sample_rate) | 1)
        ifreq_smooth = medfilt(ifreq, kernel)
        return decode_rgb(ifreq_smooth, sample_rate, data_start,
                          w, h, scan_ms, sync_ms, porch_ms)
    elif enc == "rgb-grb":
        temp = decode_rgb(ifreq, sample_rate, data_start,
                          w, h, scan_ms, sync_ms, porch_ms)
        result = temp.copy()
        result[:, :, 0], result[:, :, 2] = temp[:, :, 2].copy(), temp[:, :, 0].copy()
        return result
    elif enc == "ycc":
        if vis_code in {8, 12}:
            return decode_ycc_robot(ifreq, sample_rate, data_start,
                                    w, h, scan_ms, sync_ms, porch_ms)
        else:
            return decode_ycc_pd(ifreq, sample_rate, data_start,
                                 w, h, scan_ms, sync_ms, porch_ms)
    elif enc == "rgb_serial":
        return decode_rgb_serial(ifreq, sample_rate, data_start,
                                 w, h, scan_ms, sync_ms, porch_ms)
    elif enc == "gray":
        return decode_gray(ifreq, sample_rate, data_start,
                           w, h, scan_ms, sync_ms, porch_ms)
    else:
        raise ValueError(f"Unknown encoding: {enc}")


# ═══════════════════════════════════════════════════════════════
# Single-file processing
# ═══════════════════════════════════════════════════════════════

def process_file(audio_path, out_dir, no_filter=False):
    """Process one audio file, save images to out_dir."""
    print(f"\n  [*] {audio_path.name}")
    sample_rate, audio = load_audio(str(audio_path))
    duration = len(audio) / sample_rate
    print(f"      {sample_rate} Hz, {duration:.1f}s, "
          f"{'stereo' if audio.ndim == 2 else 'mono'}")

    if not no_filter:
        audio = bandpass_filter(audio, sample_rate)

    ifreq_raw = compute_ifreq(audio, sample_rate)
    vis_matches = detect_vis(ifreq_raw, sample_rate)

    # Smooth after VIS detection
    ifreq = smooth_ifreq(ifreq_raw, sample_rate)

    if not vis_matches:
        print(f"      No VIS detected, using multi-strategy brute-force...")
        vis_matches = [(255, int(0.050 * sample_rate))]

    base_name = audio_path.stem
    file_out = out_dir / base_name
    file_out.mkdir(parents=True, exist_ok=True)

    total_saved = 0
    for idx, (vis_code, start_pos) in enumerate(vis_matches):
        results = decode_sstv(ifreq, sample_rate, vis_code, start_pos)
        for var_idx, (img, variant_name) in enumerate(results):
            safe = variant_name.replace(" ", "_").replace("(", "").replace(")", "").replace(",", "")
            if len(results) == 1:
                fname = f"{base_name}_{idx + 1:03d}.png"
            else:
                fname = f"{base_name}_{idx + 1:03d}_{var_idx + 1:02d}_{safe}.png"
            img.save(str(file_out / fname))
            total_saved += 1

    print(f"      -> {total_saved} image(s) saved to {file_out.name}/")
    return total_saved


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="CTF SSTV Solver — Decode SSTV audio to images.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sstv_solver.py signal.wav              single file
  sstv_solver.py signal.wav -o out/      custom output dir
  sstv_solver.py ./captures/             batch: all WAVs in directory
  sstv_solver.py a.wav b.wav             batch: specific files
  sstv_solver.py --list-modes            show supported SSTV modes
        """)
    parser.add_argument("inputs", nargs="*",
                        help="Audio file(s) or directory of WAVs")
    parser.add_argument("-o", "--output", default=None,
                        help="Output root directory (default: ./sstv_output)")
    parser.add_argument("--list-modes", action="store_true",
                        help="List supported SSTV modes and exit")
    parser.add_argument("--no-filter", action="store_true",
                        help="Skip bandpass filtering")
    args = parser.parse_args()

    if args.list_modes:
        list_modes()
        return

    if not args.inputs:
        parser.print_help()
        print("\n  Provide at least one audio file or directory.")
        sys.exit(1)

    # Collect all input files
    audio_files = []
    for p in args.inputs:
        path = Path(p)
        if path.is_dir():
            audio_files.extend(sorted(path.glob("*.wav")))
        elif path.is_file():
            audio_files.append(path)
        else:
            print(f"  [!] Not found: {p}")

    if not audio_files:
        print("  No WAV files found.")
        sys.exit(1)

    # Output root
    out_root = Path(args.output) if args.output else Path.cwd() / "sstv_output"
    out_root.mkdir(parents=True, exist_ok=True)

    print(f"  CTF SSTV Solver")
    print(f"  {len(audio_files)} file(s) to process")
    print(f"  Output: {out_root.resolve()}")

    total = 0
    for af in audio_files:
        total += process_file(af, out_root, args.no_filter)

    print(f"\n  Done: {total} image(s) across {len(audio_files)} file(s)")
    print(f"  Output: {out_root.resolve()}")


if __name__ == "__main__":
    main()
