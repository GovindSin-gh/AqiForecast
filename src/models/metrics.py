import numpy as np

from src.features.aqi import PM25_UPPER

REPORT_H = (1, 6, 12, 24)


def _cat(x):
    return np.searchsorted(PM25_UPPER, x)


def metrics(pred: np.ndarray, y: np.ndarray, last: np.ndarray) -> dict:
    """pred (N,H,3) raw units, y (N,H) truth, last (N,) newest observed PM2.5."""
    p10, p50, p90 = pred[..., 0], pred[..., 1], pred[..., 2]
    err = p50 - y
    mae_h = np.abs(err).mean(0)
    pers = np.abs(last[:, None] - y)
    return {
        "mae": float(mae_h.mean()),
        "rmse": float(np.sqrt((err ** 2).mean())),
        "mae_by_h": {h: float(mae_h[h - 1]) for h in REPORT_H},
        "rmse_by_h": {h: float(np.sqrt((err[:, h - 1] ** 2).mean())) for h in REPORT_H},
        "persistence_mae": float(pers.mean()),
        "skill_vs_persistence": float(1 - mae_h.mean() / pers.mean()),
        "coverage": float(((y >= p10) & (y <= p90)).mean()),
        "category_accuracy": float((_cat(p50) == _cat(y)).mean()),
        "persistence_category_accuracy": float((_cat(last[:, None]) == _cat(y)).mean()),
    }
