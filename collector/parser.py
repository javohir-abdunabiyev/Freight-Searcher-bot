import asyncio
import re
import unicodedata
from datetime import datetime, timedelta
from sqlalchemy import select
from database.session import AsyncSessionLocal
from models.message import CargoMessage
from telethon import events

collector_stats = {
    "total_groups": 0,
    "current_group": "Инициализация...",
    "current_group_index": 0,
    "current_group_saved": 0,
    "new_caught": 0,
    "live_caught": 0,
    "duplicates_filtered": 0,
    "deleted_from_db": 0,
    "status": "Запуск..."
}

def clean_text_for_dedup(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', text)
    return re.sub(r'\s+', ' ', text.strip().lower())

async def get_folder_channels(client):
    from telethon.tl.functions.messages import GetDialogFiltersRequest
    channels = []
    try:
        result = await client(GetDialogFiltersRequest())
        for f in result.filters:
            raw_title = getattr(f, 'title', '')
            title = str(raw_title.text if hasattr(raw_title, 'text') else raw_title).lower()
            if any(kw in title for kw in ['груз', 'cargo', 'доставка', 'транспорт', 'логистик']):
                for peer in f.include_peers:
                    try:
                        entity = await client.get_entity(peer)
                        channels.append(entity)
                    except Exception:
                        pass
                break
        if not channels and result.filters:
            for peer in result.filters[0].include_peers:
                try:
                    entity = await client.get_entity(peer)
                    channels.append(entity)
                except Exception:
                    pass
    except Exception as e:
        print(f"⚠️ Ошибка получения папки: {e}")
    return channels

async def run_collector_loop(client):
    global collector_stats
    collector_stats["status"] = "Подключение к Telegram..."
    
    while client is None:
        await asyncio.sleep(2)
        
    collector_stats["status"] = "Поиск рабочей папки..."
    channels = await get_folder_channels(client)
    
    if not channels:
        collector_stats["status"] = "Папка не найдена!"
        return

    target_chat_ids = [chat.id for chat in channels]
    collector_stats["total_groups"] = len(channels)
    
    # --- ЭТАП 1: Однократный исторический сбор за 48 часов (лимит 3000 сообщений) ---
    collector_stats["status"] = "Исторический сбор за 48 часов..."
    time_limit = datetime.utcnow() - timedelta(hours=48)
    history_count = 0
    
    seen_exact_texts = set()
    
    for idx, entity in enumerate(channels, start=1):
        collector_stats["current_group_index"] = idx
        raw_title = getattr(entity, 'title', str(getattr(entity, 'username', entity.id)))
        group_name = str(raw_title.text if hasattr(raw_title, 'text') else raw_title)
        collector_stats["current_group"] = f"[{idx}/{len(channels)}] {group_name}"
        collector_stats["current_group_saved"] = 0  # Сбрасываем счетчик для текущей группы
        
        try:
            async for message in client.iter_messages(entity, limit=3000):
                if not message.date or not message.text:
                    continue
                
                msg_date_naive = message.date.replace(tzinfo=None)
                if msg_date_naive < time_limit:
                    break  # Прошли порог 48 часов, идем к следующему чату
                    
                text_raw = message.text.strip()
                text_normalized = clean_text_for_dedup(text_raw)
                
                if len(text_normalized) < 5:
                    continue
                    
                if text_normalized in seen_exact_texts:
                    collector_stats["duplicates_filtered"] += 1
                    continue
                    
                async with AsyncSessionLocal() as session:
                    stmt_id = select(CargoMessage).where(
                        (CargoMessage.chat_id == message.chat_id) & (CargoMessage.message_id == message.id)
                    )
                    existing = (await session.execute(stmt_id)).scalars().first()
                    
                    if existing:
                        collector_stats["duplicates_filtered"] += 1
                        continue
                        
                    seen_exact_texts.add(text_normalized)
                    
                    new_cargo = CargoMessage(
                        chat_id=message.chat_id,
                        message_id=message.id,
                        text=text_raw,
                        message_date=msg_date_naive
                    )
                    session.add(new_cargo)
                    await session.commit()
                    
                    history_count += 1
                    collector_stats["new_caught"] = history_count
                    collector_stats["current_group_saved"] += 1
        except Exception as ex:
            print(f"⚠️ Ошибка исторического сбора в чате {group_name}: {ex}")

    print(f"✅ Исторический сбор завершен. Загружено сообщений: {history_count}")

    # --- ЭТАП 2: Непрерывный Live-режим (только новые входящие) ---
    collector_stats["status"] = "🟢 Мониторинг в реальном времени (Live)"
    collector_stats["current_group"] = "Слушаем поток папки «Грузы»"
    collector_stats["current_group_saved"] = 0

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
                print(f"📥 [Live] Сохранено новое сообщение из чата {message.chat_id}")
        except Exception as e:
            print(f"⚠️ Ошибка в Live обработчике: {e}")

def setup_parser(client, channels_list=None):
    return asyncio.create_task(run_collector_loop(client))