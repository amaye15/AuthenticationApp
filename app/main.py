# app/main.py
# Remove Gradio imports if any remain
# import gradio as gr <--- REMOVE

import httpx # Keep if needed, but not used in this version of main.py
import websockets # Keep if needed, but not used in this version of main.py
import asyncio
import json
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request # Add Request
from fastapi.responses import HTMLResponse    # Add HTMLResponse
from fastapi.staticfiles import StaticFiles     # Add StaticFiles
from fastapi.templating import Jinja2Templates # Add Jinja2Templates (optional, but good practice)

# --- Import necessary items from database.py ---
from .database import connect_db, disconnect_db, database, metadata, users
from .api import router as api_router
from . import schemas, auth, dependencies
from .websocket import manager # Keep

# --- Import SQLAlchemy helpers for DDL generation ---
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import sqlite

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- REMOVE API_BASE_URL if not needed elsewhere ---
# API_BASE_URL = "http://127.0.0.1:7860/api"

# --- Lifespan Event (remains the same) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... (same DB setup code as previous correct version) ...
    logger.info("Application startup: Connecting DB...")
    await connect_db()
    logger.info("Application startup: DB Connected. Checking/Creating tables...")
    if database.is_connected:
        try:
            check_query = "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name;"
            table_exists = await database.fetch_one(query=check_query, values={"table_name": users.name})
            if not table_exists:
                logger.info(f"Table '{users.name}' not found, creating...")
                dialect = sqlite.dialect()
                create_table_stmt = str(CreateTable(users).compile(dialect=dialect))
                await database.execute(query=create_table_stmt)
                logger.info(f"Table '{users.name}' created.")
                table_exists_after = await database.fetch_one(query=check_query, values={"table_name": users.name})
                if table_exists_after: logger.info(f"Table '{users.name}' verified.")
                else: logger.error(f"Table '{users.name}' verification FAILED!")
            else:
                logger.info(f"Table '{users.name}' already exists.")
        except Exception as db_setup_err:
            logger.exception(f"CRITICAL error during async DB table setup: {db_setup_err}")
    else:
        logger.error("CRITICAL: Database connection failed, skipping table setup.")
    logger.info("Application startup: DB setup phase complete.")
    yield
    logger.info("Application shutdown: Disconnecting DB...")
    await disconnect_db()
    logger.info("Application shutdown: DB Disconnected.")


# Create the main FastAPI app instance
app = FastAPI(lifespan=lifespan)

# Mount API routes FIRST
app.include_router(api_router, prefix="/api")

# --- Mount Static files ---
# Ensure the path exists relative to where you run uvicorn (or use absolute paths)
# Since main.py is in app/, static/ is one level up
# Adjust 'directory' path if needed based on your execution context
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Optional: Use Jinja2Templates for more flexibility ---
# templates = Jinja2Templates(directory="templates")

# --- Serve the main HTML page ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Simple way: Read the file directly
    try:
        with open("templates/index.html", "r") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        logger.error("templates/index.html not found!")
        return HTMLResponse(content="<html><body><h1>Error: Frontend not found</h1></body></html>", status_code=500)
    # Jinja2 way (if using templates):
    # return templates.TemplateResponse("index.html", {"request": request})


# --- REMOVE Gradio mounting ---
# app = gr.mount_gradio_app(app, demo, path="/")

# --- Uvicorn run command (no changes needed here) ---
if __name__ == "__main__":
    import uvicorn
    # Note: If running from the project root directory (fastapi_gradio_auth/),
    # the app path is "app.main:app"
    uvicorn.run("app.main:app", host="0.0.0.0", port=7860, reload=True)