"""
ml/preprocess.py — Step 1 of the audio ML pipeline.

Loads all fan WAV files from ml/data/fan/, extracts log-mel spectrograms,
and saves the resulting feature arrays + labels as .npy files in ml/features/.

Run from the repo root (pratham/ folder, the one that contains ml/ and Backend/):
    python ml/preprocess.py

Output:
    ml/features/X_fan.npy  — shape (N, N_MELS, TIME_FRAMES, 1), float32
    ml/features/y_fan.npy  — shape (N,), int32  (0=normal, 1=abnormal)
    ml/features/meta_fan.json — file-level metadata for debugging/traceability

Design notes:
- Each 10-second WAV is split into overlapping 1-second frames with 50% hop.
  This multiplies the effective dataset size (more samples per file) while
  keeping each input small enough for a lightweight CNN.
- Log-mel spectrograms (128 mel bands) are the standard feature for this
  dataset — confirmed by the original MIMII baseline paper and every
  subsequent published result on this data.
- Labels come from folder structure: .../normal/... → 0, .../abnormal/... → 1
  This is the standard MIMII layout your fan/ data already uses.
"""

import json
import os
from pathlib import Path

import librosa
import numpy as np

# ── CONFIG ───────────────────────────────────────────────────────────────────
DATA_DIR    = Path("ml/data/fan/6_dB_fan/fan")
OUTPUT_DIR  = Path("ml/features")
SR          = 16000   # MIMII recorded at 16kHz
N_MELS      = 128     # mel filterbank size — standard for this dataset
N_FFT       = 1024    # FFT window size
HOP_LENGTH  = 512     # FFT hop — gives ~32ms resolution at 16kHz
FRAME_SEC   = 1.0     # each training sample = 1 second of audio
FRAME_HOP   = 1.0     # no overlap between frames — halves frame count vs 50% overlap
# ─────────────────────────────────────────────────────────────────────────────

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_log_mel(wav_path: Path) -> np.ndarray:
    """Load a WAV file and return its log-mel spectrogram as a 2D array.
    Shape: (N_MELS, time_frames)."""
    y, sr = librosa.load(wav_path, sr=SR, mono=True)
    mel = librosa.feature.melspectrogram(
        y=y, sr=sr, n_fft=N_FFT, hop_length=HOP_LENGTH, n_mels=N_MELS
    )
    log_mel = librosa.power_to_db(mel, ref=np.max)
    return log_mel.astype(np.float32)


def split_into_frames(log_mel: np.ndarray) -> list[np.ndarray]:
    """Split a full spectrogram into fixed-length 1-second frames with overlap.
    Returns a list of arrays, each shape (N_MELS, frame_width)."""
    frame_width = int(FRAME_SEC * SR / HOP_LENGTH)
    hop_frames  = int(FRAME_HOP * SR / HOP_LENGTH)
    total_cols  = log_mel.shape[1]

    frames = []
    start = 0
    while start + frame_width <= total_cols:
        frames.append(log_mel[:, start:start + frame_width])
        start += hop_frames
    return frames


def get_label(path: Path) -> int:
    """Infer label from the path: any component named 'abnormal' → 1, else → 0."""
    parts = {p.lower() for p in path.parts}
    return 1 if "abnormal" in parts else 0


def load_fan_data():
    X, y, meta = [], [], []

    machine_ids = sorted([d for d in DATA_DIR.iterdir() if d.is_dir()])
    if not machine_ids:
        raise RuntimeError(f"No machine-ID subdirectories found in {DATA_DIR}. "
                           f"Expected: fan/id_00/, fan/id_02/, etc.")

    for machine_dir in machine_ids:
        for condition in ["normal", "abnormal"]:
            condition_dir = machine_dir / condition
            if not condition_dir.exists():
                print(f"  SKIP (missing): {condition_dir}")
                continue

            wav_files = sorted(condition_dir.glob("*.wav"))
            print(f"  {machine_dir.name}/{condition}: {len(wav_files)} files")

            for wav_path in wav_files:
                try:
                    log_mel = extract_log_mel(wav_path)
                    frames  = split_into_frames(log_mel)
                    label   = get_label(wav_path)

                    for frame in frames:
                        X.append(frame[..., np.newaxis])  # add channel dim → (N_MELS, W, 1)
                        y.append(label)
                        meta.append({
                            "file": str(wav_path),
                            "label": label,
                            "machine_id": machine_dir.name,
                            "condition": condition,
                        })
                except Exception as e:
                    print(f"  ERROR loading {wav_path}: {e}")

    return X, y, meta


def main():
    print(f"Loading fan data from {DATA_DIR} ...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    machine_ids = sorted([d for d in DATA_DIR.iterdir() if d.is_dir()])
    if not machine_ids:
        raise RuntimeError(f"No machine-ID subdirectories found in {DATA_DIR}.")

    all_X_files = []
    all_y = []
    all_meta = []

    for machine_dir in machine_ids:
        X_batch, y_batch, meta_batch = [], [], []

        for condition in ["normal", "abnormal"]:
            condition_dir = machine_dir / condition
            if not condition_dir.exists():
                print(f"  SKIP (missing): {condition_dir}")
                continue

            wav_files = sorted(condition_dir.glob("*.wav"))
            print(f"  {machine_dir.name}/{condition}: {len(wav_files)} files")

            for wav_path in wav_files:
                try:
                    log_mel = extract_log_mel(wav_path)
                    frames  = split_into_frames(log_mel)
                    label   = get_label(wav_path)
                    for frame in frames:
                        X_batch.append(frame[..., np.newaxis])
                        y_batch.append(label)
                        meta_batch.append({
                            "file": str(wav_path),
                            "label": label,
                            "machine_id": machine_dir.name,
                            "condition": condition,
                        })
                except Exception as e:
                    print(f"  ERROR loading {wav_path}: {e}")

        if not X_batch:
            continue

        # Save this machine ID's data as a separate chunk to avoid OOM
        chunk_path = OUTPUT_DIR / f"X_fan_{machine_dir.name}.npy"
        X_arr = np.stack(X_batch, axis=0).astype(np.float32)
        np.save(chunk_path, X_arr)
        all_X_files.append(chunk_path)
        all_y.extend(y_batch)
        all_meta.extend(meta_batch)
        print(f"  Saved {len(X_batch)} frames for {machine_dir.name} → {chunk_path.name}")
        del X_batch, X_arr  # free RAM before next machine ID

    if not all_y:
        raise RuntimeError("No audio frames were extracted. Check your data path.")

    # Merge all chunks, compute normalization stats, save final arrays
    print("\nMerging chunks and computing normalization stats...")
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
        print(f"Abnormal frames: {(y_arr == 1).sum()}")
        print(f"Feature shape:   {X_all.shape}")

        np.save(OUTPUT_DIR / "X_fan.npy", X_all)
        np.save(OUTPUT_DIR / "y_fan.npy", y_arr)
        np.save(OUTPUT_DIR / "norm_stats.npy", np.array([mean, std], dtype=np.float32))
        del X_all

        with open(OUTPUT_DIR / "meta_fan.json", "w") as f:
            json.dump(all_meta, f, indent=2)

        # Clean up per-machine-ID chunk files only after successful merge
        for f in all_X_files:
            f.unlink()

        print(f"\nSaved to {OUTPUT_DIR}/")
        print("  X_fan.npy, y_fan.npy, norm_stats.npy, meta_fan.json")

    except MemoryError:
        # Final merge still OOM — keep the per-machine-ID chunks as-is.
        # train.py will detect and load them separately.
        print("\nWARNING: Not enough RAM to merge all chunks at once.")
        print("Keeping per-machine-ID chunk files — train.py will handle them.")
        y_arr = np.array(all_y, dtype=np.int32)
        np.save(OUTPUT_DIR / "y_fan.npy", y_arr)
        with open(OUTPUT_DIR / "meta_fan.json", "w") as f:
            json.dump(all_meta, f, indent=2)
        # Compute norm stats from first chunk only as an approximation
        c0 = np.load(all_X_files[0]).astype(np.float32)
        mean, std = float(c0.mean()), float(c0.std()) + 1e-8
        del c0
        np.save(OUTPUT_DIR / "norm_stats.npy", np.array([mean, std], dtype=np.float32))
        print(f"Saved y_fan.npy, meta_fan.json, norm_stats.npy (approx)")

    print("\nNext: run  python ml/train.py")


if __name__ == "__main__":
    main()