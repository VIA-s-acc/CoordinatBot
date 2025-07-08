"""
Обработчики кнопок и callback query
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ..keyboards.inline_keyboards import (
    create_main_menu, create_workers_menu, create_payment_menu, 
    create_back_to_menu_keyboard, create_add_record_menu,
    create_edit_menu
)
from ..states.conversation_states import SUPPLIER_CHOICE, DIRECTION, SUPPLIER_MANUAL
from ...utils.config_utils import is_user_allowed, get_user_settings, update_user_settings
from ...database.database_manager import get_db_stats, get_record_from_db
from ...google_integration.sheets_manager import get_all_spreadsheets, get_spreadsheet_info, get_worksheets_info
from ...config.settings import ADMIN_IDS

from .payment_handlers import pay_menu_handler, pay_user_handler, send_payment_report

logger = logging.getLogger(__name__)

async def button_handler(update: Update, context: CallbackContext):
    """Основной обработчик кнопок"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_user_allowed(user_id):
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    await query.answer()
    
    data = query.data
    
    # Главное меню
    if data == "back_to_menu" or data == "main_menu":
        await query.edit_message_text(
            "📋 Հիմնական ընտրացանկ:",
            reply_markup=create_main_menu(user_id)
        )
    
    # Меню добавления записи
    elif data == "add_record_menu":
        await query.edit_message_text(
            "Ընտրեք գործողությունը՝",
            reply_markup=create_add_record_menu()
        )
    
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
    
    elif data.startswith("confirm_delete_"):
        from .edit_handlers import confirm_delete
        return await confirm_delete(update, context)
    
    elif data.startswith("cancel_edit_"):
        record_id = data.replace("cancel_edit_", "")
        keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record_id}")]]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
    
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
    
    else:
        # Callback'и add_payment_ обрабатываются ConversationHandler'ом
        if not data.startswith("add_payment_"):
            logger.warning(f"Необработанный callback: {data}")
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
        spreadsheets = get_all_spreadsheets()
        
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
        
        keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
        
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
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        
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
        
        keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="select_spreadsheet")])
        
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
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        
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
        
        keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            f"📋 Ընտրեք թերթիկ <b>{spreadsheet_title}</b> աղյուսակից:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await query.edit_message_text(
            f"❌ Շխալ թերթիկների ցանկը ստանալիս: {e}",
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
        f"🧭 Մուտքագրեք ուղղությունը:"
    )
    
    return DIRECTION

async def use_firm_name(update: Update, context: CallbackContext):
    """Использовать имя фирмы как поставщика"""
    query = update.callback_query
    
    context.user_data['record']['supplier'] = "Ֆ"
    
    await query.edit_message_text(
        f"✅ Մատակարար: Ֆ\n\n"
        f"🧭 Մուտքագրեք ուղղությունը:"
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
                    [InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]
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
                [InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]
            ])
        )
