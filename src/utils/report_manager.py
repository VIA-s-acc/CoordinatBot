"""
Система отчетов и аналитики
"""
import pandas as pd
import logging
from io import BytesIO
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from telegram import Update
from telegram.ext import CallbackContext
from ..database.database_manager import get_all_records, get_payments
from ..utils.date_utils import normalize_date, format_date_for_interval
from ..config.settings import ADMIN_IDS
from .config_utils import load_bot_config

logger = logging.getLogger(__name__)

async def send_report(context: CallbackContext, action: str, record: dict, user: dict):
    """Отправляет отчет о действии в настроенные чаты"""
    config = load_bot_config()
    report_chats = config.get('report_chats', {})
    
    if not report_chats:
        return

    user_name = user.get('display_name') or user.get('name') or f"User {user['id']}"
    record_id = record.get('id', 'N/A')

    if action == "Խմբագրում":
        report_text = (
            f"📢 🟥<b>ԽՄԲԱԳՐՈՒՄ</b> ID: <code>{record_id}</code> 🟥\n\n"
            f"👤 Օգտագործող: <b>{user_name}</b> \n"
        ) + format_record_info(record) + "\n\n" 
    elif action == "Բացթողում":
        date = record.get('date', 'N/A')
        report_text = (
            f"📢 🟡<b>ԲԱՑԹՈՂՈՒՄ: {date} ամսաթվով</b>🟡\n\n"
            f"👤 Օգտագործող: <b>{user_name}</b>\n"
        ) + format_record_info(record) + "\n\n" 
    else:
        report_text = (
            f"📢 <b>Ավելացում</b>\n\n"
            f"👤 Օգտագործող: <b>{user_name}</b>\n"
        ) + format_record_info(record)
        
    for chat_id, settings in report_chats.items():
        try:
            # Проверяем, нужно ли фильтровать по листу
            configured_sheet = settings.get('sheet_name')
            record_sheet = record.get('sheet_name')
            
            # Если для чата настроен конкретный лист, отправляем отчет только для этого листа
            if configured_sheet and record_sheet and configured_sheet != record_sheet:
                logger.info(f"Пропускаем отчет для чата {chat_id}: лист '{record_sheet}' не соответствует настроенному '{configured_sheet}'")
                continue
                
            await context.bot.send_message(
                chat_id=chat_id,
                text=report_text,
                parse_mode="HTML"
            )
            logger.info(f"Отчет отправлен в чат {chat_id} для листа '{record_sheet}'")
        except Exception as e:
            logger.error(f"Սխալ հաշվետվություն ուղարկելիս {chat_id}: {e}")

def     format_record_info(record: dict) -> str:
    """Форматирует информацию о записи"""
    return (
        f"🆔 ID: <code>{record.get('id', 'N/A')}</code>\n\n\n"
        f"🏪 Մատակարար: <b>{record.get('supplier', 'N/A')}</b>\n"
        f"📅 Ամսաթիվ: <b>{record.get('date', 'N/A')}</b>\n"
        f"🧭 Ուղղություն: <b>{record.get('direction', 'N/A')}</b>\n"
        f"📝 Նկարագրություն: <b>{record.get('description', 'N/A')}</b>\n"
        f"💰 Գումար: <b>{record.get('amount', 0):,.2f}</b>\n"
    )

class ReportManager:
    """Менеджер для создания отчетов"""
    
    def __init__(self):
        pass
    
    def merge_payment_intervals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Объединяет пересекающиеся интервалы платежей
        """
        if df.empty:
            return df
        
        # Сортируем по дате начала
        df = df.sort_values('date_from').reset_index(drop=True)
        
        merged = []
        current_start = df.iloc[0]['date_from']
        current_end = df.iloc[0]['date_to']
        current_amount = df.iloc[0]['amount']
        
        for i in range(1, len(df)):
            row = df.iloc[i]
            
            # Если интервалы пересекаются или касаются
            if row['date_from'] <= current_end + timedelta(days=1):
                # Расширяем текущий интервал
                current_end = max(current_end, row['date_to'])
                current_amount += row['amount']
            else:
                # Сохраняем текущий интервал и начинаем новый
                merged.append({
                    'date_from': current_start,
                    'date_to': current_end,
                    'amount': current_amount
                })
                current_start = row['date_from']
                current_end = row['date_to']
                current_amount = row['amount']
        
        # Добавляем последний интервал
        merged.append({
            'date_from': current_start,
            'date_to': current_end,
            'amount': current_amount
        })
        
        return pd.DataFrame(merged)
    
    async def generate_user_report(self, display_name: str, update: Update, context: CallbackContext):
        """
        Генерирует отчет для конкретного пользователя
        """
        try:
            # Получаем все записи из БД
            db_records = get_all_records()
            
            # Фильтруем записи по пользователю
            filtered_records = []
            for record in db_records:
                if record['amount'] == 0:
                    continue
                if record['supplier'] != display_name:
                    continue
                
                record['date'] = normalize_date(record['date'])
                
                # Применяем фильтр по датам (разный для разных пользователей)
                if record['supplier'] == "Նարեկ":
                    cutoff_date = datetime.strptime("2025-05-10", '%Y-%m-%d').date()
                else:
                    cutoff_date = datetime.strptime("2024-12-05", '%Y-%m-%d').date()
                
                record_date = datetime.strptime(record['date'], '%d.%m.%y').date()
                if record_date >= cutoff_date:
                    filtered_records.append(record)
            
            # Группируем по листам
            sheets = {}
            for rec in filtered_records:
                spreadsheet_id = rec.get('spreadsheet_id', '—')
                sheet_name = rec.get('sheet_name', '—')
                key = (spreadsheet_id, sheet_name)
                sheets.setdefault(key, []).append(rec)
            
            all_summaries = []
            
            # Генерируем отчет по каждому листу
            for (spreadsheet_id, sheet_name), records in sheets.items():
                await self._generate_sheet_report(
                    display_name, spreadsheet_id, sheet_name, 
                    records, update, all_summaries
                )
            
            # Генерируем итоговый отчет
            if all_summaries:
                await self._generate_total_report(
                    display_name, spreadsheet_id, sheet_name, 
                    all_summaries, update
                )
                
        except Exception as e:
            logger.error(f"Ошибка генерации отчета для {display_name}: {e}")
            await update.effective_message.reply_text(f"❌ Հաշվետվություն ստեղծելու սխալ: {e}")
    
    async def _generate_sheet_report(self, display_name: str, spreadsheet_id: str, 
                                   sheet_name: str, records: List[Dict], 
                                   update: Update, all_summaries: List[Dict]):
        """Генерирует отчет по отдельному листу"""
        try:
            df = pd.DataFrame(records)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'], errors='coerce', dayfirst=True)
            else:
                df['date'] = pd.to_datetime([])
            
            df_amount_total = df['amount'].sum() if not df.empty else 0
            
            # Добавляем итоговую строку
            df.loc["Իտոգ"] = [
                '—', '—', '—', '—', '—', df_amount_total, '—', '—', '—', '—'  
            ]
            
            # Сохраняем для итоговой сводки
            all_summaries.append({
                'Աղյուսակ': spreadsheet_id,
                'Թերթ': sheet_name,
                'Ծախս': df_amount_total,
                "Վճար": '—',  
                'Մնացորդ': '—'
            })
            
            summary = pd.DataFrame([{
                'Ընդհանուր ծախս': df_amount_total,
            }])
            
            # Создаем Excel файл
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='All Expenses', index=False)
                summary.to_excel(writer, sheet_name='Summary', index=False)
            output.seek(0)
            
            await update.effective_message.reply_document(
                document=output,
                filename=f"{display_name}_{sheet_name}_report.xlsx",
                caption=(
                    f"Թերթ: {sheet_name}\n"
                    f"Ընդհանուր ծախս: {df_amount_total:,.2f}\n"
                )
            )
            
        except Exception as e:
            logger.error(f"Ошибка генерации отчета по листу {sheet_name}: {e}")
    
    async def _generate_total_report(self, display_name: str, spreadsheet_id: str, 
                                   sheet_name: str, all_summaries: List[Dict], 
                                   update: Update):
        """Генерирует итоговый отчет по всем листам"""
        try:
            df_total = pd.DataFrame(all_summaries)
            total_expenses_all = df_total['Ծախս'].sum()
            
            # Получаем платежи
            payments = get_payments(display_name, spreadsheet_id, sheet_name)
            if not payments:
                total_paid_all = 0
            else:
                df_pay_raw = pd.DataFrame(
                    payments, 
                    columns=['amount', 'date_from', 'date_to', 'comment', 'created_at']
                )
                
                # Приводим типы
                df_pay_raw['amount'] = pd.to_numeric(df_pay_raw['amount'], errors='coerce').fillna(0)
                df_pay_raw['date_from'] = pd.to_datetime(df_pay_raw['date_from'], errors='coerce')
                df_pay_raw['date_to'] = pd.to_datetime(df_pay_raw['date_to'], errors='coerce')
                
                # Слияние интервалов и агрегирование
                df_pay = self.merge_payment_intervals(df_pay_raw[['amount', 'date_from', 'date_to']])
                
                # Итоговая сумма после объединения
                total_paid_all = df_pay['amount'].sum()
            
            total_left_all = total_expenses_all - total_paid_all
            df_total.loc['Իտոգ'] = [
                '—', '—',
                total_expenses_all,
                total_paid_all,
                total_left_all
            ]
            
            output_total = BytesIO()
            with pd.ExcelWriter(output_total, engine='openpyxl') as writer:
                df_total.to_excel(writer, sheet_name='Իտոգներ', index=False)
            output_total.seek(0)
            
            await update.effective_message.reply_document(
                document=output_total,
                filename=f"{display_name}_TOTAL_report.xlsx",
                caption=(
                    f"Ընդհանուր ծախսեր:\n"
                    f"• Ընդհանուր ծախս: {total_expenses_all:,.2f}\n"
                    f"• Ընդհանուր Վճար: {total_paid_all:,.2f}\n"
                    f"• Ընդհանուր մնացորդ: {total_left_all:,.2f}"
                )
            )
            
        except Exception as e:
            logger.error(f"Ошибка генерации итогового отчета: {e}")
    
    async def generate_statistics_report(self, update: Update, context: CallbackContext):
        """Генерирует общую статистику"""
        try:
            records = get_all_records()
            
            if not records:
                await update.message.reply_text("📊 Տվյալների բազայում գրառումներ չկան:")
                return
            
            df = pd.DataFrame(records)
            
            # Общая статистика
            total_records = len(df)
            total_amount = df['amount'].sum()
            avg_amount = df['amount'].mean()
            
            # Статистика по поставщикам
            supplier_stats = df.groupby('supplier').agg({
                'amount': ['count', 'sum']
            }).round(2)
            
            # Статистика по листам
            sheet_stats = df.groupby('sheet_name').agg({
                'amount': ['count', 'sum']
            }).round(2)
            
            stats_text = (
                f"📊 <b>Ընդհանուր վիճակագրություն</b>\n\n"
                f"📝 Ընդհանուր գրառումներ: <b>{total_records}</b>\n"
                f"💰 Ընդհանուր գումար: <b>{total_amount:,.2f}</b> դրամ\n"
                f"📈 Միջին գումար: <b>{avg_amount:,.2f}</b> դրամ\n\n"
                f"<b>Մատակարարների կողմից վիճակագրություն:</b>\n"
            )
            
            for supplier, data in supplier_stats.iterrows():
                count = int(data[('amount', 'count')])
                total = data[('amount', 'sum')]
                stats_text += f"• {supplier}: {count} գրառում, {total:,.2f} դրամ\n"
            
            await update.message.reply_text(stats_text, parse_mode="HTML")
            
        except Exception as e:
            logger.error(f"Ошибка генерации статистики: {e}")
            await update.message.reply_text(f"❌ Վիճակագրություն ստեղծելու սխալ: {e}")

# Создаем глобальный экземпляр менеджера отчетов
report_manager = ReportManager()

# Экспортируем функции для использования в обработчиках
async def generate_user_report(display_name: str, update: Update, context: CallbackContext):
    return await report_manager.generate_user_report(display_name, update, context)

async def generate_statistics_report(update: Update, context: CallbackContext):
    return await report_manager.generate_statistics_report(update, context)
