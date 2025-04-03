# app/database.py
import os
from databases import Database
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text
import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

load_dotenv()
logger = logging.getLogger(__name__)

# --- Database URL Configuration ---
# --- CHANGE THIS LINE: Use path relative to WORKDIR (/code) ---
# Using an absolute path inside /code is also fine: '/code/app.db'
DEFAULT_DB_PATH = "/code/app.db" # Store DB in the main workdir

raw_db_url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

final_database_url = raw_db_url
if raw_db_url.startswith("sqlite+aiosqlite"):
    parsed_url = urlparse(raw_db_url)
    query_params = parse_qs(parsed_url.query)
    if 'check_same_thread' not in query_params:
        query_params['check_same_thread'] = ['False']
        new_query = urlencode(query_params, doseq=True)
        final_database_url = urlunparse(parsed_url._replace(query=new_query))
    logger.info(f"Using final async DB URL: {final_database_url}")
else:
    logger.info(f"Using non-SQLite async DB URL: {final_database_url}")

# --- Async Database Instance ---
database = Database(final_database_url)
metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True, nullable=False),
    Column("hashed_password", String, nullable=False),
)

# --- Synchronous Engine for Initial Table Creation ---
sync_db_url = final_database_url.replace("+aiosqlite", "")
logger.info(f"Using synchronous DB URL for initial check/create: {sync_db_url}")
engine = create_engine(sync_db_url)

# --- Directory and Table Creation Logic ---
db_file_path = ""
if sync_db_url.startswith("sqlite"):
    path_part = sync_db_url.split("sqlite:///")[-1].split("?")[0]
    # Use os.path.abspath to resolve relative paths based on WORKDIR
    db_file_path = os.path.abspath(path_part) # Should resolve to /code/app.db

if db_file_path:
    # --- CHANGE THIS LINE: Check writability of the target directory ---
    db_dir = os.path.dirname(db_file_path) # Should be /code
    logger.info(f"Ensuring database directory exists: {db_dir}")
    try:
        # Directory /code should exist because it's the WORKDIR
        # We mainly need to check if it's writable
        if not os.path.exists(db_dir):
             logger.warning(f"Database directory {db_dir} does not exist! Attempting creation (may fail).")
             # This shouldn't really happen for /code unless WORKDIR is wrong
             os.makedirs(db_dir, exist_ok=True)

        if not os.access(db_dir, os.W_OK):
            # If /code isn't writable, we have a bigger problem
            logger.error(f"Database directory {db_dir} is not writable! Database creation will likely fail.")
        else:
            logger.info(f"Database directory {db_dir} appears writable.")

    except OSError as e:
        logger.error(f"Error accessing database directory {db_dir}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking directory {db_dir}: {e}")

# Now try connecting and creating the table with the sync engine
try:
    logger.info("Attempting to connect with sync engine to check/create table...")
    with engine.connect() as connection:
        try:
            connection.execute(text("SELECT 1 FROM users LIMIT 1"))
            logger.info("Users table already exists.")
        except Exception as table_check_exc:
            logger.warning(f"Users table check failed ({type(table_check_exc).__name__}), attempting creation...")
            metadata.create_all(bind=engine)
            logger.info("Users table created (or creation attempted).")

except Exception as e:
    # Hopefully, this won't happen now if /code is writable
    logger.exception(f"CRITICAL: Failed to connect/create database tables using sync engine: {e}")


# --- Async connect/disconnect functions ---
async def connect_db():
    try:
        await database.connect()
        logger.info(f"Database connection established (async): {final_database_url}")
    except Exception as e:
        logger.exception(f"Failed to establish async database connection: {e}")
        raise

async def disconnect_db():
    try:
        await database.disconnect()
        logger.info("Database connection closed (async).")
    except Exception as e:
        logger.exception(f"Error closing async database connection: {e}")