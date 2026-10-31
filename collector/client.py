import os
import logging
from telethon import TelegramClient
from config import API_ID, API_HASH

SESSION_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cargo_collector_session")

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

async def start_telegram_client():
    if not API_ID or not API_HASH:
        logging.warning("⚠️ API_ID или API_HASH не заданы в .env!")
        return None

    try:
        await client.start()
        logging.info("📱 Telethon клиент успешно запущен и авторизован!")
        return client  # <--- ВОТ ЭТОГО НЕ ХВАТАЛО! Теперь клиент передается дальше.
    except Exception as e:
        logging.error(f"❌ Ошибка запуска Telethon клиента: {e}")
        return None

async def stop_telegram_client():
    if client.is_connected():
        await client.disconnect()
        logging.info("📱 Telethon клиент остановлен.")