"""
Расширенные настройки пользователей
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ...config.settings import ADMIN_IDS
from ...utils.config_utils import load_users, save_users, get_user_settings, update_user_settings
from ..states.conversation_states import SET_USER_LIMIT, SET_USER_CATEGORY

logger = logging.getLogger(__name__)

async def user_settings_menu(update: Update, context: CallbackContext):
    """Меню настроек пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    users = load_users()
    keyboard = []
    
    for uid, udata in users.items():
        if udata.get('display_name'):
            keyboard.append([InlineKeyboardButton(
                f"⚙️ {udata['display_name']}", 
                callback_data=f"user_settings_{uid}"
            )])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        "⚙️ Выберите пользователя для настройки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_user_settings(update: Update, context: CallbackContext):
    """Показывает настройки конкретного пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    target_user_id = query.data.replace("user_settings_", "")
    users = load_users()
    user_data = users.get(target_user_id, {})
    
    display_name = user_data.get('display_name', 'Неизвестно')
    daily_limit = user_data.get('daily_limit', 'Не установлено')
    category = user_data.get('category', 'Обычный')
    notifications = user_data.get('notifications', True)
    
    settings_text = (
        f"⚙️ <b>Настройки пользователя</b>\n\n"
        f"👤 Имя: {display_name}\n"
        f"💰 Дневной лимит: {daily_limit}\n"
        f"📂 Категория: {category}\n"
        f"🔔 Уведомления: {'Вкл' if notifications else 'Выкл'}\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 Установить лимит", callback_data=f"set_limit_{target_user_id}")],
        [InlineKeyboardButton("📂 Изменить категорию", callback_data=f"set_category_{target_user_id}")],
        [InlineKeyboardButton("🔔 Переключить уведомления", callback_data=f"toggle_notifications_{target_user_id}")],
        [InlineKeyboardButton("🚫 Заблокировать", callback_data=f"block_user_{target_user_id}")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]
    ]
    
    await query.edit_message_text(
        settings_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def set_daily_limit(update: Update, context: CallbackContext):
    """Устанавливает дневной лимит пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    target_user_id = query.data.replace("set_limit_", "")
    context.user_data['target_user_id'] = target_user_id
    
    await query.edit_message_text(
        "💰 Введите дневной лимит расходов (в драмах):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ Отмена", callback_data="user_settings_menu")]
        ])
    )
    
    return SET_USER_LIMIT

async def process_daily_limit(update: Update, context: CallbackContext):
    """Обрабатывает введенный лимит"""
    try:
        limit = float(update.message.text.strip())
        target_user_id = context.user_data.get('target_user_id')
        
        if limit <= 0:
            await update.message.reply_text("❌ Лимит должен быть положительным числом")
            return SET_USER_LIMIT
        
        # Обновляем настройки пользователя
        users = load_users()
        if target_user_id in users:
            users[target_user_id]['daily_limit'] = limit
            save_users(users)
            
            await update.message.reply_text(
                f"✅ Дневной лимит установлен: {limit:,.2f} դրամ",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]
                ])
            )
        else:
            await update.message.reply_text("❌ Пользователь не найден")
            
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text("❌ Введите корректное число")
        return SET_USER_LIMIT

async def toggle_notifications(update: Update, context: CallbackContext):
    """Переключает уведомления пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    target_user_id = query.data.replace("toggle_notifications_", "")
    users = load_users()
    
    if target_user_id in users:
        current_status = users[target_user_id].get('notifications', True)
        users[target_user_id]['notifications'] = not current_status
        save_users(users)
        
        status_text = "включены" if not current_status else "выключены"
        await query.answer(f"Уведомления {status_text}")
        
        # Обновляем отображение
        await show_user_settings(update, context)
    else:
        await query.answer("❌ Пользователь не найден")

async def create_user_backup(update: Update, context: CallbackContext):
    """Создает резервную копию настроек пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    try:
        users = load_users()
        
        # Создаем JSON с настройками
        import json
        from datetime import datetime
        
        backup_data = {
            'timestamp': datetime.now().isoformat(),
            'users': users
        }
        
        backup_json = json.dumps(backup_data, indent=2, ensure_ascii=False)
        
        # Отправляем как файл
        from io import BytesIO
        buffer = BytesIO(backup_json.encode('utf-8'))
        buffer.name = f"users_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        await query.message.reply_document(
            document=buffer,
            caption="💾 Резервная копия настроек пользователей",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания бэкапа: {e}")
        await query.answer("❌ Ошибка создания бэкапа")
