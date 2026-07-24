import asyncio
from app.database import SessionLocal
from app.schemas.auth import UserRegister
from app.services.auth_service import auth_service

async def main():
    async with SessionLocal() as db:
        try:
            user = await auth_service.register_user(
                db, 
                UserRegister(email="user@querymind.com", password="password123", role="admin")
            )
            print("Successfully created user:", user.email)
        except Exception as e:
            print("User creation error or user exists:", e)

if __name__ == "__main__":
    asyncio.run(main())
