"""
Обработчики для добавления записей
"""
import uuid
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ..states.conversation_states import DATE, SUPPLIER_CHOICE, DIRECTION, DESCRIPTION, AMOUNT, SUPPLIER_MANUAL
from ..keyboards.inline_keyboards import create_main_menu, create_supplier_choice_keyboard
from ...utils.config_utils import is_user_allowed, get_user_settings, update_user_settings, load_users, save_users
from ...utils.date_utils import normalize_date
from ...utils.formatting import format_record_info
from ...database.database_manager import add_record_to_db
from ...google_integration.sheets_manager import add_record_to_sheet
from ...utils.report_manager import send_report

logger = logging.getLogger(__name__)

async def start_add_record(update: Update, context: CallbackContext):
    """Начинает процесс добавления записи"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_user_allowed(user_id):
        await query.edit_message_text("❌ Ձեր մուտքն արգելված է:")
        return ConversationHandler.END
          
    # Получаем настройки пользователя
    user_settings = get_user_settings(user_id)
    
    # Проверяем настройки
    if not user_settings.get('active_spreadsheet_id') or not user_settings.get('active_sheet_name'):
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Նախ պետք է ընտրել թերթիկ աշխատելու համար:\n"
            "Օգտագործեք 📋 Ընտրել թերթիկ",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END
    
    # Генерируем ID и устанавливаем текущую дату
    record_id = "cb-" + str(uuid.uuid4())[:8]
    current_date = datetime.now().strftime("%Y-%m-%d")
    context.user_data['record'] = {
        'id': record_id,
        'date': current_date,
        'user_id': user_id
    }
    
    # Сразу переходим к выбору поставщика
    display_name = user_settings.get('display_name')
    
    keyboard = []
    if display_name:
        keyboard.append([InlineKeyboardButton(f"👤 Օգտագործել իմ անունը ({display_name})", callback_data="use_my_name")])
    keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել Ֆիրմայի անունը", callback_data="use_firm_name")])
    keyboard.append([InlineKeyboardButton("✏️ Մուտքագրել ձեռքով", callback_data="manual_input")])
    
    await query.edit_message_text(
        f"➕ Ավելացնել նոր գրառում\n"
        f"🆔 ID: <code>{record_id}</code>\n"
        f"📅 Ամսաթիվ: <b>{current_date}</b>\n\n"
        f"🏪 Ընտրեք մատակարարի տեսակը:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SUPPLIER_CHOICE

async def start_add_skip_record(update: Update, context: CallbackContext):
    """Начинает добавление записиpropуска"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not is_user_allowed(user_id):
        await query.edit_message_text("❌ Ձեր մուտքն արգելված է:")
        return ConversationHandler.END

    # Получаем настройки пользователя
    user_settings = get_user_settings(user_id)

    # Проверяем настройки
    if not user_settings.get('active_spreadsheet_id') or not user_settings.get('active_sheet_name'):
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Նախ պետք է ընտրել թերթիկ աշխատելու համար:\n"
            "Օգտագործեք 📋 Ընտրել թերթիկ",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    # Генерируем ID
    record_id = "cb-" + str(uuid.uuid4())[:8]
    current_date = datetime.now().strftime("%Y-%m-%d")
    context.user_data['record'] = {
        'id': record_id,
        'date': current_date,
        'user_id': user_id,
        'skip_mode': True  # флаг для выделения в логах
    }

    # Просим ввести дату вручную или отправить "+" для текущей
    await query.edit_message_text(
        f"➕ Ավելացնել Բացթողում\n"
        f"🆔 ID: <code>{record_id}</code>\n\n"
        f"📅 Մուտքագրեք ամսաթիվը (YYYY-MM-DD) կամ ուղարկեք <b>+</b>՝ ընթացիկ ամսաթվի համար:",
        parse_mode="HTML"
    )
    return DATE

async def get_date(update: Update, context: CallbackContext):
    """Обрабатывает ввод даты"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
        
    date_input = update.message.text.strip()
    
    if date_input == '+':
        date_value = context.user_data['record']['date']
    else:
        try:
            # Проверяем формат даты
            datetime.strptime(date_input, "%Y-%m-%d")
            date_value = date_input
        except ValueError:
            await update.message.reply_text(
                "❌ Ամսաթվի սխալ ձևաչափ: Օգտագործեք YYYY-MM-DD կամ ուղարկեք '+' ընթացիկ ամսաթվի համար:"
            )
            return DATE
    
    context.user_data['record']['date'] = date_value
    
    # Показываем модальное окно для выбора поставщика
    user_settings = get_user_settings(user_id)
    display_name = user_settings.get('display_name')
    
    keyboard = []
    if display_name:
        keyboard.append([InlineKeyboardButton(f"👤 Օգտագործել իմ անունը ({display_name})", callback_data="use_my_name")])
    keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել Ֆիրմայի անունը", callback_data="use_firm_name")])
    keyboard.append([InlineKeyboardButton("✏️ Մուտքագրել ձեռքով", callback_data="manual_input")])
    
    await update.message.reply_text(
        "🏪 Ընտրեք մատակարարի տեսակը:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SUPPLIER_CHOICE

async def use_my_name(update: Update, context: CallbackContext):
    """Использовать имя пользователя как поставщика"""
    query = update.callback_query
    await query.answer()
    
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
    await query.answer()
    
    context.user_data['record']['supplier'] = "Ֆ"
    
    await query.edit_message_text(
        f"✅ Մատակարար: Ֆ\n\n"
        f"🧭 Մուտքագրեք ուղղությունը:"
    )
    
    return DIRECTION

async def manual_input(update: Update, context: CallbackContext):
    """Ручной ввод поставщика"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("🏪 Մուտքագրեք մատակարարին:")
    
    return SUPPLIER_MANUAL

async def get_supplier_manual(update: Update, context: CallbackContext):
    """Получает поставщика в ручном режиме"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    supplier = update.message.text.strip()
    context.user_data['record']['supplier'] = supplier
    
    await update.message.reply_text(
        f"✅ Մատակարար: {supplier}\n\n"
        f"🧭 Մուտքագրեք ուղղությունը:"
    )
    
    return DIRECTION

async def get_direction(update: Update, context: CallbackContext):
    """Обрабатывает ввод направления"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    direction = update.message.text.strip()
    context.user_data['record']['direction'] = direction
    
    await update.message.reply_text(
        f"✅ Ուղղություն: {direction}\n\n"
        f"📝 Մուտքագրեք ծախսի նկարագրությունը:"
    )
    
    return DESCRIPTION

async def get_description(update: Update, context: CallbackContext):
    """Обрабатывает ввод описания"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    description = update.message.text.strip()
    context.user_data['record']['description'] = description
    
    await update.message.reply_text(
        f"✅ Նկարագրություն: {description}\n\n"
        f"💰 Մուտքագրեք գումարը:"
    )
    
    return AMOUNT

async def get_amount(update: Update, context: CallbackContext):
    """Обрабатывает ввод суммы и завершает создание записи"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    amount_input = update.message.text.strip()

    try:
        amount = float(amount_input)
        context.user_data['record']['amount'] = amount

        # Добавляем текущие активные таблицу и лист пользователя
        user_settings = get_user_settings(user_id)
        spreadsheet_id = user_settings.get('active_spreadsheet_id')
        sheet_name = user_settings.get('active_sheet_name')
        context.user_data['record']['spreadsheet_id'] = spreadsheet_id
        context.user_data['record']['sheet_name'] = sheet_name

        record = context.user_data['record']

        # Сохраняем в БД и Google Sheets
        db_success = add_record_to_db(record)
        sheet_success = add_record_to_sheet(spreadsheet_id, sheet_name, record)

        result_text = "✅ Գրառումն ավելացված է:\n\n"

        if db_success and sheet_success:
            result_text += "✅ Պահպանված է ՏԲ-ում և Google Sheets-ում"
        elif db_success:
            result_text += "✅ Պահպանված է ՏԲ-ում\n⚠️ Google Sheets-ում պահպանելու սխալ"
        elif sheet_success:
            result_text += "⚠️ ՏԲ-ում պահպանելու սխալ \n✅ Պահպանված է Google Sheets-ում"
        else:
            result_text += "❌ Պահպանելու սխալ ՏԲ-ում և Google Sheets-ում"

        if db_success or sheet_success:
            # Добавляем запись в отчеты пользователя
            users_data = load_users()
            user_id_str = str(user_id)
            if user_id_str in users_data:
                if 'reports' not in users_data[user_id_str]:
                    users_data[user_id_str]['reports'] = []
                
                # Добавляем ID новой записи
                users_data[user_id_str]['reports'].append(record['id'])
                save_users(users_data)
                
        result_text += "\n" + format_record_info(record) + "\n\n"

        keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record['id']}")]]
        await update.message.reply_text(result_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

        # Отправляем отчет
        user_info = {
            'id': user_id,
            'name': update.effective_user.full_name,
            'display_name': user_settings.get('display_name')
        }
        if record.get('skip_mode'):
            action = "Բացթողում"
        else:
            action = "Ավելացում"
        await send_report(context, action, record, user_info)
        
        # Очищаем данные пользователя
        context.user_data.clear()

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Գումարի սխալ ձևաչափ: Մուտքագրեք թիվ (օրինակ՝ 1000.50):")
        return AMOUNT

async def cancel_add_record(update: Update, context: CallbackContext):
    """Отменяет процесс добавления записи"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    await update.message.reply_text(
        "❌ Գրառման ավելացման գործողությունը չեղարկված է:",
        reply_markup=create_main_menu(user_id)
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext):
    """Отменяет текущую операцию"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    await update.message.reply_text(
        "❌ Գործողությունը չեղարկված է:",
        reply_markup=create_main_menu(user_id)
    )
    
    # Очищаем данные пользователя
    if context.user_data:
        context.user_data.clear()
    
    return ConversationHandler.END
