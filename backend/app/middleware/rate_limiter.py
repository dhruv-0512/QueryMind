import logging
from fastapi import Depends, HTTPException, status
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.services.cache_service import cache_service

logger = logging.getLogger(__name__)

async def rate_limiter(current_user: User = Depends(get_current_user)) -> None:
    """
    Rate limiting dependency applied to /query endpoints.
    Enforces a maximum of 10 queries per minute using a sliding window.
    """
    user_id = str(current_user.id)
    limit = 10
    window_seconds = 60

    is_limited, retry_after = await cache_service.is_rate_limited(
        user_id=user_id,
        limit=limit,
        window=window_seconds
    )

    if is_limited:
        logger.warning(f"User {user_id} exceeded query rate limit. Retry-after: {retry_after} seconds.")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. You are limited to 10 queries per minute.",
            headers={"Retry-After": str(retry_after)}
        )
