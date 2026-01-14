"""
Обработчики команд администратора
"""

import json
import os
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackContext
from ...config.settings import ADMIN_IDS, logger
from ...utils.config_utils import (
    add_allowed_user, remove_allowed_user, 
    load_allowed_users, update_user_settings,
    set_log_chat, set_report_settings
)
from ...database.database_manager import backup_db_to_dict
from ...utils.config_utils import (
    set_log_chat, set_report_settings,
    add_allowed_user, remove_allowed_user, load_allowed_users,
    load_users, save_users, update_user_settings
)
from ...database.database_manager import backup_db_to_dict


async def set_log_command(update: Update, context: CallbackContext):
    """Устанавливает текущий чат как лог-чат"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    chat_id = update.effective_chat.id
    set_log_chat(chat_id)
    
    await update.message.reply_text(
        f"✅ Ընթացիկ զրույցը սահմանված է որպես գրանցամատյան:\n"
        f"Chat ID: <code>{chat_id}</code>",
        parse_mode="HTML"
    )

async def set_sheet_command(update: Update, context: CallbackContext):
    """Команда для установки Google Sheet - заглушка"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    await update.message.reply_text("🔧 Эта функция будет реализована позже")

async def set_report_command(update: Update, context: CallbackContext):
    """Устанавливает настройки отчетов для чата"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📊 Հաշվետվությունների կարգավորում:\n"
            "Օգտագործեք: <code>/set_report [chat_id] [chat_name]</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        report_chat_id = int(args[0])
        chat_name = ' '.join(args[1:])
        
        settings = {
            'chat_id': report_chat_id,
            'name': chat_name,
            'enabled': True
        }
        
        set_report_settings(report_chat_id, settings)
        
        await update.message.reply_text(
            f"✅ Հաշվետվությունների կարգավորում պահպանված է:\n"
            f"Chat ID: <code>{report_chat_id}</code>\n"
            f"Անունը: {chat_name}",
            parse_mode="HTML"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ chat_id ձևաչափ: Մուտքագրեք թիվ")

async def initialize_sheets_command(update: Update, context: CallbackContext):
    """Команда инициализации Google Sheets - заглушка"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    await update.message.reply_text("🔧 Эта функция будет реализована позже")

async def allow_user_command(update: Update, context: CallbackContext):
    """Добавляет пользователя в список разрешенных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "👥 Օգտագործողին թույլատրելու համար օգտագործեք:\n"
            "<code>/allow_user [user_id]</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        new_user_id = int(args[0])
        add_allowed_user(new_user_id)
        
        # Добавляем пользователя в users.json если его еще нет
        users = load_users()
        user_id_str = str(new_user_id)
        if user_id_str not in users:
            users[user_id_str] = {
                'active_sheet_name': None,
                'name': f"User {new_user_id}",
                'display_name': None
            }
            save_users(users)
        
        await update.message.reply_text(
            f"✅ Օգտագործող ID <code>{new_user_id}</code> ավելացված է թույլատրելի ցուցակում:",
            parse_mode="HTML"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ user_id ձևաչափ: Մուտքագրեք թիվ")

async def disallow_user_command(update: Update, context: CallbackContext):
    """Удаляет пользователя из списка разрешенных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "👥 Օգտագործողին արգելելու համար օգտագործեք:\n"
            "<code>/disallow_user [user_id]</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        user_id_to_remove = int(args[0])
        remove_allowed_user(user_id_to_remove)
        await update.message.reply_text(
            f"✅ Օգտագործող ID <code>{user_id_to_remove}</code> հեռացված է թույլատրելի ցուցակից:",
            parse_mode="HTML"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ user_id ձևաչափ: Մուտքագրեք թիվ")

async def allowed_users_command(update: Update, context: CallbackContext):
    """Показывает список разрешенных пользователей"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    allowed = load_allowed_users()
    users = load_users()
    
    if not allowed:
        await update.message.reply_text("ℹ️ Թույլատրելի օգտագործողներ չկան:")
        return
    
    text = "👥 Թույլատրելի օգտագործողների ցուցակ:\n\n"
    for idx, user_id in enumerate(allowed, 1):
        user_info = users.get(str(user_id), {})
        user_name = user_info.get('name', 'Անհայտ')
        display_name = user_info.get('display_name', 'Չկա')
        text += f"{idx}. ID: <code>{user_id}</code>\n"
        text += f"   👤 Տրված անուն: <b>{display_name}</b>\n"
        text += f"   👤 Telegram անուն: {user_name}\n\n"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def set_user_name_command(update: Update, context: CallbackContext):
    """Назначает отображаемое имя пользователю"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "👤 Օգտագործողին անուն նշանակելու համար օգտագործեք:\n"
            "<code>/set_user_name [user_id] [անուն]</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        target_user_id = int(args[0])
        display_name = ' '.join(args[1:])
        
        update_user_settings(target_user_id, {'display_name': display_name})
        
        await update.message.reply_text(
            f"✅ Օգտագործող ID <code>{target_user_id}</code> սահմանված է նոր անունը: <b>{display_name}</b>",
            parse_mode="HTML"
        )
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ user_id ձևաչափ: Մուտքագրեք թիվ")

async def sync_sheets_command(update: Update, context: CallbackContext):
    """Команда синхронизации с Google Sheets - заглушка"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    await update.message.reply_text("🔧 Эта функция будет реализована позже")

async def my_report_command(update: Update, context: CallbackContext):
    """Команда генерации отчета - заглушка"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    await update.message.reply_text("🔧 Эта функция будет реализована позже")

async def export_command(update: Update, context: CallbackContext):
    """Команда экспорта данных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    try:
        backup_data = backup_db_to_dict()
        
        if not backup_data:
            await update.message.reply_text("❌ Ошибка создания резервной копии.")
            return
        
        # Создаем JSON файл
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        # Отправляем файл
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📤 Տվյալների բազայի резервная копия\n"
                       f"📊 Գրառումներ: {backup_data['stats']['total_records']}\n"
                       f"💰 Ընդհանուր գումար: {backup_data['stats']['total_amount']:,.2f}\n"
                       f"📅 Ստեղծման ամսաթիվ: {backup_data['backup_date']}"
            )
        
        # Удаляем временный файл
        os.remove(filename)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Արտահանման սխալ: {e}")

async def clean_duplicates_command(update: Update, context: CallbackContext):
    """Команда для очистки дублированных записей в базе данных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    try:
        # Импортируем функцию очистки дубликатов
        from ...database.database_manager import remove_duplicate_records
        
        await update.message.reply_text("🔍 Ուսումնասիրում են տվյալների բազայում կրկնվող գրառումները...")
        
        # Выполняем очистку дубликатов
        removed_count = remove_duplicate_records()
        
        if removed_count > 0:
            await update.message.reply_text(
                f"✅ Տվյալների բազայի մաքրումը ավարտված է:\n"
                f"🗑️ Ջնջված կրկնօրինակներ: {removed_count}\n"
                f"📊 Տվյալների պահոցը այժմ ավելի մաքուր է:"
            )
        else:
            await update.message.reply_text(
                f"✅ Տվյալների բազայում կրկնօրինակներ չեն գտնվել:\n"
                f"📊 Տվյալների պահոցը արդեն մաքուր է:"
            )
            
    except Exception as e:
        logger.error(f"Ошибка очистки дубликатов: {e}")
        await update.message.reply_text(f"❌ Կրկնօրինակների մաքրման սխալ: {e}")
