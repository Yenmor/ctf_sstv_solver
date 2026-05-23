# CTF SSTV Solver

Automated Slow-Scan Television (SSTV) decoder for CTF challenges.
Drop in a WAV file, get images out.

CTF 竞赛用 SSTV 音频自动解码器。丢 WAV 进去，出图片。

---

## Quick Start / 快速使用

### Release (recommended / 推荐)

Download the latest `sstv_solver` from [Releases](https://github.com/Yenmor/ctf_sstv_solver/releases).

从 [Releases](https://github.com/Yenmor/ctf_sstv_solver/releases) 下载最新的可执行文件。

| Platform | File | Usage / 用法 |
|----------|------|---------------|
| Windows (amd64) | `sstv_solver.exe` | `sstv_solver.exe signal.wav` |
| Linux (amd64) | `sstv_solver` | `./sstv_solver signal.wav` |

```bash
# Single file / 单个文件
sstv_solver signal.wav

# Custom output dir / 指定输出目录
sstv_solver signal.wav -o ./decoded/

# Batch: all WAVs in a directory / 批量：目录下所有 WAV
sstv_solver ./captures/

# Batch: specific files / 批量：指定多个文件
sstv_solver a.wav b.wav c.wav
```

### From source / 从源码运行

```bash
pip install -r requirements.txt
python sstv_solver.py signal.wav
```

---

## Supported Modes / 支持的模式

| VIS | Mode / 模式 | Resolution / 分辨率 |
|-----|-------------|---------------------|
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
| 93 | PD50 | 320x256 |
| 94 | PD90 | 320x256 |
| 95 | PD120 | 640x496 |
| 96 | PD160 | 512x400 |
| 97 | PD180 | 640x496 |
| 98 | PD240 | 640x496 |
| 99 | PD290 | 800x616 |

---

## How It Works / 工作原理

1. **Load** — reads WAV, auto-converts stereo to mono, normalizes
2. **Filter** — bandpass 800-2600 Hz Butterworth
3. **Demodulate** — Hilbert transform FM demodulation -> instantaneous frequency
4. **Detect VIS** — scans for 1900 Hz leader tone, parses 8-bit mode code
5. **Decode** — extracts pixel rows from the frequency signal
6. **Output** — saves PNG(s) to output directory

When the VIS code is not recognized (e.g. non-standard CTF challenges), the solver tries 6 fallback strategies:

1. **加载** — 读取 WAV，自动立体声转单声道，归一化
2. **滤波** — 800-2600 Hz 巴特沃斯带通滤波
3. **解调** — 希尔伯特变换 FM 解调 → 瞬时频率
4. **检测 VIS** — 扫描 1900 Hz 引导音，解析 8 位模式码
5. **解码** — 从频率信号中提取像素行
6. **输出** — 保存 PNG 到输出目录

遇到未知 VIS 码时，自动尝试 6 种回退策略：

| # | Strategy / 策略 | Resolution |
|---|-----------------|------------|
| 1 | Martin M1 (GBR) | 320x256 |
| 2 | Martin M1 (heavy smooth / 强平滑) | 320x256 |
| 3 | RGB Serial / 串行 | 320x255 |
| 4 | Scottie S1 (GRB) | 320x256 |
| 5 | Robot 36 (YCC) | 320x256 |
| 6 | Grayscale / 灰度 | 320x255 |

---

## Requirements / 依赖

- Python 3.9+
- numpy, scipy, Pillow

```bash
pip install -r requirements.txt
```

## License / 许可

GNU General Public License v3.0 — see [LICENSE](LICENSE).
