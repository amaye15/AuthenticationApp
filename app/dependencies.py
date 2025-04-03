from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer # Use FastAPI's built-in helper
from typing import Optional
from . import auth, models

# Setup OAuth2 scheme pointing to the login *API* endpoint
# tokenUrl relative to the path where the app is mounted
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

async def get_optional_current_user(token: str = Depends(oauth2_scheme)) -> Optional[models.User]:
    """
    Dependency to get the current user from the token in the Authorization header.
    Returns None if the token is invalid or not provided.
    Handles potential exceptions during token decoding/validation gracefully for optional user.
    """
    try:
        # OAuth2PasswordBearer already extracts the token from the header
        user = await auth.get_current_user_from_token(token)
        return user
    except Exception: # Catch exceptions if the token is invalid but we don't want to fail hard
        return None

async def get_required_current_user(token: str = Depends(oauth2_scheme)) -> models.User:
    """
    Dependency to get the current user, raising HTTP 401 if not authenticated.
    """
    # OAuth2PasswordBearer will raise a 401 if the header is missing/malformed
    user = await auth.get_current_user_from_token(token)
    if user is None:
        # This case covers valid token format but expired/invalid signature/user not found
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials", # Keep detail generic
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

# Modify the /users/me endpoint in api.py to use the new dependency