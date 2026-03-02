"""
Обработчики для добавления записей
"""
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ..states.conversation_states import DATE, SUPPLIER_CHOICE, DIRECTION, DESCRIPTION, AMOUNT, SUPPLIER_MANUAL
from ..keyboards.inline_keyboards import create_main_menu
from ...utils.config_utils import is_user_allowed, get_user_settings, update_user_settings, load_users, save_users, get_entity_by_index, get_entities_by_type
from ...utils.formatting import format_record_info
from ...database.database_manager import add_record_to_db
from ...google_integration.async_sheets_worker import add_record_async
from ...config.settings import ACTIVE_SPREADSHEET_ID, logger
from ...utils.report_manager import send_report
from ..handlers.translation_handlers import _


def _resolve_auto_direction(context: CallbackContext):
    """Возвращает направление для автоподстановки в flow сущностей."""
    fixed_direction = context.user_data.get('fixed_direction')
    if fixed_direction:
        return fixed_direction

    selected_entity_name = context.user_data.get('selected_entity_name')
    if selected_entity_name:
        context.user_data['fixed_direction'] = selected_entity_name
        return selected_entity_name

    selected_entity_type = context.user_data.get('selected_entity_type')
    selected_entity_index = context.user_data.get('selected_entity_index')
    if selected_entity_type is not None and selected_entity_index is not None:
        try:
            entity = get_entity_by_index(selected_entity_type, int(selected_entity_index))
            if entity and entity.get('name'):
                direction = entity.get('name')
                context.user_data['selected_entity_name'] = direction
                context.user_data['fixed_direction'] = direction
                return direction
        except Exception:
            pass

    return None


def _is_entity_expense_mode(context: CallbackContext) -> bool:
    """Определяет, что запись идет из ветки Ծախս -> Բրիգադ/Խանութ."""
    return bool(
        context.user_data.get('entity_expense_mode')
        or context.user_data.get('selected_entity_name')
        or (
            context.user_data.get('selected_entity_type') is not None
            and context.user_data.get('selected_entity_index') is not None
        )
    )


def _resolve_entity_direction_or_fallback(context: CallbackContext):
    """Возвращает направление для entity-mode; при необходимости использует fallback."""
    direction = _resolve_auto_direction(context)
    if direction:
        return direction

    direction = (
        context.user_data.get('selected_entity_name')
        or context.user_data.get('selected_entity_sheet_name')
        or context.user_data.get('selected_sheet_name')
    )
    if direction:
        context.user_data['fixed_direction'] = direction
        return direction

    return "—"


def _infer_direction_from_entity_target(spreadsheet_id: str, sheet_name: str):
    """Ищет направление сущности по паре spreadsheet_id + sheet_name."""
    if not spreadsheet_id or not sheet_name:
        return None

    for entity_type in ('brigade', 'shop'):
        entities = get_entities_by_type(entity_type)
        for entity in entities:
            entity_spreadsheet = entity.get('spreadsheet_id')
            entity_sheet = entity.get('sheet_name') or entity.get('name')
            if entity_spreadsheet == spreadsheet_id and entity_sheet == sheet_name:
                return entity.get('name')

    return None


async def start_add_record(update: Update, context: CallbackContext):
    """Начинает процесс добавления записи"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    logger.info(f"start_add_record called for user {user_id}, callback_data: {query.data}")
    
    if not is_user_allowed(user_id):
        await query.edit_message_text("❌ Ваш доступ запрещен:")
        return ConversationHandler.END
    
    # Очищаем только данные записи, сохраняя другие настройки
    context.user_data.pop('record', None)
    
    # Получаем имя листа из callback_data
    if query.data and query.data.startswith("add_record_sheet_"):
        sheet_name = query.data.replace("add_record_sheet_", "")
        logger.info(f"Extracted sheet name: {sheet_name}")
        # Сохраняем имя листа в context.user_data
        context.user_data['selected_sheet_name'] = sheet_name
    else:
        # Попытаемся получить из context.user_data
        sheet_name = context.user_data.get('selected_sheet_name')
        logger.warning(f"Sheet name not found in callback_data, obtained from context: {sheet_name}")
    
    if not sheet_name:
        # Если лист не выбран, показываем сообщение об ошибке и возвращаем в меню
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="add_record_menu")]]
        await query.edit_message_text(
            "❌ Պետք է նախ ընտրել թերթիկը:\n"
            "Կտտացնեք \"➕ Ավելացնել գրառում\" և ընտրեք թերթիկ",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    # Получаем настройки пользователя
    user_settings = get_user_settings(user_id)
    
    selected_spreadsheet_id = context.user_data.get('selected_spreadsheet_id') or ACTIVE_SPREADSHEET_ID

    # Проверяем настройки
    if not selected_spreadsheet_id:
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Նախ պետք է ընտրել աղյուսակը:\n"
            "Օգտագործեք 📊 Ընտրել աղյուսակ",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    # Устанавливаем выбранный лист как активный
    update_user_settings(user_id, {'active_sheet_name': sheet_name})
    
    # Генерируем ID и устанавливаем текущую дату
    record_id = "cb-" + str(uuid.uuid4())[:8]
    current_date = datetime.now().strftime("%Y-%m-%d")
    context.user_data['record'] = {
        'id': record_id,
        'date': current_date,
        'user_id': user_id
    }

    # Для сценариев Бригада/Магазин фиксируем направление из выбранной сущности
    if _is_entity_expense_mode(context):
        context.user_data['entity_expense_mode'] = True
        direction_value = _resolve_entity_direction_or_fallback(context)
        context.user_data['record']['direction'] = direction_value
    elif not context.user_data.get('fixed_direction'):
        inferred_direction = _infer_direction_from_entity_target(selected_spreadsheet_id, sheet_name)
        if inferred_direction:
            context.user_data['selected_entity_name'] = inferred_direction
            context.user_data['fixed_direction'] = inferred_direction
            context.user_data['record']['direction'] = inferred_direction
    
    # Сразу переходим к выбору поставщика
    display_name = user_settings.get('display_name')
    
    keyboard = []
    if display_name:
        keyboard.append([InlineKeyboardButton(f"👤 Օգտագործել իմ անունը ({display_name})", callback_data="use_my_name")])
    keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել Ֆիրմայի անունը", callback_data="use_firm_name")])
    # keyboard.append([InlineKeyboardButton("✏️ Մուտքագրել ձեռքով", callback_data="manual_input")])
    
    # Удаляем предыдущее сообщение (если есть)
    try:
        await query.delete_message()
    except Exception:
        pass
    sent_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"➕ Ավելացնել նոր գրառում\n"
            f"🆔 ID: <code>{record_id}</code>\n"
            f"📅 Ամսաթիվ: <b>{current_date}</b>\n"
            f"📋 Թերթիկ: <b>{sheet_name}</b>\n\n"
            f"🏪 Ընտրեք մատակարարի տեսակը:"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['last_bot_message_id'] = sent_msg.message_id if sent_msg else None
    return SUPPLIER_CHOICE

async def start_add_skip_record(update: Update, context: CallbackContext):
    """Начинает добавление записи пропуска"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Очищаем только данные записи, сохраняя другие настройки
    context.user_data.pop('record', None)
    
    if not is_user_allowed(user_id):
        await query.edit_message_text("❌ Ваш доступ запрещен:")
        return ConversationHandler.END

    # Получаем имя листа из callback_data
    if query.data and query.data.startswith("add_skip_sheet_"):
        sheet_name = query.data.replace("add_skip_sheet_", "")
        # Сохраняем имя листа в context.user_data
        context.user_data['selected_sheet_name'] = sheet_name
    else:
        # Попытаемся получить из context.user_data
        sheet_name = context.user_data.get('selected_sheet_name')
    
    if not sheet_name:
        # Если лист не выбран, показываем сообщение об ошибке и возвращаем в меню
        keyboard = [[InlineKeyboardButton(_("menu.back", user_id), callback_data="add_record_menu")]]
        await query.edit_message_text(
            "❌ Պետք է նախ ընտրել թերթիկը:\n"
            "Կտտացնեք \"➕ Ավելացնել բացթողում\" և ընտրեք թերթիկ",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    # Получаем настройки пользователя
    user_settings = get_user_settings(user_id)

    # Проверяем настройки
    if not ACTIVE_SPREADSHEET_ID:
        keyboard = [[InlineKeyboardButton(_("menu.back" , user_id), callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Նախ պետք է ընտրել աղյուսակը:\n"
            "Օգտագործեք � Ընտրել աղյուսակ",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

    # Устанавливаем выбранный лист как активный
    update_user_settings(user_id, {'active_sheet_name': sheet_name})

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
    # Удаляем предыдущее сообщение (если есть)
    try:
        await query.delete_message()
    except Exception:
        pass
    sent_msg = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            f"➕ Ավելացնել Բացթողում\n"
            f"🆔 ID: <code>{record_id}</code>\n"
            f"📋 Թերթիկ: <b>{sheet_name}</b>\n\n"
            f"📅 Մուտքագրեք ամսաթիվը (DD-MM-YYYY) կամ ուղարկեք <b>+</b>՝ ընթացիկ ամսաթվի համար:"
        ),
        parse_mode="HTML"
    )
    context.user_data['last_bot_message_id'] = sent_msg.message_id if sent_msg else None
    return DATE

async def get_date(update: Update, context: CallbackContext):
    """Обрабатывает ввод даты"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
        
    date_input = update.message.text.strip()

    # Проверяем формат даты
    if date_input == '+':
        date_value = context.user_data['record']['date']
    else:
        try:
            datetime.strptime(date_input, "%d-%m-%Y")
            date_value = date_input
        except ValueError:
            err_msg = await update.message.reply_text(
                "❌ Ամսաթվի սխալ ձևաչափ: Օգտագործեք DD-MM-YYYY կամ ուղարկեք '+' ընթացիկ ամսաթվի համար:"
            )
            # Сохраняем id ошибки и id сообщения пользователя для удаления
            context.user_data.setdefault('messages_to_delete', []).extend([
                err_msg.message_id,
                update.message.message_id
            ])
            return DATE
    # Преобразуем дату в формат YYYY-MM-DD
    if date_input == '+':
        date_value = context.user_data['record']['date']
    else:
        try:
            date_obj = datetime.strptime(date_input, "%d-%m-%Y")
            date_value = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            date_value = None
    if not date_value:
        err_msg = await update.message.reply_text(
            "❌ Ամսաթվի սխալ ձևաչափ: Օգտագործեք YYYY-MM-DD կամ ուղարկեք '+' ընթացիկ ամսաթվի համար:"
        )
        context.user_data.setdefault('messages_to_delete', []).extend([
            err_msg.message_id,
            update.message.message_id
        ])
        return DATE

    # Удаляем все сообщения, которые нужно удалить
    ids_to_delete = context.user_data.get('messages_to_delete', [])
    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception:
            pass
    context.user_data['messages_to_delete'] = []
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception:
        pass
    last_bot_msg_id = context.user_data.get('last_bot_message_id')
    if last_bot_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
        except Exception:
            pass

    # Сохраняем дату в формате YYYY-MM-DD
    context.user_data['record']['date'] = date_value

    # Показываем модальное окно для выбора поставщика
    user_settings = get_user_settings(user_id)
    display_name = user_settings.get('display_name')

    keyboard = []
    if display_name:
        keyboard.append([InlineKeyboardButton(f"👤 Օգտագործել իմ անունը ({display_name})", callback_data="use_my_name")])
    keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել Ֆիրմայի անունը", callback_data="use_firm_name")])

    sent_msg = await update.message.reply_text(
        "🏪 Ընտրեք մատակարարի տեսակը:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['last_bot_message_id'] = sent_msg.message_id if sent_msg else None
    context.user_data.setdefault('messages_to_delete', []).append(sent_msg.message_id)
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
    fixed_direction = _resolve_auto_direction(context)
    entity_expense_mode = _is_entity_expense_mode(context)
    if fixed_direction or entity_expense_mode:
        direction_value = _resolve_entity_direction_or_fallback(context)
        context.user_data['record']['direction'] = direction_value
        await query.edit_message_text(
            f"✅ Մատակարար: {display_name}\n"
            f"📝 Մուտքագրեք ծախսի <b>նկարագրությունը</b>:",
            parse_mode="HTML"
        )
        return DESCRIPTION

    await query.edit_message_text(
        f"✅ Մատակարար: {display_name}\n\n"
        f"🧭 Մուտքագրեք <b>ուղղությունը</b>:",
        parse_mode="HTML"
    )

    return DIRECTION

async def use_firm_name(update: Update, context: CallbackContext):
    """Использовать имя фирмы как поставщика"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['record']['supplier'] = "Ֆ"
    fixed_direction = _resolve_auto_direction(context)
    entity_expense_mode = _is_entity_expense_mode(context)
    if fixed_direction or entity_expense_mode:
        direction_value = _resolve_entity_direction_or_fallback(context)
        context.user_data['record']['direction'] = direction_value
        await query.edit_message_text(
            f"✅ Մատակարար: Ֆ\n"
            f"📝 Մուտքագրեք ծախսի <b>նկարագրությունը</b>:",
            parse_mode="HTML"
        )
        return DESCRIPTION

    await query.edit_message_text(
        f"✅ Մատակարար: Ֆ\n\n"
        f"🧭 Մուտքագրեք <b>ուղղությունը</b>:",
        parse_mode="HTML"
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

    # Удаляем сообщение пользователя и предыдущее сообщение бота (инструкцию)
    # Удаляем все сообщения, которые нужно удалить
    ids_to_delete = context.user_data.get('messages_to_delete', [])
    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception:
            pass
    context.user_data['messages_to_delete'] = []
    try:
        await update.message.delete()
    except Exception:
        pass
    last_bot_msg_id = context.user_data.get('last_bot_message_id')
    if last_bot_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
        except Exception:
            pass
    fixed_direction = _resolve_auto_direction(context)
    entity_expense_mode = _is_entity_expense_mode(context)
    if fixed_direction or entity_expense_mode:
        direction_value = _resolve_entity_direction_or_fallback(context)
        context.user_data['record']['direction'] = direction_value
        sent_msg = await update.message.reply_text(
            f"✅ Մատակարար: {supplier}\n"
            f"📝 Մուտքագրեք ծախսի <b>նկարագրությունը</b>:",
            parse_mode="HTML"
        )
        context.user_data['last_bot_message_id'] = sent_msg.message_id if sent_msg else None
        context.user_data.setdefault('messages_to_delete', []).append(sent_msg.message_id)
        return DESCRIPTION

    sent_msg = await update.message.reply_text(
        f"✅ Մատակարար: {supplier}\n\n"
        f"🧭 Մուտքագրեք <b>ուղղությունը</b>:",
        parse_mode="HTML"
    )
    context.user_data['last_bot_message_id'] = sent_msg.message_id if sent_msg else None
    context.user_data.setdefault('messages_to_delete', []).append(sent_msg.message_id)
    return DIRECTION

async def get_direction(update: Update, context: CallbackContext):
    """Обрабатывает ввод направления"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END

    fixed_direction = context.user_data.get('fixed_direction')
    if fixed_direction:
        context.user_data['record']['direction'] = fixed_direction

        ids_to_delete = context.user_data.get('messages_to_delete', [])
        for msg_id in ids_to_delete:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                pass
        context.user_data['messages_to_delete'] = []

        try:
            await update.message.delete()
        except Exception:
            pass

        sent_msg = await update.message.reply_text(
            f"✅ Ուղղություն: {fixed_direction}\n"
            f"📝 Մուտքագրեք ծախսի <b>նկարագրությունը</b>:",
            parse_mode="HTML"
        )
        context.user_data['last_bot_message_id'] = sent_msg.message_id if sent_msg else None
        context.user_data.setdefault('messages_to_delete', []).append(sent_msg.message_id)
        return DESCRIPTION
    
    direction = update.message.text.strip()
    context.user_data['record']['direction'] = direction

    # Удаляем все сообщения, которые нужно удалить
    ids_to_delete = context.user_data.get('messages_to_delete', [])
    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception:
            pass
    context.user_data['messages_to_delete'] = []
    try:
        await update.message.delete()
    except Exception:
        pass
    last_bot_msg_id = context.user_data.get('last_bot_message_id')
    if last_bot_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
        except Exception:
            pass
    sent_msg = await update.message.reply_text(
        f"📝 Մուտքագրեք ծախսի <b>նկարագրությունը</b>:",
        parse_mode="HTML"
    )
    context.user_data['last_bot_message_id'] = sent_msg.message_id if sent_msg else None
    context.user_data.setdefault('messages_to_delete', []).append(sent_msg.message_id)
    return DESCRIPTION

async def get_description(update: Update, context: CallbackContext):
    """Обрабатывает ввод описания"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    description = update.message.text.strip()
    context.user_data['record']['description'] = description

    # Удаляем все сообщения, которые нужно удалить
    ids_to_delete = context.user_data.get('messages_to_delete', [])
    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception:
            pass
    context.user_data['messages_to_delete'] = []
    try:
        await update.message.delete()
    except Exception:
        pass
    last_bot_msg_id = context.user_data.get('last_bot_message_id')
    if last_bot_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
        except Exception:
            pass
    sent_msg = await update.message.reply_text(
        f"✅ Նկարագրություն: {description}\n\n"
        f"💰 Մուտքագրեք <b>գումարը</b>:",
        parse_mode="HTML"
    )
    context.user_data['last_bot_message_id'] = sent_msg.message_id if sent_msg else None
    context.user_data.setdefault('messages_to_delete', []).append(sent_msg.message_id)
    return AMOUNT

async def get_amount(update: Update, context: CallbackContext):
    """Обрабатывает ввод суммы и завершает создание записи"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    amount_input = update.message.text.strip()

    # Удаляем сообщение пользователя и предыдущее сообщение бота (инструкцию)
    # Удаляем все сообщения, которые нужно удалить
    ids_to_delete = context.user_data.get('messages_to_delete', [])
    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception:
            pass
    context.user_data['messages_to_delete'] = []
    try:
        await update.message.delete()
    except Exception:
        pass
    last_bot_msg_id = context.user_data.get('last_bot_message_id')
    if last_bot_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
        except Exception:
            pass

    try:
        amount = float(amount_input)
        context.user_data['record']['amount'] = amount

        # Добавляем текущие активные таблицу и лист пользователя
        user_settings = get_user_settings(user_id)
        spreadsheet_id = context.user_data.get('selected_spreadsheet_id') or ACTIVE_SPREADSHEET_ID
        sheet_name = user_settings.get('active_sheet_name')
        context.user_data['record']['spreadsheet_id'] = spreadsheet_id
        context.user_data['record']['sheet_name'] = sheet_name
        context.user_data['record']['operation_type'] = context.user_data.get('operation_type', 'expense')
        context.user_data['record']['coefficient'] = context.user_data.get('coefficient', 1)

        record = context.user_data['record']

        # Сохраняем в БД 
        db_success = add_record_to_db(record)
        
        # Асинхронно добавляем в Google Sheets (не блокируем бота)
        add_record_async(spreadsheet_id, sheet_name, record)
        sheet_success = True  # Считаем успешным, так как задача добавлена в очередь

        if record.get('skip_mode'):
            result_text = "🟡 Բացթողումը ավելացված է:\n\n"
        else:
            result_text = "✅ Գրառումն ավելացված է:\n\n"

        if db_success and sheet_success:
            logger.info(f"Record saved to DB and added to Google Sheets queue - ID: {record['id']}")
        elif db_success:
            logger.info(f"Record saved to DB - ID: {record['id']}")
        else:
            logger.error(f"Failed to save record to DB - ID: {record['id']}")

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
        sent_msg = await update.message.reply_text("❌ Գումարի սխալ ձևաչափ: Մուտքագրեք թիվ (օրինակ՝ 1000.50):")
        context.user_data.setdefault('messages_to_delete', []).extend([
            sent_msg.message_id,
            update.message.message_id
        ])
        return AMOUNT

async def cancel_add_record(update: Update, context: CallbackContext):
    """Отменяет процесс добавления записи"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    # Обрабатываем как кнопку, так и команду
    if update.callback_query:
        # Если это callback от кнопки отмены в процессе редактирования
        if update.callback_query.data and update.callback_query.data.startswith("cancel_edit_"):
            record_id = update.callback_query.data.replace("cancel_edit_", "")
            keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record_id}")]]
            await update.callback_query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.edit_message_text(
                "❌ Գրառման ավելացման գործողությունը չեղարկված է:",
                reply_markup=create_main_menu(user_id)
            )
    else:
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
    
    # Обрабатываем как кнопку, так и команду
    if update.callback_query:
        # Если это callback от кнопки отмены в процессе редактирования
        if update.callback_query.data and update.callback_query.data.startswith("cancel_edit_"):
            record_id = update.callback_query.data.replace("cancel_edit_", "")
            keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record_id}")]]
            await update.callback_query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.edit_message_text(
                "❌ Գործողությունը չեղարկված է:",
                reply_markup=create_main_menu(user_id)
            )
    else:
        await update.message.reply_text(
            "❌ Գործողությունը չեղարկված է:",
            reply_markup=create_main_menu(user_id)
        )
    
    # Очищаем данные пользователя
    if context.user_data:
        context.user_data.clear()
    
    return ConversationHandler.END

async def start_record_conversation(update: Update, context: CallbackContext):
    """Начинает ConversationHandler для добавления записи"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    logger.info(f"start_record_conversation called for user {user_id}")
    
    if not is_user_allowed(user_id):
        await query.edit_message_text("❌ Ваш доступ запрещен:")
        return ConversationHandler.END
    
    await query.answer()
    
    # Импортируем здесь, чтобы избежать циклического импорта
    from .button_handlers import show_sheet_selection_for_add_record
    
    # Показываем выбор листа
    await show_sheet_selection_for_add_record(update, context, "record")
    
    # Остаемся в конversation, ожидая выбора листа
    return ConversationHandler.END  # На самом деле, мы должны ждать следующего callback'а

async def start_record_selection(update: Update, context: CallbackContext):
    """Начинает выбор листа для добавления записи в ConversationHandler"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    logger.info(f"start_record_selection called for user {user_id}")
    
    if not is_user_allowed(user_id):
        await query.edit_message_text("❌ Ваш доступ запрещен:")
        return ConversationHandler.END
    
    await query.answer()
    
    # Импортируем здесь, чтобы избежать циклического импорта
    from .button_handlers import show_sheet_selection_for_add_record
    
    # Показываем выбор листа
    await show_sheet_selection_for_add_record(update, context, "record")
    
    # Остаемся в ConversationHandler, ожидая выбора листа через entry points
    # Переходим в состояние выбора листа
    from ..states.conversation_states import SHEET_SELECTION
    return SHEET_SELECTION

async def start_skip_record_selection(update: Update, context: CallbackContext):
    """Начинает выбор листа для добавления упущения в ConversationHandler"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    logger.info(f"start_skip_record_selection called for user {user_id}")
    
    if not is_user_allowed(user_id):
        await query.edit_message_text("❌ Ваш доступ запрещен:")
        return ConversationHandler.END
    
    await query.answer()
    
    # Импортируем здесь, чтобы избежать циклического импорта
    from .button_handlers import show_sheet_selection_for_add_record
    
    # Показываем выбор листа для упущений
    await show_sheet_selection_for_add_record(update, context, "skip")
    
    # Остаемся в ConversationHandler, ожидая выбора листа через entry points
    # Переходим в состояние выбора листа
    from ..states.conversation_states import SHEET_SELECTION
    return SHEET_SELECTION


async def start_add_entity_record(update: Update, context: CallbackContext, entity: dict):
    """Запускает стандартный flow добавления записи с заранее заданными spreadsheet/sheet/direction."""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_user_allowed(user_id):
        await query.edit_message_text("❌ Ваш доступ запрещен:")
        return ConversationHandler.END

    sheet_name = entity.get('sheet_name') or entity.get('name')
    spreadsheet_id = entity.get('spreadsheet_id')
    direction = entity.get('name')

    if not spreadsheet_id or not sheet_name:
        await query.edit_message_text("❌ Для выбранного направления не настроены spreadsheet_id/sheet_name.")
        return ConversationHandler.END

    context.user_data['selected_spreadsheet_id'] = spreadsheet_id
    context.user_data['selected_sheet_name'] = sheet_name
    context.user_data['fixed_direction'] = direction
    context.user_data['operation_type'] = 'expense'
    context.user_data['coefficient'] = 1

    return await start_add_record(update, context)
