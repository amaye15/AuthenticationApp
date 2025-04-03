# app/database.py
import os
from databases import Database
from dotenv import load_dotenv
# --- ADD THIS IMPORT ---
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text, exc as sqlalchemy_exc
import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

load_dotenv()
logger = logging.getLogger(__name__)

# --- Database URL Configuration ---
DEFAULT_DB_PATH = "/tmp/app.db" # Store DB in the temporary directory
raw_db_url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

# --- URL Parsing and Async Database setup (remains the same) ---
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
    db_file_path = path_part # Should be /tmp/app.db

if db_file_path:
    db_dir = os.path.dirname(db_file_path) # Should be /tmp
    logger.info(f"Checking database directory: {db_dir}")
    try:
        if not os.path.exists(db_dir):
             logger.error(f"CRITICAL: Directory {db_dir} does not exist!")
        elif not os.access(db_dir, os.W_OK):
            logger.error(f"CRITICAL: Directory {db_dir} is not writable! Cannot create database.")
        else:
            logger.info(f"Database directory {db_dir} appears writable.")
    except OSError as e:
        logger.error(f"Error accessing database directory {db_dir}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking directory {db_dir}: {e}")


# --- Refined Synchronous Table Check/Creation ---
try:
    logger.info("Attempting sync connection to check/create table...")
    with engine.connect() as connection:
        logger.info("Sync engine connection successful.")
        try:
            # Check if table exists
            connection.execute(text("SELECT 1 FROM users LIMIT 1"))
            logger.info("Users table already exists (checked via sync connection).")
        # --- Catch specific SQLAlchemy error ---
        except sqlalchemy_exc.OperationalError as table_missing_err:
             # Check if the error message specifically indicates "no such table"
             if "no such table" in str(table_missing_err).lower():
                 logger.warning("Users table not found (expected), attempting creation...")
                 try:
                     # Begin a transaction explicitly (optional, connect() usually does)
                     # with connection.begin(): # Alternative way to manage transaction
                     # Use the connection object for create_all
                     metadata.create_all(bind=connection) # <-- Bind to connection
                     # --- Explicitly commit ---
                     connection.commit()
                     logger.info("Users table creation attempted and committed via sync connection.")
                     # --- Verify creation immediately ---
                     try:
                          connection.execute(text("SELECT 1 FROM users LIMIT 1"))
                          logger.info("Users table successfully verified immediately after creation.")
                     except Exception as verify_err:
                          logger.error(f"Failed to verify table immediately after creation: {verify_err}")

                 except Exception as creation_err:
                      logger.exception(f"Error during table creation or commit: {creation_err}")
                      # Optionally rollback? connection.rollback()

             else:
                 # Log other OperationalErrors during the check phase
                 logger.error(f"OperationalError during table check (but not 'no such table'): {table_missing_err}")
                 raise # Re-raise unexpected errors

        except Exception as table_check_exc: # Catch other unexpected errors during check
             logger.error(f"Unexpected error during table check: {type(table_check_exc).__name__}: {table_check_exc}")
             raise # Re-raise unexpected errors

except Exception as e:
    # Errors connecting, or unexpected errors during check/create phase
    logger.exception(f"CRITICAL: Failed during sync connection or table setup: {e}")


# --- Async connect/disconnect functions (remain the same) ---
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