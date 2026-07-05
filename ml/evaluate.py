"""
ml/evaluate.py — Step 3 of the audio ML pipeline.

Loads the saved model and runs a full evaluation on the held-out test set,
printing metrics and a confusion matrix so you can actually see what the
model is and isn't getting right before wiring it into the API.

Run from the repo root:
    python ml/evaluate.py

This script doesn't train anything — it's read-only against the saved model.
Re-run it any time to check model performance without retraining.
"""

import os
from pathlib import Path

import numpy as np
import tensorflow as tf
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

FEATURES_DIR = Path("ml/features")
MODELS_DIR   = Path("ml/models")
RANDOM_SEED  = 42
TEST_SPLIT   = 0.10
THRESHOLD    = 0.5   # anomaly probability above this → classified as abnormal


def main():
    print("Loading features and model...")
    X = np.load(FEATURES_DIR / "X_fan.npy", mmap_mode="r")
    y = np.load(FEATURES_DIR / "y_fan.npy")

    # Reproduce the same train/test split as train.py
    _, X_test, _, y_test = train_test_split(
        X, y, test_size=TEST_SPLIT, random_state=RANDOM_SEED, stratify=y
    )

    model_path = MODELS_DIR / "audio_model.keras"
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found at {model_path}. Run  python ml/train.py  first."
        )
    model = tf.keras.models.load_model(model_path)
    print(f"Model loaded from {model_path}")

    print(f"\nEvaluating on {len(X_test)} test frames...")
    y_prob = model.predict(X_test, batch_size=64, verbose=0).flatten()
    y_pred = (y_prob >= THRESHOLD).astype(int)

    # Core metrics
    auc = roc_auc_score(y_test, y_prob)
    print(f"\n{'='*50}")
    print(f"ROC-AUC:   {auc:.4f}  (higher is better; 0.5 = random, 1.0 = perfect)")
    print(f"Threshold: {THRESHOLD}")
    print(f"{'='*50}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["Normal", "Abnormal"]))

    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()
    print("Confusion Matrix:")
    print(f"  True  Normal predicted Normal   (TN): {tn}")
    print(f"  True  Normal predicted Abnormal (FP): {fp}  ← false alarms")
    print(f"  True Abnormal predicted Normal   (FN): {fn}  ← missed faults")
    print(f"  True Abnormal predicted Abnormal (TP): {tp}  ← caught faults")
    print(f"\n  False alarm rate (FP/total normal): {fp / (tn + fp):.1%}")
    print(f"  Fault detection rate (recall):      {tp / (tp + fn):.1%}")

    print("\n" + "="*50)
    if auc >= 0.85:
        print("✓ AUC looks solid — model is learning a real signal.")
    elif auc >= 0.70:
        print("⚠ AUC is moderate — model is learning something but not reliably.")
        print("  Consider: more data, tuning THRESHOLD, or more epochs.")
    else:
        print("✗ AUC is low — model may not have learned anything useful.")
        print("  Check: class imbalance, data quality, preprocessing.")


if __name__ == "__main__":
    main()