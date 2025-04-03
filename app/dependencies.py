from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional
from . import auth, models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def get_optional_current_user(token: str = Depends(oauth2_scheme)) -> Optional[models.User]:
    """
    Dependency to get the current user from the token in the Authorization header.
    Returns None if the token is invalid or not provided.
    Handles potential exceptions during token decoding/validation gracefully for optional user.
    """
    try:
        user = await auth.get_current_user_from_token(token)
        return user
    except Exception:
        return None

async def get_required_current_user(token: str = Depends(oauth2_scheme)) -> models.User:
    """
    Dependency to get the current user, raising HTTP 401 if not authenticated.
    """
    user = await auth.get_current_user_from_token(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user