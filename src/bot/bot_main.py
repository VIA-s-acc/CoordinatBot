"""
Основной модуль телеграм бота
"""
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from .handlers.basic_commands import start, menu_command, help_command, text_menu_handler
from .handlers.admin_handlers import (
    set_log_command, set_sheet_command, set_report_command,
    initialize_sheets_command, allow_user_command, disallow_user_command,
    allowed_users_command, set_user_name_command, sync_sheets_command,
    export_command
)
from .handlers.search_commands import my_report_command
from .handlers.record_commands import (
    search_command, recent_command, info_command
)
from .handlers.conversation_handlers import (
    create_add_record_conversation, create_edit_record_conversation,
    create_payment_conversation, create_report_conversation, create_settings_conversation,
    create_translation_conversation
)
from .handlers.button_handlers import button_handler
from .handlers.error_handler import error_handler
from ..config.settings import TOKEN

logger = logging.getLogger(__name__)

def create_application():
    """Создает и настраивает приложение Telegram бота"""
    
    # Создание приложения
    application = Application.builder().token(TOKEN).build()
    
    # Основные команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Админские команды
    application.add_handler(CommandHandler("set_log", set_log_command))
    application.add_handler(CommandHandler("set_sheet", set_sheet_command))
    application.add_handler(CommandHandler("set_report", set_report_command))
    application.add_handler(CommandHandler("initialize_sheets", initialize_sheets_command))
    application.add_handler(CommandHandler("allow_user", allow_user_command))
    application.add_handler(CommandHandler("disallow_user", disallow_user_command))
    application.add_handler(CommandHandler("allowed_users", allowed_users_command))
    application.add_handler(CommandHandler("set_user_name", set_user_name_command))
    application.add_handler(CommandHandler("sync_sheets", sync_sheets_command))
    application.add_handler(CommandHandler("my_report", my_report_command))
    application.add_handler(CommandHandler("export", export_command))
    
    # Команды для работы с записями
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("recent", recent_command))
    application.add_handler(CommandHandler("info", info_command))
    
    # Conversation handlers
    application.add_handler(create_add_record_conversation())
    application.add_handler(create_edit_record_conversation())
    application.add_handler(create_payment_conversation())
    application.add_handler(create_report_conversation())
    application.add_handler(create_settings_conversation())
    application.add_handler(create_translation_conversation())
    
    # Обработчик кнопок (должен быть после ConversationHandler'ов)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, text_menu_handler))
    
    # Обработчик ошибок
    application.add_error_handler(error_handler)
    
    logger.info("Приложение настроено успешно")
    return application
