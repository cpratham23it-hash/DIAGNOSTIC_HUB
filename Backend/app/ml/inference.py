"""
app/ml/inference.py — Production inference module for Module 3.

This is what the FastAPI audio diagnosis endpoint imports and calls.
Everything else in ml/ (preprocess, train, evaluate) is training-time only
and never imported by the running web server.

Usage from the FastAPI router:
    from app.ml.inference import AudioClassifier, get_classifier

    classifier = get_classifier()            # singleton, loads model once
    result = classifier.predict(wav_bytes)   # returns a PredictionResult

The classifier maps an uploaded audio file → anomaly probability → fault name,
using the same log-mel spectrogram feature extraction as the training pipeline.
"""

import io
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import tensorflow as tf

# ── CONFIG (must match preprocess.py exactly) ─────────────────────────────────
SR          = 16000
N_MELS      = 128
N_FFT       = 1024
HOP_LENGTH  = 512
FRAME_SEC   = 1.0
FRAME_HOP   = 0.5
THRESHOLD   = 0.5    # anomaly probability above this = fault detected
# ─────────────────────────────────────────────────────────────────────────────

# Default model path — relative to the repo root (where uvicorn is run from).
# Can be overridden via the MODEL_PATH env var for deployment flexibility.
import os
MODEL_PATH = Path(os.getenv("AUDIO_MODEL_PATH", "ml/models/audio_model.keras"))
NORM_STATS_PATH = Path(os.getenv("AUDIO_NORM_STATS_PATH", "ml/features/norm_stats.npy"))


# Appliance-type → most likely fault name when anomaly is detected.
# These are deliberately conservative single-fault mappings, not fabricated
# multi-fault ranked lists. Once more training data exists per fault type
# (not just normal vs. abnormal), these can be replaced with actual per-class
# predictions from a multi-class model.
APPLIANCE_FAULT_MAP = {
    "fridge":   "Compressor Strain",
    "ac":       "Fan Blade Imbalance",
    "purifier": "Fan Motor Wear",
    # washer and camera not covered by fan model — caller should not reach here
}


@dataclass
class PredictionResult:
    anomaly_probability: float    # 0.0 to 1.0
    is_anomalous: bool            # True if probability >= THRESHOLD
    fault_name: Optional[str]     # None if not anomalous
    confidence: float             # 0-100, same scale as Module 2a fault library
    frames_analyzed: int          # how many 1-second frames were extracted
    message: str                  # human-readable summary


class AudioClassifier:
    """
    Wraps the trained Keras model for production inference.
    Thread-safe singleton — the model is loaded once and reused across
    concurrent requests (Keras/TF inference is thread-safe for prediction).
    """

    def __init__(self):
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Trained model not found at {MODEL_PATH}. "
                f"Run  python ml/train.py  to train it first."
            )
        self._model = tf.keras.models.load_model(MODEL_PATH)

        # Load normalization stats saved by preprocess.py — same mean/std
        # must be applied at inference time as was applied during training.
        if NORM_STATS_PATH.exists():
            stats = np.load(NORM_STATS_PATH)
            self._norm_mean = float(stats[0])
            self._norm_std  = float(stats[1])
        else:
            # If stats file is missing, fall back to no normalization with a warning.
            import warnings
            warnings.warn(
                f"Normalization stats not found at {NORM_STATS_PATH}. "
                f"Inference will run without normalization, which may degrade accuracy."
            )
            self._norm_mean = 0.0
            self._norm_std  = 1.0

    def _extract_frames(self, audio_bytes: bytes) -> np.ndarray:
        """Load audio from raw bytes, extract log-mel spectrogram frames.
        Returns array of shape (N_frames, N_MELS, frame_width, 1)."""
        y, _ = librosa.load(io.BytesIO(audio_bytes), sr=SR, mono=True)

        mel = librosa.feature.melspectrogram(
            y=y, sr=SR, n_fft=N_FFT, hop_length=HOP_LENGTH, n_mels=N_MELS
        )
        log_mel = librosa.power_to_db(mel, ref=np.max).astype(np.float32)

        frame_width = int(FRAME_SEC * SR / HOP_LENGTH)
        hop_frames  = int(FRAME_HOP * SR / HOP_LENGTH)

        frames = []
        start = 0
        while start + frame_width <= log_mel.shape[1]:
            frame = log_mel[:, start:start + frame_width]
            frames.append(frame[..., np.newaxis])
            start += hop_frames

        if not frames:
            # Audio too short for even one frame — pad and use what we have
            padded = np.zeros((N_MELS, frame_width), dtype=np.float32)
            padded[:, :log_mel.shape[1]] = log_mel
            frames = [padded[..., np.newaxis]]

        arr = np.stack(frames, axis=0).astype(np.float32)

        # Apply the same normalization used during training
        arr = (arr - self._norm_mean) / (self._norm_std + 1e-8)
        return arr

    def predict(self, audio_bytes: bytes, appliance_type: str = "fridge") -> PredictionResult:
        """
        Given raw audio file bytes and the appliance type, return a
        PredictionResult with the anomaly probability and mapped fault name.

        appliance_type must be one of: fridge, ac, purifier
        (washer and camera are not covered by the fan model).
        """
        frames = self._extract_frames(audio_bytes)
        probs  = self._model.predict(frames, batch_size=32, verbose=0).flatten()

        # Aggregate frame-level probabilities into a clip-level score.
        # Mean is simple and robust; max would catch brief anomalies better
        # but is noisier. Mean is the right default here since MIMII anomalies
        # are typically sustained, not impulsive.
        clip_prob = float(np.mean(probs))

        is_anomalous = clip_prob >= THRESHOLD
        fault_name   = APPLIANCE_FAULT_MAP.get(appliance_type) if is_anomalous else None
        confidence   = round(clip_prob * 100, 1) if is_anomalous else round((1 - clip_prob) * 100, 1)

        if is_anomalous:
            msg = (f"Anomalous sound detected ({clip_prob:.1%} probability). "
                   f"Most likely: {fault_name}.")
        else:
            msg = f"Sound appears normal ({1 - clip_prob:.1%} confidence)."

        return PredictionResult(
            anomaly_probability=clip_prob,
            is_anomalous=is_anomalous,
            fault_name=fault_name,
            confidence=confidence,
            frames_analyzed=len(frames),
            message=msg,
        )


# ── Singleton pattern ─────────────────────────────────────────────────────────
# The model is large enough that loading it on every request would be slow.
# This singleton loads it once at startup and reuses it across all requests.

_classifier: Optional[AudioClassifier] = None
_lock = threading.Lock()


def get_classifier() -> AudioClassifier:
    """Returns the singleton AudioClassifier, loading it on first call."""
    global _classifier
    if _classifier is None:
        with _lock:
            if _classifier is None:
                _classifier = AudioClassifier()
    return _classifier


def model_is_available() -> bool:
    """True if the trained model file exists. Used at startup to decide
    whether to advertise audio analysis as available."""
    return MODEL_PATH.exists()