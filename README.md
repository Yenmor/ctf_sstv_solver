# CTF SSTV Solver

Automated Slow-Scan Television (SSTV) decoder for CTF challenges.  
Drop in a WAV file, get images out — auto-detects mode, falls back to multi-strategy brute-force when needed.

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Single file
python sstv_solver.py signal.wav

# Batch: all WAVs in a directory
python sstv_solver.py ./captures/

# Batch: specific files
python sstv_solver.py a.wav b.wav c.wav

# Custom output directory
python sstv_solver.py signal.wav -o ./decoded/

# List supported modes
python sstv_solver.py --list-modes
```

## Download (pre-built executables)

Grab the latest `sstv_solver` from [Releases](https://github.com/Yenmor/ctf_sstv_solver/releases).

| Platform | File |
|----------|------|
| Windows (amd64) | `sstv_solver.exe` |
| Linux (amd64) | `sstv_solver` |

Usage is identical to the Python version:

```bash
# Windows
sstv_solver.exe signal.wav

# Linux
./sstv_solver signal.wav -o ./out/
```

## Supported SSTV Modes

| VIS | Mode | Resolution |
|-----|------|------------|
| 1 | Robot 8 (B&W) | 160x120 |
| 2 | Robot 12 (B&W) | 160x120 |
| 4 | Martin M1 | 320x256 |
| 5 | Martin M2 | 320x256 |
| 8 | Robot 36 | 320x240 |
| 12 | Robot 72 | 320x240 |
| 44 | Martin M3 | 320x256 |
| 45 | Martin M4 | 320x256 |
| 56 | Scottie S2 | 320x256 |
| 60 | Scottie S1 | 320x256 |
| 76 | Scottie DX | 320x256 |
| 93-99 | PD50 — PD290 | 320-800px |

## How It Works

1. **Load** — reads WAV, auto-converts stereo to mono, normalizes
2. **Filter** — bandpass 800-2600 Hz Butterworth
3. **Demodulate** — Hilbert transform FM demodulation
4. **Detect VIS** — scans for the 1900 Hz leader tone, parses the 8-bit mode code
5. **Decode** — extracts pixel rows from the instantaneous frequency signal
6. **Output** — saves PNG(s) to the output directory

### Unknown VIS codes

When the VIS code isn't recognized (e.g. non-standard CTF challenges), the solver tries 6 strategies:

1. **Martin M1 (GBR, light)** — 320x256 line-sequential RGB
2. **Martin M1 (GBR, heavy)** — same with extra smoothing
3. **RGB Serial (320x255)** — all 3 channels in one sweep
4. **Scottie S1 (GRB)** — alternate channel order
5. **Robot 36 (YCC)** — YCrCb color model
6. **Gray (320x255)** — grayscale fallback

## Requirements

- Python 3.9+
- numpy, scipy, Pillow

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
