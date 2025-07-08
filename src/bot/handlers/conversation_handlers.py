"""
ConversationHandler'ы для диалогов с пользователем
"""
import logging
from telegram.ext import ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from .payment_handlers import (
    start_add_payment, get_payment_amount, get_payment_period, 
    get_payment_comment, cancel_payment
)
from ..states.conversation_states import (
    DATE, SUPPLIER_CHOICE, SUPPLIER_MANUAL, DIRECTION, DESCRIPTION, AMOUNT, 
    EDIT_VALUE, CONFIRM_DELETE, SET_REPORT_SHEET, PAYMENT_AMOUNT, PAYMENT_PERIOD, PAYMENT_COMMENT
)
from .record_handlers import (
    start_add_record, start_add_skip_record, get_date, get_supplier_manual, 
    get_direction, get_description, get_amount, cancel
)
from .edit_handlers import (
    get_edit_value, cancel_edit
)
from .basic_commands import text_menu_handler
from .button_handlers import button_handler
from .admin_handlers import set_report_sheet_handler

logger = logging.getLogger(__name__)

def create_add_record_conversation():
    """Создает ConversationHandler для добавления записей"""
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_record, pattern="^add_record$"),
            CallbackQueryHandler(start_add_skip_record, pattern="^add_skip_record$"),
        ],
        states={
            DATE: [MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_date)],
            SUPPLIER_CHOICE: [CallbackQueryHandler(button_handler, pattern="^(use_my_name|manual_input|use_firm_name)$")],
            SUPPLIER_MANUAL: [MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_supplier_manual)],
            DIRECTION: [MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_direction)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_description)],
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_amount)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler)
        ],
        per_message=True,  # Для CallbackQueryHandler лучше использовать per_message=True
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
            CallbackQueryHandler(button_handler, pattern="^cancel_edit_"),
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler)
        ],
        per_message=True,  # Для CallbackQueryHandler лучше использовать per_message=True
    )

def create_payment_conversation():
    """Создает ConversationHandler для платежей"""

    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_add_payment, pattern="^add_payment_"),
        ],
        states={
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
            CallbackQueryHandler(start_add_payment, pattern="^add_payment_"),  # Fallback для повторного входа
        ],
        allow_reentry=True,  # Разрешаем повторный вход
        per_message=True,  # Для CallbackQueryHandler лучше использовать per_message=True
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
            MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler)
        ],
        per_message=True,  # Для CallbackQueryHandler лучше использовать per_message=True
    )
