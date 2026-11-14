from api.ratelimit import RateLimiter


def test_limit_blocks_after_n_hits():
    rl = RateLimiter(limit=3, window=60)
    assert [rl.check("a") for _ in range(4)] == [True, True, True, False]
    assert rl.check("b")          # other clients are unaffected
