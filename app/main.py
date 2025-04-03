import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse 
from fastapi.staticfiles import StaticFiles

from .database import connect_db, disconnect_db, database, users

from .api import router as api_router

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application startup: Connecting DB...")
    await connect_db()
    logger.info("Application startup: DB Connected. Checking/Creating tables...")
    if database.is_connected:
        try:
            # Use CREATE TABLE IF NOT EXISTS to avoid race conditions with multiple workers
            create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {users.name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR UNIQUE NOT NULL,
                hashed_password VARCHAR NOT NULL
            )
            """
            await database.execute(query=create_table_query)
            logger.info(f"Table '{users.name}' exists or was created.")
        except Exception as db_setup_err:
            logger.exception(f"CRITICAL error during async DB table setup: {db_setup_err}")
    else:
        logger.error("CRITICAL: Database connection failed, skipping table setup.")
    logger.info("Application startup: DB setup phase complete.")
    yield
    logger.info("Application shutdown: Disconnecting DB...")
    await disconnect_db()
    logger.info("Application shutdown: DB Disconnected.")


app = FastAPI(lifespan=lifespan)

app.include_router(api_router, prefix="/api")

app.mount("/static", StaticFiles(directory="static"), name="static")

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

@app.get("/health", status_code=200)
async def health_check():
    """Health check endpoint for container health monitoring"""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=7860, reload=True)