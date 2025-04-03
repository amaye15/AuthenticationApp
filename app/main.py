# app/main.py
import gradio as gr
import httpx
import websockets
import asyncio
import json
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends # Import FastAPI itself
from .database import connect_db, disconnect_db, database, metadata, users
from .api import router as api_router
from . import schemas, auth, dependencies
from .websocket import manager # Import the connection manager instance

from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import sqlite

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://127.0.0.1:7860/api"

# --- Lifespan (remains the same) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... (same DB setup code) ...
    logger.info("Application startup: Connecting DB...")
    await connect_db()
    logger.info("Application startup: DB Connected. Checking/Creating tables...")
    if database.is_connected:
        try:
            check_query = "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name;"
            table_exists = await database.fetch_one(query=check_query, values={"table_name": users.name})
            if not table_exists:
                logger.info(f"Table '{users.name}' not found, attempting creation using async connection...")
                dialect = sqlite.dialect()
                create_table_stmt = str(CreateTable(users).compile(dialect=dialect))
                await database.execute(query=create_table_stmt)
                logger.info(f"Table '{users.name}' created successfully via async connection.")
                table_exists_after = await database.fetch_one(query=check_query, values={"table_name": users.name})
                if table_exists_after: logger.info(f"Table '{users.name}' verified after creation.")
                else: logger.error(f"Table '{users.name}' verification FAILED after creation attempt!")
            else:
                logger.info(f"Table '{users.name}' already exists (checked via async connection).")
        except Exception as db_setup_err:
            logger.exception(f"CRITICAL error during async DB table setup: {db_setup_err}")
    else:
        logger.error("CRITICAL: Database connection failed, skipping table setup.")
    logger.info("Application startup: DB setup phase complete.")
    yield
    logger.info("Application shutdown: Disconnecting DB...")
    await disconnect_db()
    logger.info("Application shutdown: DB Disconnected.")


# --- FastAPI App Setup (remains the same) ---
app = FastAPI(lifespan=lifespan)
app.include_router(api_router, prefix="/api")

# --- Helper functions (make_api_request remains the same) ---
async def make_api_request(method: str, endpoint: str, **kwargs):
    async with httpx.AsyncClient() as client:
        url = f"{API_BASE_URL}{endpoint}"
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            logger.error(f"HTTP Request failed: {e.request.method} {e.request.url} - {e}")
            return {"error": f"Network error contacting API: {e}"}
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status error: {e.response.status_code} - {e.response.text}")
            try: detail = e.response.json().get("detail", e.response.text)
            except json.JSONDecodeError: detail = e.response.text
            return {"error": f"API Error: {detail}"}
        except Exception as e:
             logger.error(f"Unexpected error during API call: {e}")
             return {"error": f"An unexpected error occurred: {str(e)}"}

# --- WebSocket handling within Gradio ---
# <<< MODIFIED: Accept trigger state object >>>
async def listen_to_websockets(token: str, notification_list_state: gr.State, notification_trigger_state: gr.State):
    """Connects to WS and updates state list and trigger when a message arrives."""
    ws_listener_id = f"WSListener-{os.getpid()}-{asyncio.current_task().get_name()}"
    logger.info(f"[{ws_listener_id}] Starting WebSocket listener task.")

    if not token:
        logger.warning(f"[{ws_listener_id}] No token provided. Listener task exiting.")
        # <<< Return original state values >>>
        return notification_list_state.value, notification_trigger_state.value

    ws_url_base = API_BASE_URL.replace("http", "ws")
    ws_url = f"{ws_url_base}/ws/{token}"
    logger.info(f"[{ws_listener_id}] Attempting to connect to WebSocket: {ws_url}")

    try:
        async with websockets.connect(ws_url, open_timeout=15.0) as websocket:
            logger.info(f"[{ws_listener_id}] WebSocket connected successfully to {ws_url}")
            while True:
                try:
                    message_str = await asyncio.wait_for(websocket.recv(), timeout=300.0)
                    logger.info(f"[{ws_listener_id}] Received raw message: {message_str}")
                    try:
                         message_data = json.loads(message_str)
                         logger.info(f"[{ws_listener_id}] Parsed message data: {message_data}")

                         if message_data.get("type") == "new_user":
                            notification = schemas.Notification(**message_data)
                            logger.info(f"[{ws_listener_id}] Processing 'new_user' notification: {notification.message}")

                            # <<< Modify state objects' values >>>
                            current_list = notification_list_state.value.copy()
                            current_list.insert(0, notification.message)
                            if len(current_list) > 10: current_list.pop()
                            notification_list_state.value = current_list
                            logger.info(f"[{ws_listener_id}] State list updated via state object. New length: {len(notification_list_state.value)}. Content: {notification_list_state.value[:5]}")

                            # <<< Update trigger state object's value >>>
                            notification_trigger_state.value += 1
                            logger.info(f"[{ws_listener_id}] Incremented notification trigger to {notification_trigger_state.value}")

                         else:
                              logger.warning(f"[{ws_listener_id}] Received message of unknown type: {message_data.get('type')}")
                    # ... (error handling for parsing) ...
                    except json.JSONDecodeError: logger.error(f"[{ws_listener_id}] Failed to decode JSON: {message_str}")
                    except Exception as parse_err: logger.error(f"[{ws_listener_id}] Error processing message: {parse_err}")
                # ... (error handling for websocket recv/connection) ...
                except asyncio.TimeoutError: logger.debug(f"[{ws_listener_id}] WebSocket recv timed out."); continue
                except websockets.ConnectionClosedOK: logger.info(f"[{ws_listener_id}] WebSocket connection closed normally."); break
                except websockets.ConnectionClosedError as e: logger.error(f"[{ws_listener_id}] WebSocket connection closed with error: {e}"); break
                except Exception as e: logger.error(f"[{ws_listener_id}] Error in listener receive loop: {e}"); await asyncio.sleep(1); break # Break on unknown errors too
    # ... (error handling for websocket connect) ...
    except asyncio.TimeoutError: logger.error(f"[{ws_listener_id}] WebSocket initial connection timed out: {ws_url}")
    except websockets.exceptions.InvalidURI: logger.error(f"[{ws_listener_id}] Invalid WebSocket URI: {ws_url}")
    except websockets.exceptions.WebSocketException as e: logger.error(f"[{ws_listener_id}] WebSocket connection failed: {e}")
    except Exception as e: logger.error(f"[{ws_listener_id}] Unexpected error in WebSocket listener task: {e}")

    logger.info(f"[{ws_listener_id}] Listener task finished.")
    # <<< Return original state values >>>
    return notification_list_state.value, notification_trigger_state.value

# --- Gradio Interface ---
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    # State variables
    auth_token = gr.State(None)
    user_info = gr.State(None)
    notification_list = gr.State([])
    websocket_task = gr.State(None)
    # <<< Add Dummy State >>>
    notification_trigger = gr.State(0) # Simple counter

    # --- UI Components ---
    with gr.Tabs() as tabs:
        # --- Registration/Login Tabs (remain the same) ---
        with gr.TabItem("Register", id="register_tab"):
            gr.Markdown("## Create a new account")
            reg_email = gr.Textbox(label="Email", type="email")
            reg_password = gr.Textbox(label="Password (min 8 chars)", type="password")
            reg_confirm_password = gr.Textbox(label="Confirm Password", type="password")
            reg_button = gr.Button("Register")
            reg_status = gr.Textbox(label="Status", interactive=False)
        with gr.TabItem("Login", id="login_tab"):
            gr.Markdown("## Login to your account")
            login_email = gr.Textbox(label="Email", type="email")
            login_password = gr.Textbox(label="Password", type="password")
            login_button = gr.Button("Login")
            login_status = gr.Textbox(label="Status", interactive=False)

        # --- Welcome Tab ---
        with gr.TabItem("Welcome", id="welcome_tab", visible=False) as welcome_tab:
            gr.Markdown("## Welcome!", elem_id="welcome_header")
            welcome_message = gr.Markdown("", elem_id="welcome_message")
            logout_button = gr.Button("Logout")
            gr.Markdown("---")
            gr.Markdown("## Real-time Notifications")
            notification_display = gr.Textbox(
                label="New User Alerts",
                lines=5,
                max_lines=10,
                interactive=False,
                # <<< REMOVE every=1 >>>
            )
            # <<< Add Dummy Component (Hidden) >>>
            dummy_trigger_output = gr.Textbox(label="trigger", visible=False)


    # --- Event Handlers ---

    # Registration Logic (remains the same)
    async def handle_register(email, password, confirm_password):
        if not email or not password or not confirm_password: return gr.update(value="Please fill in all fields.")
        if password != confirm_password: return gr.update(value="Passwords do not match.")
        if len(password) < 8: return gr.update(value="Password must be at least 8 characters long.")
        payload = {"email": email, "password": password}
        result = await make_api_request("post", "/register", json=payload)
        if "error" in result: return gr.update(value=f"Registration failed: {result['error']}")
        else: return gr.update(value=f"Registration successful for {result.get('email')}! Please log in.")

    reg_button.click(handle_register, inputs=[reg_email, reg_password, reg_confirm_password], outputs=[reg_status])

    # Login Logic
    # <<< MODIFIED: Pass trigger state, update outputs >>>
    async def handle_login(email, password, current_task, current_trigger_val):
        # --- Output state needs to align with return values ---
        # Returns: login_status, auth_token, user_info, tabs, welcome_tab, welcome_message, websocket_task, notification_trigger
        outputs_tuple = (
            gr.update(value="Please enter email and password."), # login_status
            None, None, None, gr.update(visible=False), None, # auth_token, user_info, tabs, welcome_tab, welcome_message
            current_task, # websocket_task (no change)
            current_trigger_val # notification_trigger (no change)
        )
        if not email or not password: return outputs_tuple

        payload = {"email": email, "password": password}
        result = await make_api_request("post", "/login", json=payload)

        if "error" in result:
             outputs_tuple = (gr.update(value=f"Login failed: {result['error']}"), None, None, None, gr.update(visible=False), None, current_task, current_trigger_val)
             return outputs_tuple
        else:
            token = result.get("access_token")
            user_data = await dependencies.get_optional_current_user(token)
            if not user_data:
                 outputs_tuple = (gr.update(value="Login succeeded but failed to fetch user data."), None, None, None, gr.update(visible=False), None, current_task, current_trigger_val)
                 return outputs_tuple

            if current_task and not current_task.done():
                current_task.cancel()
                try: await current_task
                except asyncio.CancelledError: logger.info("Previous WebSocket task cancelled.")

            # <<< Pass both state objects to listener >>>
            new_task = asyncio.create_task(listen_to_websockets(token, notification_list, notification_trigger))

            welcome_msg = f"Welcome, {user_data.email}!"
            # --- Ensure number of return values matches outputs ---
            return (
                gr.update(value="Login successful!"),       # login_status
                token,                                      # auth_token state
                user_data.model_dump(),                     # user_info state
                gr.update(selected="welcome_tab"),          # Switch Tabs
                gr.update(visible=True),                    # Make welcome tab visible
                gr.update(value=welcome_msg),               # Update welcome message markdown
                new_task,                                   # websocket_task state
                0                                           # Reset notification_trigger state to 0 on login
            )

    # <<< MODIFIED: Add notification_trigger to inputs/outputs >>>
    login_button.click(
        handle_login,
        inputs=[login_email, login_password, websocket_task, notification_trigger],
        outputs=[login_status, auth_token, user_info, tabs, welcome_tab, welcome_message, websocket_task, notification_trigger]
    )

    # Function to update the notification display based on the list state
    # <<< Triggered by dummy component now >>>
    def update_notification_ui(notif_list): # Takes the list value directly now
        log_msg = f"UI Update Triggered via Dummy. State List Length: {len(notif_list)}. Content: {notif_list[:5]}"
        logger.info(log_msg) # Use info level to ensure visibility
        new_value = "\n".join(notif_list)
        return gr.update(value=new_value)

    # <<< Add Event handler for the dummy trigger >>>
    # When the dummy_trigger_output *would* change (because notification_trigger state changed)...
    # ...call the update_notification_ui function.
    # Pass the *current* value of notification_list state as input to the function.
    dummy_trigger_output.change(
        fn=update_notification_ui,
        inputs=[notification_list],        # Input is the list state we want to display
        outputs=[notification_display]     # Output updates the real display textbox
    )

    # <<< Link the dummy trigger state to the dummy output component >>>
    # This makes the dummy_trigger_output.change event fire when notification_trigger changes
    notification_trigger.change(lambda x: x, inputs=notification_trigger, outputs=dummy_trigger_output, queue=False) # Use queue=False for immediate trigger if possible


    # Logout Logic
    # <<< MODIFIED: Add notification_trigger to outputs >>>
    async def handle_logout(current_task):
        if current_task and not current_task.done():
            current_task.cancel()
            try: await current_task
            except asyncio.CancelledError: logger.info("WebSocket task cancelled on logout.")
        # --- Ensure number of return values matches outputs ---
        return ( None, None, [], None, # auth_token, user_info, notification_list, websocket_task
                 gr.update(selected="login_tab"), gr.update(visible=False), # tabs, welcome_tab
                 gr.update(value=""), gr.update(value=""), # welcome_message, login_status
                 0 ) # notification_trigger (reset to 0)

    # <<< MODIFIED: Add notification_trigger to outputs >>>
    logout_button.click(
        handle_logout,
        inputs=[websocket_task],
        outputs=[
            auth_token, user_info, notification_list, websocket_task,
            tabs, welcome_tab, welcome_message, login_status,
            notification_trigger # Add trigger to outputs
        ]
    )

# Mount Gradio App (remains the same)
app = gr.mount_gradio_app(app, demo, path="/")

# Run Uvicorn (remains the same)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=7860, reload=True)