import os
from databases import Database
from dotenv import load_dotenv
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app/app.db")

# Use 'check_same_thread': False only for SQLite, it's generally not needed for server DBs
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

database = Database(DATABASE_URL, connect_args=connect_args)
metadata = MetaData()

# Define Users table using SQLAlchemy Core (needed for initial setup)
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String, unique=True, index=True, nullable=False),
    Column("hashed_password", String, nullable=False),
)

# Create the database and table if they don't exist
# This synchronous part runs once at startup usually
engine = create_engine(DATABASE_URL.replace("+aiosqlite", ""), connect_args=connect_args)

# Check if table exists before creating
# Using a try-except block for robustness across DB engines if needed later
try:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1 FROM users LIMIT 1"))
    print("Users table already exists.")
except Exception:
    print("Users table not found, creating...")
    metadata.create_all(engine)
    print("Users table created.")

# Async connect/disconnect functions for FastAPI lifespan events
async def connect_db():
    await database.connect()
    print("Database connection established.")

async def disconnect_db():
    await database.disconnect()
    print("Database connection closed.")