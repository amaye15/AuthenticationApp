# app/api.py
from fastapi import APIRouter, HTTPException, status, Depends, WebSocket, WebSocketDisconnect
import logging

from . import schemas, crud, auth, models
from .websocket import manager
from .dependencies import get_required_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

# --- FIX THE DECORATORS HERE ---
@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=models.User) # <-- FIX HERE
async def register_user(user_in: schemas.UserCreate):
    existing_user = await crud.get_user_by_email(user_in.email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    hashed_password = auth.get_password_hash(user_in.password)
    user_id = await crud.create_user(user_in=user_in, hashed_password=hashed_password)
    notification_msg = schemas.Notification(email=user_in.email, message=f"New user registered: {user_in.email}").model_dump_json()
    await manager.broadcast(notification_msg, sender_id=user_id)
    created_user = await crud.get_user_by_id(user_id)
    if not created_user: raise HTTPException(status_code=500, detail="Failed to retrieve created user")
    return models.User(id=created_user.id, email=created_user.email)

@router.post("/login", response_model=schemas.Token) # <-- FIX HERE
async def login_for_access_token(form_data: schemas.UserLogin):
    user = await crud.get_user_by_email(form_data.email)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    access_token = auth.create_session_token(user_id=user.id)
    return {"access_token": access_token, "token_type": "bearer"}
# --- END FIXES ---

@router.get("/users/me", response_model=models.User)
async def read_users_me(current_user: models.User = Depends(get_required_current_user)):
    """
    Returns the current authenticated user's details based on the
    Authorization: Bearer <token> header.
    """
    return current_user

@router.websocket("/ws/{user_id_token}")
async def websocket_endpoint(websocket: WebSocket, user_id_token: str):
    user_id = await auth.get_user_id_from_token(user_id_token)
    if user_id is None:
        logger.warning(f"WebSocket connection rejected: Invalid token {user_id_token}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION); return
    await manager.connect(websocket, user_id)
    try:
        while True: data = await websocket.receive_text(); logger.debug(f"Received WS msg from {user_id}: {data}")
    except WebSocketDisconnect: manager.disconnect(websocket); logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e: manager.disconnect(websocket); logger.error(f"WebSocket error for user {user_id}: {e}")