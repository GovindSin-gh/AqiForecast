"""Raw observations -> time-split windows. Arrays keep RAW units; each model
applies its own scaler, so old and new models can be compared on the same data."""
import json

import numpy as np
import pandas as pd

from src.common import ROOT, load_params
from src.features.transform import add_features, clean_city_frame, make_scaler


def main():
    P = load_params()
    F = P["features"]
    W, H = F["window"], F["horizon"]
    cities = [c["id"] for c in P["cities"]]
    obs = pd.read_parquet(ROOT / "data/raw/observations.parquet")
    parts = {k: {"X": [], "city": [], "y": [], "t": []} for k in ("train", "val", "test")}

    for ci, cid in enumerate(cities):
        sub = obs[obs["city_id"] == cid]
        if len(sub) < W + H + 100:
            print(f"skip {cid}: only {len(sub)} rows")
            continue
        d = clean_city_frame(sub)
        arr, idx = add_features(d).to_numpy(np.float32), d.index
        n = len(arr)
        i_tr = int(n * F["split"]["train"])
        i_va = int(n * (F["split"]["train"] + F["split"]["val"]))
        cs = np.concatenate([[0], np.cumsum(np.isnan(arr).any(axis=1))])
        cp = np.concatenate([[0], np.cumsum(np.isnan(arr[:, 0]))])
        for t in range(W - 1, n - H):                 # t = last input hour
            if cs[t + 1] - cs[t + 1 - W] or cp[t + H + 1] - cp[t + 1]:
                continue
            if t + H < i_tr:                          # inputs AND targets inside train
                split = "train"
                if t % F["stride"]:
                    continue
            elif i_tr <= t and t + H < i_va:
                split = "val"
            elif t >= i_va:
                split = "test"
            else:
                continue                              # straddles a boundary: dropped on purpose
            p = parts[split]
            p["X"].append(arr[t - W + 1:t + 1])
            p["city"].append(ci)
            p["y"].append(arr[t + 1:t + H + 1, 0])
            p["t"].append(int(idx[t].timestamp()))

    if not parts["train"]["X"]:
        raise SystemExit("no training windows: backfill more data first")
    out = ROOT / "data/processed"
    out.mkdir(parents=True, exist_ok=True)
    for split, p in parts.items():
        np.savez(out / f"{split}.npz", X=np.stack(p["X"]).astype(np.float32),
                 city=np.asarray(p["city"], dtype=np.int64),
                 y=np.stack(p["y"]).astype(np.float32), t=np.asarray(p["t"], dtype=np.int64))
        print(split, len(p["X"]), "windows")
    scaler = make_scaler(np.stack(parts["train"]["X"]), cities)
    (out / "scaler.json").write_text(json.dumps(scaler))


if __name__ == "__main__":
    main()
