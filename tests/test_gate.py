from src.models.promotion import promotion_gate

CFG = {"min_improvement": 0.02, "max_horizon_regression": 0.05,
       "coverage_low": 0.75, "coverage_high": 0.85}
CUR = {"mae": 14.0, "mae_by_h": {1: 5.0, 6: 11.0, 12: 15.5, 24: 20.0}}


def cand(**kw):
    base = {"mae": 13.2, "mae_by_h": {1: 4.8, 6: 10.5, 12: 14.6, 24: 19.4}, "coverage": 0.80}
    return {**base, **kw}


def test_accepts_clear_improvement():
    assert promotion_gate(cand(), CUR, 19.5, CFG).passed


def test_rejects_no_improvement():
    assert not promotion_gate(cand(mae=14.0), CUR, 19.5, CFG).passed


def test_rejects_worse_long_horizon():
    r = promotion_gate(cand(mae_by_h={1: 4.2, 6: 9.8, 12: 14.0, 24: 22.5}), CUR, 19.5, CFG)
    assert not r.passed and any("t+24h" in x for x in r.reasons)


def test_rejects_bad_coverage():
    assert not promotion_gate(cand(coverage=0.62), CUR, 19.5, CFG).passed


def test_first_model_only_needs_baseline_and_coverage():
    assert promotion_gate(cand(), None, 19.5, CFG).passed
    assert not promotion_gate(cand(mae=20.0), None, 19.5, CFG).passed
