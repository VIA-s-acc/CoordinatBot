"""
Система лимитов и контроля расходов
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from ...config.settings import ADMIN_IDS
from ...utils.config_utils import load_users, get_user_settings
from ...database.database_manager import get_all_records

logger = logging.getLogger(__name__)

async def check_daily_limit(user_id: int, amount: float) -> tuple[bool, str]:
    """
    Проверяет дневной лимит пользователя
    Возвращает (разрешено, сообщение)
    """
    try:
        users = load_users()
        user_data = users.get(str(user_id), {})
        daily_limit = user_data.get('daily_limit')
        
        if not daily_limit:
            return True, ""
        
        # Получаем расходы пользователя за сегодня
        today = datetime.now().date()
        display_name = user_data.get('display_name')
        
        if not display_name:
            return True, ""
        
        records = get_all_records()
        today_expenses = 0
        
        for record in records:
            if record['supplier'] == display_name and record['amount'] > 0:
                try:
                    record_date = datetime.strptime(record['date'], '%d.%m.%y').date()
                    if record_date == today:
                        today_expenses += record['amount']
                except ValueError:
                    continue
        
        # Проверяем лимит
        if today_expenses + amount > daily_limit:
            remaining = daily_limit - today_expenses
            message = (
                f"⚠️ Превышен дневной лимит!\n"
                f"💰 Лимит: {daily_limit:,.2f} դրամ\n"
                f"📊 Потрачено сегодня: {today_expenses:,.2f} դրամ\n"
                f"💸 Остаток: {remaining:,.2f} դրամ\n"
                f"❌ Пытаетесь добавить: {amount:,.2f} դրամ"
            )
            return False, message
        
        return True, ""
        
    except Exception as e:
        logger.error(f"Ошибка проверки лимита: {e}")
        return True, ""

async def get_spending_summary(user_id: int) -> str:
    """Получает сводку расходов пользователя"""
    try:
        users = load_users()
        user_data = users.get(str(user_id), {})
        display_name = user_data.get('display_name')
        daily_limit = user_data.get('daily_limit')
        
        if not display_name:
            return "❌ Не найдено имя пользователя"
        
        records = get_all_records()
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        today_expenses = 0
        week_expenses = 0
        month_expenses = 0
        
        for record in records:
            if record['supplier'] == display_name and record['amount'] > 0:
                try:
                    record_date = datetime.strptime(record['date'], '%d.%m.%y').date()
                    
                    if record_date == today:
                        today_expenses += record['amount']
                    
                    if record_date >= week_ago:
                        week_expenses += record['amount']
                    
                    if record_date >= month_ago:
                        month_expenses += record['amount']
                        
                except ValueError:
                    continue
        
        summary = f"📊 <b>Сводка расходов</b>\n\n"
        summary += f"📅 Сегодня: {today_expenses:,.2f} դրամ\n"
        
        if daily_limit:
            remaining = daily_limit - today_expenses
            summary += f"💰 Лимит: {daily_limit:,.2f} դրամ\n"
            summary += f"💸 Остаток: {remaining:,.2f} դրամ\n"
            
            if remaining < 0:
                summary += f"⚠️ Превышение: {abs(remaining):,.2f} դրամ\n"
        
        summary += f"\n📅 За неделю: {week_expenses:,.2f} դրամ\n"
        summary += f"📅 За месяц: {month_expenses:,.2f} դրամ\n"
        
        # Средние показатели
        avg_daily = month_expenses / 30
        avg_weekly = week_expenses / 7
        
        summary += f"\n📊 Среднее в день: {avg_daily:,.2f} դրամ\n"
        summary += f"📊 Среднее в неделю: {avg_weekly:,.2f} դրամ"
        
        return summary
        
    except Exception as e:
        logger.error(f"Ошибка получения сводки: {e}")
        return "❌ Ошибка получения сводки"

async def show_spending_summary(update: Update, context: CallbackContext):
    """Показывает сводку расходов пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    summary = await get_spending_summary(user_id)
    
    await query.edit_message_text(
        summary,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data="spending_summary")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
        ])
    )

async def check_weekly_limits(context: CallbackContext):
    """Проверяет еженедельные лимиты всех пользователей"""
    try:
        users = load_users()
        
        for user_id, user_data in users.items():
            display_name = user_data.get('display_name')
            weekly_limit = user_data.get('weekly_limit')
            
            if not display_name or not weekly_limit:
                continue
            
            # Проверяем расходы за неделю
            week_ago = datetime.now().date() - timedelta(days=7)
            records = get_all_records()
            week_expenses = 0
            
            for record in records:
                if record['supplier'] == display_name and record['amount'] > 0:
                    try:
                        record_date = datetime.strptime(record['date'], '%d.%m.%y').date()
                        if record_date >= week_ago:
                            week_expenses += record['amount']
                    except ValueError:
                        continue
            
            # Если превышен лимит - уведомляем
            if week_expenses > weekly_limit:
                await notify_limit_exceeded(context, user_id, display_name, week_expenses, weekly_limit, "недельный")
                
    except Exception as e:
        logger.error(f"Ошибка проверки недельных лимитов: {e}")

async def notify_limit_exceeded(context: CallbackContext, user_id: str, display_name: str, 
                               spent: float, limit: float, period: str):
    """Уведомляет о превышении лимита"""
    try:
        excess = spent - limit
        
        # Уведомляем пользователя
        if user_id.isdigit():
            user_message = (
                f"⚠️ <b>Превышен {period} лимит!</b>\n\n"
                f"💰 Лимит: {limit:,.2f} դրամ\n"
                f"📊 Потрачено: {spent:,.2f} դրամ\n"
                f"❌ Превышение: {excess:,.2f} դրամ\n\n"
                f"Рекомендуется сократить расходы."
            )
            
            await context.bot.send_message(
                chat_id=int(user_id),
                text=user_message,
                parse_mode="HTML"
            )
        
        # Уведомляем админов
        admin_message = (
            f"⚠️ <b>Превышен лимит!</b>\n\n"
            f"👤 Пользователь: {display_name}\n"
            f"📅 Период: {period}\n"
            f"💰 Лимит: {limit:,.2f} դրամ\n"
            f"📊 Потрачено: {spent:,.2f} դրամ\n"
            f"❌ Превышение: {excess:,.2f} դրամ"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_message,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления админа {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка уведомления о превышении лимита: {e}")

async def create_budget_report(update: Update, context: CallbackContext):
    """Создает отчет по бюджету"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        users = load_users()
        budget_data = []
        
        for uid, user_data in users.items():
            display_name = user_data.get('display_name')
            daily_limit = user_data.get('daily_limit')
            weekly_limit = user_data.get('weekly_limit')
            
            if not display_name:
                continue
            
            # Расчет расходов
            today = datetime.now().date()
            week_ago = today - timedelta(days=7)
            
            records = get_all_records()
            today_expenses = 0
            week_expenses = 0
            
            for record in records:
                if record['supplier'] == display_name and record['amount'] > 0:
                    try:
                        record_date = datetime.strptime(record['date'], '%d.%m.%y').date()
                        
                        if record_date == today:
                            today_expenses += record['amount']
                        
                        if record_date >= week_ago:
                            week_expenses += record['amount']
                            
                    except ValueError:
                        continue
            
            budget_data.append({
                'name': display_name,
                'daily_limit': daily_limit,
                'weekly_limit': weekly_limit,
                'today_expenses': today_expenses,
                'week_expenses': week_expenses,
                'daily_remaining': (daily_limit - today_expenses) if daily_limit else None,
                'weekly_remaining': (weekly_limit - week_expenses) if weekly_limit else None
            })
        
        # Формируем отчет
        report_text = "💰 <b>Отчет по бюджету</b>\n\n"
        
        for data in budget_data:
            report_text += f"👤 <b>{data['name']}</b>\n"
            
            if data['daily_limit']:
                remaining = data['daily_remaining']
                emoji = "✅" if remaining >= 0 else "❌"
                report_text += f"📅 Дневной: {data['today_expenses']:,.0f} / {data['daily_limit']:,.0f} {emoji}\n"
            
            if data['weekly_limit']:
                remaining = data['weekly_remaining']
                emoji = "✅" if remaining >= 0 else "❌"
                report_text += f"📅 Недельный: {data['week_expenses']:,.0f} / {data['weekly_limit']:,.0f} {emoji}\n"
            
            report_text += "\n"
        
        await query.edit_message_text(
            report_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Обновить", callback_data="budget_report")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания отчета по бюджету: {e}")
        await query.edit_message_text(
            f"❌ Ошибка создания отчета: {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )
