import asyncio
from database.session import engine
from sqlalchemy import text

async def run_migration():
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_expires_at TIMESTAMP WITHOUT TIME ZONE;"))
    print("✅ Колонка subscription_expires_at успешно добавлена в базу данных!")

if __name__ == "__main__":
    asyncio.run(run_migration())