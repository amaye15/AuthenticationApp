import os
from databases import Database
from dotenv import load_dotenv
from sqlalchemy import MetaData, Table, Column, Integer, String
import logging
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

load_dotenv()
logger = logging.getLogger(__name__)


DEFAULT_DB_PATH = "/tmp/app.db"
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


database = Database(final_database_url)

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True, nullable=False),
    Column("hashed_password", String, nullable=False),
)

async def connect_db():
    """Connects to the database defined by 'final_database_url'."""
    try:
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

        if not database.is_connected:
            await database.connect()
            logger.info(f"Database connection established: {final_database_url}")
        else:
            logger.info("Database connection already established.")
    except Exception as e:
        logger.exception(f"FATAL: Failed to establish async database connection: {e}")
        raise

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