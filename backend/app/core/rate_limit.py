"""
Rate limiting middleware using Redis sliding window.
Limits: 100 req/min per IP for general routes, 10 req/min for auth routes.
"""
import time
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from app.core.redis_client import get_redis


RATE_LIMITS = {
    "/api/v1/auth/login": (10, 60),
    "/api/v1/auth/register": (10, 60),
    "default": (100, 60),
}


async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path

    limit, window = RATE_LIMITS.get(path, RATE_LIMITS["default"])
    key = f"ratelimit:{client_ip}:{path}"

    try:
        r = await get_redis()
        now = time.time()
        pipe = r.pipeline()
        await pipe.zremrangebyscore(key, 0, now - window)
        await pipe.zadd(key, {str(now): now})
        await pipe.zcard(key)
        await pipe.expire(key, window)
        results = await pipe.execute()
        count = results[2]

        if count > limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded. Max {limit} requests per {window}s."},
                headers={"Retry-After": str(window)},
            )
    except Exception:
        pass  # Redis unavailable — fail open

    response = await call_next(request)
    return response
