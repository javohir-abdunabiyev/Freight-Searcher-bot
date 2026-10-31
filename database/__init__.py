from database.session import engine, AsyncSessionLocal, Base
from database.search import search_cargo_route_paginated
from models.message import CargoMessage
from models.user import User

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)