import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
dev_id = os.getenv("DEVELOPER_TELEGRAM_ID")
DEVELOPER_TELEGRAM_ID = int(dev_id) if dev_id and dev_id.isdigit() else 0

DATABASE_URL = os.getenv("DATABASE_URL")

# Параметры для Telethon
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
if API_ID:
    API_ID = int(API_ID)

if not BOT_TOKEN:
    raise ValueError("Не задан BOT_TOKEN в файле .env!")

if not DATABASE_URL:
    raise ValueError("Не задан DATABASE_URL в файле .env!")

    # Ссылка на базу групп из .env
GROUP_BASE = os.getenv("GROUP_BASE", "https://t.me/addlist/2WPMTFBfZWM0ZTFi")