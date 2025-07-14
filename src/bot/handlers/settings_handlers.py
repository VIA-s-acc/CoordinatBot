"""
Обработчики настроек системы
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ...config.settings import ADMIN_IDS
from ...utils.localization import (
    _, get_user_language, set_user_language, 
    get_available_languages, add_custom_translation
)
from ...utils.config_utils import get_user_settings, update_user_settings
from ..states.conversation_states import ADD_TRANSLATION_KEY, ADD_TRANSLATION_TEXT

logger = logging.getLogger(__name__)

async def settings_menu(update: Update, context: CallbackContext):
    """Главное меню настроек"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    
    # Получаем язык пользователя
    user_language = get_user_language(user_id)
    
    keyboard = [
        [InlineKeyboardButton(_("settings.language", user_id), callback_data="language_menu")],
        [InlineKeyboardButton(_("settings.notifications", user_id), callback_data="notification_settings")],
    ]
    
    # Дополнительные настройки для админов
    if user_id in ADMIN_IDS:
        keyboard.extend([
            [InlineKeyboardButton(_("settings.users", user_id), callback_data="user_settings_menu")],
            [InlineKeyboardButton(_("settings.backup", user_id), callback_data="backup_menu")],
            [InlineKeyboardButton("🔄 Сортировать лист по дате", callback_data="sort_sheet_by_date")],
            [InlineKeyboardButton(_("settings.translation_management", user_id), callback_data="translation_management")],
            [InlineKeyboardButton(_("settings.system_info", user_id), callback_data="system_info")]
        ])
    
    keyboard.append([InlineKeyboardButton(_("menu.back", user_id), callback_data="back_to_menu")])
    
    await query.edit_message_text(
        _("settings.main_menu", user_id),
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def language_menu(update: Update, context: CallbackContext):
    """Меню выбора языка"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    
    current_language = get_user_language(user_id)
    available_languages = get_available_languages()
    
    keyboard = []
    for lang_code, lang_name in available_languages.items():
        emoji = "✅" if lang_code == current_language else ""
        keyboard.append([
            InlineKeyboardButton(
                f"{emoji} {lang_name}", 
                callback_data=f"set_language_{lang_code}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(_("menu.back", user_id), callback_data="settings_menu")])
    
    await query.edit_message_text(
        f"{_('settings.current_language', user_id)}\n\n{_('settings.select_language', user_id)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def set_language(update: Update, context: CallbackContext):
    """Устанавливает язык пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    
    # Извлекаем код языка из callback_data
    language_code = query.data.replace("set_language_", "")
    
    # Устанавливаем язык
    set_user_language(user_id, language_code)
    
    # Получаем название языка
    available_languages = get_available_languages()
    language_name = available_languages.get(language_code, language_code)
    
    await query.edit_message_text(
        _("settings.language_changed", user_id),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(_("menu.back", user_id), callback_data="settings_menu")]
        ])
    )

async def notification_settings(update: Update, context: CallbackContext):
    """Настройки уведомлений"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    
    # Получаем текущие настройки
    settings = get_user_settings(user_id)
    notifications_enabled = settings.get('notifications', True)
    debt_notifications = settings.get('debt_notifications', True)
    limit_notifications = settings.get('limit_notifications', True)
    
    keyboard = [
        [InlineKeyboardButton(
            f"🔔 Все уведомления: {'Вкл' if notifications_enabled else 'Выкл'}",
            callback_data="toggle_notifications"
        )],
        [InlineKeyboardButton(
            f"💰 Уведомления о долгах: {'Вкл' if debt_notifications else 'Выкл'}",
            callback_data="toggle_debt_notifications"
        )],
        [InlineKeyboardButton(
            f"⚠️ Уведомления о лимитах: {'Вкл' if limit_notifications else 'Выкл'}",
            callback_data="toggle_limit_notifications"
        )],
        [InlineKeyboardButton(_("menu.back", user_id), callback_data="settings_menu")]
    ]
    
    await query.edit_message_text(
        f"🔔 <b>Настройки уведомлений</b>\n\n"
        f"Выберите, какие уведомления вы хотите получать:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def toggle_notifications(update: Update, context: CallbackContext):
    """Переключает уведомления"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    await query.answer()
    
    # Определяем тип уведомления
    callback_data = query.data
    
    settings = get_user_settings(user_id)
    
    if callback_data == "toggle_notifications":
        current = settings.get('notifications', True)
        update_user_settings(user_id, {'notifications': not current})
    elif callback_data == "toggle_debt_notifications":
        current = settings.get('debt_notifications', True)
        update_user_settings(user_id, {'debt_notifications': not current})
    elif callback_data == "toggle_limit_notifications":
        current = settings.get('limit_notifications', True)
        update_user_settings(user_id, {'limit_notifications': not current})
    
    # Обновляем меню
    await notification_settings(update, context)

async def system_info(update: Update, context: CallbackContext):
    """Показывает системную информацию"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    try:
        from ...utils.config_utils import load_users
        from ...database.database_manager import get_all_records
        from datetime import datetime
        import sys
        import os
        
        # Собираем статистику
        users = load_users()
        records = get_all_records()
        
        # Статистика по языкам пользователей
        language_stats = {}
        for uid, user_data in users.items():
            lang = user_data.get('language', 'hy')
            language_stats[lang] = language_stats.get(lang, 0) + 1
        
        # Системная информация
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        info_text = (
            f"🖥️ <b>Системная информация</b>\n"
            f"🕐 Время: {current_time}\n\n"
            f"👥 <b>Пользователи:</b> {len(users)}\n"
            f"📊 <b>Записи:</b> {len(records)}\n"
            f"🐍 <b>Python:</b> {sys.version.split()[0]}\n"
            f"💻 <b>Платформа:</b> {os.name}\n\n"
            f"<b>Статистика языков:</b>\n"
        )
        
        for lang_code, count in language_stats.items():
            lang_names = {'ru': 'Русский', 'hy': 'Հայերեն', 'en': 'English'}
            lang_name = lang_names.get(lang_code, lang_code)
            info_text += f"  {lang_name}: {count}\n"
        
        await query.edit_message_text(
            info_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Обновить", callback_data="system_info")],
                [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Ошибка получения системной информации: {e}")
        await query.edit_message_text(
            f"❌ Ошибка получения информации: {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
            ])
        )

async def sort_sheet_by_date_handler(update: Update, context: CallbackContext):
    """Обработчик для сортировки листа по дате"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    try:
        from ...utils.config_utils import get_user_settings
        from ...google_integration.sheets_manager import sort_sheet_by_date
        
        user_settings = get_user_settings(user_id)
        spreadsheet_id = user_settings.get('active_spreadsheet_id')
        sheet_name = user_settings.get('active_sheet_name')
        
        if not spreadsheet_id or not sheet_name:
            await query.edit_message_text(
                "❌ Նախ պետք է ընտրել աղյուսակը և թերթիկը:\n"
                "Գնացեք հիմնական ցանկ → Ընտրել աղյուսակ",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
                ])
            )
            return
        
        await query.edit_message_text(
            f"🔄 Сортировка листа по дате...\n\n"
            f"📊 Աղյուսակ: <b>{spreadsheet_id}</b>\n"
            f"📋 Թերթիկ: <b>{sheet_name}</b>\n\n"
            f"⏳ Пожалуйста, подождите...",
            parse_mode="HTML"
        )
        
        # Выполняем сортировку
        success = sort_sheet_by_date(spreadsheet_id, sheet_name)
        
        if success:
            await query.edit_message_text(
                f"✅ <b>Сортировка завершена успешно!</b>\n\n"
                f"📊 Աղյուսակ: <b>{spreadsheet_id}</b>\n"
                f"📋 Թերթիկ: <b>{sheet_name}</b>\n\n"
                f"🎯 Все записи отсортированы по дате\n"
                f"📅 Более старые записи находятся вверху",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Повторить сортировку", callback_data="sort_sheet_by_date")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
                ])
            )
        else:
            await query.edit_message_text(
                f"❌ <b>Ошибка сортировки</b>\n\n"
                f"Не удалось отсортировать лист. Возможные причины:\n"
                f"• Нет доступа к листу\n"
                f"• Лист не найден\n"
                f"• Проблемы с подключением\n\n"
                f"Попробуйте позже.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Повторить", callback_data="sort_sheet_by_date")],
                    [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
                ])
            )
        
    except Exception as e:
        logger.error(f"Ошибка сортировки листа: {e}")
        await query.edit_message_text(
            f"❌ <b>Критическая ошибка</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
            ])
        )
