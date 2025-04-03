# app/database.py
import os
from databases import Database
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text
import logging # Add logging

load_dotenv()
logger = logging.getLogger(__name__) # Add logger

# --- CHANGE THIS LINE ---
# Use an absolute path in a known writable directory like /data
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:////data/app.db")
# Note the four slashes for an absolute path: sqlite+aiosqlite:////path/to/db

# Use 'check_same_thread': False only for SQLite
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

database = Database(DATABASE_URL, connect_args=connect_args)
metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True, nullable=False),
    Column("hashed_password", String, nullable=False),
)

# Create the database and table if they don't exist (synchronous part)
# Derive the synchronous URL correctly from the potentially absolute DATABASE_URL
sync_db_url = DATABASE_URL.replace("+aiosqlite", "")
logger.info(f"Using synchronous DB URL for initial check/create: {sync_db_url}")
engine = create_engine(sync_db_url, connect_args=connect_args)

# Extract the directory path to ensure it exists
db_file_path = sync_db_url.split("sqlite:///")[-1] # Gets /data/app.db
if db_file_path: # Ensure we got a path
    db_dir = os.path.dirname(db_file_path)
    logger.info(f"Ensuring database directory exists: {db_dir}")
    try:
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
    except OSError as e:
        logger.error(f"Error creating database directory {db_dir}: {e}")
        # Proceed anyway, maybe permissions allow file creation but not dir listing/creation

# Now try connecting and creating the table
try:
    logger.info("Attempting to connect with sync engine to check/create table...")
    with engine.connect() as connection:
        # Try a simple query to see if the table exists
        try:
            connection.execute(text("SELECT 1 FROM users LIMIT 1"))
            logger.info("Users table already exists.")
        except Exception: # Catch specific DB exceptions if possible, e.g., sqlalchemy.exc.ProgrammingError
            logger.info("Users table not found or error checking, attempting creation...")
            metadata.create_all(engine) # Create tables if check fails
            logger.info("Users table created (or creation attempted).")

except Exception as e:
    logger.exception(f"CRITICAL: Failed to connect/create database tables using sync engine: {e}")
    # Application might fail to start properly here. Depending on requirements,
    # you might raise the exception or just log it and hope the async part works.
    # For now, just log it, as the async connection might still succeed later.


# Async connect/disconnect functions
async def connect_db():
    try:
        await database.connect()
        logger.info(f"Database connection established (async): {DATABASE_URL}")
    except Exception as e:
        logger.exception(f"Failed to establish async database connection: {e}")
        raise # Reraise critical error during startup lifespan

async def disconnect_db():
    try:
        await database.disconnect()
        logger.info("Database connection closed (async).")
    except Exception as e:
        logger.exception(f"Error closing async database connection: {e}")