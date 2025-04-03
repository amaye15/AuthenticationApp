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
        try: response = await client.request(method, url, **kwargs); response.raise_for_status(); return response.json()
        except httpx.RequestError as e: logger.error(f"HTTP Request failed: {e.request.method} {e.request.url} - {e}"); return {"error": f"Network error: {e}"}
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status error: {e.response.status_code} - {e.response.text}")
            try: detail = e.response.json().get("detail", e.response.text)
            except json.JSONDecodeError: detail = e.response.text
            return {"error": f"API Error: {detail}"}
        except Exception as e: logger.error(f"Unexpected error during API call: {e}"); return {"error": f"Unexpected error: {str(e)}"}

# --- WebSocket handling ---
# <<< Pass state objects by reference >>>
async def listen_to_websockets(token: str, notification_list_state: gr.State, notification_trigger_state: gr.State):
    """Connects to WS and updates state list and trigger when a message arrives."""
    ws_listener_id = f"WSListener-{os.getpid()}-{asyncio.current_task().get_name()}"
    logger.info(f"[{ws_listener_id}] Starting WebSocket listener task.")

    if not token:
        logger.warning(f"[{ws_listener_id}] No token provided. Task exiting.")
        return # Just exit, don't need to return state values

    ws_url_base = API_BASE_URL.replace("http", "ws")
    ws_url = f"{ws_url_base}/ws/{token}"
    logger.info(f"[{ws_listener_id}] Attempting to connect: {ws_url}")

    try:
        async with websockets.connect(ws_url, open_timeout=15.0) as websocket:
            logger.info(f"[{ws_listener_id}] WebSocket connected successfully.")
            while True:
                try:
                    message_str = await asyncio.wait_for(websocket.recv(), timeout=300.0)
                    logger.info(f"[{ws_listener_id}] Received: {message_str[:100]}...")
                    try:
                         message_data = json.loads(message_str)
                         if message_data.get("type") == "new_user":
                            notification = schemas.Notification(**message_data)
                            logger.info(f"[{ws_listener_id}] Processing 'new_user': {notification.message}")
                            # --- Modify state values directly ---
                            current_list = notification_list_state.value.copy() # Operate on copy
                            current_list.insert(0, notification.message)
                            if len(current_list) > 10: current_list.pop()
                            notification_list_state.value = current_list # Assign back modified copy
                            notification_trigger_state.value += 1 # Increment trigger
                            # --- Log the update ---
                            logger.info(f"[{ws_listener_id}] States updated: list len={len(notification_list_state.value)}, trigger={notification_trigger_state.value}")
                         else:
                              logger.warning(f"[{ws_listener_id}] Unknown message type: {message_data.get('type')}")
                    # ... (error handling for parsing) ...
                    except json.JSONDecodeError: logger.error(f"[{ws_listener_id}] JSON Decode Error: {message_str}")
                    except Exception as parse_err: logger.error(f"[{ws_listener_id}] Message Processing Error: {parse_err}")
                # ... (error handling for websocket recv/connection) ...
                except asyncio.TimeoutError: logger.debug(f"[{ws_listener_id}] WebSocket recv timed out."); continue
                except websockets.ConnectionClosedOK: logger.info(f"[{ws_listener_id}] WebSocket closed normally."); break
                except websockets.ConnectionClosedError as e: logger.error(f"[{ws_listener_id}] WebSocket closed with error: {e}"); break
                except Exception as e: logger.error(f"[{ws_listener_id}] Listener loop error: {e}"); await asyncio.sleep(1); break
    # ... (error handling for websocket connect) ...
    except asyncio.TimeoutError: logger.error(f"[{ws_listener_id}] WebSocket initial connection timed out.")
    except websockets.exceptions.InvalidURI: logger.error(f"[{ws_listener_id}] Invalid WebSocket URI.")
    except websockets.exceptions.WebSocketException as e: logger.error(f"[{ws_listener_id}] WebSocket connection failed: {e}")
    except Exception as e: logger.error(f"[{ws_listener_id}] Unexpected error in listener task: {e}")

    logger.info(f"[{ws_listener_id}] Listener task finished.")
    # No need to return state values when task ends

# --- Gradio Interface ---
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    # State variables
    auth_token = gr.State(None)
    user_info = gr.State(None)
    notification_list = gr.State([])
    websocket_task = gr.State(None)
    # Add trigger states
    notification_trigger = gr.State(0)
    last_polled_trigger = gr.State(0) # State to track last seen trigger

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
            notification_display = gr.Textbox( # Visible display
                label="New User Alerts", lines=5, max_lines=10, interactive=False
            )
            # <<< Hidden component for polling >>>
            dummy_poller = gr.Number(label="poller", value=0, visible=False, every=1)


    # --- Event Handlers ---

    # Registration Logic (remains the same)
    async def handle_register(email, password, confirm_password):
        if not email or not password or not confirm_password: return gr.update(value="Please fill fields.")
        if password != confirm_password: return gr.update(value="Passwords mismatch.")
        if len(password) < 8: return gr.update(value="Password >= 8 chars.")
        payload = {"email": email, "password": password}
        result = await make_api_request("post", "/register", json=payload)
        if "error" in result: return gr.update(value=f"Register failed: {result['error']}")
        else: return gr.update(value=f"Register success: {result.get('email')}! Log in.")
    reg_button.click(handle_register, inputs=[reg_email, reg_password, reg_confirm_password], outputs=[reg_status])

    # Login Logic
    # <<< MODIFIED: Pass/Reset both trigger states >>>
    async def handle_login(email, password, current_task, current_trigger_val, current_last_poll_val):
        # Define failure outputs matching the outputs list
        fail_outputs = (gr.update(value="..."), None, None, None, gr.update(visible=False), None, current_task, current_trigger_val, current_last_poll_val)

        if not email or not password: return fail_outputs[:1] + (gr.update(value="Enter email/password"),) + fail_outputs[2:]

        payload = {"email": email, "password": password}
        result = await make_api_request("post", "/login", json=payload)

        if "error" in result: return (gr.update(value=f"Login failed: {result['error']}"),) + fail_outputs[1:]
        else:
            token = result.get("access_token")
            user_data = await dependencies.get_optional_current_user(token)
            if not user_data: return (gr.update(value="Login ok but user fetch failed."),) + fail_outputs[1:]

            if current_task and not current_task.done():
                current_task.cancel()
                try: await current_task
                except asyncio.CancelledError: logger.info("Previous WebSocket task cancelled.")

            # <<< Pass state objects to listener >>>
            new_task = asyncio.create_task(listen_to_websockets(token, notification_list, notification_trigger))

            welcome_msg = f"Welcome, {user_data.email}!"
            # Reset triggers on successful login
            return (
                gr.update(value="Login successful!"), token, user_data.model_dump(), # status, token, user_info
                gr.update(selected="welcome_tab"), gr.update(visible=True), gr.update(value=welcome_msg), # UI changes
                new_task, 0, 0 # websocket_task, notification_trigger, last_polled_trigger
            )

    # <<< MODIFIED: Add last_polled_trigger to inputs/outputs >>>
    login_button.click(
        handle_login,
        inputs=[login_email, login_password, websocket_task, notification_trigger, last_polled_trigger],
        outputs=[login_status, auth_token, user_info, tabs, welcome_tab, welcome_message, websocket_task, notification_trigger, last_polled_trigger]
    )


    # <<< Polling function >>>
    def poll_and_update(current_trigger_value, last_known_trigger, current_notif_list):
        """ Checks trigger state change and updates UI if needed. """
        if current_trigger_value != last_known_trigger:
            logger.info(f"Polling detected trigger change ({last_known_trigger} -> {current_trigger_value}). Updating UI.")
            new_value = "\n".join(current_notif_list)
            # Return new display value AND update last_known_trigger state value
            return gr.update(value=new_value), current_trigger_value
        else:
            # No change, return NoUpdate for display AND existing last_known_trigger value
            return gr.NoUpdate(), last_known_trigger

    # <<< Attach polling function to the dummy component's change event >>>
    dummy_poller.change(
        fn=poll_and_update,
        inputs=[notification_trigger, last_polled_trigger, notification_list],
        outputs=[notification_display, last_polled_trigger], # Update display & last polled state
        queue=False # Try immediate update
    )


    # Logout Logic
    # <<< MODIFIED: Reset both trigger states >>>
    async def handle_logout(current_task):
        if current_task and not current_task.done():
            current_task.cancel()
            try: await current_task
            except asyncio.CancelledError: logger.info("WebSocket task cancelled on logout.")
        # Reset all relevant states
        return ( None, None, [], None, # auth_token, user_info, notification_list, websocket_task
                 gr.update(selected="login_tab"), gr.update(visible=False), # tabs, welcome_tab
                 gr.update(value=""), gr.update(value=""), # welcome_message, login_status
                 0, 0 ) # notification_trigger, last_polled_trigger (reset)

    # <<< MODIFIED: Add last_polled_trigger to outputs >>>
    logout_button.click(
        handle_logout,
        inputs=[websocket_task],
        outputs=[
            auth_token, user_info, notification_list, websocket_task,
            tabs, welcome_tab, welcome_message, login_status,
            notification_trigger, last_polled_trigger # Add trigger states here
        ]
    )

# Mount Gradio App (remains the same)
app = gr.mount_gradio_app(app, demo, path="/")

# Run Uvicorn (remains the same)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=7860, reload=True)