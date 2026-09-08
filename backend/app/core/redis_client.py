"""
Redis client + helper for caching and task queuing.
"""
import json
import redis.asyncio as aioredis
from app.config import settings

_redis_client = None


async def get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client


async def cache_set(key: str, value: dict, ttl: int = 300):
    try:
        r = await get_redis()
        if r:
            await r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


async def cache_get(key: str) -> dict | None:
    try:
        r = await get_redis()
        if r:
            data = await r.get(key)
            return json.loads(data) if data else None
    except Exception:
        pass
    return None


async def cache_delete(key: str):
    try:
        r = await get_redis()
        if r:
            await r.delete(key)
    except Exception:
        pass


async def enqueue_task(queue_name: str, payload: dict):
    try:
        r = await get_redis()
        if r:
            await r.lpush(queue_name, json.dumps(payload))
    except Exception:
        pass


async def dequeue_task(queue_name: str) -> dict | None:
    try:
        r = await get_redis()
        if r:
            data = await r.rpop(queue_name)
            return json.loads(data) if data else None
    except Exception:
        pass
    return None


async def zadd_priority(key: str, score: float, member: str):
    try:
        r = await get_redis()
        if r:
            await r.zadd(key, {member: score})
    except Exception:
        pass


async def zpop_min(key: str) -> str | None:
    try:
        r = await get_redis()
        if r:
            result = await r.zpopmin(key, 1)
            return result[0][0] if result else None
    except Exception:
        pass
    return None
