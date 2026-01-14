"""
Главный файл для запуска бота в новой модульной структуре
"""
import sys
import os
import argparse
import shutil

# Добавляем корневую папку в path для импортов
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler

# Импорты модулей
from src.bot.handlers.conversation_handlers import (
    create_add_record_conversation,
    create_edit_record_conversation,
    create_payment_conversation,
    create_report_conversation,
)
from src.bot.handlers.role_management_handlers import (
    role_management_menu, list_all_users, view_secondary_users,
    start_add_user, receive_user_id, receive_display_name, set_role_for_new_user,
    start_change_role, select_new_role, apply_new_role,
    start_remove_user, confirm_remove_user, cancel_role_operation,
    INPUT_USER_ID, INPUT_DISPLAY_NAME, SELECT_ROLE
)
from src.bot.handlers.payment_management_handlers import (
    payments_main_menu, payments_secondary_list, payments_clients_list,
    user_payments_list, payment_detail,
    start_edit_payment_amount, receive_new_amount,
    start_edit_payment_comment, receive_new_comment,
    confirm_delete_payment, execute_delete_payment, cancel_edit as cancel_payment_edit,
    get_summary_report,
    EDIT_AMOUNT, EDIT_COMMENT
)
from src.bot.handlers.basic_commands import (
    start, menu_command, text_menu_handler, help_command, message_handler
)
from src.bot.handlers.admin_handlers import (
    set_log_command, set_report_command, allow_user_command,
    disallow_user_command, allowed_users_command, set_user_name_command,
    export_command, sync_sheets_command, initialize_sheets_command, set_sheet_command,
    send_data_files_command, add_backup_chat_command, scheduled_backup_job
)
from src.bot.handlers.admin_commands import clean_duplicates_command
from src.bot.handlers.search_commands import (
    search_command, recent_command, info_command, my_report_command
)
from src.bot.handlers.button_handlers import button_handler
from src.bot.handlers.error_handler import error_handler
from src.config.settings import TOKEN, logger
from src.database.database_manager import init_db
from src.google_integration.async_sheets_worker import start_worker, stop_worker


def main():
    """Основная функция запуска бота"""
    try:
        # Инициализация базы данных
        if not init_db():
            logger.error("Не удалось инициализировать базу данных!")
            return

        # Миграция пользователей к системе ролей (если требуется)
        try:
            from src.utils.migrate_users_roles import auto_migrate_if_needed
            logger.info("🔄 Проверка необходимости миграции пользователей...")
            auto_migrate_if_needed()
        except Exception as e:
            logger.error(f"❌ Ошибка при миграции пользователей: {e}", exc_info=True)

        # Запуск асинхронного воркера для Google Sheets
        start_worker()
        logger.info("🔄 Асинхронный воркер Google Sheets запущен")

        # Инициализация таблицы платежей и синхронизация
        try:
            from src.google_integration.payments_sheets_manager import PaymentsSheetsManager
            from src.google_integration.payments_sync_manager import PaymentsSyncManager
            from src.config.settings import PAYMENTS_SPREADSHEET_ID

            if PAYMENTS_SPREADSHEET_ID:
                logger.info("📊 Инициализация таблицы платежей...")
                payments_sheets = PaymentsSheetsManager()

                if payments_sheets.initialize_payment_sheets():
                    logger.info("✅ Таблица платежей инициализирована")

                    # Синхронизация платежей
                    logger.info("🔄 Синхронизация платежей...")
                    sync_manager = PaymentsSyncManager()
                    stats = sync_manager.full_sync_payments()

                    logger.info(
                        f"✅ Синхронизация платежей завершена. "
                        f"Всего добавлено: {stats['total_added']}, "
                        f"Ошибок: {stats['total_errors']}"
                    )
                else:
                    logger.warning("⚠️ Не удалось инициализировать таблицу платежей")
            else:
                logger.warning("⚠️ PAYMENTS_SPREADSHEET_ID не установлен. Синхронизация платежей отключена.")

        except Exception as e:
            logger.error(f"❌ Ошибка при инициализации платежей: {e}", exc_info=True)

        # Создание приложения
        application = Application.builder().token(TOKEN).build()
        
        # Создание ConversationHandler'ов
        add_record_conv = create_add_record_conversation()
        edit_record_conv = create_edit_record_conversation()
        payment_conv = create_payment_conversation()
        report_conv = create_report_conversation()

        # ConversationHandler для добавления пользователя
        add_user_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_add_user, pattern="^role_add_user$")],
            states={
                INPUT_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_id)],
                INPUT_DISPLAY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_display_name)],
                SELECT_ROLE: [CallbackQueryHandler(set_role_for_new_user, pattern="^setrole_")]
            },
            fallbacks=[CallbackQueryHandler(cancel_role_operation, pattern="^role_menu$")],
            name="add_user_conversation",
            persistent=False
        )

        # ConversationHandler для редактирования суммы платежа
        edit_payment_amount_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_edit_payment_amount, pattern="^payment_edit_amount_")],
            states={
                EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_amount)]
            },
            fallbacks=[CommandHandler("cancel", cancel_payment_edit)],
            name="edit_payment_amount_conversation",
            persistent=False
        )

        # ConversationHandler для редактирования комментария платежа
        edit_payment_comment_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_edit_payment_comment, pattern="^payment_edit_comment_")],
            states={
                EDIT_COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_comment)]
            },
            fallbacks=[CommandHandler("cancel", cancel_payment_edit)],
            name="edit_payment_comment_conversation",
            persistent=False
        )

        # Регистрация ConversationHandler'ов (должны быть первыми)
        application.add_handler(add_record_conv)
        application.add_handler(edit_record_conv)
        application.add_handler(payment_conv)
        application.add_handler(report_conv)
        application.add_handler(add_user_conv)
        application.add_handler(edit_payment_amount_conv)
        application.add_handler(edit_payment_comment_conv)
        
        # Регистрация обработчиков команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("roles", role_management_menu))
        
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
        application.add_handler(CommandHandler("send_data_files", send_data_files_command))
        application.add_handler(CommandHandler("add_backup_chat", add_backup_chat_command))

        # Настройка автоматического бэкапа
        from src.config.settings import BACKUP_CHAT_ID, BACKUP_INTERVAL_HOURS
        if BACKUP_CHAT_ID:
            print(BACKUP_CHAT_ID, BACKUP_INTERVAL_HOURS)
            logger.info(f"Настройка автоматического бэкапа: чат {BACKUP_CHAT_ID}, интервал {BACKUP_INTERVAL_HOURS}ч")
            job_queue = application.job_queue
            job_queue.run_repeating(
                scheduled_backup_job,
                interval=BACKUP_INTERVAL_HOURS * 3600,  # конвертируем часы в секунды
                first=10,  # первый бэкап через 10 секунд после запуска
                name="automated_backup"
            )
        else:
            logger.info("BACKUP_CHAT_ID не установлен, автоматический бэкап отключен")

        # Отдельные обработчики для специфичных callback'ов (должны быть ДО общего button_handler)
        from src.bot.handlers.edit_handlers import confirm_delete, cancel_edit
        logger.info("Регистрируем handlers для confirm_delete_ и cancel_edit_")
        
        # Тестируем, что функции импортированы правильно
        logger.info(f"confirm_delete функция: {confirm_delete}")
        logger.info(f"cancel_edit функция: {cancel_edit}")
        
        application.add_handler(CallbackQueryHandler(confirm_delete, pattern=r"^confirm_delete_"))
        application.add_handler(CallbackQueryHandler(cancel_edit, pattern=r"^cancel_edit_"))
        logger.info("Handlers для confirm_delete_ и cancel_edit_ зарегистрированы")
        application.add_handler(CommandHandler("clean_duplicates", clean_duplicates_command))

        # Регистрация обработчиков управления ролями
        application.add_handler(CallbackQueryHandler(role_management_menu, pattern="^role_menu$"))
        application.add_handler(CallbackQueryHandler(list_all_users, pattern="^role_list_users$"))
        application.add_handler(CallbackQueryHandler(view_secondary_users, pattern="^role_view_secondary$"))
        application.add_handler(CallbackQueryHandler(start_change_role, pattern="^role_change_role$"))
        application.add_handler(CallbackQueryHandler(select_new_role, pattern="^changerole_user_"))
        application.add_handler(CallbackQueryHandler(apply_new_role, pattern="^newrole_"))
        application.add_handler(CallbackQueryHandler(start_remove_user, pattern="^role_remove_user$"))
        application.add_handler(CallbackQueryHandler(confirm_remove_user, pattern="^removeuser_confirm_"))

        # Регистрация обработчиков управления платежами
        application.add_handler(CallbackQueryHandler(payments_main_menu, pattern="^pay_menu$"))
        application.add_handler(CallbackQueryHandler(payments_main_menu, pattern="^payments_workers_page_"))
        application.add_handler(CallbackQueryHandler(payments_secondary_list, pattern="^payments_secondary"))
        application.add_handler(CallbackQueryHandler(payments_clients_list, pattern="^payments_clients"))
        application.add_handler(CallbackQueryHandler(user_payments_list, pattern="^worker_payments_"))
        application.add_handler(CallbackQueryHandler(user_payments_list, pattern="^secondary_payments_"))
        application.add_handler(CallbackQueryHandler(user_payments_list, pattern="^client_payments_"))
        application.add_handler(CallbackQueryHandler(payment_detail, pattern="^payment_detail_"))
        application.add_handler(CallbackQueryHandler(confirm_delete_payment, pattern="^payment_delete_confirm_"))
        application.add_handler(CallbackQueryHandler(execute_delete_payment, pattern="^payment_delete_execute_"))
        application.add_handler(CallbackQueryHandler(get_summary_report, pattern="^get_summary_report_"))

        # Регистрация обработчика кнопок (должен быть после ConversationHandler'ов)
        # Исключаем callback'и, которые должны обрабатываться ConversationHandler'ами
        application.add_handler(CallbackQueryHandler(
            button_handler,
            pattern=r"^(?!add_record_sheet_|add_skip_sheet_|add_record_select_sheet$|use_my_name$|use_firm_name$|manual_input$|edit_record_|confirm_delete_|cancel_edit_|add_payment_|confirm_payment_|payment_edit_|payment_delete_|role_|changerole_|newrole_|removeuser_|setrole_).*"
        ))
        
        # Регистрация обработчиков сообщений
        application.add_handler(MessageHandler(filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, text_menu_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, message_handler))
        
        # Регистрация обработчика ошибок
        application.add_error_handler(error_handler)
        
        # Запуск бота
        logger.info("🚀 Бот запущен в новой модульной архитектуре!")
        print("🚀 Бот запущен! Нажмите Ctrl+C для остановки.")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
        stop_worker()
        logger.info("Воркер Google Sheets остановлен")
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        print(f"❌ Критическая ошибка: {e}")
    finally:
        stop_worker()

if __name__ == '__main__':
    # Парсинг аргументов командной строки
    parser = argparse.ArgumentParser(description='CoordinatBot - Telegram бот для управления данными')
    parser.add_argument('-dep', '--deploy', action='store_true', help='Режим деплоя (использует /app_data volume)')
    parser.add_argument('-loc', '--local', action='store_true', help='Локальный режим (использует ./app_data)')
    args = parser.parse_args()
    
    # Определяем режим работы
    if args.deploy:
        os.environ['DEPLOY_MODE'] = 'true'
        DATA_DIR = '/app_data'
        logger.info("🚀 Запуск в режиме деплоя (используется /app_data volume)")
    elif args.local:
        os.environ['DEPLOY_MODE'] = 'false'
        DATA_DIR = 'data'
        logger.info("🏠 Запуск в локальном режиме (используется ./app_data)")
    else:
        # По умолчанию используем режим деплоя
        os.environ['DEPLOY_MODE'] = 'true'
        DATA_DIR = '/app_data'
        logger.info("🚀 Запуск в режиме деплоя по умолчанию (используется /app_data volume)")
    
    # Создаем директорию для данных если ее нет
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # Проверяем, нужно ли копировать данные при первом деплое
    if os.environ.get('DEPLOY_MODE') == 'true':
        local_data_dir = 'data'
        if os.path.exists(local_data_dir):
            try:
                local_items = set(os.listdir(local_data_dir))
                volume_items = set(os.listdir(DATA_DIR))

                if local_items - volume_items:
                    logger.info("🔄 Обнаружено расхождение данных, выполняется полная синхронизация")

                    for item in os.listdir(local_data_dir):
                        src_path = os.path.join(local_data_dir, item)
                        dst_path = os.path.join(DATA_DIR, item)

                        if os.path.isdir(dst_path):
                            shutil.rmtree(dst_path)
                        elif os.path.isfile(dst_path):
                            os.remove(dst_path)

                        if os.path.isdir(src_path):
                            shutil.copytree(src_path, dst_path)
                        else:
                            shutil.copy2(src_path, dst_path)

                    logger.info("✅ Полная синхронизация данных завершена")
                else:
                    logger.info("✅ Структура данных полностью совпадает, синхронизация не требуется")

            except Exception as e:
                logger.error(f"❌ Ошибка при синхронизации данных: {e}")

    
    # Инициализация файлов конфигурации, если они не существуют
    import json
    from src.config.settings import USERS_FILE, ALLOWED_USERS_FILE, BOT_CONFIG_FILE
    
    # Обновляем пути к файлам в соответствии с режимом
    if os.environ.get('DEPLOY_MODE') == 'true':
        USERS_FILE = os.path.join(DATA_DIR, 'users.json')
        ALLOWED_USERS_FILE = os.path.join(DATA_DIR, 'allowed_users.json')
        BOT_CONFIG_FILE = os.path.join(DATA_DIR, 'bot_config.json')
    
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
