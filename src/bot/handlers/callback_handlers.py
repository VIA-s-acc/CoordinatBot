"""
Обработчики callback запросов (кнопок)
"""
import logging
from telegram import Update
from telegram.ext import CallbackContext
from ..keyboards.inline_keyboards import create_main_menu, create_back_to_menu_keyboard
from ...utils.config_utils import is_user_allowed

logger = logging.getLogger(__name__)

async def button_handler(update: Update, context: CallbackContext):
    """Основной обработчик кнопок"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_user_allowed(user_id):
        await query.answer("❌ Ձեր մուտքն արգելված է:")
        return
    
    await query.answer()
    
    data = query.data
    
    # Обработка основных кнопок меню
    if data == "back_to_menu":
        await query.edit_message_text(
            "📋 Հիմնական ընտրացանկ:",
            reply_markup=create_main_menu(user_id)
        )
    elif data == "show_status":
        await show_status(update, context)
    elif data == "show_stats":
        await show_stats(update, context)
    elif data == "workers_menu":
        await show_workers_menu(update, context)
    elif data.startswith("pay_user_"):
        display_name = data.replace("pay_user_", "")
        await show_payment_menu(update, context, display_name)
    elif data.startswith("generate_report_"):
        display_name = data.replace("generate_report_", "")
        await generate_user_report(update, context, display_name)
    else:
        # Перенаправляем необработанные callback'и в соответствующие модули
        logger.warning(f"Необработанный callback: {data}")

async def show_status(update: Update, context: CallbackContext):
    """Показывает статус бота"""
    query = update.callback_query
    
    status_text = "📊 Ընթացիկ կարգավիճակ:\n\n"
    status_text += "🤖 Բոտը աշխատում է\n"
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
    
    from ...database.database_manager import get_db_stats
    
    stats = get_db_stats()
    if stats:
        stats_text = (
            f"📈 Վիճակագրություն:\n\n"
            f"📝 Ընդհանուր գրառումներ: {stats['total_records']}\n"
            f"💰 Ընդհանուր գումար: {stats['total_amount']:,.2f} դրամ\n"
        )
    else:
        stats_text = "❌ Վիճակագրություն ստանալու սխալ:"
    
    await query.edit_message_text(
        stats_text,
        reply_markup=create_back_to_menu_keyboard()
    )

async def show_workers_menu(update: Update, context: CallbackContext):
    """Показывает меню работников"""
    query = update.callback_query
    
    from ..keyboards.inline_keyboards import create_workers_menu
    
    await query.edit_message_text(
        "👥 Ընտրեք աշխատակցին:",
        reply_markup=create_workers_menu()
    )

async def show_payment_menu(update: Update, context: CallbackContext, display_name: str):
    """Показывает меню для работы с конкретным работником"""
    query = update.callback_query
    
    from ..keyboards.inline_keyboards import create_payment_menu
    
    await query.edit_message_text(
        f"👤 Աշխատակից: {display_name}\n\n"
        f"Ընտրեք գործողությունը:",
        reply_markup=create_payment_menu(display_name)
    )

async def generate_user_report(update: Update, context: CallbackContext, display_name: str):
    """Генерирует отчет для пользователя"""
    # Здесь должна быть логика генерации отчета
    # Пока что заглушка
    query = update.callback_query
    
    await query.edit_message_text(
        f"📊 Генерация отчета для {display_name}...\n"
        f"Эта функция будет реализована позже.",
        reply_markup=create_back_to_menu_keyboard()
    )
