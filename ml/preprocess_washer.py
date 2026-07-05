"""
ml/preprocess_washer.py — Preprocessing for CWRU bearing dataset (washer model).

Loads .npz files from ml/data/washer/CWRU_Bearing_NumPy-main/Data/,
extracts STFT-based spectrogram features from the Drive End (DE) channel,
and saves feature arrays to ml/features/.

Key difference from preprocess.py (fan/audio):
  - Input is vibration time-series (accelerometer), not microphone audio
  - Sampled at 12kHz (some files at 48kHz — we resample to 12kHz)
  - Uses raw power spectrogram instead of mel spectrogram — mel warping
    compresses the high-frequency range where bearing fault harmonics live,
    which is counterproductive for vibration fault detection
  - Label comes from filename: 'Normal' in name → 0, anything else → 1

Run from the repo root (pratham/ folder):
    python ml/preprocess_washer.py
"""

import json
import re
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

# ── CONFIG ────────────────────────────────────────────────────────────────────
DATA_DIR    = Path("ml/data/washer/CWRU_Bearing_NumPy-main/Data")
OUTPUT_DIR  = Path("ml/features")
SR          = 12000    # target sample rate — resample 48kHz files down to this
N_FFT       = 512      # FFT window — smaller than audio pipeline since SR is lower
HOP_LENGTH  = 256      # 50% overlap
FRAME_SEC   = 1.0      # each training sample = 1 second of vibration
FRAME_HOP   = 1.0      # no overlap between frames (memory constraint)
CHANNEL     = "DE"     # Drive End — most informative channel for bearing faults
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_label(filename: str) -> int:
    """Normal in filename → 0, any fault → 1."""
    return 0 if "Normal" in filename else 1


def get_sr_from_filename(filename: str) -> int:
    """Infer sample rate from filename suffix: DE12→12kHz, DE48→48kHz, FE→12kHz."""
    if "48" in filename:
        return 48000
    return 12000


def extract_spectrogram(signal: np.ndarray, file_sr: int) -> np.ndarray:
    """
    Convert raw vibration time-series to a power spectrogram.
    Returns shape (N_FFT//2+1, time_frames).
    """
    sig = signal.flatten().astype(np.float32)

    # Resample to target SR if needed
    if file_sr != SR:
        sig = resample_poly(sig, SR, file_sr).astype(np.float32)

    # Normalize signal amplitude
    sig = sig / (np.max(np.abs(sig)) + 1e-8)

    # STFT → power spectrogram
    from numpy.lib.stride_tricks import sliding_window_view
    n_samples = len(sig)
    window = np.hanning(N_FFT).astype(np.float32)

    starts = np.arange(0, n_samples - N_FFT + 1, HOP_LENGTH)
    frames = np.array([sig[s:s + N_FFT] * window for s in starts])  # (T, N_FFT)
    spectrogram = np.abs(np.fft.rfft(frames, n=N_FFT)) ** 2  # (T, N_FFT//2+1)
    log_spec = np.log1p(spectrogram).T.astype(np.float32)   # (N_FFT//2+1, T)
    return log_spec


def split_into_frames(spectrogram: np.ndarray) -> list:
    """Split spectrogram into fixed-length 1-second frames."""
    frame_width = int(FRAME_SEC * SR / HOP_LENGTH)
    hop_frames  = int(FRAME_HOP * SR / HOP_LENGTH)
    total_cols  = spectrogram.shape[1]

    frames = []
    start = 0
    while start + frame_width <= total_cols:
        frames.append(spectrogram[:, start:start + frame_width])
        start += hop_frames
    return frames


def main():
    rpm_dirs = sorted([d for d in DATA_DIR.iterdir() if d.is_dir() and "RPM" in d.name])
    if not rpm_dirs:
        raise RuntimeError(f"No RPM subdirectories found in {DATA_DIR}.")

    print(f"Loading washer data from {DATA_DIR}")
    print(f"Found RPM folders: {[d.name for d in rpm_dirs]}")

    all_X_files = []
    all_y = []
    all_meta = []

    for rpm_dir in rpm_dirs:
        X_batch, y_batch, meta_batch = [], [], []
        npz_files = sorted(rpm_dir.glob("*.npz"))
        print(f"\n  {rpm_dir.name}: {len(npz_files)} files")

        for npz_path in npz_files:
            try:
                data = np.load(npz_path)
                if CHANNEL not in data:
                    print(f"    SKIP (no {CHANNEL} channel): {npz_path.name}")
                    continue

                signal = data[CHANNEL]
                file_sr = get_sr_from_filename(npz_path.name)
                label = get_label(npz_path.name)

                spec = extract_spectrogram(signal, file_sr)
                frames = split_into_frames(spec)

                for frame in frames:
                    X_batch.append(frame[..., np.newaxis])  # (freq_bins, T, 1)
                    y_batch.append(label)
                    meta_batch.append({
                        "file": str(npz_path),
                        "label": label,
                        "rpm": rpm_dir.name,
                        "condition": "normal" if label == 0 else "fault",
                    })

            except Exception as e:
                print(f"    ERROR loading {npz_path.name}: {e}")

        if not X_batch:
            continue

        chunk_path = OUTPUT_DIR / f"X_washer_{rpm_dir.name.replace(' ', '_')}.npy"
        X_arr = np.stack(X_batch, axis=0).astype(np.float32)
        np.save(chunk_path, X_arr)
        all_X_files.append(chunk_path)
        all_y.extend(y_batch)
        all_meta.extend(meta_batch)
        print(f"    Saved {len(X_batch)} frames → {chunk_path.name}")
        del X_batch, X_arr

    if not all_y:
        raise RuntimeError("No frames extracted. Check your data path and file structure.")

    print("\nMerging chunks...")
    try:
        chunks = [np.load(f) for f in all_X_files]
        X_all = np.concatenate(chunks, axis=0).astype(np.float32)
        del chunks

        mean = float(X_all.mean())
        std  = float(X_all.std()) + 1e-8
        X_all = ((X_all - mean) / std).astype(np.float32)

        y_arr = np.array(all_y, dtype=np.int32)

        print(f"\nExtracted {len(X_all)} frames from {len(set(m['file'] for m in all_meta))} files.")
        print(f"Normal frames:   {(y_arr == 0).sum()}")
        print(f"Fault frames:    {(y_arr == 1).sum()}")
        print(f"Feature shape:   {X_all.shape}")

        np.save(OUTPUT_DIR / "X_washer.npy", X_all)
        np.save(OUTPUT_DIR / "y_washer.npy", y_arr)
        np.save(OUTPUT_DIR / "norm_stats_washer.npy", np.array([mean, std], dtype=np.float32))

        with open(OUTPUT_DIR / "meta_washer.json", "w") as f:
            json.dump(all_meta, f, indent=2)

        for f in all_X_files:
            f.unlink()

        print(f"\nSaved to {OUTPUT_DIR}/")
        print("  X_washer.npy, y_washer.npy, norm_stats_washer.npy, meta_washer.json")

    except MemoryError:
        print("\nWARNING: OOM during merge — keeping chunk files.")
        y_arr = np.array(all_y, dtype=np.int32)
        np.save(OUTPUT_DIR / "y_washer.npy", y_arr)
        with open(OUTPUT_DIR / "meta_washer.json", "w") as f:
            json.dump(all_meta, f, indent=2)
        c0 = np.load(all_X_files[0]).astype(np.float32)
        mean, std = float(c0.mean()), float(c0.std()) + 1e-8
        del c0
        np.save(OUTPUT_DIR / "norm_stats_washer.npy", np.array([mean, std], dtype=np.float32))
        print("Saved y_washer.npy, meta_washer.json, norm_stats_washer.npy")

    print("\nNext: run  python ml/train_washer.py")


if __name__ == "__main__":
    main()