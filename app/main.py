import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse 
from fastapi.staticfiles import StaticFiles

from .database import connect_db, disconnect_db, database, users
from .api import router as api_router

from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import sqlite

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=7860, reload=True)