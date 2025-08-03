"""
Система экспорта и резервных копий
"""
import logging
import json
from datetime import datetime
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext
import pandas as pd

from ...config.settings import ADMIN_IDS
from ...utils.config_utils import load_users
from ...database.database_manager import get_all_records, get_payments

logger = logging.getLogger(__name__)

async def export_menu(update: Update, context: CallbackContext):
    """Меню экспорта данных"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Экспорт всех записей", callback_data="export_all_records")],
        [InlineKeyboardButton("💰 Экспорт всех платежей", callback_data="export_all_payments")],
        [InlineKeyboardButton("👥 Экспорт пользователей", callback_data="export_users")],
        [InlineKeyboardButton("📋 Полный экспорт", callback_data="export_full")],
        [InlineKeyboardButton("📅 Экспорт за период", callback_data="export_period")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        "📤 Выберите тип экспорта:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def export_all_records(update: Update, context: CallbackContext):
    """Экспортирует все записи"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        records = get_all_records()
        
        if not records:
            await query.answer("❌ Нет записей для экспорта")
            return
        
        # Создаем DataFrame
        df = pd.DataFrame(records)
        
        # Экспорт в Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Все записи', index=False)
        output.seek(0)
        
        filename = f"all_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await query.message.reply_document(
            document=output,
            filename=filename,
            caption=f"📊 Экспорт всех записей ({len(records)} записей)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="export_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка экспорта записей: {e}")
        await query.answer("❌ Ошибка экспорта")

async def export_all_payments(update: Update, context: CallbackContext):
    """Экспортирует все платежи"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        users = load_users()
        all_payments = []
        
        for uid, user_data in users.items():
            display_name = user_data.get('display_name')
            if not display_name:
                continue
            
            payments = get_payments(display_name)
            if payments:
                for payment in payments:
                    payment_data = {
                        'display_name': display_name,
                        'amount': payment[0],
                        'date_from': payment[1],
                        'date_to': payment[2],
                        'comment': payment[3],
                        'created_at': payment[4],
                        'spreadsheet_id': payment[5] if len(payment) > 5 else '',
                        'sheet_name': payment[6] if len(payment) > 6 else ''
                    }
                    all_payments.append(payment_data)
        
        if not all_payments:
            await query.answer("❌ Нет платежей для экспорта")
            return
        
        # Создаем DataFrame
        df = pd.DataFrame(all_payments)
        
        # Экспорт в Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Все платежи', index=False)
        output.seek(0)
        
        filename = f"all_payments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await query.message.reply_document(
            document=output,
            filename=filename,
            caption=f"💰 Экспорт всех платежей ({len(all_payments)} платежей)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="export_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка экспорта платежей: {e}")
        await query.answer("❌ Ошибка экспорта")

async def export_users_data(update: Update, context: CallbackContext):
    """Экспортирует данные пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        users = load_users()
        
        # Создаем данные для экспорта
        export_data = []
        for uid, user_data in users.items():
            export_data.append({
                'user_id': uid,
                'display_name': user_data.get('display_name', ''),
                'daily_limit': user_data.get('daily_limit', ''),
                'weekly_limit': user_data.get('weekly_limit', ''),
                'category': user_data.get('category', ''),
                'notifications': user_data.get('notifications', True),
                'is_allowed': user_data.get('is_allowed', False),
                'created_at': user_data.get('created_at', ''),
                'last_activity': user_data.get('last_activity', '')
            })
        
        # Экспорт в JSON
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'users_count': len(users),
            'users': export_data
        }
        
        backup_json = json.dumps(backup_data, indent=2, ensure_ascii=False)
        
        buffer = BytesIO(backup_json.encode('utf-8'))
        filename = f"users_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        await query.message.reply_document(
            document=buffer,
            filename=filename,
            caption=f"👥 Экспорт данных пользователей ({len(users)} пользователей)",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="export_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка экспорта пользователей: {e}")
        await query.answer("❌ Ошибка экспорта")

async def export_full_backup(update: Update, context: CallbackContext):
    """Создает полную резервную копию"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        # Собираем все данные
        records = get_all_records()
        users = load_users()
        
        # Собираем все платежи
        all_payments = []
        for uid, user_data in users.items():
            display_name = user_data.get('display_name')
            if display_name:
                payments = get_payments(display_name)
                if payments:
                    for payment in payments:
                        all_payments.append({
                            'display_name': display_name,
                            'amount': payment[0],
                            'date_from': payment[1],
                            'date_to': payment[2],
                            'comment': payment[3],
                            'created_at': payment[4],
                            'spreadsheet_id': payment[5] if len(payment) > 5 else '',
                            'sheet_name': payment[6] if len(payment) > 6 else ''
                        })
        
        # Создаем полный бэкап
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'version': '1.0',
            'statistics': {
                'records_count': len(records),
                'users_count': len(users),
                'payments_count': len(all_payments)
            },
            'records': records,
            'users': users,
            'payments': all_payments
        }
        
        # Создаем Excel файл с несколькими листами
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Лист с записями
            if records:
                df_records = pd.DataFrame(records)
                df_records.to_excel(writer, sheet_name='Записи', index=False)
            
            # Лист с платежами
            if all_payments:
                df_payments = pd.DataFrame(all_payments)
                df_payments.to_excel(writer, sheet_name='Платежи', index=False)
            
            # Лист с пользователями
            users_data = []
            for uid, user_data in users.items():
                users_data.append({
                    'user_id': uid,
                    'display_name': user_data.get('display_name', ''),
                    'daily_limit': user_data.get('daily_limit', ''),
                    'is_allowed': user_data.get('is_allowed', False)
                })
            
            if users_data:
                df_users = pd.DataFrame(users_data)
                df_users.to_excel(writer, sheet_name='Пользователи', index=False)
            
            # Лист со статистикой
            stats_data = [
                ['Показатель', 'Значение'],
                ['Дата создания', datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
                ['Количество записей', len(records)],
                ['Количество пользователей', len(users)],
                ['Количество платежей', len(all_payments)]
            ]
            
            df_stats = pd.DataFrame(stats_data[1:], columns=stats_data[0])
            df_stats.to_excel(writer, sheet_name='Статистика', index=False)
        
        output.seek(0)
        
        filename = f"full_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await query.message.reply_document(
            document=output,
            filename=filename,
            caption=(
                f"💾 <b>Полная резервная копия</b>\n\n"
                f"📊 Записей: {len(records)}\n"
                f"👥 Пользователей: {len(users)}\n"
                f"💰 Платежей: {len(all_payments)}\n"
                f"📅 Создано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            ),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="export_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания полного бэкапа: {e}")
        await query.answer("❌ Ошибка создания бэкапа")

async def schedule_automated_backup(context: CallbackContext):
    """Создает автоматическую резервную копию"""
    try:
        # Получаем данные
        records = get_all_records()
        users = load_users()
        
        # Создаем JSON бэкап
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'type': 'automated',
            'records': records,
            'users': users
        }
        
        backup_json = json.dumps(backup_data, indent=2, ensure_ascii=False)
        
        # Отправляем админам
        filename = f"auto_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        buffer = BytesIO(backup_json.encode('utf-8'))
        
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_document(
                    chat_id=admin_id,
                    document=buffer,
                    filename=filename,
                    caption=f"🤖 Автоматическая резервная копия\n📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                buffer.seek(0)  # Сбрасываем позицию для следующей отправки
            except Exception as e:
                logger.error(f"Ошибка отправки автобэкапа админу {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка создания автоматического бэкапа: {e}")

async def cleanup_old_data(update: Update, context: CallbackContext):
    """Меню очистки старых данных"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Очистить записи старше 1 года", callback_data="cleanup_records_1y")],
        [InlineKeyboardButton("🗑️ Очистить записи старше 6 месяцев", callback_data="cleanup_records_6m")],
        [InlineKeyboardButton("🗑️ Очистить платежи старше 1 года", callback_data="cleanup_payments_1y")],
        [InlineKeyboardButton("🗑️ Очистить неактивных пользователей", callback_data="cleanup_inactive_users")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
    ]
    
    await query.edit_message_text(
        "🧹 Выберите данные для очистки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
