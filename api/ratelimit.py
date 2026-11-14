import time
from collections import deque


class RateLimiter:
    """Tiny in-memory sliding window. Enough to protect a free LLM quota on one instance."""

    def __init__(self, limit: int = 6, window: int = 60):
        self.limit, self.window, self.hits = limit, window, {}

    def check(self, key: str) -> bool:
        now = time.time()
        q = self.hits.setdefault(key, deque())
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        if len(self.hits) > 5000:
            self.hits.clear()
        return True
