from __future__ import annotations

import numpy as np
import tensorflow as tf


class TensorFlowAnomalyDetector:
    """
    Lightweight autoencoder-style model for anomaly scoring.
    We keep it tiny so it runs quickly on CPU for demos.
    """

    def __init__(self, window_size: int = 8):
        self.window_size = window_size
        self.model = self._build_model(window_size)
        self._warmup_train()

    def _build_model(self, input_dim: int) -> tf.keras.Model:
        inputs = tf.keras.Input(shape=(input_dim,))
        x = tf.keras.layers.Dense(16, activation="relu")(inputs)
        x = tf.keras.layers.Dense(8, activation="relu")(x)
        x = tf.keras.layers.Dense(16, activation="relu")(x)
        outputs = tf.keras.layers.Dense(input_dim)(x)
        model = tf.keras.Model(inputs, outputs)
        model.compile(optimizer="adam", loss="mse")
        return model

    def _warmup_train(self) -> None:
        baseline = np.random.normal(loc=50.0, scale=5.0, size=(256, self.window_size)).astype(
            np.float32
        )
        self.model.fit(baseline, baseline, epochs=3, batch_size=32, verbose=0)

    def score(self, window: list[float]) -> float:
        arr = np.array(window, dtype=np.float32).reshape(1, self.window_size)
        reconstructed = self.model.predict(arr, verbose=0)
        mse = float(np.mean((arr - reconstructed) ** 2))
        return min(1.0, mse / 100.0)
