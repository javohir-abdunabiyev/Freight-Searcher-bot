import asyncio
from database.session import AsyncSessionLocal
from models.message import CargoMessage
from sqlalchemy import delete

async def clear_database():
    async with AsyncSessionLocal() as session:
        await session.execute(delete(CargoMessage))
        await session.commit()
        print("🗑️ База данных полностью очищена! Все записи удалены.")

if __name__ == "__main__":
    asyncio.run(clear_database())