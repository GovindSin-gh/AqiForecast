"""The promotion gate. Pure Python so it is easy to test."""
from dataclasses import dataclass, field


@dataclass
class GateResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def promotion_gate(cand: dict, cur: dict | None, persistence_mae: float, cfg: dict) -> GateResult:
    """cand/cur: output of metrics(). cur is None for the very first model."""
    reasons = []
    if cur is not None:
        if cand["mae"] > cur["mae"] * (1 - cfg["min_improvement"]):
            reasons.append(f"overall MAE is not at least {cfg['min_improvement']:.0%} better")
        for h, cur_mae in cur["mae_by_h"].items():
            if cand["mae_by_h"][h] > cur_mae * (1 + cfg["max_horizon_regression"]):
                reasons.append(f"t+{h} MAE is more than {cfg['max_horizon_regression']:.0%} worse")
    if not cfg["coverage_low"] <= cand["coverage"] <= cfg["coverage_high"]:
        reasons.append(
            f"p10-p90 coverage is outside {cfg['coverage_low']:.0%}-{cfg['coverage_high']:.0%}"
        )
    if cand["mae"] >= persistence_mae:
        reasons.append("does not beat the persistence baseline")
    return GateResult(not reasons, reasons)
