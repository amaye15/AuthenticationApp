from fastapi import HTTPException, status, Request # Request may not be needed if token passed directly
from typing import Optional
from . import auth
from .models import User

# This dependency assumes the token is passed somehow,
# e.g., in headers (less likely from Gradio client code) or as an argument
# We will adapt how the token is passed from Gradio later.
async def get_optional_current_user(token: Optional[str] = None) -> Optional[User]:
    if token:
        user = await auth.get_current_user_from_token(token)
        return user
    return None

async def get_required_current_user(token: Optional[str] = None) -> User:
    user = await get_optional_current_user(token)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user