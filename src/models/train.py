"""Train the quantile LSTM. Shuffling batches INSIDE the train split is fine;
the time split itself was already done in features/build.py."""
import copy
import json
import os
import random

import mlflow
import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from src.common import ROOT, load_params
from src.features.transform import normalize, y_stats
from src.models.lstm import build_model, pinball_loss, torch_predict
from src.models.metrics import metrics


def load(split):
    z = np.load(ROOT / "data/processed" / f"{split}.npz")
    return z["X"], z["city"], z["y"]


def main():
    P = load_params()
    T = P["train"]
    random.seed(T["seed"])
    np.random.seed(T["seed"])
    torch.manual_seed(T["seed"])
    scaler = json.loads((ROOT / "data/processed/scaler.json").read_text())
    mu, sd = y_stats(scaler)
    Xtr, ctr, ytr = load("train")
    Xva, cva, yva = load("val")
    cfg = {
        "n_features": len(scaler["features"]),
        "n_cities": len(scaler["cities"]),
        "hidden": T["hidden"],
        "layers": T["layers"],
        "dropout": T["dropout"],
        "emb": T["emb"],
        "horizons": P["features"]["horizon"],
    }
    model = build_model(cfg)
    opt = torch.optim.AdamW(model.parameters(), lr=T["lr"])

    def tens(X, c, y):
        return (
            torch.from_numpy(normalize(X, scaler)),
            torch.from_numpy(c.astype(np.int64)),
            torch.from_numpy(((y - mu) / sd).astype(np.float32)),
        )

    train_dl = DataLoader(TensorDataset(*tens(Xtr, ctr, ytr)), batch_size=T["batch_size"], shuffle=True)
    xv, cv, yv = tens(Xva, cva, yva)

    if os.getenv("MLFLOW_TRACKING_URI"):
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment("aqi-lstm")
    best, best_state, bad = float("inf"), None, 0
    with mlflow.start_run() as run:
        mlflow.log_params({
            **{f"train.{k}": v for k, v in T.items()},
            "n_train": len(Xtr),
            "n_val": len(Xva),
        })
        for epoch in range(T["epochs"]):
            model.train()
            for x, c, y in train_dl:
                opt.zero_grad()
                loss = pinball_loss(model(x, c), y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
            model.eval()
            with torch.no_grad():
                val = float(pinball_loss(model(xv, cv), yv))
            mlflow.log_metric("val_pinball", val, step=epoch)
            print(f"epoch {epoch + 1}: val pinball {val:.4f}")
            if val < best - 1e-4:
                best, best_state, bad = val, copy.deepcopy(model.state_dict()), 0
            else:
                bad += 1
                if bad >= T["patience"]:
                    break
        model.load_state_dict(best_state)
        m = metrics(torch_predict(model, scaler, Xva, cva), yva, Xva[:, -1, 0])
        mlflow.log_metrics({
            "val_mae": m["mae"],
            "val_coverage": m["coverage"],
            "val_skill_vs_persistence": m["skill_vs_persistence"],
        })
        (ROOT / "models").mkdir(exist_ok=True)
        (ROOT / "reports").mkdir(exist_ok=True)
        torch.save({"state": model.state_dict(), "config": cfg}, ROOT / "models/candidate.pt")
        (ROOT / "reports/metrics.json").write_text(json.dumps(m, indent=2))
        (ROOT / "reports/run.json").write_text(json.dumps({"run_id": run.info.run_id}))
        print(json.dumps(m, indent=2))


if __name__ == "__main__":
    main()
