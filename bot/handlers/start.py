import os
from datetime import datetime, timedelta
from aiogram import Router, F, types
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import func, select
from database.session import AsyncSessionLocal
from models.user import User
from models.message import CargoMessage
from models.channel import RecommendedChannel
from config import DEVELOPER_TELEGRAM_ID, GROUP_BASE
from bot.keyboards import get_main_menu_keyboard, get_tg_account_keyboard, get_request_contact_keyboard

try:
    from collector.parser import collector_stats
except ImportError:
    collector_stats = {
        "total_groups": 15,
        "current_group": "Ожидание запуска...",
        "current_group_saved": 0,
        "duplicates_filtered": 0,
        "new_caught": 0,
        "status": "Инициализация"
    }

router = Router()

class AuthStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()

@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user_id = message.from_user.id
        user = await session.get(User, user_id)
        
        if not user or not user.is_authenticated:
            await message.answer(
                "👋 <b>Добро пожаловать в сервис поиска грузов!</b>\n\n"
                "Для доступа к функциям необходимо привязать ваш Telegram аккаунт.\n"
                "Пожалуйста, поделитесь вашим номером телефона с помощью кнопки ниже:",
                reply_markup=get_request_contact_keyboard(),
                parse_mode="HTML"
            )
            await state.set_state(AuthStates.waiting_for_phone)
            return

    await message.answer(
        "👋 С возвращением! Главное меню:",
        reply_markup=get_main_menu_keyboard(message.from_user.id)
    )

@router.message(AuthStates.waiting_for_phone, F.contact)
async def process_contact_auth(message: Message, state: FSMContext):
    contact = message.contact
    phone = contact.phone_number
    
    await state.update_data(phone=phone)
    
    is_first_registration = False
    
    async with AsyncSessionLocal() as session:
        user_id = message.from_user.id
        user = await session.get(User, user_id)
        
        now = datetime.utcnow()
        if not user:
            is_first_registration = True
            free_trial_expire = now + timedelta(days=2)
            user = User(
                id=user_id,
                username=message.from_user.username,
                full_name=message.from_user.full_name,
                phone=phone,
                is_authenticated=True,
                subscription_expires_at=free_trial_expire
            )
            session.add(user)
        else:
            user.phone = phone
            user.is_authenticated = True
            user.username = message.from_user.username
            user.full_name = message.from_user.full_name
            
        await session.commit()

    await state.clear()
    
    if is_first_registration:
        success_text = (
            "✅ <b>Аккаунт успешно подключен!</b>\n\n"
            "🎁 В качестве подарка вам активирован <b>бесплатный пробный период на 2 дня</b>!\n"
            "Теперь вам доступны все функции поиска грузов."
        )
    else:
        success_text = (
            "✅ <b>Аккаунт успешно подключен!</b>\n\n"
            "Вы вошли в существующий профиль. Статус подписки можно проверить в разделе «Мой профиль»."
        )

    await message.answer(
        success_text,
        reply_markup=get_main_menu_keyboard(message.from_user.id),
        parse_mode="HTML"
    )

@router.message(F.text == "/menu")
async def cmd_menu(message: Message):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        if not user or not user.is_authenticated:
            await message.answer("⚠️ Сначала необходимо авторизоваться через /start", reply_markup=get_request_contact_keyboard())
            return
    await message.answer("📋 Главное меню:", reply_markup=get_main_menu_keyboard(message.from_user.id))

# ---------------------------------------------------------
# КОМАНДА /поддержка (вместо /help)
# ---------------------------------------------------------
@router.message(F.text == "/поддержка")
async def cmd_support(message: Message):
    await message.answer(
        "💬 <b>Служба поддержки и администратор:</b>\n\n"
        "Если у вас возникли вопросы по работе бота, продлению подписки или размещению рекламы, вы всегда можете написать нашему администратору:\n\n"
        "👉 <b>@FreightSearcher_support</b>",
        parse_mode="HTML"
    )

# ---------------------------------------------------------
# КНОПКА И ИНСТРУКЦИЯ
# ---------------------------------------------------------
@router.callback_query(F.data == "btn_instruction")
async def cb_instruction(callback: CallbackQuery):
    instruction_text = (
        "📖 <b>Инструкция по использованию бота:</b>\n\n"
        "<b>1. Авторизация:</b>\n"
        "При первом запуске бот попросит поделиться номером телефона. После этого вам автоматически активируется <b>бесплатный пробный период на 2 дня</b>.\n\n"
        "<b>2. Поиск грузов:</b>\n"
        "Нажмите кнопку «🔍 Найти груз», чтобы быстро находить актуальные заявки на перевозки по вашим критериям.\n\n"
        "<b>2.1. ОБЯЗАТЕЛЬНО ДОБАВЬТЕ БАЗУ ГРУПП, ЭТО ОБЯЗАТЕЛЬНО ДЛЯ РАБОТЫ С ПОИСКОМ. КНОПКА В ГЛАВНОМ МЕНЮ:</b> «📁 БАЗА ГРУПП»\n"
        "<b>2.2. Поиск по маршруту:</b>\n"
        "Обязательно пишите названия маршрутов правильно без ошибок, чтобы бот мог корректно их распознать. Например: «Ташкент» вместо «Ташкента», «Душанбе» вместо «Душанбы», «Москва» вместо «Maskva» и т.д.\n\n"
        "Вы можете указать пункт отправления и назначения, чтобы найти грузы, которые соответствуют вашему маршруту.\n\n"
        "<b>3. Подписка:</b>\n"
        "После окончания пробного периода для работы с поиском необходима подписка. Вы можете продлить её или купить у администратора (доступны тарифы на 40 и 80 дней).\n\n"
        "<b>4. База групп:</b>\n"
        "В главном меню нажмите кнопку «📁 База групп», чтобы получить готовую папку с тематическими группами для логистики. Это обязательно чтобы работать с поиском.\n\n"
        "<b>5. Рекомендация для логистов и диспетчеров:</b>\n"
        "Рекомендуется рассылать свои сообщения с грузами с правильным написанием маршрутов, например:\n\n"
        "Ташкент - Москва (правильно)\n"
        "Ташкент-Алмата (правильно)\n"
        "TOSHKANT MASKVA (неправильно)\n"
        "TOSHKENT - ALMATY (неправильно)\n\n"

        "<b>6. Рекомендованные каналы:</b>\n"
        "В соответствующем разделе собраны проверенные каналы партнеров с полезной информацией. Если хотите добавить свой канал (добавление канала платное), напишите в тех. поддержку.\n\n"
        "❓ Возникли вопросы? Напишите в тех. поддержку через кнопку в главном меню!"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(instruction_text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

# ---------------------------------------------------------
# КНОПКА «БАЗА ГРУПП» (выдает ссылку из .env)
# ---------------------------------------------------------
@router.callback_query(F.data == "btn_group_base")
async def cb_group_base(callback: CallbackQuery):
    base_text = (
        "📁 <b>База групп и каналов для логистики:</b>\n\n"
        "Нажмите на кнопку ниже, чтобы добавить готовую папку со всеми нашими рабочими группами и чатами в ваш Telegram:"
    )
    base_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Добавить базу групп", url=GROUP_BASE)],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(base_text, reply_markup=base_kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "tg_account_settings")
async def cb_tg_account(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        status = "🟢 Подключен" if user and user.is_authenticated else "🔴 Не подключен"
        
    await callback.message.edit_text(
        f"👤 <b>Управление вашим Telegram аккаунтом:</b>\n\nСтатус: {status}",
        reply_markup=get_tg_account_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "back_to_main")
async def cb_back_to_menu(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        if not user or not user.is_authenticated:
            await callback.message.answer("⚠️ Пожалуйста, авторизуйтесь через /start", reply_markup=get_request_contact_keyboard())
            return
            
    await callback.message.edit_text(
        "📋 Главное меню:",
        reply_markup=get_main_menu_keyboard(callback.from_user.id)
    )
    await callback.answer()

@router.callback_query(F.data == "btn_profile")
async def cb_profile(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        user_db = await session.get(User, callback.from_user.id)
        if not user_db or not user_db.is_authenticated:
            await callback.answer("⚠️ Аккаунт не подключен!", show_alert=True)
            return
        phone = user_db.phone or "Не указан"
        
        now = datetime.utcnow()
        if user_db.subscription_expires_at and user_db.subscription_expires_at > now:
            remaining = user_db.subscription_expires_at - now
            days = remaining.days
            seconds = remaining.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            
            sub_status = f"✅ <b>Активна</b> (осталось: <b>{days} дн. {hours} ч. {minutes} мин.</b> до {user_db.subscription_expires_at.strftime('%d.%m.%Y %H:%M')} UTC)"
        else:
            sub_status = "❌ <b>Неактивна</b> (требуется продление)"

    user = callback.from_user
    username_str = f"@{user.username}" if user.username else "Не указан"
    text = (
        f"📄 <b>Ваш профиль:</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"👤 <b>Имя:</b> {user.full_name}\n"
        f"🔗 <b>Username:</b> {username_str}\n"
        f"📱 <b>Телефон:</b> {phone}\n"
        f"💳 <b>Статус подписки:</b>\n{sub_status}"
    )
    
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ])
    
    await callback.message.edit_text(text, reply_markup=back_kb, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "btn_subscriptions")
async def cb_subscriptions(callback: CallbackQuery):
    sub_text = (
        "⭐ <b>Раздел подписок</b>\n\n"
        "Для работы с поиском грузов необходима активная подписка. Доступные тарифы:\n\n"
        "⏳ <b>40 дней</b> — <code>90 000 сум</code>\n"
        "⏳ <b>80 дней</b> — <code>160 000 сум</code>\n\n"
        "📌 <b>Оформить или продлить подписку можно напрямую у нашего администратора. Нажмите на кнопку 'Купить подписку', чтобы связаться с ним.</b>"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Купить подписку", url="https://t.me/FreightSearcher_support")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ])
    await callback.message.edit_text(
        sub_text,
        reply_markup=back_kb,
        parse_mode="HTML"
    )
    await callback.answer()

# ---------------------------------------------------------
# РЕКОМЕНДОВАННЫЕ КАНАЛЫ (ДЛЯ ПОЛЬЗОВАТЕЛЕЙ)
# ---------------------------------------------------------
@router.callback_query(F.data == "recommended_channels")
async def cb_channels(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        stmt = select(RecommendedChannel).where(
            RecommendedChannel.is_active == True,
            RecommendedChannel.expires_at > now
        )
        channels = (await session.execute(stmt)).scalars().all()

    keyboard_buttons = []
    
    if channels:
        text = (
            "📢 <b>Рекомендованные каналы с грузами:</b>\n\n"
            "Выберите канал для перехода:\n\n"
            "💡 <i>Хотите добавить свой канал сюда (платно)? Напишите нашему администратору: @FreightSearcher_support</i>"
        )
        for ch in channels:
            keyboard_buttons.append([InlineKeyboardButton(text=f"🔗 {ch.title}", url=ch.link)])
    else:
        text = (
            "📢 <b>Рекомендованные каналы с грузами:</b>\n\n"
            "В данный момент список пуст.\n\n"
            "💡 <i>Хотите добавить свой канал сюда (платно)? Напишите нашему администратору: @FreightSearcher_support</i>"
        )

    keyboard_buttons.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")])
    reply_markup = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    await callback.message.edit_text(
        text,
        reply_markup=reply_markup,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()

# ---------------------------------------------------------
# АДМИН-ПАНЕЛЬ / СТАТУС СБОРЩИКА
# ---------------------------------------------------------
@router.callback_query(F.data == "collector_status")
async def cb_collector_status(callback: CallbackQuery):
    if callback.from_user.id != DEVELOPER_TELEGRAM_ID:
        await callback.answer("⛔ У вас нет доступа к этой панели.", show_alert=True)
        return

    async with AsyncSessionLocal() as session:
        total_messages_stmt = select(func.count(CargoMessage.id))
        total_result = await session.execute(total_messages_stmt)
        total_messages = total_result.scalar() or 0

    status_text = (
        f"📊 <b>Статус сборщика грузов (Админ-панель)</b>\n\n"
        f"📂 Всего сканировано групп: <b>{collector_stats['total_groups']}</b>\n"
        f"🔄 Текущая сканируемая группа: <b>{collector_stats['current_group']}</b>\n"
        f"📥 Сообщений сохранено с текущей группы: <b>{collector_stats['current_group_saved']}</b>\n"
        f"📦 Всего сообщений в базе данных: <b>{total_messages}</b>\n"
        f"🧹 Отфильтровано/исправлено дублей: <b>{collector_stats['duplicates_filtered']}</b>\n"
        f"⚡ Новых сообщений поймано за цикл: <b>{collector_stats['new_caught']}</b>\n"
        f"⚡ Поймано в Live: <b>{collector_stats.get('live_caught', 0)}</b>\n"
        f"🗑 Удалено из БД (протухшие): <b>{collector_stats.get('deleted_from_db', 0)}</b>\n"
        f"⚙️ Режим: <b>{collector_stats['status']}</b>\n\n"
        f"🟢 Сборщик работает в штатном режиме."
    )

    back_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить статус", callback_data="collector_status")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ])

    try:
        await callback.message.edit_text(status_text, reply_markup=back_kb, parse_mode="HTML")
    except Exception:
        pass
        
    await callback.answer("Статус обновлен!")

@router.callback_query(F.data == "tg_reconnect")
async def cb_reconnect(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        if user:
            user.is_authenticated = False
            user.phone = None
            await session.commit()

    await callback.message.answer(
        "🔄 <b>Переподключение аккаунта.</b>\n\nПожалуйста, поделитесь вашим актуальным номером телефона:",
        reply_markup=get_request_contact_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AuthStates.waiting_for_phone)
    await callback.answer()

@router.callback_query(F.data == "tg_disconnect")
async def cb_disconnect(callback: CallbackQuery, state: FSMContext):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, callback.from_user.id)
        if user:
            user.is_authenticated = False
            user.phone = None
            await session.commit()
            
    await state.clear()
    await callback.message.answer(
        "❌ <b>Ваш аккаунт успешно отвязан.</b>\n\n"
        "Чтобы привязать аккаунт заново, поделитесь номером телефона:",
        reply_markup=get_request_contact_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AuthStates.waiting_for_phone)
    await callback.answer()

# ---------------------------------------------------------
# АДМИН-КОМАНДЫ ДЛЯ УПРАВЛЕНИЯ КАНАЛАМИ И ПОДПИСКАМИ
# ---------------------------------------------------------

@router.message(F.text.startswith("/addgroup"))
async def cmd_add_group(message: Message):
    if message.from_user.id != DEVELOPER_TELEGRAM_ID:
        return

    parts = message.text.strip().split(maxsplit=3)
    if len(parts) < 4:
        await message.answer(
            "⚠️ <b>Использование:</b>\n<code>/addgroup ссылка название_канала дни</code>\n\n"
            "<b>Пример:</b>\n<code>/addgroup https://t.me/cargo_channel Логистика_Узбекистан 30</code>",
            parse_mode="HTML"
        )
        return

    link = parts[1].strip()
    title = parts[2].strip()
    try:
        days = int(parts[3].strip())
    except ValueError:
        await message.answer("⚠️ Количество дней должно быть числом!")
        return

    expires_at = datetime.utcnow() + timedelta(days=days)

    async with AsyncSessionLocal() as session:
        new_channel = RecommendedChannel(
            title=title,
            link=link,
            expires_at=expires_at,
            is_active=True
        )
        session.add(new_channel)
        await session.commit()
        await session.refresh(new_channel)

    await message.answer(
        f"✅ <b>Канал успешно добавлен!</b>\n\n"
        f"🆔 <b>ID в БД:</b> <code>{new_channel.id}</code>\n"
        f"📢 <b>Название:</b> {title}\n"
        f"🔗 <b>Ссылка:</b> {link}\n"
        f"⏳ <b>Дней размещения:</b> {days}\n"
        f"📅 <b>Действует до:</b> <code>{expires_at.strftime('%d.%m.%Y %H:%M')} (UTC)</code>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )

@router.message(F.text.startswith("/extendgroup"))
async def cmd_extend_group(message: Message):
    if message.from_user.id != DEVELOPER_TELEGRAM_ID:
        return

    parts = message.text.strip().split()
    if len(parts) < 3:
        await message.answer(
            "⚠️ <b>Использование:</b>\n<code>/extendgroup ID_канала дни</code>\n\n"
            "<b>Пример:</b>\n<code>/extendgroup 1 30</code>",
            parse_mode="HTML"
        )
        return

    try:
        channel_id = int(parts[1])
        add_days = int(parts[2])
    except ValueError:
        await message.answer("⚠️ ID и количество дней должны быть числами!")
        return

    async with AsyncSessionLocal() as session:
        channel = await session.get(RecommendedChannel, channel_id)
        if not channel:
            await message.answer(f"❌ Канал с ID <code>{channel_id}</code> не найден.", parse_mode="HTML")
            return

        now = datetime.utcnow()
        base_date = channel.expires_at if (channel.expires_at and channel.expires_at > now) else now
        new_expire = base_date + timedelta(days=add_days)

        channel.expires_at = new_expire
        channel.is_active = True
        await session.commit()

        await message.answer(
            f"✅ <b>Размещение канала продлено!</b>\n\n"
            f"📢 <b>Канал:</b> {channel.title}\n"
            f"⏳ <b>Добавлено дней:</b> {add_days}\n"
            f"📅 <b>Новая дата окончания:</b> <code>{new_expire.strftime('%d.%m.%Y %H:%M')} (UTC)</code>",
            parse_mode="HTML"
        )

@router.message(F.text.startswith("/delgroup"))
async def cmd_del_group(message: Message):
    if message.from_user.id != DEVELOPER_TELEGRAM_ID:
        return

    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer(
            "⚠️ <b>Использование:</b>\n<code>/delgroup ID_канала</code>\n\n"
            "<b>Пример:</b>\n<code>/delgroup 1</code>",
            parse_mode="HTML"
        )
        return

    try:
        channel_id = int(parts[1])
    except ValueError:
        await message.answer("⚠️ ID канала должен быть числом!")
        return

    async with AsyncSessionLocal() as session:
        channel = await session.get(RecommendedChannel, channel_id)
        if not channel:
            await message.answer(f"❌ Канал с ID <code>{channel_id}</code> не найден в базе.", parse_mode="HTML")
            return

        title = channel.title
        await session.delete(channel)
        await session.commit()

    await message.answer(
        f"🗑 <b>Канал удален!</b>\n\nКанал <b>{title}</b> (ID: {channel_id}) успешно стерт из раздела рекомендованных.",
        parse_mode="HTML"
    )

@router.message(F.text.startswith("/reset_sub"))
async def cmd_reset_sub(message: Message):
    if message.from_user.id != DEVELOPER_TELEGRAM_ID:
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "⚠️ <b>Использование:</b>\n<code>/reset_sub номер_или_id</code>\n\n"
            "<b>Пример:</b>\n<code>/reset_sub +998901234567</code> ИЛИ <code>/reset_sub 123456789</code>",
            parse_mode="HTML"
        )
        return

    query = parts[1].strip()

    async with AsyncSessionLocal() as session:
        if query.isdigit():
            user = await session.get(User, int(query))
        else:
            stmt = select(User).where(User.phone.ilike(f"%{query.replace('+', '')}%"))
            user = (await session.execute(stmt)).scalars().first()

        if not user:
            await message.answer(f"❌ Пользователь <b>{query}</b> не найден в базе данных.", parse_mode="HTML")
            return

        user.subscription_expires_at = datetime.utcnow() - timedelta(minutes=1)
        await session.commit()

        await message.answer(
            f"✅ <b>Подписка успешно аннулирована (обнулена)!</b>\n\n"
            f"👤 <b>Пользователь:</b> {user.full_name or user.username or user.id}\n"
            f"📱 <b>Телефон:</b> {user.phone or 'Не указан'}\n"
            f"🆔 <b>ID:</b> <code>{user.id}</code>",
            parse_mode="HTML"
        )

@router.message(F.text == "/listgroups")
async def cmd_list_groups(message: Message):
    if message.from_user.id != DEVELOPER_TELEGRAM_ID:
        return

    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        stmt = select(RecommendedChannel).where(
            RecommendedChannel.is_active == True,
            RecommendedChannel.expires_at > now
        ).order_by(RecommendedChannel.id)
        
        channels = (await session.execute(stmt)).scalars().all()

    if not channels:
        await message.answer("📢 <b>Список рекомендованных каналов пуст.</b>", parse_mode="HTML")
        return

    text = "📋 <b>Список активных рекомендованных каналов:</b>\n\n"
    
    for ch in channels:
        remaining = ch.expires_at - now
        days_left = remaining.days
        hours_left = remaining.seconds // 3600
        
        text += (
            f"🆔 <b>ID:</b> <code>{ch.id}</code>\n"
            f"📢 <b>Название:</b> {ch.title}\n"
            f"🔗 <b>Ссылка:</b> {ch.link}\n"
            f"⏳ <b>Осталось:</b> {days_left} дн. {hours_left} ч. (до {ch.expires_at.strftime('%d.%m.%Y %H:%M')} UTC)\n"
            f"❌ <i>Удалить:</i> <code>/delgroup {ch.id}</code>\n"
            f"➕ <i>Продлить:</i> <code>/extendgroup {ch.id} 30</code>\n"
            f"-----------------------------------\n"
        )

    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)

@router.message(F.text == "/stats")
async def cmd_stats(message: Message):
    if message.from_user.id != DEVELOPER_TELEGRAM_ID:
        return

    async with AsyncSessionLocal() as session:
        total_users_stmt = select(func.count(User.id))
        total_users = (await session.execute(total_users_stmt)).scalar() or 0

        auth_users_stmt = select(func.count(User.id)).where(User.is_authenticated == True)
        auth_users = (await session.execute(auth_users_stmt)).scalar() or 0

        now = datetime.utcnow()
        active_sub_stmt = select(func.count(User.id)).where(
            User.is_authenticated == True,
            User.subscription_expires_at > now
        )
        active_subs = (await session.execute(active_sub_stmt)).scalar() or 0

    stats_text = (
        f"📊 <b>Статистика пользователей бота:</b>\n\n"
        f"👥 Всего зарегистрировано: <b>{total_users}</b>\n"
        f"📱 Подтвердили аккаунт (телефон): <b>{auth_users}</b>\n"
        f"⭐ С активной подпиской: <b>{active_subs}</b>"
    )

    await message.answer(stats_text, parse_mode="HTML")

@router.message(F.text == "/users")
async def cmd_list_users(message: Message):
    if message.from_user.id != DEVELOPER_TELEGRAM_ID:
        return

    async with AsyncSessionLocal() as session:
        stmt = select(User).order_by(User.id)
        users = (await session.execute(stmt)).scalars().all()

    if not users:
        await message.answer("👥 В базе данных пока нет ни одного пользователя.", parse_mode="HTML")
        return

    now = datetime.utcnow()
    chunk = "📋 <b>Список пользователей:</b>\n\n"
    
    for user in users:
        status_sub = "❌ Неактивна"
        if user.subscription_expires_at and user.subscription_expires_at > now:
            status_sub = f"✅ До {user.subscription_expires_at.strftime('%d.%m.%Y %H:%M')} UTC"

        auth_status = "🟢 Подключен" if user.is_authenticated else "🔴 Не подключен"
        username_str = f"@{user.username}" if user.username else "Нет"
        phone_str = user.phone if user.phone else "Не указан"
        name_str = user.full_name or "Не указано"

        user_block = (
            f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
            f"👤 <b>Имя:</b> {name_str}\n"
            f"🔗 <b>Username:</b> {username_str}\n"
            f"📱 <b>Телефон:</b> {phone_str}\n"
            f"🔌 <b>Статус аккаунта:</b> {auth_status}\n"
            f"💳 <b>Подписка:</b> {status_sub}\n"
            f"-----------------------------------\n"
        )

        if len(chunk) + len(user_block) > 4000:
            await message.answer(chunk, parse_mode="HTML")
            chunk = ""

        chunk += user_block

    if chunk:
        await message.answer(chunk, parse_mode="HTML")


@router.message(F.text.in_({"/help", "/поддержка"}))
async def cmd_support(message: Message):
    await message.answer(
        "💬 <b>Служба поддержки и администратор:</b>\n\n"
        "Если у вас возникли вопросы по работе бота, продлению подписки или размещению рекламы, вы всегда можете написать нашему администратору:\n\n"
        "👉 <b>@FreightSearcher_support</b>",
        parse_mode="HTML"
    )