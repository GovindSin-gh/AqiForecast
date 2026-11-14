"""Compare the candidate with the production model on the SAME held-out test windows,
then promote or reject. A rejection is a normal outcome, not an error."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

import numpy as np
import torch
from psycopg.types.json import Jsonb

from src.common import ROOT, connect, load_params
from src.models.export_onnx import export_onnx
from src.models.lstm import build_model, torch_predict
from src.models.metrics import metrics
from src.models.promotion import promotion_gate
from src.serving.predictor import OnnxPredictor
from src.serving.store import load_production


def _tag_mlflow(decision: str, onnx_path: Path, scaler_path: Path):
    try:
        import mlflow
        run_file = ROOT / "reports/run.json"
        if not (os.getenv("MLFLOW_TRACKING_URI") and run_file.exists()):
            return None
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        run_id = json.loads(run_file.read_text())["run_id"]
        with mlflow.start_run(run_id=run_id):
            mlflow.set_tag("gate", decision)
            if decision == "promoted":
                mlflow.log_artifact(str(onnx_path))
                mlflow.log_artifact(str(scaler_path))
        return run_id
    except Exception as e:  # tracking must never block the gate
        print("mlflow tagging skipped:", e)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", default="models/candidate.pt")
    args = ap.parse_args()
    P = load_params()
    scaler_path = ROOT / "data/processed/scaler.json"
    scaler = json.loads(scaler_path.read_text())
    z = np.load(ROOT / "data/processed/test.npz")
    X, city, y = z["X"], z["city"], z["y"]
    if len(X) == 0:
        raise SystemExit("test set is empty; backfill more data")
    last = X[:, -1, 0]

    ck = torch.load(ROOT / args.candidate, map_location="cpu")
    model = build_model(ck["config"])
    model.load_state_dict(ck["state"])
    cand = metrics(torch_predict(model, scaler, X, city), y, last)

    cur, note = None, "no production model yet"
    with connect() as conn:
        prod = load_production(conn)
        if prod and prod["scaler"]["cities"] == scaler["cities"]:
            cur = metrics(OnnxPredictor(prod["onnx"], prod["scaler"]).predict(X, city), y, last)
            note = f"compared with {prod['version']}"
        elif prod:
            note = "city list changed; replacing without comparison"

        res = promotion_gate(cand, cur, cand["persistence_mae"], P["gate"])
        version = "v" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
        print(f"{version}: {'PROMOTED' if res.passed else 'REJECTED'} ({note})")
        for r in res.reasons:
            print(" -", r)

        onnx_path = ROOT / "models/candidate.onnx"
        if res.passed:
            export_onnx(model, len(scaler["features"]), scaler["window"], str(onnx_path))
        run_id = _tag_mlflow("promoted" if res.passed else "rejected", onnx_path, scaler_path)

        with conn.cursor() as cur_db:
            if res.passed:
                cur_db.execute("update model_runs set stage='archived' where stage='production'")
            cur_db.execute(
                "insert into model_runs (version, stage, mae, coverage, metrics, reasons, "
                "mlflow_run_id, promoted_at) values (%s,%s,%s,%s,%s,%s,%s,%s)",
                (version, "production" if res.passed else "rejected", cand["mae"],
                 cand["coverage"], Jsonb(cand), res.reasons, run_id,
                 dt.datetime.now(dt.timezone.utc) if res.passed else None))
            if res.passed:
                cur_db.execute("insert into model_artifacts (version, onnx, scaler) values (%s,%s,%s)",
                               (version, onnx_path.read_bytes(), Jsonb(scaler)))
        conn.commit()


if __name__ == "__main__":
    main()
