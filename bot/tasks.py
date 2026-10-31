from datetime import datetime, timedelta
from sqlalchemy import select
from database.session import AsyncSessionLocal
from models.user import User
from models.channel import RecommendedChannel
from config import DEVELOPER_TELEGRAM_ID
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot

async def check_expiring_subscriptions(bot: Bot):
    """
    Фоновая задача: проверяет пользователей, у которых подписка истекает через 1 день (от 23 до 25 часов),
    и отправляет им напоминание ровно один раз.
    """
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        target_start = now + timedelta(hours=23)
        target_end = now + timedelta(hours=25)
        
        stmt = select(User).where(
            User.subscription_expires_at >= target_start,
            User.subscription_expires_at <= target_end,
            User.is_authenticated == True
        )
        users = (await session.execute(stmt)).scalars().all()
        
        for user in users:
            try:
                text = (
                    "⚠️ <b>Внимание! Ваша подписка истекает через 1 день!</b>\n\n"
                    f"📅 Действует до: <code>{user.subscription_expires_at.strftime('%d.%m.%Y %H:%M')} (UTC)</code>\n\n"
                    "Чтобы не потерять доступ к поиску грузов, вы можете продлить подписку прямо сейчас:\n\n"
                    "⏳ <b>40 дней</b> — <code>90 000 сум</code>\n"
                    "⏳ <b>80 дней</b> — <code>160 000 сум</code>\n\n"
                    "📌 <i>Для продления нажмите на кнопку ниже и свяжитесь с администратором.</i>"
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🛒 Продлить подписку", url="https://t.me/FreightSearcher_support")],
                    [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main")]
                ])
                
                await bot.send_message(user.id, text, reply_markup=keyboard, parse_mode="HTML")
            except Exception as e:
                print(f"Не удалось отправить напоминание пользователю {user.id}: {e}")

async def check_expiring_channels(bot: Bot):
    """
    Проверяет каналы: предупреждает админа за 2 дня и деактивирует просроченные.
    """
    async with AsyncSessionLocal() as session:
        now = datetime.utcnow()
        
        notify_start = now + timedelta(hours=47)
        notify_end = now + timedelta(hours=49)
        
        stmt_warning = select(RecommendedChannel).where(
            RecommendedChannel.expires_at >= notify_start,
            RecommendedChannel.expires_at <= notify_end,
            RecommendedChannel.is_active == True
        )
        expiring_channels = (await session.execute(stmt_warning)).scalars().all()
        
        for ch in expiring_channels:
            try:
                text = (
                    f"⚠️ <b>Внимание! Истекает срок размещения канала!</b>\n\n"
                    f"📢 <b>Канал:</b> <a href='{ch.link}'>{ch.title}</a>\n"
                    f"🆔 <b>ID в базе:</b> <code>{ch.id}</code>\n"
                    f"📅 <b>Действует до:</b> <code>{ch.expires_at.strftime('%d.%m.%Y %H:%M')} UTC</code>\n\n"
                    f"<i>Осталось менее 2 дней. Канал скоро будет удален из списка.</i>"
                )
                await bot.send_message(DEVELOPER_TELEGRAM_ID, text, parse_mode="HTML", disable_web_page_preview=True)
            except Exception as e:
                print(f"Ошибка отправки уведомления админу по каналу {ch.id}: {e}")

        stmt_expired = select(RecommendedChannel).where(
            RecommendedChannel.expires_at <= now,
            RecommendedChannel.is_active == True
        )
        expired_channels = (await session.execute(stmt_expired)).scalars().all()
        
        for ch in expired_channels:
            ch.is_active = False
            try:
                await bot.send_message(
                    DEVELOPER_TELEGRAM_ID,
                    f"🔴 <b>Срок размещения канала истек!</b>\n\nКанал <b>{ch.title}</b> ({ch.link}) автоматически удален из рекомендованных.",
                    parse_mode="HTML",
                    disable_web_page_preview=True
                )
            except Exception:
                pass
                
        await session.commit()