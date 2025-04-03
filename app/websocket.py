from fastapi import WebSocket
from typing import List, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Store connections with user ID if available for targeted messaging later
        self.active_connections: Dict[Optional[int], List[WebSocket]] = {}
        # Map websocket to user_id for easier removal
        self.websocket_to_user: Dict[WebSocket, Optional[int]] = {}

    async def connect(self, websocket: WebSocket, user_id: Optional[int] = None):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        self.websocket_to_user[websocket] = user_id
        logger.info(f"WebSocket connected: {websocket.client.host}:{websocket.client.port}, User ID: {user_id}")
        logger.info(f"Total connections: {sum(len(conns) for conns in self.active_connections.values())}")


    def disconnect(self, websocket: WebSocket):
        user_id = self.websocket_to_user.pop(websocket, None)
        if user_id in self.active_connections:
            try:
                self.active_connections[user_id].remove(websocket)
                if not self.active_connections[user_id]:
                    del self.active_connections[user_id]
            except ValueError:
                logger.warning(f"WebSocket not found in active list for user {user_id} during disconnect.")

        logger.info(f"WebSocket disconnected: {websocket.client.host}:{websocket.client.port}, User ID: {user_id}")
        logger.info(f"Total connections: {sum(len(conns) for conns in self.active_connections.values())}")


    async def broadcast(self, message: str, sender_id: Optional[int] = None):
        disconnected_websockets = []
        # Iterate through all connections
        all_websockets = [ws for user_conns in self.active_connections.values() for ws in user_conns]
        logger.info(f"Broadcasting to {len(all_websockets)} connections (excluding sender if ID matches). Sender ID: {sender_id}")

        for websocket in all_websockets:
             # Send to all *other* users (or all if sender_id is None)
            ws_user_id = self.websocket_to_user.get(websocket)
            # Requirement: "all *other* connected users should see"
            # Send if the websocket isn't associated with the sender_id
            # (Note: If a user has multiple tabs/connections open, they might still receive it
            # if the sender_id check only excludes one specific connection. This simple broadcast
            # targets users based on their ID at connection time).
            # Let's refine: Send if the user_id associated with the WS is not the sender_id
            if ws_user_id != sender_id:
                try:
                    await websocket.send_text(message)
                    logger.debug(f"Message sent to user {ws_user_id}")
                except Exception as e:
                    logger.error(f"Error sending message to websocket {websocket.client}: {e}. Marking for disconnect.")
                    disconnected_websockets.append(websocket)

        # Clean up connections that failed during broadcast
        for ws in disconnected_websockets:
            self.disconnect(ws)

manager = ConnectionManager()