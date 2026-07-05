"""
ml/train_washer.py — Train the bearing fault CNN on CWRU vibration data.

Memory-safe version with oversampling to fix the severe class imbalance
(143 normal vs 1487 fault frames — 10:1 ratio causes the model to collapse
to always predicting "fault"). We oversample normal frames with small
Gaussian noise augmentation to bring the ratio to roughly 1:1.

Run from the repo root:
    python ml/train_washer.py
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

FEATURES_DIR    = Path("ml/features")
MODELS_DIR      = Path("ml/models")
BATCH_SIZE      = 32
EPOCHS          = 40
LR              = 1e-3
VAL_SPLIT       = 0.15
TEST_SPLIT      = 0.10
RANDOM_SEED     = 42
# Target ratio after oversampling — 1:1 gives the model equal exposure to
# both classes, which forces it to actually learn the boundary rather than
# collapsing to always predicting the majority class.
TARGET_RATIO    = 1.0
NOISE_STD       = 0.05   # std of Gaussian noise added to augmented normal frames

MODELS_DIR.mkdir(parents=True, exist_ok=True)


def oversample_normal(X, y, rng):
    """
    Oversample the normal class (y==0) with Gaussian noise augmentation
    until normal count reaches TARGET_RATIO * fault count.

    Why noise augmentation rather than pure duplication:
    Pure duplication would give the model identical frames to memorize,
    which doesn't generalise. Small Gaussian noise (std=0.05, which is
    ~5% of the normalized value range) preserves the underlying spectral
    pattern while creating genuinely distinct training samples.
    """
    normal_idx = np.where(y == 0)[0]
    fault_idx  = np.where(y == 1)[0]

    n_normal_needed = int(len(fault_idx) * TARGET_RATIO) - len(normal_idx)
    print(f"  Normal frames: {len(normal_idx)}, Fault frames: {len(fault_idx)}")
    print(f"  Oversampling normal by {n_normal_needed} augmented frames "
          f"(target ratio {TARGET_RATIO}:1)")

    if n_normal_needed <= 0:
        return X, y

    # Sample with replacement from existing normal frames, add noise
    chosen = rng.choice(normal_idx, size=n_normal_needed, replace=True)
    X_aug = X[chosen] + rng.normal(0, NOISE_STD, X[chosen].shape).astype(np.float32)
    y_aug = np.zeros(n_normal_needed, dtype=np.int32)

    X_balanced = np.concatenate([X, X_aug], axis=0)
    y_balanced = np.concatenate([y, y_aug], axis=0)

    # Shuffle
    idx = np.arange(len(y_balanced))
    rng.shuffle(idx)
    return X_balanced[idx], y_balanced[idx]


def build_model(input_shape):
    inputs = tf.keras.Input(shape=input_shape, name="vibration_spectrogram")

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
    outputs = tf.keras.layers.Dense(1, activation="sigmoid", name="fault_prob")(x)

    return tf.keras.Model(inputs, outputs)


def main():
    print("Loading washer features...")
    y_full = np.load(FEATURES_DIR / "y_washer.npy")
    print(f"  Raw dataset: {len(y_full)} frames "
          f"(normal={(y_full==0).sum()}, fault={(y_full==1).sum()})")

    X_full = np.load(FEATURES_DIR / "X_washer.npy", mmap_mode="r")
    X = np.array(X_full, dtype=np.float32)
    y = y_full.copy()
    del X_full

    # Split BEFORE oversampling — critical to avoid data leakage.
    # If we oversample first, augmented versions of test frames could appear
    # in training, making test metrics look better than they really are.
    X_trainval, X_test, y_trainval, y_test = train_test_split(
        X, y, test_size=TEST_SPLIT, random_state=RANDOM_SEED, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_trainval, y_trainval,
        test_size=VAL_SPLIT / (1 - TEST_SPLIT),
        random_state=RANDOM_SEED, stratify=y_trainval
    )
    del X, y, X_trainval, y_trainval
    print(f"  Split (before oversample): train={len(X_train)}, "
          f"val={len(X_val)}, test={len(X_test)}")

    # Oversample only the training set
    print("\nOversampling training normal frames...")
    rng = np.random.default_rng(RANDOM_SEED)
    X_train, y_train = oversample_normal(X_train, y_train, rng)
    print(f"  After oversampling: train={len(X_train)} "
          f"(normal={(y_train==0).sum()}, fault={(y_train==1).sum()})")

    # No class weighting needed after oversampling — classes are balanced
    print(f"\n  Val:  normal={(y_val==0).sum()}, fault={(y_val==1).sum()}")
    print(f"  Test: normal={(y_test==0).sum()}, fault={(y_test==1).sum()}")

    input_shape = X_train.shape[1:]
    print(f"  Input shape: {input_shape}")
    model = build_model(input_shape)
    model.summary()

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LR),
        loss="binary_crossentropy",
        metrics=["accuracy", tf.keras.metrics.AUC(name="auc")],
    )

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
            monitor="val_auc", patience=6,
            restore_best_weights=True, mode="max", verbose=1
        ),
        tf.keras.callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=3, verbose=1
        ),
        tf.keras.callbacks.ModelCheckpoint(
            filepath=str(MODELS_DIR / "washer_model_best.keras"),
            monitor="val_auc", save_best_only=True, mode="max", verbose=0
        ),
    ]

    print(f"\nTraining (up to {EPOCHS} epochs, early stopping on val_auc)...")
    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=EPOCHS,
        callbacks=callbacks,
        verbose=1,
    )

    model_path = MODELS_DIR / "washer_model.keras"
    model.save(model_path)
    print(f"\nModel saved → {model_path}")

    with open(MODELS_DIR / "washer_training_history.json", "w") as f:
        json.dump({k: [float(v) for v in vals]
                   for k, vals in history.history.items()}, f, indent=2)

    print("\nTest set evaluation...")
    test_ds = (tf.data.Dataset
               .from_tensor_slices((X_test, y_test))
               .batch(BATCH_SIZE))
    results = model.evaluate(test_ds, verbose=0)
    for name, val in zip(model.metrics_names, results):
        print(f"  test_{name}: {val:.4f}")

    print("\nNext: run  python ml/evaluate_washer.py")


if __name__ == "__main__":
    main()