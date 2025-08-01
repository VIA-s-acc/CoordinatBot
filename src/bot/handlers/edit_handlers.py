"""
Обработчики для редактирования записей
"""
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ..states.conversation_states import EDIT_VALUE, CONFIRM_DELETE
from ..keyboards.inline_keyboards import create_main_menu, create_edit_menu
from ...utils.config_utils import is_user_allowed, get_user_settings, load_users, save_users
from ...config.settings import ADMIN_IDS
from ...utils.formatting import format_record_info
from ...database.database_manager import get_record_from_db, update_record_in_db, delete_record_from_db
from ...google_integration.sheets_manager import update_record_in_sheet, delete_record_from_sheet
from ...utils.report_manager import send_report

logger = logging.getLogger(__name__)

def get_user_id_by_record_id(record_id: str) -> int:
    """Возвращает ID пользователя по ID записи"""
    users = load_users()
    for user_id_str, user_data in users.items():
        if 'reports' in user_data and str(record_id) in user_data['reports']:
            return int(user_id_str)
    # Если не найдено — ищем по имени в БД
    rec = get_record_from_db(record_id)
    if rec:
        supplier = rec.get('supplier')
        # ищем пользователя с таким display_name
        for user_id_str, user_data in users.items():
            if user_data.get('display_name') == supplier:
                return int(user_id_str)
    return 0

def get_user_id_by_name(name: str) -> int:
    """Возвращает ID пользователя по имени"""
    users = load_users()
    for user_id_str, user_data in users.items():
        if user_data.get('display_name') == name:
            return int(user_id_str)
    return 0

async def handle_edit_button(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопок редактирования"""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    data = query.data
    
    if data.startswith("edit_record_"):
        # Показываем меню редактирования
        record_id = data.replace("edit_record_", "")
        return await show_edit_menu(update, context, record_id, user_id)
    
    # Обрабатываем редактирование конкретных полей
    parts = data.split("_")
    if len(parts) >= 3:
        field = parts[1]
        record_id = "_".join(parts[2:])
        
        context.user_data['edit_record_id'] = record_id
        context.user_data['edit_field'] = field
        
        field_names = {
            'date': 'ամսաթիվ (YYYY-MM-DD)',
            'supplier': 'մատակարար',
            'direction': 'ուղղություն',
            'description': 'նկարագրություն',
            'amount': 'գումար'
        }
        record = get_record_from_db(record_id)
        if not record:
            await query.edit_message_text("❌ Գրառումը չի գտնվել:")
            return ConversationHandler.END
        
        # Проверяем права доступа
        user_id_rec = get_user_id_by_record_id(record_id)
        
        if user_id not in ADMIN_IDS and user_id_rec != user_id:
            await query.edit_message_text("❌ Դուք կարող եք խմբագրել միայն ձեր սեփական գրառումները:")
            return ConversationHandler.END
        
        keyboard = create_edit_menu(record_id, user_id in ADMIN_IDS)
        await query.edit_message_text(
            f"✏️ Գրառման խմբագրում ID: <code>{record_id}</code>\n\n"
            f"Մուտքագրեք նոր արժեք '{field_names.get(field, field)}' դաշտի համար \nՀին։ {record[field]}",
            parse_mode="HTML",
            reply_markup=keyboard
        )

        return EDIT_VALUE

async def show_edit_menu(update: Update, context: CallbackContext, record_id: str, user_id: int):
    """Показывает меню редактирования записи"""
    query = update.callback_query
    if not is_user_allowed(user_id):
        return
    
    # Получаем запись из базы данных
    record = get_record_from_db(record_id)
    if not record:
        await query.edit_message_text("❌ Գրառումը չի գտնվել:")
        return ConversationHandler.END
    
    # Проверяем права доступа
    user_id_rec = get_user_id_by_record_id(record_id)
    
    if user_id not in ADMIN_IDS and user_id_rec != user_id:
        await query.edit_message_text("❌ Դուք կարող եք խմբագրել միայն ձեր սեփական գրառումները:")
        return ConversationHandler.END
    
    text = "✏️ Գրառման խմբագրում:\n\n"
    text += format_record_info(record)
    text += "\n\nԸնտրեք դաշտը խմբագրելու համար:"
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=create_edit_menu(record_id, user_id in ADMIN_IDS))

async def get_edit_value(update: Update, context: CallbackContext):
    """Получает новое значение для редактируемого поля"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    new_value = update.message.text.strip()
    record_id = context.user_data.get('edit_record_id')
    field = context.user_data.get('edit_field')
    
    if not record_id or not field:
        await update.message.reply_text("❌ Խմբագրման սխալ:")
        return ConversationHandler.END
    
    # Получаем запись и проверяем права
    record = get_record_from_db(record_id)
    if not record:
        await update.message.reply_text("❌ Գրառումը չի գտնվել:")
        return ConversationHandler.END

    user_id_rec = get_user_id_by_record_id(record_id)
    

    if user_id not in ADMIN_IDS and user_id_rec != user_id:
        await update.message.reply_text("❌ Դուք կարող եք խմբագրել միայն ձեր սեփական գրառումները:")
        return ConversationHandler.END
    
    # Валидация данных
    if field == 'date':
        try:
            datetime.strptime(new_value, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                "❌ Ամսաթվի սխալ ձևաչափ: Օգտագործեք YYYY-MM-DD:"
            )
            return EDIT_VALUE
    elif field == 'amount':
        try:
            new_value = float(new_value)
        except ValueError:
            await update.message.reply_text(
                "❌ Գումարի սխալ ձևաչափ: Մուտքագրեք թիվ:"
            )
            return EDIT_VALUE
    
    # Обновляем в Google Sheets
    spreadsheet_id = record.get('spreadsheet_id')
    sheet_name = record.get('sheet_name')
    sheet_success = update_record_in_sheet(spreadsheet_id, sheet_name, record_id, field, new_value)
    
    # Обновляем в базе данных
    db_success = update_record_in_db(record_id, field, new_value)
    
    # Результат
    if db_success and sheet_success:
        result_text = f"✅ '{field}' դաշտը թարմացված է '{new_value}' արժեքով"
        record = get_record_from_db(record_id)
        result_text += "\n\n" + format_record_info(record)
    elif db_success:
        result_text = f"✅ '{field}' դաշտը թարմացված է ՏԲ-ում\n⚠️ Սխալ Google Sheets-ում թարմացնելիս"
    elif sheet_success:
        result_text = f"⚠️ Սխալ ՏԲ-ում թարմացնելիս\n✅ '{field}' դաշտը թարմացված է Google Sheets-ում"
    else:
        result_text = f"❌ '{field}' դաշտը թարմացնելու սխալ"
    
    keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record['id']}")]]
    await update.message.reply_text(result_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Отправляем отчет
    user_settings = get_user_settings(user_id)
    user_info = {
        'id': user_id,
        'name': update.effective_user.full_name,
        'display_name': user_settings.get('display_name')
    }
    await send_report(context, "Խմբագրում", record, user_info)
    
    # Очищаем данные пользователя
    context.user_data.clear()
    
    return ConversationHandler.END

async def handle_delete_button(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопки удаления"""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    record_id = query.data.replace("delete_", "")
    
    # Получаем информацию о записи
    record = get_record_from_db(record_id)
    if not record:
        await query.edit_message_text("❌ Գրառումը չի գտնվել:")
        return ConversationHandler.END
    
    # Проверяем права доступа
    user_id_rec = get_user_id_by_record_id(record_id)
    

    if user_id not in ADMIN_IDS and user_id_rec != user_id:
        await query.edit_message_text("❌ Դուք կարող եք ջնջել միայն ձեր սեփական գրառումները:")
        return ConversationHandler.END
    
    text = "🗑 Ջնջելու հաստատում:\n\n"
    text += format_record_info(record)
    text += "\n\n⚠️ Այս գործողությունը չի կարող չեղարկվել:"
    
    keyboard = [
        [InlineKeyboardButton("🗑 Այո, ջնջել", callback_data=f"confirm_delete_{record_id}")],
        [InlineKeyboardButton("❌ Չեղարկել", callback_data=f"cancel_edit_{record_id}")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard))

async def confirm_delete(update: Update, context: CallbackContext):
    """Подтверждает удаление записи"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    logger.info(f"confirm_delete вызвана для пользователя {user_id}, callback_data: {query.data}")
    
    if not is_user_allowed(user_id):
        logger.warning(f"Пользователь {user_id} не имеет доступа к удалению")
        return
    
    record_id = query.data.replace("confirm_delete_", "")
    logger.info(f"Извлечен record_id: {record_id}")
    
    # Удаляем из Google Sheets
    record = get_record_from_db(record_id)
    if not record:
        logger.error(f"Запись {record_id} не найдена в БД")
        await query.edit_message_text("❌ Գրառումը չի գտնվել:")
        return
    
    spreadsheet_id = record.get('spreadsheet_id')
    sheet_name = record.get('sheet_name')
    
    # Удаляем из базы данных
    db_success = delete_record_from_db(record_id)
    
    # Удаляем из Google Sheets
    sheet_success = delete_record_from_sheet(spreadsheet_id, sheet_name, record_id)
    
    # Результат
    if db_success and sheet_success:
        result_text = f"✅ Գրառում ID: <code>{record_id}</code> ջնջված է"
    elif db_success:
        result_text = f"✅ Գրառումը ջնջված է ՏԲ-ից\n⚠️ Սխալ Google Sheets-ից ջնջելիս"
    elif sheet_success:
        result_text = f"⚠️ Սխալ ՏԲ-ից ջնջելիս\n✅ Գրառումը ջնջված է Google Sheets-ից"
    else:
        result_text = f"❌ Գրառումը ջնջելու սխալ ID: <code>{record_id}</code>"
    
    if db_success or sheet_success:
        # Удаляем запись из отчетов пользователя
        users_data = load_users()
        creator_id = record.get('user_id')
        if creator_id:
            creator_id_str = str(creator_id)
            if creator_id_str in users_data and 'reports' in users_data[creator_id_str]:
                if record_id in users_data[creator_id_str]['reports']:
                    users_data[creator_id_str]['reports'].remove(record_id)
                    save_users(users_data)
                    
    await query.edit_message_text(
        result_text,
        parse_mode="HTML",
        reply_markup=create_main_menu(user_id)
    )
    
    # Отправляем отчет
    user_settings = get_user_settings(user_id)
    user_info = {
        'id': user_id,
        'name': update.effective_user.full_name,
        'display_name': user_settings.get('display_name')
    }
    await send_report(context, "Ջնջում", record, user_info)
    
    return ConversationHandler.END

async def cancel_edit(update: Update, context: CallbackContext):
    """Отменяет редактирование"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    # Обрабатываем как кнопку, так и команду
    if update.callback_query:
        record_id = update.callback_query.data.replace("cancel_edit_", "")
        record = get_record_from_db(record_id)
        if record:
            text = format_record_info(record)
            keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record_id}")]]
            await update.callback_query.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.callback_query.edit_message_text("❌ Գրառումը չի գտնվել:")
    else:
        await update.message.reply_text(
            "❌ Խմբագրման գործողությունը չեղարկված է:",
            reply_markup=create_main_menu(user_id)
        )
    context.user_data.clear()
    return ConversationHandler.END
