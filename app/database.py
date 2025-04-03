# app/database.py
import os
from databases import Database
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text
import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode # For URL manipulation

load_dotenv()
logger = logging.getLogger(__name__)

# --- Database URL Configuration ---
DEFAULT_DB_PATH = "/data/app.db"
# Start with the base URL from env or default
raw_db_url = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}")

# Ensure 'check_same_thread=False' is in the URL for SQLite async connection
final_database_url = raw_db_url
if raw_db_url.startswith("sqlite+aiosqlite"):
    # Parse the URL
    parsed_url = urlparse(raw_db_url)
    # Parse existing query parameters into a dictionary
    query_params = parse_qs(parsed_url.query)
    # Add check_same_thread=False ONLY if it's not already there
    # (in case it's set via DATABASE_URL env var)
    if 'check_same_thread' not in query_params:
        query_params['check_same_thread'] = ['False'] # Needs to be a list for urlencode
        # Rebuild the query string
        new_query = urlencode(query_params, doseq=True)
        # Rebuild the URL using _replace method of the named tuple
        final_database_url = urlunparse(parsed_url._replace(query=new_query))
    logger.info(f"Using final async DB URL: {final_database_url}")
else:
    logger.info(f"Using non-SQLite async DB URL: {final_database_url}")


# --- Async Database Instance (using 'databases' library) ---
# Pass the *modified* URL. DO NOT pass connect_args separately here.
database = Database(final_database_url)

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True, nullable=False),
    Column("hashed_password", String, nullable=False),
)

# --- Synchronous Engine for Initial Table Creation (using SQLAlchemy Core) ---
# Derive the sync URL (remove +aiosqlite). The query param should remain.
sync_db_url = final_database_url.replace("+aiosqlite", "")

# SQLAlchemy's create_engine *can* take connect_args, but for check_same_thread,
# it also understands it from the URL query string. Let's rely on the URL for simplicity.
# sync_connect_args = {"check_same_thread": False} if sync_db_url.startswith("sqlite") else {} # Keep for reference if other args are needed

logger.info(f"Using synchronous DB URL for initial check/create: {sync_db_url}")
# Create the engine using the URL which now includes ?check_same_thread=False
engine = create_engine(sync_db_url) # No connect_args needed here if only using check_same_thread

# --- Directory and Table Creation Logic ---
# Extract path correctly, ignoring query parameters for os.path operations
db_file_path = ""
if sync_db_url.startswith("sqlite"):
    # Get the path part after 'sqlite:///' and before '?'
    path_part = sync_db_url.split("sqlite:///")[-1].split("?")[0]
    # Ensure it's an absolute path if it starts with /
    if path_part.startswith('/'):
        db_file_path = path_part
    else:
        # Handle relative paths if they were somehow configured (though /data should be absolute)
        # This case is less likely with our default /data/app.db
        db_file_path = os.path.abspath(path_part)


if db_file_path:
    db_dir = os.path.dirname(db_file_path)
    logger.info(f"Ensuring database directory exists: {db_dir}")
    try:
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")
        # Add a check for writability after ensuring directory exists
        if db_dir and not os.access(db_dir, os.W_OK):
             logger.error(f"Database directory {db_dir} is not writable!")
        # Also check if the file itself can be created/opened (might fail here if dir is writable but file isn't)
        # This check is implicitly done by engine.connect() below

    except OSError as e:
        logger.error(f"Error creating or accessing database directory {db_dir}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error checking/creating DB directory {db_dir}: {e}")


# Now try connecting and creating the table with the sync engine
try:
    logger.info("Attempting to connect with sync engine to check/create table...")
    with engine.connect() as connection:
        try:
            # Use text() for literal SQL
            connection.execute(text("SELECT 1 FROM users LIMIT 1"))
            logger.info("Users table already exists.")
        except Exception as table_check_exc: # Catch specific DB errors if possible
            logger.warning(f"Users table check failed ({type(table_check_exc).__name__}), attempting creation...")
            # Pass the engine explicitly to create_all
            metadata.create_all(bind=engine)
            logger.info("Users table created (or creation attempted).")

except Exception as e:
    # This OperationalError "unable to open database file" might still indicate
    # a fundamental permission issue with /data/app.db in the HF environment.
    logger.exception(f"CRITICAL: Failed to connect/create database tables using sync engine: {e}")


# --- Async connect/disconnect functions ---
async def connect_db():
    try:
        # The 'database' instance now uses the URL with the query param
        await database.connect()
        logger.info(f"Database connection established (async): {final_database_url}")
    except Exception as e:
        logger.exception(f"Failed to establish async database connection: {e}")
        # If the sync engine failed earlier due to permissions, this might fail too.
        raise # Reraise critical error during startup lifespan

async def disconnect_db():
    try:
        await database.disconnect()
        logger.info("Database connection closed (async).")
    except Exception as e:
        logger.exception(f"Error closing async database connection: {e}")