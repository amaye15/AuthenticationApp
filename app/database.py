# # app/database.py
# import os
# from databases import Database
# from dotenv import load_dotenv
# # --- Keep only these SQLAlchemy imports ---
# from sqlalchemy import MetaData, Table, Column, Integer, String
# import logging
# from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# load_dotenv()
# logger = logging.getLogger(__name__)

# # --- Database URL Configuration ---
# DEFAULT_DB_PATH = "/tmp/app.db" # Store DB in the temporary directory
# raw_db_url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

# final_database_url = raw_db_url
# if raw_db_url.startswith("sqlite+aiosqlite"):
#     parsed_url = urlparse(raw_db_url)
#     query_params = parse_qs(parsed_url.query)
#     if 'check_same_thread' not in query_params:
#         query_params['check_same_thread'] = ['False']
#         new_query = urlencode(query_params, doseq=True)
#         final_database_url = urlunparse(parsed_url._replace(query=new_query))
#     logger.info(f"Using final async DB URL: {final_database_url}")
# else:
#     logger.info(f"Using non-SQLite async DB URL: {final_database_url}")

# # --- Async Database Instance ---
# database = Database(final_database_url)

# # --- Metadata and Table Definition (Still needed for DDL generation) ---
# metadata = MetaData()
# users = Table(
#     "users",
#     metadata,
#     Column("id", Integer, primary_key=True),
#     Column("email", String, unique=True, index=True, nullable=False),
#     Column("hashed_password", String, nullable=False),
# )

# # --- REMOVE ALL SYNCHRONOUS ENGINE AND TABLE CREATION LOGIC ---

# # --- Keep and refine Async connect/disconnect functions ---
# async def connect_db():
#     """Connects to the database, ensuring the parent directory exists."""
#     try:
#         # Ensure the directory exists just before connecting
#         db_file_path = final_database_url.split("sqlite:///")[-1].split("?")[0]
#         db_dir = os.path.dirname(db_file_path)
#         if db_dir: # Only proceed if a directory path was found
#              if not os.path.exists(db_dir):
#                  logger.info(f"Database directory {db_dir} does not exist. Attempting creation...")
#                  try:
#                      os.makedirs(db_dir, exist_ok=True)
#                      logger.info(f"Created database directory {db_dir}.")
#                  except Exception as mkdir_err:
#                      # Log error but proceed, connection might still work if path is valid but dir creation failed weirdly
#                      logger.error(f"Failed to create directory {db_dir}: {mkdir_err}")
#              # Check writability after ensuring existence attempt
#              if os.path.exists(db_dir) and not os.access(db_dir, os.W_OK):
#                   logger.error(f"CRITICAL: Directory {db_dir} exists but is not writable!")
#              elif not os.path.exists(db_dir):
#                   logger.error(f"CRITICAL: Directory {db_dir} does not exist and could not be created!")


#         # Now attempt connection
#         await database.connect()
#         logger.info(f"Database connection established (async): {final_database_url}")
#         # Table creation will happen in main.py lifespan event using this connection
#     except Exception as e:
#         logger.exception(f"Failed to establish async database connection: {e}")
#         raise # Reraise critical error during startup

# async def disconnect_db():
#     """Disconnects from the database if connected."""
#     try:
#         if database.is_connected:
#              await database.disconnect()
#              logger.info("Database connection closed (async).")
#         else:
#              logger.info("Database already disconnected (async).")
#     except Exception as e:
#         logger.exception(f"Error closing async database connection: {e}")



# app/database.py
import os
from databases import Database
from dotenv import load_dotenv
# --- Keep only these SQLAlchemy imports ---
# MetaData and Table are needed for defining the table structure
# which is used by crud.py and for DDL generation in main.py
from sqlalchemy import MetaData, Table, Column, Integer, String
import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# Load environment variables from .env file (if it exists)
load_dotenv()
logger = logging.getLogger(__name__)

# --- Database URL Configuration ---
# Use /tmp directory for the SQLite file as it's generally writable in containers
DEFAULT_DB_PATH = "/tmp/app.db"
# Get the URL from environment or use the default /tmp path
raw_db_url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

final_database_url = raw_db_url
# Ensure 'check_same_thread=False' is in the URL query string for SQLite async connection
if raw_db_url.startswith("sqlite+aiosqlite"):
    parsed_url = urlparse(raw_db_url)
    query_params = parse_qs(parsed_url.query)
    if 'check_same_thread' not in query_params:
        query_params['check_same_thread'] = ['False'] # Value needs to be a list for urlencode
        new_query = urlencode(query_params, doseq=True)
        # Rebuild the URL using _replace method of the named tuple
        final_database_url = urlunparse(parsed_url._replace(query=new_query))
    logger.info(f"Using final async DB URL: {final_database_url}")
else:
    logger.info(f"Using non-SQLite async DB URL: {final_database_url}")


# --- Async Database Instance ---
# This 'database' object will be used by crud.py and main.py lifespan
database = Database(final_database_url)


# --- Metadata and Table Definition ---
# These definitions are needed by:
# 1. crud.py to construct queries (e.g., users.select())
# 2. main.py (lifespan) to generate the CREATE TABLE statement
metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True, nullable=False),
    Column("hashed_password", String, nullable=False),
)


# --- Async connect/disconnect functions ---
# Called by the FastAPI lifespan event handler in main.py
async def connect_db():
    """Connects to the database defined by 'final_database_url'."""
    try:
        # Optional: Check/create directory if using file-based DB like SQLite
        if final_database_url.startswith("sqlite"):
            db_file_path = final_database_url.split("sqlite:///")[-1].split("?")[0]
            db_dir = os.path.dirname(db_file_path)
            if db_dir:
                 if not os.path.exists(db_dir):
                     logger.info(f"DB directory '{db_dir}' missing, creating.")
                     try:
                         os.makedirs(db_dir, exist_ok=True)
                     except Exception as mkdir_err:
                         logger.error(f"Failed to create DB directory '{db_dir}': {mkdir_err}")
                 # Check writability (best effort)
                 if os.path.exists(db_dir) and not os.access(db_dir, os.W_OK):
                      logger.error(f"CRITICAL: DB directory '{db_dir}' exists but is not writable!")
                 elif not os.path.exists(db_dir):
                      logger.error(f"CRITICAL: DB directory '{db_dir}' does not exist and could not be created!")

        # Connect using the 'databases' library instance
        if not database.is_connected:
            await database.connect()
            logger.info(f"Database connection established: {final_database_url}")
        else:
            logger.info("Database connection already established.")
        # Note: Table creation happens in main.py lifespan after connection
    except Exception as e:
        logger.exception(f"FATAL: Failed to establish async database connection: {e}")
        raise # Stop application startup if DB connection fails

async def disconnect_db():
    """Disconnects from the database if connected."""
    try:
        if database.is_connected:
             await database.disconnect()
             logger.info("Database connection closed.")
        else:
             logger.info("Database already disconnected.")
    except Exception as e:
        logger.exception(f"Error closing database connection: {e}")