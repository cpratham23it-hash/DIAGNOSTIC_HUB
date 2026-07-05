"""
app/ml/inference.py — Production inference for Module 3.

Two trained models:
  - audio_model.keras    → fan-type sounds (fridge, ac, purifier)
  - washer_model.keras   → bearing vibration (washer)

Camera is excluded — no audio fault signature applies.
"""

import io
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import librosa
import numpy as np
import tensorflow as tf

# ── Fan/audio model config (must match preprocess.py) ────────────────────────
SR          = 16000
N_MELS      = 128
N_FFT       = 1024
HOP_LENGTH  = 512
FRAME_SEC   = 1.0
FRAME_HOP   = 1.0
THRESHOLD   = 0.5

# ── Washer/vibration model config (must match preprocess_washer.py) ───────────
WASHER_SR         = 12000
WASHER_N_FFT      = 512
WASHER_HOP_LENGTH = 256
WASHER_FRAME_SEC  = 1.0
WASHER_FRAME_HOP  = 1.0
WASHER_THRESHOLD  = 0.995
# ─────────────────────────────────────────────────────────────────────────────

AUDIO_MODEL_PATH  = Path(os.getenv("AUDIO_MODEL_PATH",  "ml/models/audio_model.keras"))
WASHER_MODEL_PATH = Path(os.getenv("WASHER_MODEL_PATH", "ml/models/washer_model.keras"))
NORM_STATS_PATH        = Path(os.getenv("AUDIO_NORM_STATS_PATH",  "ml/features/norm_stats.npy"))
WASHER_NORM_STATS_PATH = Path(os.getenv("WASHER_NORM_STATS_PATH", "ml/features/norm_stats_washer.npy"))

APPLIANCE_FAULT_MAP = {
    "fridge":   "Compressor Strain",
    "ac":       "Fan Blade Imbalance",
    "purifier": "Fan Motor Wear",
    "washer":   "Drum Bearing Wear",
}

FAN_APPLIANCES    = {"fridge", "ac", "purifier"}
WASHER_APPLIANCES = {"washer"}


@dataclass
class PredictionResult:
    anomaly_probability: float
    is_anomalous: bool
    fault_name: Optional[str]
    confidence: float
    frames_analyzed: int
    message: str


# ── Fan model ─────────────────────────────────────────────────────────────────

class AudioClassifier:
    def __init__(self):
        if not AUDIO_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Fan model not found at {AUDIO_MODEL_PATH}. Run  python ml/train.py  first."
            )
        self._model = tf.keras.models.load_model(AUDIO_MODEL_PATH)
        if NORM_STATS_PATH.exists():
            stats = np.load(NORM_STATS_PATH)
            self._mean, self._std = float(stats[0]), float(stats[1])
        else:
            import warnings
            warnings.warn(f"Fan norm stats not found at {NORM_STATS_PATH}.")
            self._mean, self._std = 0.0, 1.0

    def _extract_frames(self, audio_bytes: bytes) -> np.ndarray:
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
            frames.append(log_mel[:, start:start + frame_width][..., np.newaxis])
            start += hop_frames
        if not frames:
            padded = np.zeros((N_MELS, frame_width, 1), dtype=np.float32)
            padded[:, :log_mel.shape[1], 0] = log_mel
            frames = [padded]
        arr = np.stack(frames).astype(np.float32)
        return (arr - self._mean) / (self._std + 1e-8)

    def predict(self, audio_bytes: bytes, appliance_type: str = "fridge") -> PredictionResult:
        frames = self._extract_frames(audio_bytes)
        probs = self._model.predict(frames, batch_size=32, verbose=0).flatten()
        clip_prob = float(np.mean(probs))
        is_anomalous = clip_prob >= THRESHOLD
        fault_name = APPLIANCE_FAULT_MAP.get(appliance_type) if is_anomalous else None
        confidence = round(clip_prob * 100, 1) if is_anomalous else round((1 - clip_prob) * 100, 1)
        msg = (f"Anomalous sound detected ({clip_prob:.1%}). Most likely: {fault_name}."
               if is_anomalous else f"Sound appears normal ({1-clip_prob:.1%} confidence).")
        return PredictionResult(
            anomaly_probability=clip_prob, is_anomalous=is_anomalous,
            fault_name=fault_name, confidence=confidence,
            frames_analyzed=len(frames), message=msg,
        )


# ── Washer model ──────────────────────────────────────────────────────────────

class WasherClassifier:
    """
    Bearing fault detector trained on CWRU vibration data.
    Accepts the same audio bytes interface as AudioClassifier so the
    diagnoses router doesn't need to know which model it's using — it
    just calls predict() on whichever classifier get_classifier() returns.

    Note: trained on lab accelerometer data, not mic recordings. Real-world
    performance on phone mic audio will be lower than lab metrics suggest.
    """

    def __init__(self):
        if not WASHER_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Washer model not found at {WASHER_MODEL_PATH}. "
                f"Run  python ml/train_washer.py  first."
            )
        self._model = tf.keras.models.load_model(WASHER_MODEL_PATH)
        if WASHER_NORM_STATS_PATH.exists():
            stats = np.load(WASHER_NORM_STATS_PATH)
            self._mean, self._std = float(stats[0]), float(stats[1])
        else:
            import warnings
            warnings.warn(f"Washer norm stats not found at {WASHER_NORM_STATS_PATH}.")
            self._mean, self._std = 0.0, 1.0

    def _extract_frames(self, audio_bytes: bytes) -> np.ndarray:
        """
        Load audio and extract STFT-based power spectrogram frames,
        matching the feature extraction in preprocess_washer.py.
        """
        y, _ = librosa.load(io.BytesIO(audio_bytes), sr=WASHER_SR, mono=True)
        y = y / (np.max(np.abs(y)) + 1e-8)

        window = np.hanning(WASHER_N_FFT).astype(np.float32)
        n_samples = len(y)
        starts = np.arange(0, n_samples - WASHER_N_FFT + 1, WASHER_HOP_LENGTH)
        frames_stft = np.array([y[s:s + WASHER_N_FFT] * window for s in starts])
        spec = np.abs(np.fft.rfft(frames_stft, n=WASHER_N_FFT)) ** 2
        log_spec = np.log1p(spec).T.astype(np.float32)  # (freq_bins, T)

        frame_width = int(WASHER_FRAME_SEC * WASHER_SR / WASHER_HOP_LENGTH)
        hop_frames  = int(WASHER_FRAME_HOP * WASHER_SR / WASHER_HOP_LENGTH)
        frames = []
        start = 0
        while start + frame_width <= log_spec.shape[1]:
            frames.append(log_spec[:, start:start + frame_width][..., np.newaxis])
            start += hop_frames
        if not frames:
            padded = np.zeros((log_spec.shape[0], frame_width, 1), dtype=np.float32)
            padded[:, :log_spec.shape[1], 0] = log_spec
            frames = [padded]

        arr = np.stack(frames).astype(np.float32)
        return (arr - self._mean) / (self._std + 1e-8)

    def predict(self, audio_bytes: bytes, appliance_type: str = "washer") -> PredictionResult:
        frames = self._extract_frames(audio_bytes)
        probs = self._model.predict(frames, batch_size=32, verbose=0).flatten()
        clip_prob = float(np.mean(probs))
        is_anomalous = clip_prob >= WASHER_THRESHOLD
        fault_name = APPLIANCE_FAULT_MAP.get(appliance_type) if is_anomalous else None
        confidence = round(clip_prob * 100, 1) if is_anomalous else round((1 - clip_prob) * 100, 1)
        msg = (f"Bearing fault detected ({clip_prob:.1%}). Most likely: {fault_name}. "
               f"Note: trained on lab vibration data — treat result conservatively."
               if is_anomalous else f"No bearing fault detected ({1-clip_prob:.1%} confidence).")
        return PredictionResult(
            anomaly_probability=clip_prob, is_anomalous=is_anomalous,
            fault_name=fault_name, confidence=confidence,
            frames_analyzed=len(frames), message=msg,
        )


# ── Singleton cache ───────────────────────────────────────────────────────────

_fan_classifier: Optional[AudioClassifier] = None
_washer_classifier: Optional[WasherClassifier] = None
_lock = threading.Lock()


def get_classifier(appliance_type: str):
    """Returns the right singleton classifier for the given appliance type."""
    global _fan_classifier, _washer_classifier

    if appliance_type in WASHER_APPLIANCES:
        if _washer_classifier is None:
            with _lock:
                if _washer_classifier is None:
                    _washer_classifier = WasherClassifier()
        return _washer_classifier
    else:
        if _fan_classifier is None:
            with _lock:
                if _fan_classifier is None:
                    _fan_classifier = AudioClassifier()
        return _fan_classifier


def model_is_available(appliance_type: str = "fridge") -> bool:
    """True if the relevant trained model file exists."""
    if appliance_type in WASHER_APPLIANCES:
        return WASHER_MODEL_PATH.exists()
    return AUDIO_MODEL_PATH.exists()