import asyncio
import re
import unicodedata
from datetime import datetime, timedelta
from sqlalchemy import select, func
from database.session import AsyncSessionLocal
from models.message import CargoMessage
from telethon import events

# Глобальный словарь статистики для админ-панели
collector_stats = {
    "total_groups": 0,
    "current_group_index": 0,
    "current_group": "Инициализация...",
    "current_group_saved": 0,
    "duplicates_filtered": 0,
    "new_caught": 0,       # За исторический сбор
    "live_caught": 0,      # Поймано строго в режиме Live
    "deleted_from_db": 0,  # Удалено из базы (протухшие/истекшие)
    "status": "Запуск..."
}

def clean_text_for_dedup(text: str) -> str:
    """Мягкая нормализация: убирает лишние пробелы и приводит к нижнему регистру"""
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text)
    return re.sub(r'\s+', ' ', text.strip().lower())

async def get_folder_channels(client):
    from telethon.tl.functions.messages import GetDialogFiltersRequest
    channels = []
    target_folder = None
    
    try:
        result = await client(GetDialogFiltersRequest())
        filters = list(result.filters)
        
        for f in filters:
            raw_title = getattr(f, 'title', '')
            title = str(raw_title.text if hasattr(raw_title, 'text') else raw_title).lower()
            if any(keyword in title for keyword in ['груз', 'cargo', 'доставка', 'транспорт', 'логистик']):
                target_folder = f
                break
                
        if not target_folder and len(filters) > 0:
            target_folder = filters[0]

        if target_folder:
            for peer in target_folder.include_peers:
                try:
                    entity = await client.get_entity(peer)
                    channels.append(entity)
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Ошибка при запросе папок Telethon: {e}")
        
    return channels

async def run_collector_loop(client, channels_list=None):
    global collector_stats
    collector_stats["status"] = "Подключение к Telegram..."
    
    while client is None:
        await asyncio.sleep(2)
        
    while True:
        try:
            collector_stats["status"] = "Поиск рабочей папки..."
            target_channels = await get_folder_channels(client)
            
            if not target_channels:
                collector_stats["status"] = "Папка пуста или не найдена!"
                await asyncio.sleep(60)
                continue

            target_chat_ids = [chat.id for chat in target_channels]
            total_len = len(target_channels)
            collector_stats["total_groups"] = total_len
            collector_stats["status"] = "Исторический сбор за 48 часов (до 5000 сооб.)"
            collector_stats["new_caught"] = 0
            collector_stats["live_caught"] = 0
            
            time_limit = datetime.utcnow() - timedelta(hours=48)
            cycle_new_count = 0
            
            # Оперативный кэш точных текстов для надежного отсечения дублей в текущем цикле
            seen_exact_texts = set()
            
            # 1. Исторический сбор по всем группам (до 5000 сообщений или до 48 часов)
            for idx, entity in enumerate(target_channels, start=1):
                collector_stats["current_group_index"] = idx
                
                raw_title = getattr(entity, 'title', str(getattr(entity, 'username', entity.id)))
                group_name = str(raw_title.text if hasattr(raw_title, 'text') else raw_title)
                
                collector_stats["current_group"] = f"[{idx}/{total_len}] {group_name}"
                collector_stats["current_group_saved"] = 0
                
                try:
                    # Ограничиваем исторический проход до 5000 сообщений на чат
                    async for message in client.iter_messages(entity, limit=5000):
                        if not message.date or not message.text:
                            continue
                        
                        msg_date_naive = message.date.replace(tzinfo=None)
                        if msg_date_naive < time_limit:
                            break  # Дошли до сообщений старше 48 часов — переходим к следующему чату
                            
                        text_raw = message.text.strip()
                        text_normalized = clean_text_for_dedup(text_raw)
                        
                        if len(text_normalized) < 5:
                            continue
                            
                        # Проверка 1: Если этот же текст уже встречался в этом цикле сбора
                        if text_normalized in seen_exact_texts:
                            collector_stats["duplicates_filtered"] += 1
                            continue
                            
                        async with AsyncSessionLocal() as session:
                            # Проверка 2: По ID чата и сообщения в базе данных
                            stmt_id = select(CargoMessage).where(
                                (CargoMessage.chat_id == message.chat_id) & (CargoMessage.message_id == message.id)
                            )
                            existing = (await session.execute(stmt_id)).scalars().first()
                            
                            if existing:
                                collector_stats["duplicates_filtered"] += 1
                                continue
                                
                            # Фиксируем в оперативном кэше цикла
                            seen_exact_texts.add(text_normalized)
                            
                            new_cargo = CargoMessage(
                                chat_id=message.chat_id,
                                message_id=message.id,
                                text=text_raw,
                                message_date=msg_date_naive
                            )
                            session.add(new_cargo)
                            await session.commit()
                            
                            collector_stats["current_group_saved"] += 1
                            cycle_new_count += 1
                            collector_stats["new_caught"] = cycle_new_count
                            
                except Exception as ex:
                    print(f"⚠️ Ошибка чтения чата {group_name}: {ex}")
                    continue
                    
            # 2. Переходим в непрерывный режим Live (реальное время)
            collector_stats["status"] = "Мониторинг в реальном времени (Live)"
            collector_stats["current_group"] = "Папка «Грузы» (слушаем поток)"
            
            @client.on(events.NewMessage(chats=target_chat_ids))
            async def live_message_handler(event):
                try:
                    message = event.message
                    if not message.date or not message.text:
                        return
                        
                    msg_date_naive = message.date.replace(tzinfo=None)
                    text_raw = message.text.strip()
                    text_normalized = clean_text_for_dedup(text_raw)
                    
                    if len(text_normalized) < 5:
                        return
                        
                    async with AsyncSessionLocal() as session:
                        stmt_id = select(CargoMessage).where(
                            (CargoMessage.chat_id == message.chat_id) & (CargoMessage.message_id == message.id)
                        )
                        existing = (await session.execute(stmt_id)).scalars().first()
                        
                        if existing:
                            collector_stats["duplicates_filtered"] += 1
                            return
                            
                        new_cargo = CargoMessage(
                            chat_id=message.chat_id,
                            message_id=message.id,
                            text=text_raw,
                            message_date=msg_date_naive
                        )
                        session.add(new_cargo)
                        await session.commit()
                        
                        collector_stats["live_caught"] += 1
                except Exception as e:
                    print(f"⚠️ Ошибка в Live обработчике: {e}")

            while True:
                await asyncio.sleep(60)
                
        except Exception as e:
            collector_stats["status"] = f"Ошибка цикла: {e}"
            print(f"⚠️ Ошибка в фоновом сборщике: {e}")
            await asyncio.sleep(10)

def setup_parser(client, channels_list=None):
    return asyncio.create_task(run_collector_loop(client, channels_list))

async def parse_history_for_last_48h(client=None, channels_list=None):
    if client:
        setup_parser(client, channels_list)