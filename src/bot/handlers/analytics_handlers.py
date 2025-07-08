"""
Обработчики аналитики и статистики
"""
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import matplotlib.pyplot as plt
import seaborn as sns
from io import BytesIO
import pandas as pd

from ...config.settings import ADMIN_IDS
from ...database.database_manager import get_all_records, get_payments
from ...utils.config_utils import load_users

logger = logging.getLogger(__name__)

async def generate_analytics_report(update: Update, context: CallbackContext):
    """Генерирует аналитический отчет с графиками"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        # Получаем данные
        records = get_all_records()
        users = load_users()
        
        # Создаем DataFrame
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date'], errors='coerce', dayfirst=True)
        df = df.dropna(subset=['date'])
        
        # Группируем по месяцам
        df_monthly = df.groupby([df['date'].dt.to_period('M'), 'supplier'])['amount'].sum().reset_index()
        df_monthly['date'] = df_monthly['date'].astype(str)
        
        # Создаем графики
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        
        # 1. Расходы по месяцам
        monthly_expenses = df.groupby(df['date'].dt.to_period('M'))['amount'].sum()
        axes[0, 0].bar(range(len(monthly_expenses)), monthly_expenses.values)
        axes[0, 0].set_title('Расходы по месяцам')
        axes[0, 0].set_xlabel('Месяц')
        axes[0, 0].set_ylabel('Сумма (драм)')
        
        # 2. Топ сотрудников по расходам
        top_employees = df.groupby('supplier')['amount'].sum().sort_values(ascending=False).head(10)
        axes[0, 1].barh(range(len(top_employees)), top_employees.values)
        axes[0, 1].set_title('Топ 10 сотрудников по расходам')
        axes[0, 1].set_xlabel('Сумма (драм)')
        axes[0, 1].set_yticks(range(len(top_employees)))
        axes[0, 1].set_yticklabels(top_employees.index)
        
        # 3. Динамика расходов по дням
        daily_expenses = df.groupby(df['date'].dt.date)['amount'].sum()
        axes[1, 0].plot(daily_expenses.index, daily_expenses.values)
        axes[1, 0].set_title('Динамика расходов')
        axes[1, 0].set_xlabel('Дата')
        axes[1, 0].set_ylabel('Сумма (драм)')
        
        # 4. Распределение расходов по направлениям
        direction_expenses = df.groupby('direction')['amount'].sum()
        axes[1, 1].pie(direction_expenses.values, labels=direction_expenses.index, autopct='%1.1f%%')
        axes[1, 1].set_title('Распределение по направлениям')
        
        plt.tight_layout()
        
        # Сохраняем график
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        
        # Отправляем график
        await query.message.reply_photo(
            photo=buffer,
            caption="📊 Аналитический отчет по расходам",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка генерации аналитики: {e}")
        await query.edit_message_text(
            f"❌ Ошибка генерации аналитики: {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )

async def generate_payment_analytics(update: Update, context: CallbackContext):
    """Генерирует аналитику по платежам"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        users = load_users()
        analytics_data = []
        
        for user_id, user_data in users.items():
            display_name = user_data.get('display_name')
            if not display_name:
                continue
                
            # Получаем расходы
            records = get_all_records()
            total_expenses = sum(r['amount'] for r in records if r['supplier'] == display_name)
            
            # Получаем платежи
            payments = get_payments(display_name)
            total_paid = sum(p[0] for p in payments) if payments else 0
            
            # Рассчитываем показатели
            debt = total_expenses - total_paid
            payment_rate = (total_paid / total_expenses * 100) if total_expenses > 0 else 0
            
            analytics_data.append({
                'name': display_name,
                'expenses': total_expenses,
                'paid': total_paid,
                'debt': debt,
                'payment_rate': payment_rate
            })
        
        # Сортируем по долгу
        analytics_data.sort(key=lambda x: x['debt'], reverse=True)
        
        # Формируем отчет
        report_text = "💰 <b>Аналитика по платежам</b>\n\n"
        
        for i, data in enumerate(analytics_data[:15], 1):
            report_text += (
                f"{i}. <b>{data['name']}</b>\n"
                f"   💸 Расходы: {data['expenses']:,.2f} դրամ\n"
                f"   💵 Выплачено: {data['paid']:,.2f} դրամ\n"
                f"   💰 Долг: {data['debt']:,.2f} դրամ\n"
                f"   📊 Процент выплат: {data['payment_rate']:.1f}%\n\n"
            )
        
        await query.edit_message_text(
            report_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📊 Графики", callback_data="analytics_charts")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка аналитики платежей: {e}")
        await query.edit_message_text(
            f"❌ Ошибка аналитики: {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )

async def generate_trends_report(update: Update, context: CallbackContext):
    """Генерирует отчет по трендам"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        records = get_all_records()
        df = pd.DataFrame(records)
        df['date'] = pd.to_datetime(df['date'], errors='coerce', dayfirst=True)
        df = df.dropna(subset=['date'])
        
        # Анализ за последние 30 дней
        today = datetime.now()
        last_30_days = today - timedelta(days=30)
        df_recent = df[df['date'] >= last_30_days]
        
        # Анализ за предыдущие 30 дней
        prev_30_days = today - timedelta(days=60)
        df_prev = df[(df['date'] >= prev_30_days) & (df['date'] < last_30_days)]
        
        # Сравниваем показатели
        recent_total = df_recent['amount'].sum()
        prev_total = df_prev['amount'].sum()
        
        change = ((recent_total - prev_total) / prev_total * 100) if prev_total > 0 else 0
        change_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
        
        # Топ сотрудников за последний месяц
        top_recent = df_recent.groupby('supplier')['amount'].sum().sort_values(ascending=False).head(5)
        
        # Самые частые направления
        top_directions = df_recent.groupby('direction')['amount'].sum().sort_values(ascending=False).head(5)
        
        report_text = (
            f"📊 <b>Анализ трендов (последние 30 дней)</b>\n\n"
            f"💰 Общие расходы: {recent_total:,.2f} դրամ\n"
            f"{change_emoji} Изменение: {change:+.1f}%\n\n"
            f"🏆 <b>Топ сотрудников:</b>\n"
        )
        
        for i, (name, amount) in enumerate(top_recent.items(), 1):
            report_text += f"{i}. {name}: {amount:,.2f} դրամ\n"
        
        report_text += "\n🎯 <b>Топ направлений:</b>\n"
        for i, (direction, amount) in enumerate(top_directions.items(), 1):
            report_text += f"{i}. {direction}: {amount:,.2f} դրամ\n"
        
        await query.edit_message_text(
            report_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка анализа трендов: {e}")
        await query.edit_message_text(
            f"❌ Ошибка анализа: {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )
