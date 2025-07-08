"""
Обработчики уведомлений и алертов
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from ...config.settings import ADMIN_IDS
from ...utils.config_utils import load_users, send_to_log_chat
from ...database.database_manager import get_all_records, get_payments

logger = logging.getLogger(__name__)

async def check_debt_alerts(context: CallbackContext):
    """Проверяет долги сотрудников и отправляет уведомления"""
    try:
        users = load_users()
        
        for user_id, user_data in users.items():
            display_name = user_data.get('display_name')
            if not display_name:
                continue
                
            # Рассчитываем долг
            debt = await calculate_user_debt(display_name)
            
            if debt > 100000:  # Если долг больше 100к драм
                # Уведомляем админов
                await notify_admins_about_debt(context, display_name, debt)
                
                # Уведомляем самого пользователя
                if user_id.isdigit():
                    await notify_user_about_debt(context, int(user_id), debt)
                    
    except Exception as e:
        logger.error(f"Ошибка проверки долгов: {e}")

async def calculate_user_debt(display_name: str) -> float:
    """Рассчитывает долг пользователя"""
    # Получаем все записи пользователя
    db_records = get_all_records()
    total_expenses = 0
    
    for record in db_records:
        if record['supplier'] == display_name and record['amount'] > 0:
            total_expenses += record['amount']
    
    # Получаем все платежи пользователя
    payments = get_payments(display_name)
    total_paid = sum(payment[0] for payment in payments) if payments else 0
    
    return total_expenses - total_paid

async def notify_admins_about_debt(context: CallbackContext, display_name: str, debt: float):
    """Уведомляет админов о большом долге"""
    message = (
        f"⚠️ <b>Предупреждение о долге!</b>\n\n"
        f"👤 Сотрудник: {display_name}\n"
        f"💸 Долг: {debt:,.2f} դրամ\n\n"
        f"Рекомендуется принять меры."
    )
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")

async def notify_user_about_debt(context: CallbackContext, user_id: int, debt: float):
    """Уведомляет пользователя о долге"""
    message = (
        f"💰 <b>Информация о задолженности</b>\n\n"
        f"Ваша текущая задолженность: {debt:,.2f} դրամ\n\n"
        f"Просьба обратиться к администратору для урегулирования."
    )
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=message,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

async def send_weekly_report(context: CallbackContext):
    """Отправляет еженедельный отчет админам"""
    try:
        users = load_users()
        report_data = []
        
        for user_id, user_data in users.items():
            display_name = user_data.get('display_name')
            if not display_name:
                continue
                
            debt = await calculate_user_debt(display_name)
            report_data.append({
                'name': display_name,
                'debt': debt
            })
        
        # Сортируем по размеру долга
        report_data.sort(key=lambda x: x['debt'], reverse=True)
        
        # Формируем отчет
        report_text = "📊 <b>Еженедельный отчет по задолженностям</b>\n\n"
        
        for i, user_data in enumerate(report_data[:10], 1):  # Топ 10
            report_text += f"{i}. {user_data['name']}: {user_data['debt']:,.2f} դրամ\n"
        
        # Отправляем админам
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=report_text,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки отчета админу {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка создания еженедельного отчета: {e}")
