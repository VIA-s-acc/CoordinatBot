"""
ConversationHandler'ы для диалогов с пользователем
"""

from telegram.ext import ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from .payment_handlers import (
    start_add_payment, get_payment_amount, get_payment_period,
    get_payment_comment, cancel_payment, select_payment_sheet
)
from .translation_handlers import (
    start_add_translation, get_translation_key, get_translation_language,
    save_translation, cancel_translation
)
from ..states.conversation_states import (
    DATE, SUPPLIER_CHOICE, SUPPLIER_MANUAL, DIRECTION, DESCRIPTION, AMOUNT,
    EDIT_VALUE, SET_REPORT_SHEET, PAYMENT_AMOUNT, PAYMENT_PERIOD, PAYMENT_COMMENT,
    ADD_TRANSLATION_KEY, ADD_TRANSLATION_LANG, ADD_TRANSLATION_TEXT, SHEET_SELECTION,
    PAYMENT_SHEET_SELECTION
)
from .record_handlers import (
    start_add_record, start_add_skip_record, get_date, get_supplier_manual, 
    get_direction, get_description, get_amount, cancel, start_record_selection, start_skip_record_selection
)
from .edit_handlers import (
    get_edit_value
)
from .basic_commands import text_menu_handler
from .button_handlers import button_handler, conversation_fallback_handler
from .admin_handlers import set_report_sheet_handler
from ...config.settings import logger


def create_add_record_conversation():
    """Создает ConversationHandler для добавления записей"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_record, pattern="^add_record_sheet_"),
            CallbackQueryHandler(start_add_skip_record, pattern="^add_skip_sheet_"),
            CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),
            CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),
        ],
        states={
            SHEET_SELECTION: [
                CallbackQueryHandler(start_add_record, pattern="^add_record_sheet_"),
                CallbackQueryHandler(start_add_skip_record, pattern="^add_skip_sheet_"),
                CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),  # Возможность перезапуска записей
                CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),  # Возможность перезапуска упущений
            ],
            DATE: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_date),
                CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),  # Возможность перезапуска записей
                CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),  # Возможность перезапуска упущений
            ],
            SUPPLIER_CHOICE: [
                CallbackQueryHandler(button_handler, pattern="^(use_my_name|manual_input|use_firm_name)$"),
                CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),  # Возможность перезапуска записей
                CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),  # Возможность перезапуска упущений
            ],
            SUPPLIER_MANUAL: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_supplier_manual),
                CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),  # Возможность перезапуска записей
                CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),  # Возможность перезапуска упущений
            ],
            DIRECTION: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_direction),
                CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),  # Возможность перезапуска записей
                CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),  # Возможность перезапуска упущений
            ],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_description),
                CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),  # Возможность перезапуска записей
                CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),  # Возможность перезапуска упущений
            ],
            AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_amount),
                CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),  # Возможность перезапуска записей
                CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),  # Возможность перезапуска упущений
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler),
            CallbackQueryHandler(conversation_fallback_handler, pattern="^(back_to_menu|main_menu)$"),
            CallbackQueryHandler(start_record_selection, pattern="^add_record_select_sheet$"),  # Fallback для перезапуска записей
            CallbackQueryHandler(start_skip_record_selection, pattern="^add_skip_record_select_sheet$"),  # Fallback для перезапуска упущений
        ],
        per_message=False,  # Изменено на False для корректной работы с MessageHandler
    )

def create_edit_record_conversation():
    """Создает ConversationHandler для редактирования записей"""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^edit_")],
        states={
            EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_edit_value)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler),
            CallbackQueryHandler(conversation_fallback_handler, pattern="^(back_to_menu|main_menu|add_record_menu|select_spreadsheet|select_sheet_menu|settings_menu|analytics_menu|backup_menu|workers_menu|pay_menu|my_payments)$")
        ],
        per_message=False,  # Изменено на False для корректной работы с MessageHandler
    )

def create_payment_conversation():
    """Создает ConversationHandler для платежей"""

    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_payment, pattern="^add_payment_"),
        ],
        states={
            PAYMENT_SHEET_SELECTION: [
                CallbackQueryHandler(select_payment_sheet, pattern="^select_pay_sheet_"),
                CallbackQueryHandler(start_add_payment, pattern="^add_payment_"),  # Повторный вход
            ],
            PAYMENT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_payment_amount),
                CallbackQueryHandler(start_add_payment, pattern="^add_payment_"),  # Повторный вход
            ],
            PAYMENT_PERIOD: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_payment_period),
                CallbackQueryHandler(start_add_payment, pattern="^add_payment_"),  # Повторный вход
            ],
            PAYMENT_COMMENT: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_payment_comment),
                CallbackQueryHandler(start_add_payment, pattern="^add_payment_"),  # Повторный вход
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_payment),
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler),
            CallbackQueryHandler(conversation_fallback_handler, pattern="^(back_to_menu|main_menu|add_record_menu|select_spreadsheet|select_sheet_menu|settings_menu|analytics_menu|backup_menu|workers_menu|pay_menu|my_payments)$")
        ],
        allow_reentry=True,  # Разрешаем повторный вход
        per_message=False,  # Изменено на False для корректной работы с MessageHandler
    )

def create_report_conversation():
    """Создает ConversationHandler для настройки отчетов"""
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^set_report_")],
        states={
            SET_REPORT_SHEET: [MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, set_report_sheet_handler)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler),
            CallbackQueryHandler(conversation_fallback_handler, pattern="^(back_to_menu|main_menu|add_record_menu|select_spreadsheet|select_sheet_menu|settings_menu|analytics_menu|backup_menu|workers_menu|pay_menu|my_payments)$")
        ],
        per_message=False,  # Изменено на False для корректной работы с MessageHandler
    )

def create_translation_conversation():
    """Создает ConversationHandler для управления переводами"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_translation, pattern="^add_translation$"),
        ],
        states={
            ADD_TRANSLATION_KEY: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_translation_key)
            ],
            ADD_TRANSLATION_LANG: [
                CallbackQueryHandler(get_translation_language, pattern="^trans_lang_")
            ],
            ADD_TRANSLATION_TEXT: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, save_translation)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_translation),
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler),
            CallbackQueryHandler(conversation_fallback_handler, pattern="^(back_to_menu|main_menu|add_record_menu|select_spreadsheet|select_sheet_menu|settings_menu|analytics_menu|backup_menu|workers_menu|pay_menu|my_payments)$")
        ],
        per_message=True,
    )

def create_settings_conversation():
    """Создает ConversationHandler для настроек переводов"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_translation, pattern="^add_translation$"),
        ],
        states={
            ADD_TRANSLATION_KEY: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_translation_key)
            ],
            ADD_TRANSLATION_TEXT: [
                MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, save_translation)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler),
            CallbackQueryHandler(conversation_fallback_handler, pattern="^(back_to_menu|main_menu|add_record_menu|select_spreadsheet|select_sheet_menu|settings_menu|analytics_menu|backup_menu|workers_menu|pay_menu|my_payments)$")
        ],
        allow_reentry=True,
        per_message=True
    )
