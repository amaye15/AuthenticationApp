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
# --- Keep only Sync SQLAlchemy ---
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text, exc as sqlalchemy_exc
from dotenv import load_dotenv
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# Use /tmp for ephemeral storage in HF Space
DEFAULT_DB_PATH = "/tmp/app.db"
# Construct sync URL directly
DATABASE_URL = os.getenv("DATABASE_URL_SYNC", f"sqlite:///{DEFAULT_DB_PATH}")

logger.info(f"Using DB URL for sync operations: {DATABASE_URL}")

# SQLite specific args for sync engine
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, echo=False) # echo=True for debugging SQL

metadata = MetaData()
users_table = Table( # Renamed slightly to avoid confusion with Pydantic model name
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True, nullable=False),
    Column("hashed_password", String, nullable=False),
)

def ensure_db_and_table_exist():
    """Synchronously ensures DB file directory and users table exist."""
    logger.info("Ensuring DB and table exist...")
    try:
        # Ensure directory exists
        db_file_path = DATABASE_URL.split("sqlite:///")[-1]
        db_dir = os.path.dirname(db_file_path)
        if db_dir:
            if not os.path.exists(db_dir):
                logger.info(f"Creating DB directory: {db_dir}")
                os.makedirs(db_dir, exist_ok=True)
            if not os.access(db_dir, os.W_OK):
                 logger.error(f"CRITICAL: Directory {db_dir} not writable!")
                 return # Cannot proceed

        # Check/Create table using the engine
        with engine.connect() as connection:
            try:
                connection.execute(text("SELECT 1 FROM users LIMIT 1"))
                logger.info("Users table already exists.")
            except sqlalchemy_exc.OperationalError as e:
                if "no such table" in str(e).lower():
                    logger.warning("Users table not found, creating...")
                    metadata.create_all(bind=connection) # Use connection
                    connection.commit()
                    logger.info("Users table created and committed.")
                    # Verify
                    try:
                         connection.execute(text("SELECT 1 FROM users LIMIT 1"))
                         logger.info("Users table verified post-creation.")
                    except Exception as verify_err:
                         logger.error(f"Verification failed after creating table: {verify_err}")
                else:
                    logger.error(f"DB OperationalError checking table (not 'no such table'): {e}")
                    raise # Re-raise unexpected errors
            except Exception as check_err:
                 logger.error(f"Unexpected error checking table: {check_err}")
                 raise # Re-raise unexpected errors

    except Exception as e:
        logger.exception(f"CRITICAL error during DB setup: {e}")
        # Potentially raise to halt app start?