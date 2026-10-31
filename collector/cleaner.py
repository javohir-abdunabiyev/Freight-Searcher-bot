from datetime import datetime, timedelta
import logging
from sqlalchemy import delete
from database import AsyncSessionLocal
from models.message import CargoMessage

async def delete_expired_messages():
    async with AsyncSessionLocal() as session:
        try:
            expiry_threshold = datetime.utcnow() - timedelta(hours=48)
            stmt = delete(CargoMessage).where(CargoMessage.message_date < expiry_threshold)
            result = await session.execute(stmt)
            await session.commit()
            
            deleted_count = result.rowcount
            if deleted_count > 0:
                logging.info(f"🧹 Очистка БД: удалено устаревших сообщений: {deleted_count}")
        except Exception as e:
            await session.rollback()
            logging.error(f"❌ Ошибка при очистке старых сообщений: {e}")