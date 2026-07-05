"""
ml/train.py — Step 2 of the audio ML pipeline.

Memory-safe version: loads data in batches via tf.data instead of holding
all 55k frames in RAM simultaneously. Also samples a subset of normal frames
to keep total training data manageable on CPU with limited RAM.

Run from the repo root:
    python ml/train.py
"""

import json
import os
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"

import numpy as np
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.utils.class_weight import compute_class_weight

# ── CONFIG ────────────────────────────────────────────────────────────────────
FEATURES_DIR    = Path("ml/features")
MODELS_DIR      = Path("ml/models")
BATCH_SIZE      = 32       # smaller batch = less peak RAM during training
EPOCHS          = 30
LR              = 1e-3
VAL_SPLIT       = 0.15
TEST_SPLIT      = 0.10
RANDOM_SEED     = 42
# Cap normal samples to 3x abnormal count — avoids OOM while keeping enough
# class balance for the weighted loss to work correctly.
MAX_NORMAL_RATIO = 3.0
# ─────────────────────────────────────────────────────────────────────────────

MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_balanced_subset(X, y):
    """
    Subsample normal frames so the dataset fits in RAM and the class ratio
    stays manageable. Abnormal frames are kept in full since they're already
    the minority class.
    """
    normal_idx   = np.where(y == 0)[0]
    abnormal_idx = np.where(y == 1)[0]

    max_normal = int(len(abnormal_idx) * MAX_NORMAL_RATIO)
    if len(normal_idx) > max_normal:
        rng = np.random.default_rng(RANDOM_SEED)
        normal_idx = rng.choice(normal_idx, size=max_normal, replace=False)
        print(f"  Subsampled normal: {len(np.where(y==0)[0])} → {len(normal_idx)} "
              f"(keeping {MAX_NORMAL_RATIO}x abnormal)")

    idx = np.concatenate([normal_idx, abnormal_idx])
    rng = np.random.default_rng(RANDOM_SEED + 1)
    rng.shuffle(idx)
    return X[idx], y[idx]


def build_model(input_shape):
    inputs = tf.keras.Input(shape=input_shape, name="spectrogram")

    x = tf.keras.layers.Conv2D(16, (3, 3), padding="same", activation="relu")(inputs)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.MaxPooling2D((2, 2))(x)
    x = tf.keras.layers.Dropout(0.25)(x)

    x = tf.keras.layers.Conv2D(32, (3, 3), padding="same", activation="relu")(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.MaxPooling2D((2, 2))(x)
    x = tf.keras.layers.Dropout(0.25)(x)

    x = tf.keras.layers.Conv2D(64, (3, 3), padding="same", activation="relu")(x)
    x = tf.keras.layers.BatchNormalization()(x)
    x = tf.keras.layers.GlobalAveragePooling2D()(x)
    x = tf.keras.layers.Dropout(0.3)(x)

    x = tf.keras.layers.Dense(64, activation="relu")(x)
    x = tf.keras.layers.Dropout(0.3)(x)
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="anomaly_prob")(x)

    return tf.keras.Model(inputs, outputs)


def main():
    print("Loading features...")
    # Load indices only first to check sizes before loading full array
    y_full = np.load(FEATURES_DIR / "y_fan.npy")
    print(f"  Full dataset: {len(y_full)} frames "
          f"(normal={( y_full==0).sum()}, abnormal={(y_full==1).sum()})")

    # Load X in a memory-mapped mode so OS can page it in as needed
    X_full = np.load(FEATURES_DIR / "X_fan.npy", mmap_mode="r")

    # Balance and subsample
    print("Balancing dataset...")
    X, y = load_balanced_subset(X_full, y_full)
    # Force a real copy of the subsampled data — small enough now
    X = np.array(X, dtype=np.float32)
    del X_full, y_full
    print(f"  Working set: {len(X)} frames "
          f"(normal={(y==0).sum()}, abnormal={(y==1).sum()})")

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SPLIT, random_state=RANDOM_SEED, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train, y_train,
        test_size=VAL_SPLIT / (1 - TEST_SPLIT),
        random_state=RANDOM_SEED, stratify=y_train
    )
    print(f"  Split: train={len(X_train)}, val={len(X_val)}, test={len(X_test)}")
    del X  # free the unsplit array

    # Class weights
    classes = np.unique(y_train)
    weights = compute_class_weight("balanced", classes=classes, y=y_train)
    class_weight = dict(zip(classes.tolist(), weights.tolist()))
    print(f"  Class weights: {class_weight}")

    # Build and compile model
    input_shape = X_train.shape[1:]
    model = build_model(input_shape)
    model.summary()

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR),
        loss="binary_crossentropy",
        metrics=["accuracy", tf.keras.metrics.AUC(name="auc")],
    )

    # Use tf.data for memory-efficient batching during training
    train_ds = (tf.data.Dataset
                .from_tensor_slices((X_train, y_train))
                .shuffle(buffer_size=2000, seed=RANDOM_SEED)
                .batch(BATCH_SIZE)
                .prefetch(tf.data.AUTOTUNE))

    val_ds = (tf.data.Dataset
              .from_tensor_slices((X_val, y_val))
              .batch(BATCH_SIZE)
              .prefetch(tf.data.AUTOTUNE))

    callbacks = [
        tf.keras.callbacks.EarlyStopping(
            monitor="val_auc", patience=5,
            restore_best_weights=True, mode="max", verbose=1
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=3, verbose=1
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(MODELS_DIR / "audio_model_best.keras"),
            monitor="val_auc", save_best_only=True, mode="max", verbose=0
        ),
    ]

    print(f"\nTraining (up to {EPOCHS} epochs, early stopping on val_auc)...")
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS,
        class_weight=class_weight,
        callbacks=callbacks,
        verbose=1,
    )

    model_path = MODELS_DIR / "audio_model.keras"
    model.save(model_path)
    print(f"\nModel saved → {model_path}")

    with open(MODELS_DIR / "training_history.json", "w") as f:
        json.dump({k: [float(v) for v in vals]
                   for k, vals in history.history.items()}, f, indent=2)

    # Test set evaluation
    print("\nTest set evaluation...")
    test_ds = (tf.data.Dataset
               .from_tensor_slices((X_test, y_test))
               .batch(BATCH_SIZE))
    results = model.evaluate(test_ds, verbose=0)
    for name, val in zip(model.metrics_names, results):
        print(f"  test_{name}: {val:.4f}")

    print("\nNext: run  python ml/evaluate.py")


if __name__ == "__main__":
    main()