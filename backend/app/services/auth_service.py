import hashlib
import logging
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi import HTTPException, status
from app.models.user import User
from app.schemas.auth import UserRegister, UserLogin
from app.utils.jwt_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_access_token,
)
from app.services.cache_service import cache_service
from app.services.kafka_service import kafka_service

logger = logging.getLogger(__name__)

class AuthService:
    async def register_user(self, db: AsyncSession, register_data: UserRegister) -> User:
        """Register a new user, hashes password, and stores in PostgreSQL."""
        # Check if email is already registered
        stmt = select(User).where(User.email == register_data.email)
        result = await db.execute(stmt)
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already registered"
            )

        hashed = hash_password(register_data.password)
        new_user = User(
            email=register_data.email,
            hashed_password=hashed,
            role=register_data.role
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        logger.info(f"Registered user: {new_user.email} with role: {new_user.role}")
        return new_user

    async def login_user(self, db: AsyncSession, login_data: UserLogin) -> Tuple[str, str]:
        """Authenticate user, generates access and refresh tokens, and saves in Redis."""
        stmt = select(User).where(User.email == login_data.email)
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user or not verify_password(login_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password"
            )

        access_token = create_access_token(str(user.id), user.email, user.role)
        refresh_token = create_refresh_token(str(user.id))

        # Store the hash of the refresh token in Redis
        await cache_service.set_refresh_token(str(user.id), refresh_token, expire_days=7)

        # Publish UserLoggedIn event to Kafka
        await kafka_service.publish_event(
            topic="auth-events",
            event_type="UserLoggedIn",
            user_id=str(user.id),
            payload={"email": user.email, "role": user.role}
        )

        logger.info(f"User logged in: {user.email}")
        return access_token, refresh_token

    async def refresh_tokens(self, db: AsyncSession, refresh_token: str) -> Tuple[str, str]:
        """Validates and rotates the refresh token, issuing a new access token."""
        payload = decode_access_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload"
            )

        # Fetch user
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        # Verify against Redis hash
        stored_hash = await cache_service.get_refresh_token_hash(user_id)
        if not stored_hash:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired or logged out"
            )

        incoming_hash = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
        if stored_hash != incoming_hash:
            # Token reuse detected. Revoke all refresh tokens for security.
            await cache_service.delete_refresh_token(user_id)
            logger.warning(f"Replay attack / token reuse detected for user {user_id}. Revoked session.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security breach: Token reuse detected. Session invalidated."
            )

        # Generate new pair (rotation)
        new_access = create_access_token(str(user.id), user.email, user.role)
        new_refresh = create_refresh_token(str(user.id))

        await cache_service.set_refresh_token(str(user.id), new_refresh, expire_days=7)
        logger.info(f"Rotated tokens for user: {user.email}")
        return new_access, new_refresh

    async def logout_user(self, user_id: str, email: str) -> None:
        """Revoke refresh token from Redis and publishes UserLoggedOut event to Kafka."""
        await cache_service.delete_refresh_token(user_id)

        await kafka_service.publish_event(
            topic="auth-events",
            event_type="UserLoggedOut",
            user_id=user_id,
            payload={"email": email}
        )
        logger.info(f"User logged out: {email}")

auth_service = AuthService()
