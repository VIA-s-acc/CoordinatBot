"""
Обработчики кнопок и callback query
"""
import os
import json
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ..keyboards.inline_keyboards import (
    create_main_menu, create_workers_menu, create_payment_menu, 
    create_back_to_menu_keyboard, create_add_record_menu,
    create_add_record_sheet_selection
)
from ..states.conversation_states import DIRECTION, SUPPLIER_MANUAL
from ...utils.config_utils import is_user_allowed, get_user_settings, update_user_settings
from ...utils.localization import _
from ...database.database_manager import get_db_stats
from ...utils.sheets_cache import get_cached_sheets_info, get_cached_spreadsheets
from ...config.settings import ADMIN_IDS

from .payment_handlers import pay_menu_handler, pay_user_handler, send_payment_report
from .settings_handlers import (
    settings_menu, language_menu, set_language, notification_settings,
    toggle_notifications, system_info
)

logger = logging.getLogger(__name__)

def safe_parse_date(date_str: str, default_date: str = '2000-01-01') -> datetime:
    """Безопасный парсинг даты с обработкой пустых значений"""
    try:
        if not date_str or date_str.strip() == '':
            return datetime.fromisoformat(default_date)
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return datetime.fromisoformat(default_date)
async def show_sheet_selection_for_add_record(update: Update, context: CallbackContext, record_type: str):
    """Показывает выбор листа для добавления записи"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    logger.info(f"show_sheet_selection_for_add_record вызвана для пользователя {user_id}, record_type: {record_type}")
    
    # Получаем настройки пользователя
    user_settings = get_user_settings(user_id)
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    
    if not spreadsheet_id:
        logger.warning(f"У пользователя {user_id} не настроен активный spreadsheet")
        # Используем правильную кнопку возврата в главное меню
        keyboard = [[InlineKeyboardButton("🏠 Գլխավոր Մենյու", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Նախ պետք է ընտրել աղյուսակը",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        logger.info(f"Получаем информацию о листах для spreadsheet_id: {spreadsheet_id}")
        sheets_info, spreadsheet_title = get_cached_sheets_info(spreadsheet_id)
        
        if not sheets_info:
            logger.warning(f"Нет листов в spreadsheet {spreadsheet_id}")
            # Используем правильную кнопку возврата в главное меню
            keyboard = [[InlineKeyboardButton("🏠 Գլխավոր Մենյու", callback_data="back_to_menu")]]
            await query.edit_message_text(
                "❌ Աղյուսակում թերթիկներ չկան",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        logger.info(f"Создаем клавиатуру для {len(sheets_info)} листов")
        keyboard = create_add_record_sheet_selection(sheets_info, record_type)
        
        record_text = "գրառում" if record_type == "record" else "բացթողում"
        logger.info(f"Отправляем сообщение с клавиатурой для выбора листа")
        await query.edit_message_text(
            f"📋 Ընտրեք թերթիկը {record_text}-ի համար:\n\n"
            f"📊 Աղյուսակ: <b>{spreadsheet_title}</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        logger.info(f"Сообщение с клавиатурой успешно отправлено")
        
    except Exception as e:
        logger.error(f"Ошибка при создании выбора листов: {e}")
        logger.error(f"Полная ошибка: {e}", exc_info=True)
        # Используем правильную кнопку возврата в главное меню
        keyboard = [[InlineKeyboardButton("🏠 Գլխավոր Մենյու", callback_data="back_to_menu")]]
        await query.edit_message_text(
            f"❌ Շխալ թերթիկների ցանկը ստանալիս: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def button_handler(update: Update, context: CallbackContext):
    """Основной обработчик кнопок"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_user_allowed(user_id):
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    await query.answer()
    
    data = query.data
    logger.info(f"Обработка callback: {data} от пользователя {user_id}")
    
    # ДЕБАГ: Проверяем специфичные callback'и
    if data.startswith("confirm_delete_"):
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: callback {data} попал в button_handler вместо confirm_delete handler!")
        await query.edit_message_text(
            f"❌ Техническая ошибка\n\n"
            f"Callback {data} попал в неправильный обработчик.\n"
            f"Обратитесь к администратору.",
            reply_markup=create_back_to_menu_keyboard()
        )
        return
    
    if data.startswith("cancel_edit_"):
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: callback {data} попал в button_handler вместо cancel_edit handler!")
        await query.edit_message_text(
            f"❌ Техническая ошибка\n\n"
            f"Callback {data} попал в неправильный обработчик.\n"
            f"Обратитесь к администратору.",
            reply_markup=create_back_to_menu_keyboard()
        )
        return
    
    # ДЕБАГ: Проверяем, не должен ли этот callback обрабатываться ConversationHandler'ом
    if data.startswith(("add_record_sheet_", "add_skip_sheet_")):
        logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: callback {data} попал в button_handler вместо ConversationHandler!")
        await query.edit_message_text(
            f"❌ Техническая ошибка\n\n"
            f"Callback {data} попал в неправильный обработчик.\n"
            f"Обратитесь к администратору.",
            reply_markup=create_back_to_menu_keyboard()
        )
        return
    
    # Главное меню - завершаем любой активный ConversationHandler
    if data == "back_to_menu" or data == "main_menu":
        await query.edit_message_text(
            "📋 Հիմնական ընտրացանկ:",
            reply_markup=create_main_menu(user_id)
        )
        return ConversationHandler.END
    
    # Меню добавления записи
    elif data == "add_record_menu":
        await query.edit_message_text(
            "Ընտրեք գործողությունը՝",
            reply_markup=create_add_record_menu()
        )
    
    # Обработка выбора листа для добавления записи - УДАЛЕНО, теперь обрабатывается ConversationHandler
    # elif data == "add_record_select_sheet":
    #     logger.info(f"Вызываем show_sheet_selection_for_add_record для record")
    #     await show_sheet_selection_for_add_record(update, context, "record")
    
    elif data == "add_skip_record_select_sheet":
        logger.info(f"Вызываем show_sheet_selection_for_add_record для skip")
        await show_sheet_selection_for_add_record(update, context, "skip")
    

    
    # Статус
    elif data == "show_status" or data == "status":
        await show_status(update, context)
        return

    # Статистика
    elif data == "show_stats" or data == "stats":
        await show_stats(update, context)
        return
    
    # Меню работников (только для админов)
    elif data == "workers_menu" or data == "pay_menu":
        if user_id in ADMIN_IDS:
            await query.edit_message_text(
                "👥 Ընտրեք աշխատակցին:",
                reply_markup=create_workers_menu()
            )
        else:
            await query.edit_message_text("❌ Մուտքն արգելված է")
    
    # Обработка работников
    elif data.startswith("pay_user_"):
        display_name = data.replace("pay_user_", "")
        await query.edit_message_text(
            f"👤 Աշխատակից: {display_name}",
            reply_markup=create_payment_menu(display_name)
        )
    
    # Выбор таблицы
    elif data == "select_spreadsheet":
        await select_spreadsheet_menu(update, context)
    
    elif data.startswith("spreadsheet_"):
        await select_spreadsheet(update, context)
    
    elif data.startswith("final_sheet_"):
        await select_final_sheet(update, context)
    
    # Меню выбора листа
    elif data == "select_sheet_menu" or data == "select_sheet":
        await select_sheet_menu(update, context)
    
    elif data.startswith("sheet_"):
        await select_sheet(update, context)
    
    # Обработка выбора поставщика
    elif data == "use_my_name":
        return await use_my_name(update, context)
    
    elif data == "use_firm_name":
        return await use_firm_name(update, context)
    
    elif data == "manual_input":
        return await manual_input(update, context)
    
    # Редактирование записей
    elif data.startswith("edit_"):
        from .edit_handlers import handle_edit_button
        return await handle_edit_button(update, context)
    
    elif data.startswith("delete_"):
        from .edit_handlers import handle_delete_button
        return await handle_delete_button(update, context)
    
    # Генерация отчетов
    elif data.startswith("generate_report_"):
        display_name = data.replace("generate_report_", "")
        await generate_user_report(update, context, display_name)
    
    # Платежи
    elif data == "pay_menu" and user_id in ADMIN_IDS:
        await pay_menu_handler(update, context)
        return
    
    elif data.startswith("pay_user_") and user_id in ADMIN_IDS:
        await pay_user_handler(update, context)
        return
        
    elif data.startswith("get_payment_report_") and user_id in ADMIN_IDS:
        display_name = data.replace("get_payment_report_", "")
        await send_payment_report(update, context, display_name)
        return
    
    # Просмотр платежей для обычных пользователей
    elif data == "my_payments":
        await show_my_payments(update, context)
        return
    
    # Настройки
    elif data == "settings_menu":
        await settings_menu(update, context)
        return
    
    elif data == "language_menu":
        await language_menu(update, context)
        return
    
    elif data.startswith("set_language_"):
        await set_language(update, context)
        return
    
    elif data == "notification_settings":
        await notification_settings(update, context)
        return
    
    elif data in ["toggle_notifications", "toggle_debt_notifications", "toggle_limit_notifications"]:
        await toggle_notifications(update, context)
        return
    
    elif data == "translation_management":
        from .translation_handlers import translation_management
        await translation_management(update, context)
    
    elif data == "list_translations":
        from .translation_handlers import list_translations
        await list_translations(update, context)
    
    elif data == "reload_translations":
        from .translation_handlers import reload_translations
        await reload_translations(update, context)
    
    elif data == "system_info":
        await system_info(update, context)
        return
    
    elif data == "sort_sheet_by_date":
        from .settings_handlers import sort_sheet_by_date_handler
        await sort_sheet_by_date_handler(update, context)
        return
    
    elif data == "analytics_menu":
        await analytics_menu(update, context)
        return
    
    elif data == "user_settings_menu":
        await user_settings_menu(update, context)
        return
    
    elif data == "users_management_menu":
        await user_settings_menu(update, context)
        return
    
    elif data == "backup_menu":
        await backup_menu(update, context)
        return
    
    elif data == "add_language":
        await add_language_menu(update, context)
        return
    
    # Обработчики для резервного копирования
    elif data == "create_backup":
        await create_backup(update, context)
        return
    
    elif data == "backup_list":
        await backup_list(update, context)
        return
    
    elif data == "restore_backup":
        await restore_backup(update, context)
        return
    
    elif data == "cleanup_backups":
        await cleanup_backups(update, context)
        return
    
    # Обработчики детальной очистки резервных копий
    elif data == "cleanup_30_days":
        await cleanup_backups_by_age(update, context, 30)
        return
    
    elif data == "cleanup_keep_3":
        await cleanup_backups_by_count(update, context, 3)
        return
    
    elif data == "cleanup_keep_5":
        await cleanup_backups_by_count(update, context, 5)
        return
    
    elif data == "cleanup_keep_10":
        await cleanup_backups_by_count(update, context, 10)
        return
    
    # Обработчики для управления пользователями
    elif data == "user_list":
        await user_list(update, context)
        return
    
    elif data == "add_user":
        await add_user(update, context)
        return
    
    elif data == "user_permissions":
        await user_permissions_menu(update, context)
        return
    
    elif data == "user_stats":
        await user_stats_menu(update, context)
        return
    
    # Дополнительные обработчики для подменю
    elif data == "add_admin":
        await add_admin_handler(update, context)
        return
    
    elif data == "remove_admin":
        await remove_admin_handler(update, context)
        return
    
    elif data == "show_analytics":
        await show_analytics_handler(update, context)
        return
    
    elif data.startswith("select_backup_"):
        await select_backup_handler(update, context)
        return
    
    elif data.startswith("confirm_restore_"):
        await confirm_restore_handler(update, context)
        return
    
    elif data == "confirm_cleanup":
        await confirm_cleanup_handler(update, context)
        return
    
    elif data == "export_analytics":
        await export_analytics_handler(update, context)
        return
    
    # Обработчики для подменю аналитики
    elif data == "general_analytics":
        await general_analytics_handler(update, context)
        return
    
    elif data == "user_analytics":
        await user_analytics_handler(update, context)
        return
    
    elif data == "financial_analytics":
        await financial_analytics_handler(update, context)
        return
    
    elif data == "period_analytics":
        await period_analytics_handler(update, context)
        return
    
    # Обработчики экспорта аналитики
    elif data == "export_user_analytics":
        await export_user_analytics_handler(update, context)
        return
    
    elif data == "export_financial_analytics":
        await export_financial_analytics_handler(update, context)
        return
    
    elif data == "export_period_analytics":
        await export_period_analytics_handler(update, context)
        return
    
    elif data == "export_general_analytics":
        await export_general_analytics_handler(update, context)
        return
    
    # Обработчики кеша
    elif data == "cache_management":
        from .cache_handlers import cache_management_menu
        await cache_management_menu(update, context)
    
    elif data == "cache_stats":
        from .cache_handlers import show_cache_stats
        await show_cache_stats(update, context)
    
    elif data == "refresh_spreadsheets_cache":
        from .cache_handlers import refresh_spreadsheets_cache
        await refresh_spreadsheets_cache(update, context)
    
    elif data == "clear_all_cache":
        from .cache_handlers import clear_cache
        await clear_cache(update, context)
    
    # Обработчики управления пользователями
    elif data == "add_user_by_id":
        await add_user_by_id_handler(update, context)
    
    elif data == "show_unauthorized_users":
        await show_unauthorized_users_handler(update, context)
    
    elif data == "show_authorized_users":
        await show_authorized_users_handler(update, context)
    
    elif data == "add_permissions":
        await add_permissions_handler(update, context)
    
    elif data == "remove_permissions":
        await remove_permissions_handler(update, context)
    
    elif data.startswith("authorize_user_"):
        await authorize_user_handler(update, context)
    
    elif data.startswith("revoke_user_"):
        await revoke_user_handler(update, context)
    
    # Обработчик для user_management
    elif data == "user_management":
        await user_settings_menu(update, context)
        return
    
    # Обработчик для отмены добавления пользователя
    elif data == "cancel_add_user":
        await cancel_add_user_handler(update, context)
        return
    
    else:
        logger.warning(f"Необработанный callback: {data}")
        # Дополнительная диагностика для специфичных callback'ов
        if data.startswith("confirm_delete_"):
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: confirm_delete callback {data} попал в button_handler!")
        elif data.startswith("cancel_edit_"):
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА: cancel_edit callback {data} попал в button_handler!")
        
        # Проверяем, не является ли это callback'ом для ConversationHandler
        if data.startswith(("add_record_sheet_", "add_skip_sheet_")):
            logger.error(f"ОШИБКА: callback {data} должен обрабатываться ConversationHandler, но попал в button_handler!")
            await query.edit_message_text(
                "❌ Сհալ: callback не обрабатывается правильно\n"
                "Попробуйте снова или обратитесь к администратору",
                reply_markup=create_back_to_menu_keyboard()
            )
        # Callback'и add_payment_ обрабатываются ConversationHandler'ом
        # Для add_payment_ callback'ов не логируем, они обрабатываются в ConversationHandler

async def show_status(update: Update, context: CallbackContext):
    """Показывает статус бота"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_user_allowed(user_id):
        return
    
    user_settings = get_user_settings(user_id)
    
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    sheet_name = user_settings.get('active_sheet_name')
    
    status_text = "📊 Ընթացիկ կարգավիճակ:\n\n"
    
    if spreadsheet_id:
        status_text += f"✅ Միացված աղյուսակ: <code>{spreadsheet_id}</code>\n"
        if sheet_name:
            status_text += f"📋 Ակտիվ թերթիկ: <code>{sheet_name}</code>\n"
        else:
            status_text += "⚠️ Թերթիկը չի ընտրվել\n"
    else:
        status_text += "❌ Աղյուսակը չի միացված\n"
    
    display_name = user_settings.get('display_name')
    if display_name:
        status_text += f"👤 Ձեր անունը: <b>{display_name}</b>\n"
    else:
        status_text += "👤 Ձեր անունը: <b>Սահմանված չէ</b>\n"
    
    status_text += "\n🤖 Բոտը աշխատում է\n"
    status_text += "📊 Տվյալների բազայի կապը՝ ակտիվ\n"
    status_text += "🔗 Google Sheets կապը՝ ակտիվ\n"
    
    await query.edit_message_text(
        status_text, 
        parse_mode="HTML",
        reply_markup=create_back_to_menu_keyboard()
    )

async def show_stats(update: Update, context: CallbackContext):
    """Показывает статистику"""
    query = update.callback_query
    
    stats = get_db_stats()
    if stats:
        stats_text = (
            f"📈 Վիճակագրություն:\n\n"
            f"📝 Ընդհանուր գրառումներ: {stats['total_records']}\n"
            f"💰 Ընդհանուր գումար: {stats['total_amount']:,.2f} դրամ\n"
            f"📅 Վերջին 30 օրում: {stats.get('recent_records', 0)} գրառում"
        )
    else:
        stats_text = "❌ Վիճակագրություն ստանալու սխալ:"
    
    await query.edit_message_text(
        stats_text,
        reply_markup=create_back_to_menu_keyboard()
    )

async def select_spreadsheet_menu(update: Update, context: CallbackContext):
    """Показывает меню выбора таблицы"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        spreadsheets = get_cached_spreadsheets()
        
        if not spreadsheets:
            await query.edit_message_text(
                "❌ Доступных таблиц не найдено",
                reply_markup=create_back_to_menu_keyboard()
            )
            return
        
        keyboard = []
        for spreadsheet in spreadsheets[:10]:  # Показываем только первые 10
            title = spreadsheet.get('name', 'Без названия')[:30]
            keyboard.append([InlineKeyboardButton(
                f"📊 {title}", 
                callback_data=f"spreadsheet_{spreadsheet['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton(_("menu.back" , user_id), callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "📊 Ընտրեք աղյուսակը:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Շխալ աղյուսակների ցանկը ստանալիս: {e}",
            reply_markup=create_back_to_menu_keyboard()
        )

async def select_spreadsheet(update: Update, context: CallbackContext):
    """Выбирает таблицу"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    spreadsheet_id = query.data.replace("spreadsheet_", "")
    
    try:
        sheets_info, spreadsheet_title = get_cached_sheets_info(spreadsheet_id)
        
        if not sheets_info:
            await query.edit_message_text(
                "❌ Հնարավոր չէ մուտք գործել աղյուսակ",
                reply_markup=create_back_to_menu_keyboard()
            )
            return
        
        # Сохраняем выбранную таблицу
        update_user_settings(user_id, {'active_spreadsheet_id': spreadsheet_id})
        
        keyboard = []
        for sheet in sheets_info:
            keyboard.append([InlineKeyboardButton(
                f"📋 {sheet['title']}", 
                callback_data=f"final_sheet_{sheet['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton(_("menu.back" , user_id), callback_data="select_spreadsheet")])
        
        await query.edit_message_text(
            f"✅ Ընտրված աղյուսակ: <b>{spreadsheet_title}</b>\n\n"
            f"📋 Ընտրեք թերթիկը:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Շխալ աղյուսակին միանալիս: {e}",
            reply_markup=create_back_to_menu_keyboard()
        )

async def select_final_sheet(update: Update, context: CallbackContext):
    """Окончательно выбирает лист"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    sheet_name = query.data.replace("final_sheet_", "")
    
    # Сохраняем выбранный лист
    update_user_settings(user_id, {'active_sheet_name': sheet_name})
    
    await query.edit_message_text(
        f"✅ Ընտրված թերթիկ: <b>{sheet_name}</b>\n\n"
        f"Այժմ կարող եք գրառումներ ավելացնել:",
        parse_mode="HTML",
        reply_markup=create_main_menu(user_id)
    )

async def select_sheet_menu(update: Update, context: CallbackContext):
    """Показывает меню выбора листа"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    user_settings = get_user_settings(user_id)
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    
    if not spreadsheet_id:
        await query.edit_message_text(
            "❌ Նախ պետք է ընտրել աղյուսակը",
            reply_markup=create_back_to_menu_keyboard()
        )
        return
    
    try:
        sheets_info, spreadsheet_title = get_cached_sheets_info(spreadsheet_id)
        
        if not sheets_info:
            await query.edit_message_text(
                "❌ Աղյուսակում թերթիկներ չկան",
                reply_markup=create_back_to_menu_keyboard()
            )
            return
        
        keyboard = []
        for sheet in sheets_info:
            keyboard.append([InlineKeyboardButton(
                f"📋 {sheet['title']}", 
                callback_data=f"sheet_{sheet['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton(_("menu.back" , user_id), callback_data="back_to_menu")])
        
        await query.edit_message_text(
            f"📋 Ընտրեք թերթիկ <b>{spreadsheet_title}</b> աղյուսակից:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Շխալ թերթիկների ցանկը ստանալու ժամանակ: {e}",
            reply_markup=create_back_to_menu_keyboard()
        )

async def select_sheet(update: Update, context: CallbackContext):
    """Выбирает лист"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    sheet_name = query.data.replace("sheet_", "")
    
    # Сохраняем выбранный лист
    update_user_settings(user_id, {'active_sheet_name': sheet_name})
    
    await query.edit_message_text(
        f"✅ Ընտրված թերթիկ: <b>{sheet_name}</b>\n\n"
        f"Այժմ կարող եք գրառումներ ավելացնել:",
        parse_mode="HTML",
        reply_markup=create_main_menu(user_id)
    )

# Обработчики выбора поставщика
async def use_my_name(update: Update, context: CallbackContext):
    """Использовать имя пользователя как поставщика"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    user_settings = get_user_settings(user_id)
    display_name = user_settings.get('display_name')
    
    if not display_name:
        await query.edit_message_text("❌ Ձեր անունը չի սահմանված: Օգտագործվելու է Ֆիրմայի անունը:")
        display_name = "Ֆ"
    
    context.user_data['record']['supplier'] = display_name
    
    await query.edit_message_text(
        f"✅ Մատակարար: {display_name}\n\n"
        f"🧭 Մուտքագրեք <b>ուղղությունը</b>:",
        parse_mode="HTML"
    )
    
    return DIRECTION

async def use_firm_name(update: Update, context: CallbackContext):
    """Использовать имя фирмы как поставщика"""
    query = update.callback_query
    
    context.user_data['record']['supplier'] = "Ֆ"
    
    await query.edit_message_text(
        f"✅ Մատակարար: Ֆ\n\n"
        f"🧭 Մուտքագրեք <b>ուղղությունը</b>:",
        parse_mode="HTML"
    )
    
    return DIRECTION

async def manual_input(update: Update, context: CallbackContext):
    """Ручной ввод поставщика"""
    query = update.callback_query
    
    await query.edit_message_text("🏪 Մուտքագրեք մատակարարին:")
    
    return SUPPLIER_MANUAL

async def generate_user_report(update: Update, context: CallbackContext, display_name: str):
    """Генерирует отчет для пользователя"""
    query = update.callback_query
    
    try:
        from ...database.database_manager import get_all_records
        from openpyxl import Workbook
        from io import BytesIO
        from datetime import datetime
        
        # Получаем все записи пользователя
        all_records = get_all_records()
        user_records = [record for record in all_records if record.get('supplier') == display_name]
        
        if not user_records:
            await query.edit_message_text(
                f"📊 {display_name}-ի համար գրառումներ չեն գտնվել:",
                reply_markup=create_back_to_menu_keyboard()
            )
            return
        
        # Создаем Excel файл
        wb = Workbook()
        ws = wb.active
        ws.title = f"Отчет {display_name}"
        
        # Заголовки
        headers = ['ID', 'Ամսաթիվ', 'Մատակարար', 'Ուղղություն', 'Նկարագրություն', 'Գումար', 'Թերթիկ']
        ws.append(headers)
        
        # Данные
        total_amount = 0
        for record in user_records:
            ws.append([
                record.get('id', ''),
                record.get('date', ''),
                record.get('supplier', ''),
                record.get('direction', ''),
                record.get('description', ''),
                record.get('amount', 0),
                record.get('sheet_name', '')
            ])
            total_amount += record.get('amount', 0)
        
        # Добавляем строку итога
        ws.append(['', '', '', '', 'Ընդհանուր:', total_amount, ''])
        
        # Сохраняем в память
        file_buffer = BytesIO()
        wb.save(file_buffer)
        file_buffer.seek(0)
        
        # Отправляем файл
        filename = f"report_{display_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        await query.message.reply_document(
            document=file_buffer,
            filename=filename,
            caption=f"📊 Հաշվետվություն {display_name}-ի համար\n"
                   f"📝 Գրառումներ: {len(user_records)}\n"
                   f"💰 Ընդհանուր գումար: {total_amount:,.2f} դրամ\n"
                   f"📅 Ստեղծվել է: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        
        await query.edit_message_text(
            f"✅ Հաշվետվությունը ուղարկված է {display_name}-ի համար",
            reply_markup=create_back_to_menu_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка создания отчета для {display_name}: {e}")
        await query.edit_message_text(
            f"❌ Հաշվետվություն ստեղծելու սխալ: {e}",
            reply_markup=create_back_to_menu_keyboard()
        )

async def send_payment_report(update: Update, context: CallbackContext, display_name: str):
    """Отправляет отчет о платежах"""
    # Импортируем функцию из payment_handlers
    from .payment_handlers import send_payment_report as payment_report_func
    await payment_report_func(update, context, display_name)

async def show_my_payments(update: Update, context: CallbackContext):
    """Показывает платежи текущего пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    try:
        # Получаем настройки пользователя
        from ...utils.config_utils import get_user_settings
        user_settings = get_user_settings(user_id)
        display_name = user_settings.get('display_name')
        
        if not display_name:
            await query.edit_message_text(
                "❌ Ձեր անունը չի սահմանված: Խնդրում ենք դիմել ադմինիստրատորին:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(_("menu.back" , user_id), callback_data="back_to_menu")]
                ])
            )
            return
        
        # Импортируем функцию из payment_handlers
        from .payment_handlers import send_payment_report
        await send_payment_report(update, context, display_name)
        
    except Exception as e:
        logger.error(f"Ошибка получения платежей пользователя {user_id}: {e}")
        await query.edit_message_text(
            f"❌ Վճարումների տեղեկությունները ստանալու սխալ: Փորձեք նորից:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_("menu.back" , user_id), callback_data="back_to_menu")]
            ])
        )

async def analytics_menu(update: Update, context: CallbackContext):
    """Меню аналитики"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📊 Общая статистика", callback_data="general_analytics")],
        [InlineKeyboardButton("👥 Статистика пользователей", callback_data="user_analytics")],
        [InlineKeyboardButton("💰 Финансовая аналитика", callback_data="financial_analytics")],
        [InlineKeyboardButton("📈 Отчеты по периодам", callback_data="period_analytics")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        "📊 <b>Անալիտիկա</b>\n\n"
        "Ընտրեք անալիտիկայի տեսակը:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def user_settings_menu(update: Update, context: CallbackContext):
    """Меню настроек пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("👥 Սписок пользователей", callback_data="user_list")],
        [InlineKeyboardButton("➕ Добавить пользователя", callback_data="add_user")],
        [InlineKeyboardButton("🔧 Настройки доступа", callback_data="user_permissions")],
        [InlineKeyboardButton("📊 Статистика пользователей", callback_data="user_stats")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
    ]
    
    await query.edit_message_text(
        "👥 <b>Օգտագործողների կառավարում</b>\n\n"
        "Ընտրեք գործողությունը:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def backup_menu(update: Update, context: CallbackContext):
    """Меню резервного копирования"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("notifications.access_denied", user_id))
        return
    
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(_("backup.create", user_id), callback_data="create_backup")],
        [InlineKeyboardButton(_("backup.list", user_id), callback_data="backup_list")],
        [InlineKeyboardButton(_("backup.restore", user_id), callback_data="restore_backup")],
        [InlineKeyboardButton(_("backup.cleanup", user_id), callback_data="cleanup_backups")],
        [InlineKeyboardButton(_("menu.back", user_id), callback_data="settings_menu")]
    ]
    
    await query.edit_message_text(
        f"💾 <b>{_('backup.main_menu', user_id)}</b>\n\n"
        f"{_('backup.choose_action', user_id)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_language_menu(update: Update, context: CallbackContext):
    """Меню добавления нового языка"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🇫🇷 Français", callback_data="add_lang_fr")],
        [InlineKeyboardButton("🇩🇪 Deutsch", callback_data="add_lang_de")],
        [InlineKeyboardButton("🇪🇸 Español", callback_data="add_lang_es")],
        [InlineKeyboardButton("🇮🇹 Italiano", callback_data="add_lang_it")],
        [InlineKeyboardButton("✏️ Другой язык", callback_data="add_custom_lang")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="translation_management")]
    ]
    
    await query.edit_message_text(
        "🌍 <b>Նոր լեզու ավելացնել</b>\n\n"
        "Ընտրեք լեզու ավելացնելու համար կամ ստեղծեք ձերը:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ===== ФՈՒՆԿՑԻԱ РԵԶԵՐՎՆՈՒ ԿՈՊԻՐՈՎԱԼՈՒ =====

async def create_backup(update: Update, context: CallbackContext):
    """Создание резервной копии"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("notifications.access_denied", user_id))
        return
    
    await query.answer()
    await query.edit_message_text(
        f"💾 <b>{_('backup.create', user_id)}</b>\n\n"
        f"{_('backup.creating', user_id)}\n"
        f"{_('backup.please_wait', user_id)}",
        parse_mode="HTML"
    )
    
    try:
        from ...utils.backup_manager import backup_manager
        
        # Создаем резервную копию
        backup_info = backup_manager.create_backup("Ручное создание через բոտը")
        
        # Форматируем размер файла
        size_mb = backup_info["size"] / (1024 * 1024)
        
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]]
        
        await query.edit_message_text(
            f"✅ <b>{_('backup.created_successfully', user_id)}</b>\n\n"
            f"📁 <b>{_('backup.file_name', user_id)}</b> <code>{backup_info['name']}</code>\n"
            f"📅 <b>{_('backup.creation_date', user_id)}</b> {datetime.fromisoformat(backup_info['created_at']).strftime('%d.%m.%Y %H:%M')}\n"
            f"💾 <b>{_('backup.size', user_id)}</b> {size_mb:.1f} {_('backup.mb', user_id)}\n"
            f"📄 <b>{_('backup.files_count', user_id)}</b> {backup_info['files_count']}\n\n"
            f"{_('backup.saved_safely', user_id)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]]
        await query.edit_message_text(
            f"❌ <b>{_('backup.error_creating', user_id)}</b>\n\n"
            f"Подробности: {str(e)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def backup_list(update: Update, context: CallbackContext):
    """Список резервных копий"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("notifications.access_denied", user_id))
        return
    
    await query.answer()
    
    try:
        from ...utils.backup_manager import backup_manager
        
        backups = backup_manager.list_backups()
        
        if not backups:
            backup_info = f"📁 <b>{_('backup.list', user_id)}</b>\n\n❌ {_('backup.no_backups_found', user_id)}"
            keyboard = [
                [InlineKeyboardButton(_("backup.create", user_id), callback_data="create_backup")],
                [InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]
            ]
        else:
            backup_info = f"📁 <b>{_('backup.list', user_id)}</b>\n\n📋 <b>{_('backup.available_backups', user_id)}</b>\n"
            
            total_size = 0
            for i, backup in enumerate(backups[:5], 1):  # Показываем только первые 5
                created_at = datetime.fromisoformat(backup['created_at'])
                size_mb = backup['size'] / (1024 * 1024)
                total_size += backup['size']
                
                backup_info += f"• <code>{backup['name']}</code>\n"
                backup_info += f"  📅 {created_at.strftime('%d.%m.%Y %H:%M')} ({size_mb:.1f} {_('backup.mb', user_id)})\n"
                if backup.get('description'):
                    backup_info += f"  📝 {backup['description']}\n"
                backup_info += "\n"
            
            if len(backups) > 5:
                backup_info += f"... {_('backup.and_more', user_id)} {len(backups) - 5} {_('backup.backups', user_id)}\n\n"
            
            total_size_mb = total_size / (1024 * 1024)
            backup_info += f"💾 <b>{_('backup.total_size', user_id)}</b> {total_size_mb:.1f} {_('backup.mb', user_id)}\n"
            backup_info += f"📊 <b>{_('backup.count', user_id)}</b> {len(backups)} {_('backup.backups', user_id)}"
            
            keyboard = [
                [InlineKeyboardButton(_("backup.restore", user_id), callback_data="restore_backup")],
                [InlineKeyboardButton(_("backup.cleanup", user_id), callback_data="cleanup_backups")],
                [InlineKeyboardButton(_("backup.update_list", user_id), callback_data="backup_list")],
                [InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]
            ]
        
        await query.edit_message_text(
            backup_info,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]]
        await query.edit_message_text(
            f"❌ <b>{_('backup.error_loading_list', user_id)}</b>\n\n{str(e)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def restore_backup(update: Update, context: CallbackContext):
    """Восстановление из резервной копии"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("notifications.access_denied", user_id))
        return
    
    await query.answer()
    
    try:
        from ...utils.backup_manager import backup_manager
        
        backups = backup_manager.list_backups()
        
        if not backups:
            keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]]
            await query.edit_message_text(
                f"🔄 <b>{_('backup.restore', user_id)}</b>\n\n"
                f"❌ {_('backup.no_backups_found', user_id)}.\n"
                f"{_('backup.create_first', user_id)}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        keyboard = []
        for backup in backups[:10]:  # Показываем только первые 10
            created_at = datetime.fromisoformat(backup['created_at'])
            size_mb = backup['size'] / (1024 * 1024)
            
            button_text = f"📁 {backup['name']} ({size_mb:.1f}{_('backup.mb', user_id)})"
            callback_data = f"select_backup_{backup['name']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        keyboard.append([InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")])
        
        await query.edit_message_text(
            f"🔄 <b>{_('backup.restore', user_id)}</b>\n\n"
            f"⚠️ <b>{_('backup.restore_warning', user_id)}</b>\n"
            f"{_('backup.restore_info', user_id)}\n\n"
            f"📋 {_('backup.select_backup', user_id)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]]
        await query.edit_message_text(
            f"❌ <b>{_('backup.error_loading_backups', user_id)}</b>\n\n{str(e)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cleanup_backups(update: Update, context: CallbackContext):
    """Очистка старых резервных копий"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("notifications.access_denied", user_id))
        return
    
    await query.answer()
    
    try:
        from ...utils.backup_manager import backup_manager
        
        backups = backup_manager.list_backups()
        total_size = sum(backup['size'] for backup in backups)
        total_size_mb = total_size / (1024 * 1024)
        
        oldest_date = ""
        if backups:
            oldest_backup = min(backups, key=lambda x: x['created_at'])
            oldest_date = datetime.fromisoformat(oldest_backup['created_at']).strftime('%d.%m.%Y')
        
        keyboard = [
            [InlineKeyboardButton(_("backup.keep_last_10", user_id), callback_data="cleanup_keep_10")],
            [InlineKeyboardButton(_("backup.keep_last_5", user_id), callback_data="cleanup_keep_5")],
            [InlineKeyboardButton(_("backup.keep_last_3", user_id), callback_data="cleanup_keep_3")],
            [InlineKeyboardButton(_("backup.delete_older_30", user_id), callback_data="cleanup_30_days")],
            [InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]
        ]
        
        await query.edit_message_text(
            f"🧹 <b>{_('backup.cleanup_title', user_id)}</b>\n\n"
            f"📊 <b>{_('backup.cleanup_status', user_id)}</b>\n"
            f"• {_('backup.total_backups', user_id)} {len(backups)}\n"
            f"• {_('backup.total_size', user_id)} {total_size_mb:.1f} {_('backup.mb', user_id)}\n"
            f"• {_('backup.oldest_backup', user_id)} {oldest_date}\n\n"
            f"{_('backup.select_cleanup_rule', user_id)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="backup_menu")]]
        await query.edit_message_text(
            f"❌ <b>{_('backup.error_loading_info', user_id)}</b>\n\n{str(e)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cleanup_backups_by_count(update: Update, context: CallbackContext, keep_count: int):
    """Очистка резервных копий с сохранением указанного количества"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("notifications.access_denied", user_id))
        return
    
    await query.answer()
    
    try:
        from ...utils.backup_manager import backup_manager
        
        # Получаем список копий до очистки
        backups_before = backup_manager.list_backups()
        total_before = len(backups_before)
        size_before = sum(backup['size'] for backup in backups_before) / (1024 * 1024)
        
        if total_before <= keep_count:
            keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="cleanup_backups")]]
            await query.edit_message_text(
                f"ℹ️ <b>{_('backup.no_cleanup_needed', user_id)}</b>\n\n"
                f"У вас только {total_before} резервных копий, что не превышает лимит в {keep_count}.\n\n"
                f"💾 <b>{_('backup.total_size', user_id)}</b> {size_before:.1f} {_('backup.mb', user_id)}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Выполняем очистку
        cleanup_result = backup_manager.cleanup_old_backups(keep_count=keep_count)
        
        freed_space_mb = cleanup_result['freed_space'] / (1024 * 1024)
        
        keyboard = [
            [InlineKeyboardButton(_("backup.repeat_cleanup", user_id), callback_data="cleanup_backups")],
            [InlineKeyboardButton(_("backup.back_to_backup", user_id), callback_data="backup_menu")]
        ]
        
        await query.edit_message_text(
            f"✅ <b>{_('backup.cleanup_completed', user_id)}</b>\n\n"
            f"🗑️ <b>{_('backup.deleted_count', user_id)}</b> {cleanup_result['deleted_count']}\n"
            f"💾 <b>{_('backup.kept_count', user_id)}</b> {cleanup_result['kept_count']}\n"
            f"💿 <b>{_('backup.freed_space', user_id)}</b> {freed_space_mb:.1f} {_('backup.mb', user_id)}\n\n"
            f"📋 <b>{_('backup.cleanup_rule', user_id)}</b> Սահմանված է վերջին {keep_count} կոպիաների պահպանում",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка очистки резервных копий: {e}")
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="cleanup_backups")]]
        await query.edit_message_text(
            f"❌ <b>{_('backup.error_cleanup', user_id)}</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cleanup_backups_by_age(update: Update, context: CallbackContext, max_age_days: int):
    """Очистка резервных копий старше указанного количества дней"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("notifications.access_denied", user_id))
        return
    
    await query.answer()
    
    try:
        from ...utils.backup_manager import backup_manager
        from datetime import datetime, timedelta
        
        # Получаем список всех копий
        all_backups = backup_manager.list_backups()
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        
        # Определяем какие копии нужно удалить
        old_backups = []
        total_size_to_delete = 0
        
        for backup in all_backups:
            backup_date = datetime.fromisoformat(backup['created_at'])
            if backup_date < cutoff_date:
                old_backups.append(backup)
                total_size_to_delete += backup['size']
        
        if not old_backups:
            keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="cleanup_backups")]]
            await query.edit_message_text(
                f"ℹ️ <b>{_('backup.no_cleanup_needed', user_id)}</b>\n\n"
                f"{_('backup.cleanup_no_old', user_id)} {max_age_days} {_('backup.days', user_id)}.\n\n"
                f"📁 <b>{_('backup.total_backups', user_id)}</b> {len(all_backups)}\n"
                f"📅 <b>{_('backup.oldest_backup', user_id)}</b> {datetime.fromisoformat(min(all_backups, key=lambda x: x['created_at'])['created_at']).strftime('%d.%m.%Y') if all_backups else 'Нет'}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Удаляем старые копии
        deleted_count = 0
        freed_space = 0
        
        for backup in old_backups:
            if backup_manager.delete_backup(backup['name']):
                deleted_count += 1
                freed_space += backup['size']
        
        freed_space_mb = freed_space / (1024 * 1024)
        remaining_count = len(all_backups) - deleted_count
        
        keyboard = [
            [InlineKeyboardButton(_("backup.repeat_cleanup", user_id), callback_data="cleanup_backups")],
            [InlineKeyboardButton(_("backup.back_to_backup", user_id), callback_data="backup_menu")]
        ]
        
        await query.edit_message_text(
            f"✅ <b>{_('backup.cleanup_completed', user_id)}</b>\n\n"
            f"🗑️ <b>{_('backup.deleted_count', user_id)}</b> {deleted_count}\n"
            f"💾 <b>Осталось копий:</b> {remaining_count}\n"
            f"💿 <b>{_('backup.freed_space', user_id)}</b> {freed_space_mb:.1f} {_('backup.mb', user_id)}\n\n"
            f"📋 <b>{_('backup.cleanup_rule', user_id)}</b> Удалены копии старше {max_age_days} {_('backup.days', user_id)}\n"
            f"📅 <b>{_('backup.boundary_date', user_id)}</b> {cutoff_date.strftime('%d.%m.%Y')}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка очистки резервных копий по возрасту: {e}")
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="cleanup_backups")]]
        await query.edit_message_text(
            f"❌ <b>{_('backup.error_cleanup', user_id)}</b>\n\n"
            f"<code>{str(e)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ===== НԵԴՈՍՏԱՅՈՒՄ ФՈՒՆԿՑԻԱ РԵԶԵՐՎՆՈՒ ԿՈՊԻՐՈՎԱԼՈՒ =====

async def user_permissions_menu(update: Update, context: CallbackContext):
    """Меню разрешений пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✅ Авторизованные пользователи", callback_data="show_authorized_users")],
        [InlineKeyboardButton("❌ Неавторизованные пользователи", callback_data="show_unauthorized_users")],
        [InlineKeyboardButton("➕ Добавить разрешения", callback_data="add_permissions")],
        [InlineKeyboardButton("➖ Убрать разрешения", callback_data="remove_permissions")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]
    ]
    
    await query.edit_message_text(
        "🔧 <b>Настройки доступа</b>\n\n"
        "Управление разрешениями пользователей:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def user_stats_menu(update: Update, context: CallbackContext):
    """Меню статистики пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    try:
        from ...utils.config_utils import load_users
        from ...database.database_manager import get_all_records
        
        users = load_users()
        all_records = get_all_records()
        
        # Статистика активности пользователей
        user_activity = {}
        for record in all_records:
            supplier = record.get('supplier', 'Неизвестно')
            if supplier not in user_activity:
                user_activity[supplier] = {'count': 0, 'amount': 0}
            user_activity[supplier]['count'] += 1
            user_activity[supplier]['amount'] += record.get('amount', 0)
        
        # Топ активных пользователей
        top_users = sorted(user_activity.items(), key=lambda x: x[1]['count'], reverse=True)[:5]
        
        stats_text = f"📊 <b>Статистика пользователей</b>\n\n"
        stats_text += f"👥 Всего пользователей: {len(users)}\n"
        stats_text += f"📝 Активных поставщиков: {len(user_activity)}\n"
        stats_text += f"📋 Всего записей: {len(all_records)}\n\n"
        stats_text += f"🏆 Топ активных пользователей:\n"
        
        for i, (supplier, stats) in enumerate(top_users, 1):
            stats_text += f"{i}. {supplier}: {stats['count']} գրառում\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="user_stats")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]
        ]
        
        await query.edit_message_text(
            stats_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка в user_stats_menu: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]]
        await query.edit_message_text(
            f"❌ <b>Ошибка</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# Заглушки для всех остальных недостающих функций
async def add_admin_handler(update: Update, context: CallbackContext):
    """Заглушка для добавления админа"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]])
    )

async def remove_admin_handler(update: Update, context: CallbackContext):
    """Заглушка для удаления админа"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]])
    )

async def show_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для показа аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def select_backup_handler(update: Update, context: CallbackContext):
    """Заглушка для выбора резервной копии"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="backup_menu")]])
    )

async def confirm_restore_handler(update: Update, context: CallbackContext):
    """Заглушка для подтверждения восстановления"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="backup_menu")]])
    )

async def confirm_cleanup_handler(update: Update, context: CallbackContext):
    """Заглушка для подтверждения очистки"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="backup_menu")]])
    )

async def export_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для экспорта аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def export_user_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для экспорта пользовательской аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def export_financial_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для экспорта финансовой аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def export_period_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для экспорта периодической аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def export_general_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для экспорта общей аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def show_unauthorized_users_handler(update: Update, context: CallbackContext):
    """Показывает неавторизованных пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="user_permissions")]]
    await query.edit_message_text(
        "❌ <b>Неавторизованные пользователи</b>\n\n"
        "⚠️ Функция в разработке\n\n"
        "Будет показывать пользователей, которые пытались получить доступ к боту, но не были авторизованы.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def general_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для общей аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def user_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для пользовательской аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def financial_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для финансовой аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def period_analytics_handler(update: Update, context: CallbackContext):
    """Заглушка для периодической аналитики"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="analytics_menu")]])
    )

async def show_authorized_users_handler(update: Update, context: CallbackContext):
    """Показывает список авторизованных пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    try:
        import json
        import os
        
        # Загружаем список разрешенных пользователей
        allowed_users_path = os.path.join("data", "allowed_users.json")
        try:
            with open(allowed_users_path, 'r', encoding='utf-8') as f:
                allowed_users = json.load(f)
        except FileNotFoundError:
            allowed_users = []
        
        if not allowed_users:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="user_permissions")]]
            await query.edit_message_text(
                "✅ <b>Авторизованные пользователи</b>\n\n"
                "📊 Авторизованных пользователей нет",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        users_text = f"✅ <b>Авторизованные пользователи</b>\n\n"
        users_text += f"👥 Всего: {len(allowed_users)}\n\n"
        
        for i, user_id_int in enumerate(allowed_users[:10], 1):
            is_admin = user_id_int in ADMIN_IDS
            admin_badge = "👑" if is_admin else "👤"
            users_text += f"{i}. {admin_badge} <code>{user_id_int}</code>\n"
        
        if len(allowed_users) > 10:
            users_text += f"\n... и еще {len(allowed_users) - 10} пользователей"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="show_authorized_users")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="user_permissions")]
        ]
        
        await query.edit_message_text(
            users_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка в show_authorized_users_handler: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="user_permissions")]]
        await query.edit_message_text(
            f"❌ <b>Ошибка</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def add_permissions_handler(update: Update, context: CallbackContext):
    """Заглушка для добавления разрешений"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="user_permissions")]])
    )

async def remove_permissions_handler(update: Update, context: CallbackContext):
    """Заглушка для удаления разрешений"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="user_permissions")]])
    )

async def authorize_user_handler(update: Update, context: CallbackContext):
    """Заглушка для авторизации пользователя"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="user_permissions")]])
    )

async def revoke_user_handler(update: Update, context: CallbackContext):
    """Заглушка для отзыва прав пользователя"""
    query = update.callback_query
    await query.edit_message_text(
        "⚠️ Функция в разработке",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="user_permissions")]])
    )

# Недостающие функции для управления пользователями
async def user_list(update: Update, context: CallbackContext):
    """Показывает список пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    try:
        # Загружаем список авторизованных пользователей
        allowed_users_path = os.path.join("data", "allowed_users.json")
        try:
            with open(allowed_users_path, 'r', encoding='utf-8') as f:
                allowed_users = json.load(f)
        except FileNotFoundError:
            allowed_users = []
        
        # Загружаем информацию о пользователях
        users_path = os.path.join("data", "users.json")
        try:
            with open(users_path, 'r', encoding='utf-8') as f:
                users_data = json.load(f)
        except FileNotFoundError:
            users_data = {}
        
        if not allowed_users:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]]
            await query.edit_message_text(
                "👥 <b>Список пользователей</b>\n\n"
                "📊 Авторизованных пользователей не найдено",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        users_text = f"👥 <b>Список пользователей</b>\n\n"
        users_text += f"Всего авторизованных: {len(allowed_users)}\n\n"
        
        # Показываем только первых 10 пользователей
        users_to_show = allowed_users[:10] if len(allowed_users) > 10 else allowed_users
        
        for i, user_id_int in enumerate(users_to_show, 1):
            user_info = f"{i}. ID: <code>{user_id_int}</code>"
            
            # Проверяем, есть ли дополнительная информация о пользователе
            if str(user_id_int) in users_data:
                user_data = users_data[str(user_id_int)]
                if user_data.get('display_name'):
                    user_info += f" - {user_data['display_name']}"
            
            # Отмечаем админов
            if user_id_int in ADMIN_IDS:
                user_info += " 👑"
            
            users_text += f"{user_info}\n"
        
        if len(allowed_users) > 10:
            users_text += f"\n... и еще {len(allowed_users) - 10} пользователей"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="user_list")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]
        ]
        
        await query.edit_message_text(
            users_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка в user_list: {e}")
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]]
        await query.edit_message_text(
            f"❌ <b>Ошибка</b>\n\n<code>{str(e)}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def add_user(update: Update, context: CallbackContext):
    """Добавление нового пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ Добавить по ID", callback_data="add_user_by_id")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="user_settings_menu")]
    ]
    
    await query.edit_message_text(
        "➕ <b>Добавление пользователя</b>\n\n"
        "Выберите способ добавления пользователя:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def add_user_by_id_handler(update: Update, context: CallbackContext):
    """Добавление пользователя по ID"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Доступ запрещен")
        return
    
    await query.answer()
    
    # Устанавливаем состояние ожидания ввода ID
    context.user_data['waiting_for_user_id'] = True
    context.user_data['message_to_edit'] = query.message
    
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_user")]]
    
    await query.edit_message_text(
        "➕ <b>Добавление пользователя по ID</b>\n\n"
        "📝 Введите ID пользователя (только цифры):\n\n"
        "💡 <i>Пример: 123456789</i>\n\n"
        "ℹ️ ID можно получить из настроек Telegram կամ խնդրել օգտվողին ուղարկել /start հրահանգը բոտին",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def cancel_add_user_handler(update: Update, context: CallbackContext):
    """Отмена добавления пользователя"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем состояние
    context.user_data.pop('waiting_for_user_id', None)
    context.user_data.pop('message_to_edit', None)
    
    # Возвращаемся к меню добавления пользователя
    await add_user(update, context)

async def add_user_id_to_allowed(user_id_to_add: int) -> bool:
    """Добавляет пользователя в список разрешенных"""
    try:
        allowed_users_path = os.path.join("data", "allowed_users.json")
        
        # Загружаем текущий список
        try:
            with open(allowed_users_path, 'r', encoding='utf-8') as f:
                allowed_users = json.load(f)
        except FileNotFoundError:
            allowed_users = []
        
        # Проверяем, не добавлен ли уже пользователь
        if user_id_to_add in allowed_users:
            return False  # Пользователь уже добавлен
        
        # Добавляем пользователя
        allowed_users.append(user_id_to_add)
        
        # Сохраняем обновленный список
        os.makedirs(os.path.dirname(allowed_users_path), exist_ok=True)
        with open(allowed_users_path, 'w', encoding='utf-8') as f:
            json.dump(allowed_users, f, ensure_ascii=False, indent=2)
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении пользователя {user_id_to_add}: {e}")
        return False

async def handle_user_id_input(update: Update, context: CallbackContext):
    """Обрабатывает ввод ID пользователя"""
    # Проверяем, ожидаем ли мы ввод ID пользователя
    if not context.user_data.get('waiting_for_user_id'):
        return
    
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        return
    
    message_text = update.message.text.strip()
    message_to_edit = context.user_data.get('message_to_edit')
    
    # Очищаем состояние
    context.user_data.pop('waiting_for_user_id', None)
    context.user_data.pop('message_to_edit', None)
    
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except:
        pass
    
    # Проверяем, что введен корректный ID
    try:
        user_id_to_add = int(message_text)
        if user_id_to_add <= 0:
            raise ValueError("ID должен быть положительным числом")
    except ValueError:
        keyboard = [[InlineKeyboardButton("🔄 Попробовать снова", callback_data="add_user_by_id")],
                   [InlineKeyboardButton("⬅️ Назад", callback_data="add_user")]]
        
        if message_to_edit:
            await message_to_edit.edit_text(
                "❌ <b>Ошибка ввода</b>\n\n"
                "📝 ID пользователя должен содержать только цифры\n\n"
                "💡 <i>Пример правильного ID: 123456789</i>",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
    # Проверяем, не пытается ли админ добавить самого себя
    if user_id_to_add == user_id:
        keyboard = [[InlineKeyboardButton("🔄 Попробовать снова", callback_data="add_user_by_id")],
                   [InlineKeyboardButton("⬅️ Назад", callback_data="add_user")]]
        
        if message_to_edit:
            await message_to_edit.edit_text(
                "⚠️ <b>Предупреждение</b>\n\n"
                "Вы не можете добавить самого себя - вы уже являетесь администратором",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
    # Добавляем пользователя
    if add_user_id_to_allowed(user_id_to_add):
        keyboard = [
            [InlineKeyboardButton("➕ Добавить еще", callback_data="add_user_by_id")],
            [InlineKeyboardButton("👥 Список пользователей", callback_data="user_list")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="add_user")]
        ]
        
        if message_to_edit:
            await message_to_edit.edit_text(
                f"✅ <b>Пользователь добавлен</b>\n\n"
                f"👤 ID: <code>{user_id_to_add}</code>\n\n"
                f"✔️ Пользователь теперь может использовать бота\n"
                f"📝 Он получит доступ при следующем обращении к боту",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
    else:
        keyboard = [[InlineKeyboardButton("🔄 Попробовать снова", callback_data="add_user_by_id")],
                   [InlineKeyboardButton("⬅️ Назад", callback_data="add_user")]]
        
        if message_to_edit:
            await message_to_edit.edit_text(
                f"⚠️ <b>Пользователь уже добавлен</b>\n\n"
                f"👤 ID: <code>{user_id_to_add}</code>\n\n"
                f"ℹ️ Этот пользователь уже имеет доступ к боту",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

async def conversation_fallback_handler(update: Update, context: CallbackContext):
    """Fallback handler для ConversationHandler - завершает диалог и возвращает в главное меню"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_user_allowed(user_id):
        await query.answer("❌ Մուտքն արգելված է")
        return ConversationHandler.END
    
    await query.answer()
    
    data = query.data
    logger.info(f"ConversationHandler fallback: {data} от пользователя {user_id}")
    
    # Только для кнопок возврата в меню - завершаем диалог
    if data in ["back_to_menu", "main_menu"]:
        # Очищаем только данные диалога, но не все user_data
        context.user_data.pop('record', None)
        context.user_data.pop('payment', None)
        context.user_data.pop('selected_sheet_name', None)
        
        await query.edit_message_text(
            "📋 Հիմնական ընտրացանկ:",
            reply_markup=create_main_menu(user_id)
        )
        return ConversationHandler.END
    
    # Для других кнопок меню - завершаем ConversationHandler и передаем в button_handler
    menu_actions = [
        "add_record_menu", "add_record_select_sheet", "add_skip_record_select_sheet",
        "select_spreadsheet", "select_sheet_menu", "settings_menu",
        "analytics_menu", "backup_menu", "workers_menu", "pay_menu", "my_payments"
    ]
    
    if data in menu_actions or data.startswith(("spreadsheet_", "sheet_", "final_sheet_")):
        # Очищаем только данные диалога
        context.user_data.pop('record', None)
        context.user_data.pop('payment', None)
        context.user_data.pop('selected_sheet_name', None)
        
        logger.info(f"Завершение ConversationHandler и переход к button_handler для: {data}")
        
        # Имитируем новый callback для button_handler
        await button_handler(update, context)
        return ConversationHandler.END
    
    # Для всех остальных callback'ов - просто завершаем ConversationHandler
    logger.info(f"Неизвестный callback в ConversationHandler fallback: {data}")
    return ConversationHandler.END
