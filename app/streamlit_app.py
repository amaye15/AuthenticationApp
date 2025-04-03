# streamlit_app.py
import streamlit as st
from streamlit_autorefresh import st_autorefresh # For periodic refresh
import httpx
import asyncio
import websockets
import json
import threading
import queue
import logging
import time
import os

# Import backend components
from app import crud, models, schemas, auth, dependencies
from app.database import ensure_db_and_table_exist # Sync function
from app.websocket import manager # Import the manager instance

# FastAPI imports for mounting
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.routing import Mount
from fastapi.staticfiles import StaticFiles
from app.api import router as api_router # Import the specific API router

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Configuration ---
# Use environment variable or default for local vs deployed API endpoint
# Since we are mounting FastAPI within Streamlit for the HF Space deployment:
API_BASE_URL = "http://127.0.0.1:7860/api" # Calls within the same process
WS_BASE_URL = API_BASE_URL.replace("http", "ws")

# --- Ensure DB exists on first run ---
# This runs once per session/process start
ensure_db_and_table_exist()

# --- FastAPI Mounting Setup ---
# Create a FastAPI instance (separate from the Streamlit one)
# We won't run this directly with uvicorn, but Streamlit uses it internally
api_app = FastAPI(title="Backend API") # Can add lifespan if needed for API-specific setup later
api_app.include_router(api_router, prefix="/api")

# Mount the FastAPI app within Streamlit's internal Tornado server
# This requires monkey-patching or using available hooks if Streamlit allows.
# Simpler approach for HF Space: Run FastAPI separately is cleaner if possible.
# Reverting to the idea that for this HF Space demo, API calls will be internal HTTP requests.

# --- WebSocket Listener Thread ---
stop_event = threading.Event()
notification_queue = queue.Queue()

def websocket_listener(token: str):
    """Runs in a background thread to listen for WebSocket messages."""
    logger.info(f"[WS Thread] Listener started for token: {token[:10]}...")
    ws_url = f"{WS_BASE_URL}/ws/{token}"

    async def listen():
        try:
            async with websockets.connect(ws_url, open_timeout=10.0) as ws:
                logger.info(f"[WS Thread] Connected to {ws_url}")
                st.session_state['ws_connected'] = True
                while not stop_event.is_set():
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0) # Check stop_event frequently
                        logger.info(f"[WS Thread] Received message: {message[:100]}...")
                        try:
                             data = json.loads(message)
                             if data.get("type") == "new_user":
                                  notification = schemas.Notification(**data)
                                  notification_queue.put(notification.message) # Put message in queue
                                  logger.info("[WS Thread] Put notification in queue.")
                        except json.JSONDecodeError:
                             logger.error("[WS Thread] Failed to decode JSON.")
                        except Exception as e:
                             logger.error(f"[WS Thread] Error processing message: {e}")

                    except asyncio.TimeoutError:
                        continue # No message, check stop_event again
                    except websockets.ConnectionClosed:
                        logger.warning("[WS Thread] Connection closed.")
                        break # Exit loop if closed
        except Exception as e:
            logger.error(f"[WS Thread] Connection failed or error: {e}")
        finally:
            logger.info("[WS Thread] Listener loop finished.")
            st.session_state['ws_connected'] = False

    try:
        asyncio.run(listen())
    except Exception as e:
        logger.error(f"[WS Thread] asyncio.run error: {e}")
    logger.info("[WS Thread] Listener thread exiting.")


# --- Streamlit UI ---

st.set_page_config(layout="wide")

# --- Initialize Session State ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'token' not in st.session_state:
    st.session_state.token = None
if 'user_email' not in st.session_state:
    st.session_state.user_email = None
if 'notifications' not in st.session_state:
    st.session_state.notifications = []
if 'ws_thread' not in st.session_state:
    st.session_state.ws_thread = None
if 'ws_connected' not in st.session_state:
     st.session_state.ws_connected = False

# --- Notification Processing ---
new_notifications = []
while not notification_queue.empty():
    try:
        msg = notification_queue.get_nowait()
        new_notifications.append(msg)
    except queue.Empty:
        break

if new_notifications:
    logger.info(f"Processing {len(new_notifications)} notifications from queue.")
    # Prepend new notifications to the session state list
    current_list = st.session_state.notifications
    st.session_state.notifications = new_notifications + current_list
    # Limit history
    if len(st.session_state.notifications) > 15:
        st.session_state.notifications = st.session_state.notifications[:15]
    # No explicit rerun needed here, Streamlit should rerun due to state change (?)
    # or due to autorefresh below.

# --- Auto Refresh ---
# Refresh every 2 seconds to check the queue and update display
count = st_autorefresh(interval=2000, limit=None, key="notifrefresh")

# --- API Client ---
client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=10.0)

# --- Helper Functions for API Calls ---
async def api_register(email, password):
    try:
        response = await client.post("/register", json={"email": email, "password": password})
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", e.response.text)
        logger.error(f"API Register Error: {e.response.status_code} - {detail}")
        return {"success": False, "error": f"API Error: {detail}"}
    except Exception as e:
        logger.exception("Register call failed")
        return {"success": False, "error": f"Request failed: {e}"}

async def api_login(email, password):
    try:
        response = await client.post("/login", json={"email": email, "password": password})
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", e.response.text)
        logger.error(f"API Login Error: {e.response.status_code} - {detail}")
        return {"success": False, "error": f"API Error: {detail}"}
    except Exception as e:
        logger.exception("Login call failed")
        return {"success": False, "error": f"Request failed: {e}"}

# --- UI Rendering ---
st.title("Authentication & Notification App (Streamlit)")

if not st.session_state.logged_in:
    st.sidebar.header("Login or Register")
    login_tab, register_tab = st.sidebar.tabs(["Login", "Register"])

    with login_tab:
        with st.form("login_form"):
            login_email = st.text_input("Email", key="login_email")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_button = st.form_submit_button("Login")

            if login_button:
                if not login_email or not login_password:
                    st.error("Please enter email and password.")
                else:
                    result = asyncio.run(api_login(login_email, login_password)) # Run async in sync context
                    if result["success"]:
                        token = result["data"]["access_token"]
                        # Attempt to get user info immediately - needs modification if /users/me requires auth header
                        # For simplicity, just store email from login form for now
                        st.session_state.logged_in = True
                        st.session_state.token = token
                        st.session_state.user_email = login_email # Store email used for login
                        st.session_state.notifications = [] # Clear old notifications

                        # Start WebSocket listener thread
                        stop_event.clear() # Ensure stop event is clear
                        thread = threading.Thread(target=websocket_listener, args=(token,), daemon=True)
                        st.session_state.ws_thread = thread
                        thread.start()
                        logger.info("Login successful, WS thread started.")
                        st.rerun() # Rerun immediately to switch view
                    else:
                        st.error(f"Login failed: {result['error']}")

    with register_tab:
        with st.form("register_form"):
            reg_email = st.text_input("Email", key="reg_email")
            reg_password = st.text_input("Password", type="password", key="reg_password")
            reg_confirm = st.text_input("Confirm Password", type="password", key="reg_confirm")
            register_button = st.form_submit_button("Register")

            if register_button:
                if not reg_email or not reg_password or not reg_confirm:
                    st.error("Please fill all fields.")
                elif reg_password != reg_confirm:
                    st.error("Passwords do not match.")
                elif len(reg_password) < 8:
                    st.error("Password must be at least 8 characters.")
                else:
                    result = asyncio.run(api_register(reg_email, reg_password))
                    if result["success"]:
                        st.success(f"Registration successful for {result['data']['email']}! Please log in.")
                    else:
                        st.error(f"Registration failed: {result['error']}")

else: # Logged In View
    st.sidebar.header(f"Welcome, {st.session_state.user_email}!")
    if st.sidebar.button("Logout"):
        logger.info("Logout requested.")
        # Stop WebSocket thread
        if st.session_state.ws_thread and st.session_state.ws_thread.is_alive():
             logger.info("Signalling WS thread to stop.")
             stop_event.set()
             st.session_state.ws_thread.join(timeout=2.0) # Wait briefly for thread exit
             if st.session_state.ws_thread.is_alive():
                  logger.warning("WS thread did not exit cleanly.")
        # Clear session state
        st.session_state.logged_in = False
        st.session_state.token = None
        st.session_state.user_email = None
        st.session_state.notifications = []
        st.session_state.ws_thread = None
        st.session_state.ws_connected = False
        logger.info("Session cleared.")
        st.rerun()

    st.header("Dashboard")
    # Display notifications
    st.subheader("Real-time Notifications")
    ws_status = "Connected" if st.session_state.ws_connected else "Disconnected"
    st.caption(f"WebSocket Status: {ws_status}")

    if st.session_state.notifications:
        for i, msg in enumerate(st.session_state.notifications):
            st.info(f"{msg}", icon="🔔")
    else:
        st.text("No new notifications.")

    # Add a button to manually check queue/refresh if needed
    # if st.button("Check for notifications"):
    #      st.rerun() # Force rerun which includes queue check


# --- Final Cleanup ---
# Ensure httpx client is closed if script exits abnormally
# (This might not always run depending on how Streamlit terminates)
# Ideally handled within context managers if used more extensively
# asyncio.run(client.aclose())