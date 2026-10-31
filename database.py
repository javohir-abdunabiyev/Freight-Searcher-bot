from datetime import datetime, timedelta
from typing import List, Tuple
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import select, and_, func
from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    pass

async def init_db():
    async with engine.begin() as conn:
        from models.message import CargoMessage
        from models.user import User
        await conn.run_sync(Base.metadata.create_all)


async def search_cargo_messages_paginated(query_str: str, page: int = 1, per_page: int = 5) -> Tuple[List, int]:
    """
    Поиск грузов за последние 48 часов с пагинацией.
    Требует наличия всех указанных ключевых слов (Откуда и Куда).
    Возвращает список сообщений и общее количество найденных.
    """
    from models.message import CargoMessage
    
    query_clean = query_str.strip().lower()
    if not query_clean:
        return [], 0

    async with AsyncSessionLocal() as session:
        time_limit = datetime.utcnow() - timedelta(hours=48)
        
        # Разбиваем запрос на слова (Откуда и Куда)
        words = [w for w in query_clean.split() if len(w) > 1]
        if not words:
            words = [query_clean]
        
        # Все слова должны присутствовать в тексте (Откуда И Куда)
        word_conditions = [CargoMessage.text.ilike(f"%{word}%") for word in words]
        search_filter = and_(
            CargoMessage.message_date >= time_limit,
            *word_conditions
        )
        
        # Считаем общее количество найденных
        count_stmt = select(func.count(CargoMessage.id)).where(search_filter)
        total_res = await session.execute(count_stmt)
        total_count = total_res.scalar() or 0
        
        if total_count == 0:
            return [], 0

        # Получаем срез для текущей страницы
        offset = (page - 1) * per_page
        stmt = (
            select(CargoMessage)
            .where(search_filter)
            .order_by(CargoMessage.message_date.desc())
            .offset(offset)
            .limit(per_page)
        )
        
        result = await session.execute(stmt)
        messages = list(result.scalars().all())
        
        return messages, total_count