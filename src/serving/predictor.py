import numpy as np
import onnxruntime as ort

from src.features.transform import normalize, y_stats


class OnnxPredictor:
    """Runs the exported model. Input raw features (N, window, F); output ug/m3 (N, H, 3)."""

    def __init__(self, onnx_bytes: bytes, scaler: dict):
        self.sess = ort.InferenceSession(bytes(onnx_bytes), providers=["CPUExecutionProvider"])
        self.scaler = scaler
        self.mu, self.sd = y_stats(scaler)

    def predict(self, X: np.ndarray, city_ids, batch: int = 2048) -> np.ndarray:
        city_ids = np.asarray(city_ids, dtype=np.int64)
        out = []
        for i in range(0, len(X), batch):
            out.append(self.sess.run(None, {"x": normalize(X[i:i + batch], self.scaler),
                                            "city_id": city_ids[i:i + batch]})[0])
        return np.clip(np.concatenate(out) * self.sd + self.mu, 0, None)
