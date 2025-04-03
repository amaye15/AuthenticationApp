import os
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from dotenv import load_dotenv
from typing import Optional
from . import crud, models

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret") # Fallback, but .env should be used
# Use URLSafeTimedSerializer for session tokens that expire
serializer = URLSafeTimedSerializer(SECRET_KEY)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

# Session Token generation (using itsdangerous for simplicity)
# Stores user_id securely signed with a timestamp
def create_session_token(user_id: int) -> str:
    return serializer.dumps(user_id)

# Session Token verification
async def get_user_id_from_token(token: str) -> Optional[int]:
    if not token:
        return None
    try:
        # Set max_age to something reasonable, e.g., 1 day
        user_id = serializer.loads(token, max_age=86400) # 24 hours * 60 min * 60 sec
        return int(user_id)
    except (SignatureExpired, BadSignature, ValueError):
        return None

# Function to get current user from token
async def get_current_user_from_token(token: str) -> Optional[models.User]:
    user_id = await get_user_id_from_token(token)
    if user_id is None:
        return None
    user = await crud.get_user_by_id(user_id)
    if user:
        # Return the public User model, not UserInDB
        return models.User(id=user.id, email=user.email)
    return None