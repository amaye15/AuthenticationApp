from .database import database, users
from .models import UserInDB
from .schemas import UserCreate
from typing import Optional

async def get_user_by_email(email: str) -> Optional[UserInDB]:
    query = users.select().where(users.c.email == email)
    result = await database.fetch_one(query)
    return UserInDB(**result) if result else None

async def create_user(user_in: UserCreate, hashed_password: str) -> int:
    query = users.insert().values(
        email=user_in.email,
        hashed_password=hashed_password
    )
    last_record_id = await database.execute(query)
    return last_record_id

async def get_user_by_id(user_id: int) -> Optional[UserInDB]:
    query = users.select().where(users.c.id == user_id)
    result = await database.fetch_one(query)
    return UserInDB(**result) if result else None