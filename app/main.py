import gradio as gr
import httpx # Use httpx for async requests from Gradio backend to API
import websockets # Use websockets library to connect from Gradio backend
import asyncio
import json
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends # Import FastAPI itself
from .api import router as api_router # Import the API router
from .database import connect_db, disconnect_db
from . import schemas, auth, dependencies # Import necessary modules

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base URL for the API (since Gradio runs its own server, even if mounted)
# Assuming Gradio runs on 7860, FastAPI routes mounted under it
API_BASE_URL = "http://127.0.0.1:7860/api" # Adjust if needed

# --- FastAPI Lifespan Event ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_db()
    # Start background task for websocket listening if needed (or handle within component interaction)
    yield
    # Shutdown
    await disconnect_db()

# Create the main FastAPI app instance that Gradio will use
# We attach our API routes to this instance.
app = FastAPI(lifespan=lifespan)
app.include_router(api_router, prefix="/api") # Mount API routes under /api

# --- Gradio UI Definition ---

# Store websocket connection globally (or within a class) for the Gradio app instance
# This is tricky because Gradio re-runs functions. State management is key.
# We'll connect the WebSocket *after* login and store the connection task/info in gr.State.

# --- Helper functions for Gradio calling the API ---

async def make_api_request(method: str, endpoint: str, **kwargs):
    async with httpx.AsyncClient() as client:
        url = f"{API_BASE_URL}{endpoint}"
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status() # Raise exception for 4xx/5xx errors
            return response.json()
        except httpx.RequestError as e:
            logger.error(f"HTTP Request failed: {e.request.method} {e.request.url} - {e}")
            return {"error": f"Network error contacting API: {e}"}
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Status error: {e.response.status_code} - {e.response.text}")
            try:
                detail = e.response.json().get("detail", e.response.text)
            except json.JSONDecodeError:
                detail = e.response.text
            return {"error": f"API Error: {detail}"}
        except Exception as e:
             logger.error(f"Unexpected error during API call: {e}")
             return {"error": f"An unexpected error occurred: {str(e)}"}

# --- WebSocket handling within Gradio ---

async def listen_to_websockets(token: str, notification_state: list):
    """Connects to WS and updates state list when a message arrives."""
    if not token:
        logger.warning("WebSocket listener: No token provided.")
        return notification_state # Return current state if no token

    ws_url_base = API_BASE_URL.replace("http", "ws")
    ws_url = f"{ws_url_base}/ws/{token}"
    logger.info(f"Attempting to connect to WebSocket: {ws_url}")

    try:
        # Add timeout to websocket connection attempt
        async with asyncio.wait_for(websockets.connect(ws_url), timeout=10.0) as websocket:
            logger.info(f"WebSocket connected successfully to {ws_url}")
            while True:
                try:
                    message_str = await websocket.recv()
                    logger.info(f"Received raw message: {message_str}")
                    message_data = json.loads(message_str)
                    logger.info(f"Parsed message data: {message_data}")

                    # Ensure it's the expected notification format
                    if message_data.get("type") == "new_user":
                         notification = schemas.Notification(**message_data)
                         # Prepend to show newest first
                         notification_state.insert(0, notification.message)
                         logger.info(f"Notification added: {notification.message}")
                         # Limit state history (optional)
                         if len(notification_state) > 10:
                             notification_state.pop()
                         # IMPORTANT: Need to trigger Gradio update. This function itself
                         # cannot directly update UI. It modifies the state, and we need
                         # a gr.update() returned by a Gradio event handler that *reads*
                         # this state. We use a polling mechanism or a hidden button trick.
                         # Let's use polling via `every=` parameter in Gradio.
                         # This function's primary job is just modifying the list.
                         # We return the modified list, but Gradio needs an event.
                         # ---> See the use of `gr.Textbox.change` and `every` below.

                except websockets.ConnectionClosedOK:
                    logger.info("WebSocket connection closed normally.")
                    break
                except websockets.ConnectionClosedError as e:
                    logger.error(f"WebSocket connection closed with error: {e}")
                    break
                except json.JSONDecodeError:
                     logger.error(f"Failed to decode JSON from WebSocket message: {message_str}")
                except Exception as e:
                     logger.error(f"Error in WebSocket listener loop: {e}")
                     # Avoid breaking the loop on transient errors maybe? Add delay?
                     await asyncio.sleep(1) # Short delay before retrying receive
    except asyncio.TimeoutError:
        logger.error(f"WebSocket connection timed out: {ws_url}")
    except websockets.exceptions.InvalidURI:
         logger.error(f"Invalid WebSocket URI: {ws_url}")
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket connection failed: {e}")
    except Exception as e:
        logger.error(f"Unexpected error connecting/listening to WebSocket: {e}")

    # Return the state as it is if connection failed or ended
    # The calling Gradio function will handle this return value.
    return notification_state


# --- Gradio Interface ---
with gr.Blocks(theme=gr.themes.Soft()) as demo:
    # State variables
    # Holds the session token after login
    auth_token = gr.State(None)
    # Holds user info {id, email} after login
    user_info = gr.State(None)
    # Holds the list of notification messages
    notification_list = gr.State([])
    # Holds the asyncio task for the WebSocket listener
    websocket_task = gr.State(None)

    # --- UI Components ---
    with gr.Tabs() as tabs:
        # --- Registration Tab ---
        with gr.TabItem("Register", id="register_tab"):
            gr.Markdown("## Create a new account")
            reg_email = gr.Textbox(label="Email", type="email")
            reg_password = gr.Textbox(label="Password (min 8 chars)", type="password")
            reg_confirm_password = gr.Textbox(label="Confirm Password", type="password")
            reg_button = gr.Button("Register")
            reg_status = gr.Textbox(label="Status", interactive=False)

        # --- Login Tab ---
        with gr.TabItem("Login", id="login_tab"):
            gr.Markdown("## Login to your account")
            login_email = gr.Textbox(label="Email", type="email")
            login_password = gr.Textbox(label="Password", type="password")
            login_button = gr.Button("Login")
            login_status = gr.Textbox(label="Status", interactive=False)

        # --- Welcome Tab (shown after login) ---
        with gr.TabItem("Welcome", id="welcome_tab", visible=False) as welcome_tab:
            gr.Markdown("## Welcome!", elem_id="welcome_header")
            welcome_message = gr.Markdown("", elem_id="welcome_message")
            logout_button = gr.Button("Logout")
            gr.Markdown("---") # Separator
            gr.Markdown("## Real-time Notifications")
            # Textbox to display notifications, updated periodically
            notification_display = gr.Textbox(
                label="New User Alerts",
                lines=5,
                max_lines=10,
                interactive=False,
                # The `every=1` makes Gradio call the update function every 1 second
                # This function will read the `notification_list` state
                every=1
            )

    # --- Event Handlers ---

    # Registration Logic
    async def handle_register(email, password, confirm_password):
        if not email or not password or not confirm_password:
            return gr.update(value="Please fill in all fields.")
        if password != confirm_password:
            return gr.update(value="Passwords do not match.")
        if len(password) < 8:
            return gr.update(value="Password must be at least 8 characters long.")

        payload = {"email": email, "password": password}
        result = await make_api_request("post", "/register", json=payload)

        if "error" in result:
            return gr.update(value=f"Registration failed: {result['error']}")
        else:
            # Optionally switch to login tab after successful registration
            return gr.update(value=f"Registration successful for {result.get('email')}! Please log in.")

    reg_button.click(
        handle_register,
        inputs=[reg_email, reg_password, reg_confirm_password],
        outputs=[reg_status]
    )

    # Login Logic
    async def handle_login(email, password, current_task):
        if not email or not password:
            return gr.update(value="Please enter email and password."), None, None, None, gr.update(visible=False), current_task

        payload = {"email": email, "password": password}
        result = await make_api_request("post", "/login", json=payload)

        if "error" in result:
            return gr.update(value=f"Login failed: {result['error']}"), None, None, None, gr.update(visible=False), current_task
        else:
            token = result.get("access_token")
            # Fetch user details using the token
            user_data = await dependencies.get_optional_current_user(token) # Use dependency directly

            if not user_data:
                 # This shouldn't happen if login succeeded, but check anyway
                 return gr.update(value="Login succeeded but failed to fetch user data."), None, None, None, gr.update(visible=False), current_task

            # Cancel any existing websocket listener task before starting a new one
            if current_task and not current_task.done():
                current_task.cancel()
                try:
                    await current_task # Wait for cancellation
                except asyncio.CancelledError:
                    logger.info("Previous WebSocket task cancelled.")

            # Start the WebSocket listener task in the background
            # We pass the notification_list state *object* itself, which the task will modify
            new_task = asyncio.create_task(listen_to_websockets(token, notification_list.value)) # Pass the list

            # Update state and UI
            welcome_msg = f"Welcome, {user_data.email}!"
            # Switch tabs and show welcome message
            return (
                gr.update(value="Login successful!"),       # login_status
                token,                                      # auth_token state
                user_data.model_dump(),                     # user_info state (store as dict)
                gr.update(selected="welcome_tab"),          # Switch Tabs
                gr.update(visible=True),                    # Make welcome tab visible
                gr.update(value=welcome_msg),               # Update welcome message markdown
                new_task                                    # websocket_task state
            )

    login_button.click(
        handle_login,
        inputs=[login_email, login_password, websocket_task],
        outputs=[login_status, auth_token, user_info, tabs, welcome_tab, welcome_message, websocket_task]
    )


    # Function to update the notification display based on the state
    # This function is triggered by the `every=1` on the notification_display Textbox
    def update_notification_ui(notif_list_state):
        # Join the list items into a string for display
        return "\n".join(notif_list_state)

    notification_display.change( # Use .change with every= setup on the component
        fn=update_notification_ui,
        inputs=[notification_list], # Read the state
        outputs=[notification_display] # Update the component
    )


    # Logout Logic
    async def handle_logout(current_task):
         # Cancel the websocket listener task if it's running
        if current_task and not current_task.done():
            current_task.cancel()
            try:
                await current_task
            except asyncio.CancelledError:
                logger.info("WebSocket task cancelled on logout.")

        # Clear state and switch back to login tab
        return (
            None,                           # Clear auth_token
            None,                           # Clear user_info
            [],                             # Clear notifications
            None,                           # Clear websocket_task
            gr.update(selected="login_tab"),# Switch Tabs
            gr.update(visible=False),       # Hide welcome tab
            gr.update(value=""),            # Clear welcome message
            gr.update(value="")             # Clear login status
        )

    logout_button.click(
        handle_logout,
        inputs=[websocket_task],
        outputs=[
            auth_token,
            user_info,
            notification_list,
            websocket_task,
            tabs,
            welcome_tab,
            welcome_message,
            login_status
        ]
    )

# Mount the Gradio app onto the FastAPI app at the root
app = gr.mount_gradio_app(app, demo, path="/")

# If running this file directly (for local testing)
# Use uvicorn to run the FastAPI app (which now includes Gradio)
if __name__ == "__main__":
    import uvicorn
    # Use port 7860 as Gradio prefers, host 0.0.0.0 for Docker
    uvicorn.run(app, host="0.0.0.0", port=7860)