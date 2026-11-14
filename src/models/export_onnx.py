import numpy as np
import onnxruntime as ort
import torch


def export_onnx(model, n_features: int, window: int, path: str):
    model.eval()
    x = torch.zeros(1, window, n_features)
    c = torch.zeros(1, dtype=torch.long)
    kw = dict(input_names=["x", "city_id"], output_names=["quantiles"], opset_version=17,
              dynamic_axes={"x": {0: "batch"}, "city_id": {0: "batch"}, "quantiles": {0: "batch"}})
    try:
        torch.onnx.export(model, (x, c), path, dynamo=False, **kw)   # newer torch
    except TypeError:
        torch.onnx.export(model, (x, c), path, **kw)                 # older torch
    # parity check: ONNX must match PyTorch before we ship it
    xs = torch.randn(5, window, n_features)
    cs = torch.randint(0, model.city_emb.num_embeddings, (5,))
    with torch.no_grad():
        ref = model(xs, cs).numpy()
    got = ort.InferenceSession(path, providers=["CPUExecutionProvider"]).run(
        None, {"x": xs.numpy(), "city_id": cs.numpy().astype(np.int64)})[0]
    if np.abs(ref - got).max() > 1e-3:
        raise RuntimeError("ONNX output differs from PyTorch; refusing to export")
