"""
Главный файл для запуска бота в новой модульной структуре
"""
import logging
import sys
import os

# Добавляем корневую папку в path для импортов
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# Импорты модулей
from src.bot.handlers.conversation_handlers import (
    create_add_record_conversation, 
    create_edit_record_conversation,
    create_payment_conversation,
    create_report_conversation
)
from src.bot.handlers.basic_commands import (
    start, menu_command, text_menu_handler, help_command, message_handler
)
from src.bot.handlers.admin_handlers import (
    set_log_command, set_report_command, allow_user_command, 
    disallow_user_command, allowed_users_command, set_user_name_command,
    export_command, sync_sheets_command, initialize_sheets_command, set_sheet_command
)
from src.bot.handlers.search_commands import (
    search_command, recent_command, info_command, my_report_command
)
from src.bot.handlers.button_handlers import button_handler
from src.bot.handlers.error_handler import error_handler
from src.config.settings import TOKEN
from src.database.database_manager import init_db
from src.utils.config_utils import load_bot_config

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Основная функция запуска бота"""
    try:
        # Инициализация базы данных
        if not init_db():
            logger.error("Не удалось инициализировать базу данных!")
            return
        
        # Создание приложения
        application = Application.builder().token(TOKEN).build()
        
        # Создание ConversationHandler'ов
        add_record_conv = create_add_record_conversation()
        edit_record_conv = create_edit_record_conversation()
        payment_conv = create_payment_conversation()
        report_conv = create_report_conversation()
        
        # Регистрация ConversationHandler'ов (должны быть первыми)
        application.add_handler(add_record_conv)
        application.add_handler(edit_record_conv)
        application.add_handler(payment_conv)
        application.add_handler(report_conv)
        
        # Регистрация обработчиков команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("help", help_command))
        
        # Команды поиска и информации
        application.add_handler(CommandHandler("search", search_command))
        application.add_handler(CommandHandler("recent", recent_command))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(CommandHandler("my_report", my_report_command))
        
        # Административные команды
        application.add_handler(CommandHandler("set_log", set_log_command))
        application.add_handler(CommandHandler("set_sheet", set_sheet_command))
        application.add_handler(CommandHandler("set_report", set_report_command))
        application.add_handler(CommandHandler("allow_user", allow_user_command))
        application.add_handler(CommandHandler("disallow_user", disallow_user_command))
        application.add_handler(CommandHandler("allowed_users", allowed_users_command))
        application.add_handler(CommandHandler("set_user_name", set_user_name_command))
        application.add_handler(CommandHandler("export", export_command))
        application.add_handler(CommandHandler("sync_sheets", sync_sheets_command))
        application.add_handler(CommandHandler("initialize_sheets", initialize_sheets_command))
        
        # Регистрация обработчика кнопок (должен быть после ConversationHandler'ов)
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Регистрация обработчиков сообщений
        application.add_handler(MessageHandler(filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, text_menu_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, message_handler))
        
        # Регистрация обработчика ошибок
        application.add_error_handler(error_handler)
        
        # Запуск бота
        logger.info("🚀 Бот запущен в новой модульной архитектуре!")
        print("🚀 Бот запущен! Нажмите Ctrl+C для остановки.")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == '__main__':
    # Инициализация файлов конфигурации, если они не существуют
    import json
    from src.config.settings import USERS_FILE, ALLOWED_USERS_FILE, BOT_CONFIG_FILE
    
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
    
    if not os.path.exists(ALLOWED_USERS_FILE):
        with open(ALLOWED_USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f)
    
    if not os.path.exists(BOT_CONFIG_FILE):
        with open(BOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump({'log_chat_id': None, 'report_chats': {}}, f)
    
    main()
