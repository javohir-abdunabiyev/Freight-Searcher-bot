from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User

async def get_or_create_user(session: AsyncSession, telegram_id: int, full_name: str, username: str | None = None) -> User:
    """Находит пользователя в базе или создает нового, если его нет."""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    
    if not user:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            username=username,
            phone_number=None,
            is_tg_connected=False
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
    return user

async def update_user_phone(session: AsyncSession, telegram_id: int, phone_number: str):
    """Сохраняет номер телефона пользователя и проверяет регистрацию."""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    
    if user:
        user.phone_number = phone_number
        await session.commit()
        await session.refresh(user)
    return user