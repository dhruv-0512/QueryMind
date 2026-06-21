import hashlib
import logging
import time
from typing import Optional
import redis.asyncio as aioredis
from app.config import settings

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self):
        self.redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    def _hash_token(self, token: str) -> str:
        """Hash token using SHA-256 for secure comparison in Redis."""
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def set_refresh_token(self, user_id: str, token: str, expire_days: int) -> None:
        """Hash and save the refresh token in Redis with a 7-day expiration."""
        key = f"refresh:{user_id}"
        hashed = self._hash_token(token)
        ttl_seconds = expire_days * 24 * 3600
        await self.redis_client.set(key, hashed, ex=ttl_seconds)

    async def get_refresh_token_hash(self, user_id: str) -> Optional[str]:
        """Retrieve the stored refresh token hash."""
        key = f"refresh:{user_id}"
        return await self.redis_client.get(key)

    async def delete_refresh_token(self, user_id: str) -> None:
        """Remove the refresh token from Redis (used on logout/invalidation)."""
        key = f"refresh:{user_id}"
        await self.redis_client.delete(key)

    async def get_cache(self, key: str) -> Optional[str]:
        """Fetch general cached data."""
        try:
            return await self.redis_client.get(key)
        except Exception as e:
            logger.error(f"Redis get cache error for key {key}: {e}")
            return None

    async def set_cache(self, key: str, value: str, ttl_seconds: int) -> None:
        """Store general data in cache with a TTL."""
        try:
            await self.redis_client.set(key, value, ex=ttl_seconds)
        except Exception as e:
            logger.error(f"Redis set cache error for key {key}: {e}")

    async def is_rate_limited(self, user_id: str, limit: int = 10, window: int = 60) -> tuple[bool, int]:
        """
        Sliding window rate limiting using sorted sets (ZSET).
        Returns (is_limited, retry_after_seconds).
        """
        try:
            key = f"rate_limit:{user_id}"
            now = time.time()
            clear_before = now - window

            # pipeline executions for atomic sliding window evaluation
            async with self.redis_client.pipeline(transaction=True) as pipe:
                # Remove timestamps older than the sliding window
                pipe.zremrangebyscore(key, 0, clear_before)
                # Count remaining items in sliding window
                pipe.zcard(key)
                # Add the current timestamp
                pipe.zadd(key, {str(now): now})
                # Set TTL for the key to auto clean up
                pipe.expire(key, window)
                
                _, current_count, _, _ = await pipe.execute()

            if current_count >= limit:
                # Calculate retry after (oldest timestamp in set + window - now)
                oldest = await self.redis_client.zrange(key, 0, 0, withscores=True)
                retry_after = 0
                if oldest:
                    retry_after = int(oldest[0][1] + window - now)
                return True, max(1, retry_after)

            return False, 0
        except Exception as e:
            logger.error(f"Rate limiting evaluation failed: {e}")
            return False, 0

cache_service = CacheService()
