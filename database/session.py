from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL

# Добавляем connect_args={"ssl": True} для безопасного подключения к Neon через asyncpg
engine = create_async_engine(DATABASE_URL, connect_args={"ssl": True}, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass