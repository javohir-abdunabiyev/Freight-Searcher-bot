from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DEVELOPER_TELEGRAM_ID

def get_main_menu_keyboard(user_id: int):
    buttons = [
        [InlineKeyboardButton(text="🔍 Найти груз", callback_data="btn_search")],
        [InlineKeyboardButton(text="📄 Мой профиль", callback_data="btn_profile"),
         InlineKeyboardButton(text="⭐ Подписка", callback_data="btn_subscriptions")],
        [InlineKeyboardButton(text="📢 Рекомендованные каналы", callback_data="recommended_channels")],
        [InlineKeyboardButton(text="📁 База групп", callback_data="btn_group_base")],
        [InlineKeyboardButton(text="📖 Инструкция", callback_data="btn_instruction"),
         InlineKeyboardButton(text="💬 Тех. поддержка", url="https://t.me/FreightSearcher_support")],
        [InlineKeyboardButton(text="👤 Управление аккаунтом Telegram", callback_data="tg_account_settings")]
    ]
    
    # Если это админ, добавляем кнопку админ-панели
    if user_id == DEVELOPER_TELEGRAM_ID:
        buttons.append([InlineKeyboardButton(text="📊 Админ-панель (Сборщик)", callback_data="collector_status")])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_tg_account_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Переподключить аккаунт", callback_data="tg_reconnect")],
        [InlineKeyboardButton(text="❌ Отвязать аккаунт", callback_data="tg_disconnect")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ])

def get_request_contact_keyboard():
    from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться контактом", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True
    )