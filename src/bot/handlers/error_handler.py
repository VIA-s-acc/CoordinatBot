"""
Обработчик ошибок
"""
import logging
import traceback
from telegram import Update
from telegram.ext import CallbackContext

from ...utils.config_utils import send_to_log_chat

logger = logging.getLogger(__name__)

async def error_handler(update: object, context: CallbackContext) -> None:
    """Обрабатывает ошибки"""
    logger.error(f"Բացառություն թարմացումը մշակելիս: {context.error}")
    logger.error(traceback.format_exc())
    
    # Отправляем ошибку в лог-чат
    if context.error:
        error_message = f"🔴 ՍԽԱԼ: {str(context.error)}"
        await send_to_log_chat(context, error_message)
        
        # Если есть update, можем отправить пользователю сообщение об ошибке
        if update and hasattr(update, 'effective_user') and update.effective_user:
            try:
                if hasattr(update, 'message') and update.message:
                    await update.message.reply_text(
                        "❌ Սխալ է տեղի ունեցել: Խնդրում ենք փորձել նորից:"
                    )
                elif hasattr(update, 'callback_query') and update.callback_query:
                    await update.callback_query.answer(
                        "❌ Սխալ է տեղի ունեցել",
                        show_alert=True
                    )
            except Exception as e:
                logger.error(f"Չհաջողվեց ուղարկել սխալի հաղորդագրությունը օգտագործողին: {e}")
