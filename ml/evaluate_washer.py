"""
ml/evaluate_washer.py — Evaluate the washer bearing fault model.

Run from the repo root:
    python ml/evaluate_washer.py
"""

import os
from pathlib import Path

import numpy as np
import tensorflow as tf
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.model_selection import train_test_split

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

FEATURES_DIR = Path("ml/features")
MODELS_DIR   = Path("ml/models")
RANDOM_SEED  = 42
TEST_SPLIT   = 0.10
THRESHOLD    = 0.995


def main():
    print("Loading features and model...")
    X = np.load(FEATURES_DIR / "X_washer.npy", mmap_mode="r")
    y = np.load(FEATURES_DIR / "y_washer.npy")

    _, X_test, _, y_test = train_test_split(
        X, y, test_size=TEST_SPLIT, random_state=RANDOM_SEED, stratify=y
    )

    model_path = MODELS_DIR / "washer_model.keras"
    if not model_path.exists():
        raise FileNotFoundError(
            f"Model not found at {model_path}. Run  python ml/train_washer.py  first."
        )
    model = tf.keras.models.load_model(model_path)
    print(f"Model loaded from {model_path}")

    print(f"\nEvaluating on {len(X_test)} test frames...")
    y_prob = model.predict(X_test, batch_size=64, verbose=0).flatten()
    y_pred = (y_prob >= THRESHOLD).astype(int)

    auc = roc_auc_score(y_test, y_prob)
    print(f"\n{'='*50}")
    print(f"ROC-AUC:   {auc:.4f}")
    print(f"Threshold: {THRESHOLD}")
    print(f"{'='*50}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["Normal", "Fault"]))

    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()
    print("Confusion Matrix:")
    print(f"  True  Normal predicted Normal   (TN): {tn}")
    print(f"  True  Normal predicted Fault    (FP): {fp}  ← false alarms")
    print(f"  True  Fault  predicted Normal   (FN): {fn}  ← missed faults")
    print(f"  True  Fault  predicted Fault    (TP): {tp}  ← caught faults")
    print(f"\n  False alarm rate: {fp / (tn + fp):.1%}")
    print(f"  Fault detection rate (recall): {tp / (tp + fn):.1%}")

    print(f"\n{'='*50}")
    if auc >= 0.85:
        print("✓ AUC looks solid.")
    elif auc >= 0.70:
        print("⚠ AUC moderate — model is learning but not reliably.")
    else:
        print("✗ AUC low — check class balance and preprocessing.")

    print("\nIMPORTANT CAVEAT: this model was trained on lab vibration data")
    print("(CWRU bearing rig), not real washing machine microphone recordings.")
    print("Real-world performance on phone mic audio will be lower than these")
    print("lab-data metrics suggest. Treat washer fault scores conservatively.")


if __name__ == "__main__":
    main()