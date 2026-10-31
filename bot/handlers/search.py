import math
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from database import search_cargo_route_paginated
from database.session import AsyncSessionLocal
from models.user import User
from bot.keyboards import get_main_menu_keyboard

router = Router()

PER_PAGE = 10

class RouteSearchState(StatesGroup):
    waiting_for_origin = State()
    waiting_for_destination = State()

def get_message_link(chat_id: int, message_id: int) -> str:
    chat_str = str(chat_id)
    if chat_str.startswith("-100"):
        clean_id = chat_str[4:]
    elif chat_str.startswith("-"):
        clean_id = chat_str[1:]
    else:
        clean_id = chat_str
    return f"https://t.me/c/{clean_id}/{message_id}"

def build_route_keyboard(messages, page: int, total_count: int) -> InlineKeyboardMarkup:
    total_pages = math.ceil(total_count / PER_PAGE)
    keyboard_rows = []
    
    row_1 = []
    row_2 = []
    
    start_number = (page - 1) * PER_PAGE + 1
    
    for idx, msg in enumerate(messages):
        item_number = start_number + idx
        chat_id = msg.chat_id if hasattr(msg, 'chat_id') else msg['chat_id']
        message_id = msg.message_id if hasattr(msg, 'message_id') else msg['message_id']
        
        link = get_message_link(chat_id, message_id)
        btn = InlineKeyboardButton(text=f"{item_number}", url=link)
        
        if idx < 5:
            row_1.append(btn)
        else:
            row_2.append(btn)
            
    if row_1:
        keyboard_rows.append(row_1)
    if row_2:
        keyboard_rows.append(row_2)

    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(text="◀️", callback_data=f"route_page_{page - 1}"))
    
    start_p = max(1, page - 2)
    end_p = min(total_pages, start_p + 4)
    if end_p - start_p < 4:
        start_p = max(1, end_p - 4)
        
    for p in range(start_p, end_p + 1):
        label = f"• {p} •" if p == page else str(p)
        pagination_row.append(InlineKeyboardButton(text=label, callback_data=f"route_page_{p}"))
        
    if page < total_pages:
        pagination_row.append(InlineKeyboardButton(text="▶️", callback_data=f"route_page_{page + 1}"))
        
    if pagination_row:
        keyboard_rows.append(pagination_row)

    keyboard_rows.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

@router.callback_query(F.data == "btn_search")
async def start_search_callback(callback: types.CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        
        if not user or not user.is_authenticated:
            await callback.answer("⚠️ Сначала привяжите аккаунт через раздел «Telegram аккаунт»!", show_alert=True)
            return

        now = datetime.utcnow()
        is_sub_active = user.subscription_expires_at and user.subscription_expires_at > now
        
        if not is_sub_active:
            await callback.message.edit_text(
                "💳 <b>Доступ к поиску грузов ограничен</b>\n\n"
                "Для работы с сервисом необходима активная подписка. Выберите удобный тариф:\n\n"
                "⏳ <b>40 дней</b> — <code>90 000 сум</code>\n"
                "⏳ <b>80 дней</b> — <code>160 000 сум</code>\n\n"
                "📌 <i>Оформить или продлить подписку можно напрямую у нашего администратора.</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Купить подписку", url="https://t.me/FreightSearcher_support")],
                    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
                ])
            )
            await callback.answer()
            return

    await state.set_state(RouteSearchState.waiting_for_origin)
    await callback.message.edit_text(
        "🔍 <b>Поиск грузов</b>\n\nВведите пункт отправления (<b>Откуда</b>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
        ])
    )
    await callback.answer()

@router.message(RouteSearchState.waiting_for_origin)
async def process_origin_handler(message: types.Message, state: FSMContext):
    origin_text = message.text.strip()
    await state.update_data(origin=origin_text, search_id=datetime.utcnow().timestamp())
    await state.set_state(RouteSearchState.waiting_for_destination)
    
    await message.answer(
        "📍 Введите пункт назначения (<b>Куда</b>):",
        parse_mode="HTML"
    )

@router.message(RouteSearchState.waiting_for_destination)
async def process_destination_handler(message: types.Message, state: FSMContext):
    destination_text = message.text.strip()
    data = await state.get_data()
    origin_text = data.get("origin")
    
    # Генерируем уникальный ID текущей сессии поиска (это сделает старые инлайн-кнопки неактуальными)
    current_search_id = datetime.utcnow().timestamp()
    
    loading_msg = await message.answer("🔍 <b>Ищем грузы по маршруту...</b> Пожалуйста, подождите.", parse_mode="HTML")
    
    messages, total_count = await search_cargo_route_paginated(
        origin=origin_text, 
        destination=destination_text, 
        page=1, 
        per_page=1000 
    )
    
    if not messages:
        await loading_msg.edit_text(
            f"❌ <b>По маршруту «{origin_text} ➔ {destination_text}» грузы не найдены.</b>",
            reply_markup=get_main_menu_keyboard(message.from_user.id),
            parse_mode="HTML"
        )
        await state.clear()
        return

    cached_messages = [{"chat_id": m.chat_id, "message_id": m.message_id} for m in messages]
    
    await state.update_data(
        destination=destination_text, 
        current_page=1,
        cached_messages=cached_messages,
        total_count=total_count,
        search_id=current_search_id
    )
    
    page_messages = cached_messages[0:PER_PAGE]
    markup = build_route_keyboard(page_messages, page=1, total_count=total_count)
    
    response_text = (
        f"🔎 Маршрут: <b>{origin_text} ➔ {destination_text}</b>\n"
        f"📦 Найдено грузов: <b>{total_count}</b>\n\n"
        f"<i>Нажмите на номер груза, чтобы открыть оригинал сообщения:</i>\n"
        )
    
    await loading_msg.edit_text(response_text, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data.startswith("route_page_"))
async def route_pagination_handler(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    data = await state.get_data()
    
    origin_text = data.get("origin")
    destination_text = data.get("destination")
    cached_messages = data.get("cached_messages", [])
    total_count = data.get("total_count", 0)
    saved_search_id = data.get("search_id")
    
    if not origin_text or not destination_text or not cached_messages:
        await callback.answer("⚠️ Сессия поиска истекла. Запустите поиск заново через меню.", show_alert=True)
        return

    await state.update_data(current_page=page)
    
    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    page_messages = cached_messages[start_idx:end_idx]
    
    markup = build_route_keyboard(page_messages, page=page, total_count=total_count)
    
    response_text = (
        f"🔎 Маршрут: <b>{origin_text} ➔ {destination_text}</b>\n"
        f"📦 Найдено грузов: <b>{total_count}</b>\n\n"
        f"<i>Нажмите на номер груза, чтобы открыть оригинал сообщения:</i>\n"
        f"<code>[Сессия поиска # {int(saved_search_id) if saved_search_id else 0}]</code>"
    )
    
    try:
        await callback.message.edit_text(response_text, reply_markup=markup, parse_mode="HTML")
    except Exception:
        pass
    await callback.answer()

@router.message(F.text.startswith("/sub "))
async def give_subscription_handler(message: types.Message):
    async with AsyncSessionLocal() as session:
        admin_user = await session.get(User, message.from_user.id)
        if not admin_user or not admin_user.phone or "773442033" not in admin_user.phone:
            return

    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer(
            "⚠️ <b>Использование:</b> <code>/sub номер_телефона дни</code>\n"
            "<b>Пример:</b> <code>/sub +998901234567 40</code>",
            parse_mode="HTML"
        )
        return

    phone_input = parts[1].strip()
    try:
        days_to_add = int(parts[2])
    except ValueError:
        await message.answer("⚠️ Количество дней должно быть целым числом!")
        return

    async with AsyncSessionLocal() as session:
        stmt = select(User).where(User.phone.ilike(f"%{phone_input.replace('+', '')}%"))
        user = (await session.execute(stmt)).scalars().first()

        if not user:
            await message.answer(f"❌ Пользователь с номером телефона <b>{phone_input}</b> не найден в базе данных.", parse_mode="HTML")
            return

        now = datetime.utcnow()
        base_date = user.subscription_expires_at if (user.subscription_expires_at and user.subscription_expires_at > now) else now
        new_expire_date = base_date + timedelta(days=days_to_add)

        user.subscription_expires_at = new_expire_date
        await session.commit()

        await message.answer(
            f"✅ <b>Подписка успешно выдана!</b>\n\n"
            f"👤 <b>Пользователь:</b> {user.full_name or user.username or user.id}\n"
            f"📱 <b>Телефон:</b> {user.phone}\n"
            f"⏳ <b>Добавлено дней:</b> {days_to_add}\n"
            f"📅 <b>Действует до:</b> <code>{new_expire_date.strftime('%Y-%m-%d %H:%M')} (UTC)</code>",
            parse_mode="HTML"
        )