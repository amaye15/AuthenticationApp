from fastapi import APIRouter, HTTPException, status, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import logging

from . import schemas, crud, auth, models
from .websocket import manager
from .dependencies import get_required_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=models.User)
async def register_user(user_in: schemas.UserCreate):
    existing_user = await crud.get_user_by_email(user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    hashed_password = auth.get_password_hash(user_in.password)
    user_id = await crud.create_user(user_in=user_in, hashed_password=hashed_password)

    # Send notification to other connected users
    notification_msg = schemas.Notification(
        email=user_in.email,
        message=f"New user registered: {user_in.email}"
    ).model_dump_json() # Use model_dump_json for Pydantic v2

    # We broadcast but conceptually exclude the sender.
    # Since the new user isn't connected via WebSocket *yet* during registration,
    # we don't have a sender_id from the WebSocket context here.
    # We can pass the new user_id to prevent potential self-notification if
    # the WebSocket connection happens very quickly and maps the ID.
    await manager.broadcast(notification_msg, sender_id=user_id)

    # Return the newly created user's public info
    # Fetch the user details to return them accurately
    created_user = await crud.get_user_by_id(user_id)
    if not created_user:
         # This case should ideally not happen if create_user is successful
         raise HTTPException(status_code=500, detail="Failed to retrieve created user")

    # Convert UserInDB to User model for response
    return models.User(id=created_user.id, email=created_user.email)


@router.post("/login", response_model=schemas.Token)
async def login_for_access_token(form_data: schemas.UserLogin):
    user = await crud.get_user_by_email(form_data.email)
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = auth.create_session_token(user_id=user.id)
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users/me", response_model=models.User)
async def read_users_me(current_user: models.User = Depends(get_required_current_user)):
    # This endpoint now relies on the dependency correctly getting the user from the token
    # The token needs to be passed to get_required_current_user somehow.
    # In Gradio's case, we might call this function directly from Gradio's backend
    # passing the token from gr.State, rather than relying on HTTP Headers/Cookies.
    # Let's adjust the dependency call when we use it in main.py.
    return current_user


# WebSocket endpoint (can be associated with the main API router or separate)
@router.websocket("/ws/{user_id_token}")
async def websocket_endpoint(websocket: WebSocket, user_id_token: str):
    """
    WebSocket endpoint. Connects user and listens for messages.
    The user_id_token is the signed session token from login.
    """
    user_id = await auth.get_user_id_from_token(user_id_token)
    if user_id is None:
        logger.warning(f"WebSocket connection rejected: Invalid token {user_id_token}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive, maybe handle incoming messages if needed later
            data = await websocket.receive_text()
            # For now, we just broadcast on registration, not handle client messages
            logger.debug(f"Received message from {user_id}: {data} (currently ignored)")
            # Example: await websocket.send_text(f"Message text was: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        manager.disconnect(websocket)
        logger.error(f"WebSocket error for user {user_id}: {e}")
        # Optionally close with an error code
        # await websocket.close(code=status.WS_1011_INTERNAL_ERROR)