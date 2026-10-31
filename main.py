import asyncio
import logging
import os
import sys
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.handlers.start import router as start_router
from bot.handlers.search import router as search_router
from bot.tasks import check_expiring_subscriptions, check_expiring_channels
from collector.cleaner import delete_expired_messages
from collector.client import start_telegram_client, stop_telegram_client
from collector.parser import setup_parser
from config import BOT_TOKEN
from database import init_db


# Простейший веб-сервер для Render, чтобы он видел открытый порт и не усыплял бота
async def handle(request):
    return web.Response(text="Bot is alive and working 24/7!")


async def start_web_server():
    app = web.Application()
    app.add_routes([web.get("/", handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🌐 Встроенный веб-сервер успешно запущен на порту {port}")


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="menu", description="📋 Главное меню"),
        BotCommand(command="help", description="❓ Помощь"),
    ]
    await bot.set_my_commands(commands)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout
    )

    # Запускаем веб-сервер в фоновом режиме для Render
    async asyncio.create_task(start_web_server())

    await init_db()
    client = await start_telegram_client()

    channels_list = [
        "@cargo_logistics_2026",
    ]
    setup_parser(client=client, channels_list=channels_list)

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())
    
    dp.include_router(start_router)
    dp.include_router(search_router)

    await set_commands(bot)

    await delete_expired_messages()
    
    scheduler = AsyncIOScheduler()
    scheduler.add_job(delete_expired_messages, "interval", minutes=15)
    scheduler.add_job(check_expiring_subscriptions, "interval", hours=1, args=[bot])
    scheduler.add_job(check_expiring_channels, "interval", hours=1, args=[bot])
    scheduler.start()

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 Бот, база данных и сборщик успешно запущены!")
    
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await stop_telegram_client()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен.")