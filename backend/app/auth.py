from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque

from fastapi import Header, HTTPException, Request


class RateLimiter:
    def __init__(self, limit: int = 120, window: int = 60):
        self.limit, self.window, self.hits = limit, window, defaultdict(deque)

    def check(self, key: str) -> None:
        now, q = time.time(), self.hits[key]
        while q and q[0] < now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            raise HTTPException(429, "تعداد درخواست‌ها زیاد است؛ کمی بعد تلاش کنید.")
        q.append(now)


def make_auth(tokens: list[str], limiter: RateLimiter):
    async def auth(request: Request, authorization: str = Header(default="")) -> str:
        tok = authorization.removeprefix("Bearer ").strip()
        user = next((f"user{i}" for i, t in enumerate(tokens) if t and secrets.compare_digest(tok, t)), None)
        if user is None:
            raise HTTPException(401, "توکن نامعتبر است.")
        limiter.check(tok[:8] + (request.client.host if request.client else ""))
        return user
    return auth
