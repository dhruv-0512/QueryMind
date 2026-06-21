from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.middleware.auth_middleware import get_current_user
from app.schemas.auth import (
    UserRegister,
    UserLogin,
    TokenResponse,
    TokenRefreshRequest,
    UserResponse,
)
from app.services.auth_service import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(register_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """Register a new user with standard credentials and role assignment."""
    user = await auth_service.register_user(db, register_data)
    return user

@router.post("/login", response_model=TokenResponse)
async def login(login_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """Authenticate credentials and generate token pairs."""
    access_token, refresh_token = await auth_service.login_user(db, login_data)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/refresh", response_model=TokenResponse)
async def refresh(refresh_data: TokenRefreshRequest, db: AsyncSession = Depends(get_db)):
    """Validate and rotate the refresh token, issuing a new set of tokens."""
    access_token, refresh_token = await auth_service.refresh_tokens(db, refresh_data.refresh_token)
    return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(current_user: User = Depends(get_current_user)):
    """Log out current user and blacklist their refresh token."""
    await auth_service.logout_user(str(current_user.id), current_user.email)
    return {"detail": "Successfully logged out"}
