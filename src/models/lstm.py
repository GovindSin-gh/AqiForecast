import numpy as np
import torch
import torch.nn as nn

from src.features.transform import normalize, y_stats

QUANTILES = (0.1, 0.5, 0.9)


class AQILSTM(nn.Module):
    def __init__(self, n_features, n_cities, hidden=64, layers=2, dropout=0.1,
                 emb=8, horizons=24, n_q=3):
        super().__init__()
        self.horizons, self.n_q = horizons, n_q
        self.city_emb = nn.Embedding(n_cities, emb)
        self.lstm = nn.LSTM(n_features + emb, hidden, num_layers=layers, batch_first=True,
                            dropout=dropout if layers > 1 else 0.0)
        self.head = nn.Linear(hidden, horizons * n_q)

    def forward(self, x, city_id):
        # x: (batch, window, n_features); city_id: (batch,)
        e = self.city_emb(city_id).unsqueeze(1).expand(-1, x.size(1), -1)
        out, _ = self.lstm(torch.cat([x, e], dim=-1))
        y = self.head(out[:, -1]).view(-1, self.horizons, self.n_q)
        return torch.sort(y, dim=-1).values        # keeps p10 <= p50 <= p90


def build_model(cfg: dict) -> AQILSTM:
    return AQILSTM(cfg["n_features"], cfg["n_cities"], cfg["hidden"], cfg["layers"],
                   cfg["dropout"], cfg["emb"], cfg["horizons"])


def pinball_loss(pred, target, quantiles=QUANTILES):
    # pred: (B, H, Q), target: (B, H)
    q = torch.tensor(quantiles, device=pred.device).view(1, 1, -1)
    err = target.unsqueeze(-1) - pred
    return torch.maximum(q * err, (q - 1) * err).mean()


@torch.no_grad()
def torch_predict(model, scaler, X, city, batch=2048):
    """Raw-unit predictions (N, horizon, 3) in ug/m3."""
    model.eval()
    mu, sd = y_stats(scaler)
    out = []
    for i in range(0, len(X), batch):
        x = torch.from_numpy(normalize(X[i:i + batch], scaler))
        c = torch.from_numpy(np.asarray(city[i:i + batch], dtype=np.int64))
        out.append(model(x, c).numpy())
    return np.clip(np.concatenate(out) * sd + mu, 0, None)
