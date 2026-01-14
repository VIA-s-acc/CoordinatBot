"""
Система отчетов и аналитики
"""
import pandas as pd

from io import BytesIO
from datetime import datetime, timedelta
from .date_utils import safe_parse_date_or_none
from typing import Dict, List
from telegram import Update
from telegram.ext import CallbackContext
from ..database.database_manager import get_all_records, get_payments
from ..utils.date_utils import normalize_date
from .config_utils import load_bot_config
from ..config.settings import logger


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
            f"📢 🟥<b>ԽՄԲԱԳՐՈՒՄ</b> ID: <code>{record_id}</code> 🟥\n"
            f"👤 Օգտագործող: <b>{user_name}</b> \n"
        ) + format_record_info(record) + "\n\n" 
    elif action == "Բացթողում":
        date = record.get('date', 'N/A')
        report_text = (
            f"📢 🟡<b>ԲԱՑԹՈՂՈՒՄ: {date} ամսաթվով</b>🟡\n"
            f"👤 Օգտագործող: <b>{user_name}</b>\n"
        ) + format_record_info(record) + "\n\n" 
    elif action == "Ջնջում":
        report_text = (
            f"💩<b>ՋՆՋՈՒՄ</b> ID: <code>{record_id}</code> 💩\n"
            f"👤 Օգտագործող: <b>{user_name}</b>\n"
        )
    else:
        report_text = (
            f"📢 <b>Ավելացում</b>\n"
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

def format_record_info(record: dict) -> str:
    """Форматирует информацию о записи"""
    # Преобразуем дату из Y.M.D (или Y-M-D) в D.M.Y, если возможно
    date_str = record.get('date', 'N/A')
    if date_str and date_str != 'N/A':
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
        except Exception:
            formatted_date = date_str
    else:
        formatted_date = 'N/A'

    amount = record.get('amount', 0)
    # Форматируем сумму без .00, но с разделителем тысяч
    if isinstance(amount, float) and amount.is_integer():
        amount_str = f"{int(amount):,}".replace(",", ",")
    else:
        amount_str = f"{amount:,}".replace(",", ",")
    return (
        f"🆔 ID: <code>{record.get('id', 'N/A')}</code>\n\n\n"
        f"🏪: <b>{record.get('supplier', 'N/A')}</b>\n"
        f"📅: <b>{formatted_date}</b>\n"
        f"🧭: <b>{record.get('direction', 'N/A')}</b>\n"
        f"📝: <b>{record.get('description', 'N/A')}</b>\n"
        f"💰: <b>{amount_str}</b>\n"
        f"📋: <b>{record.get('sheet_name', 'N/A')}</b>"
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
            
            # ИСПРАВЛЕНИЕ: Дедупликация записей по ID
            # Создаем словарь для хранения уникальных записей
            unique_records = {}
            
            # Фильтруем записи по пользователю и убираем дубликаты
            for record in db_records:
                if record['amount'] == 0:
                    continue
                if record['supplier'] != display_name:
                    continue
                
                record_id = record.get('id')
                if not record_id:
                    continue
                
                # Если запись с таким ID уже есть, берем более новую по updated_at
                if record_id in unique_records:
                    existing_updated = unique_records[record_id].get('updated_at', '')
                    current_updated = record.get('updated_at', '')
                    
                    # Сравниваем даты обновления, берем более новую
                    if current_updated > existing_updated:
                        unique_records[record_id] = record
                        logger.info(f"Заменили дубликат записи {record_id}: {existing_updated} -> {current_updated}")
                    else:
                        logger.info(f"Пропустили старый дубликат записи {record_id}: {current_updated} <= {existing_updated}")
                else:
                    unique_records[record_id] = record
            
            # Преобразуем обратно в список и применяем фильтры
            filtered_records = []
            for record in unique_records.values():
                record['date'] = normalize_date(record['date'])
                
                # Применяем фильтр по датам (разный для разных пользователей)
                if record['supplier'] == "Նարեկ":
                    cutoff_date = datetime.strptime("2025-05-10", '%Y-%m-%d').date()
                else:
                    cutoff_date = datetime.strptime("2024-12-05", '%Y-%m-%d').date()
                
                # Безопасный парсинг даты
                record_date = safe_parse_date_or_none(record['date'])
                if record_date is None:
                    logger.warning(f"Пропускаем запись с некорректной датой: {record['date']}")
                    continue
                    
                if record_date >= cutoff_date:
                    filtered_records.append(record)
            
            logger.info(f"После дедупликации: {len(unique_records)} уникальных записей, {len(filtered_records)} после фильтрации")
            
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
            # ИСПРАВЛЕНИЕ: Дополнительная проверка на дубликаты на уровне листа
            unique_records_dict = {}
            for record in records:
                record_id = record.get('id')
                if record_id:
                    if record_id in unique_records_dict:
                        # Если дубликат, берем запись с более новой датой обновления
                        existing_updated = unique_records_dict[record_id].get('updated_at', '')
                        current_updated = record.get('updated_at', '')
                        if current_updated > existing_updated:
                            unique_records_dict[record_id] = record
                    else:
                        unique_records_dict[record_id] = record
                else:
                    # Если нет ID, добавляем как есть (не должно происходить)
                    unique_key = f"no_id_{len(unique_records_dict)}"
                    unique_records_dict[unique_key] = record
            
            # Преобразуем обратно в список
            deduplicated_records = list(unique_records_dict.values())
            logger.info(f"Лист {sheet_name}: было {len(records)} записей, после дедупликации {len(deduplicated_records)}")
            
            df = pd.DataFrame(deduplicated_records)
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
            
            # ИСПРАВЛЕНИЕ: Дедупликация записей по ID для статистики
            unique_records = {}
            for record in records:
                record_id = record.get('id')
                if record_id:
                    if record_id in unique_records:
                        existing_updated = unique_records[record_id].get('updated_at', '')
                        current_updated = record.get('updated_at', '')
                        if current_updated > existing_updated:
                            unique_records[record_id] = record
                    else:
                        unique_records[record_id] = record
            
            # Преобразуем в список уникальных записей
            deduplicated_records = list(unique_records.values())
            logger.info(f"Статистика: было {len(records)} записей, после дедупликации {len(deduplicated_records)}")
            
            df = pd.DataFrame(deduplicated_records)
            
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
