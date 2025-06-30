import json
import logging
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, CallbackContext
from google_connector import (get_worksheets_info, add_record_to_sheet, 
                            update_record_in_sheet, delete_record_from_sheet, 
                            get_record_by_id, get_all_spreadsheets, get_spreadsheet_info, initialize_and_sync_sheets)
from database import init_db, add_record_to_db, update_record_in_db, delete_record_from_db, get_record_from_db, get_db_stats
import uuid

# === Конфигурация ===
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise ValueError("TOKEN не найден в переменных окружения! Добавьте его в .env файл")

CONFIG_FILE = 'config.json'
ADMIN_IDS = [714158870]  # Добавьте ID администраторов

# Состояния для ConversationHandler
(DATE, SUPPLIER, DIRECTION, DESCRIPTION, AMOUNT, 
 EDIT_FIELD, EDIT_VALUE, CONFIRM_DELETE) = range(8)

# === Настройка логирования ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Вспомогательные функции ===

def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            'active_spreadsheet_id': None,
            'active_sheet_name': None,
            'log_chat_id': None
        }

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def get_active_spreadsheet_id():
    return load_config().get('active_spreadsheet_id')

def get_active_sheet_name():
    return load_config().get('active_sheet_name')

def get_log_chat_id():
    return load_config().get('log_chat_id')

def set_active_spreadsheet(spreadsheet_id: str, sheet_name: str = None):
    config = load_config()
    config['active_spreadsheet_id'] = spreadsheet_id
    config['active_sheet_name'] = sheet_name
    save_config(config)

def set_log_chat(chat_id: int):
    config = load_config()
    config['log_chat_id'] = chat_id
    save_config(config)

async def send_to_log_chat(context: CallbackContext, message: str):
    """Отправляет сообщение в лог-чат"""
    log_chat_id = get_log_chat_id()
    if log_chat_id:
        try:
            await context.bot.send_message(chat_id=log_chat_id, text=f"📝 LOG: {message}")
        except Exception as e:
            logger.error(f"Ошибка отправки в лог-чат: {e}")

def create_main_menu():
    """Создает основное меню бота"""
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել գրառում", callback_data="add_record")],
        [InlineKeyboardButton("📋 Ընտրել թերթիկ", callback_data="select_sheet")],
        [InlineKeyboardButton("📊 Կարգավիճակ", callback_data="status")],
        [InlineKeyboardButton("📈 Վիճակագրություն", callback_data="stats")],
        [InlineKeyboardButton("📊 Ընտրել աղյուսակ", callback_data="select_spreadsheet")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_edit_menu(record_id: str):
    """Создает меню для редактирования записи"""
    keyboard = [
        [InlineKeyboardButton("📅 Ամսաթիվ", callback_data=f"edit_date_{record_id}")],
        [InlineKeyboardButton("🏪 Մատակարար", callback_data=f"edit_supplier_{record_id}")],
        [InlineKeyboardButton("🧭 Ուղղություն", callback_data=f"edit_direction_{record_id}")],
        [InlineKeyboardButton("📝 Նկարագրություն", callback_data=f"edit_description_{record_id}")],
        [InlineKeyboardButton("💰 Գումար", callback_data=f"edit_amount_{record_id}")],
        [InlineKeyboardButton("🗑 Ջնջել", callback_data=f"delete_{record_id}")],
        [InlineKeyboardButton("❌ Չեղարկել", callback_data=f"cancel_edit_{record_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_record_info(record: dict) -> str:
    """Форматирует информацию о записи"""
    return (
        f"🆔 ID: <code>{record.get('id', 'N/A')}</code>\n"
        f"📅 Ամսաթիվ: <b>{record.get('date', 'N/A')}</b>\n"
        f"🏪 Մատակարար: <b>{record.get('supplier', 'N/A')}</b>\n"
        f"🧭 Ուղղություն: <b>{record.get('direction', 'N/A')}</b>\n"
        f"📝 Նկարագրություն: <b>{record.get('description', 'N/A')}</b>\n"
        f"💰 गумار: <b>{record.get('amount', 0):,.2f}</b>\n"
        f"📊 Աղյուսակ: <code>{record.get('spreadsheet_id', '—')}</code>\n"
        f"📋 Թերթիկ: <code>{record.get('sheet_name', '—')}</code>"
    )


# === Обработчики команд ===

async def start(update: Update, context: CallbackContext):
    # Инициализируем базу данных при запуске
    init_db()
    
    await update.message.reply_text(
        "👋 Բարի գալուստ ծախսերի հաշվառման բոտ!\n\n"
        "Ֆունկցիաներ:\n"
        "• ➕ Գրառումների ավելացում Google Sheets-ում\n"
        "• ✏️ Գրառումների խմբագրում և ջնջում\n"
        "• 📊 Տվյալների բազայի հետ համաժամեցում\n"
        "• 📝 Գործողությունների մատյանավարում\n\n"
        "Հրամաններ:\n"
        "/menu - հիմնական ցանկ\n"
        "/set_log - մատյանի չատի կարգավորում (միայն ադմիններ)\n"
        "/set_sheet - Google Sheet ID-ի կարգավորում",
        reply_markup=create_main_menu()
    )

async def menu_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📋 Հիմնական ցանկ:",
        reply_markup=create_main_menu()
    )

async def set_log_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and len(ADMIN_IDS) > 0:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու իրավունք:")
        return
    
    chat_id = update.effective_chat.id
    set_log_chat(chat_id)
    await update.message.reply_text(
        f"✅ Մատյանի չատը կարգավորված է!\n"
        f"Chat ID: <code>{chat_id}</code>\n"
        f"Բոլոր մատյանները կուղարկվեն այս չատին:",
        parse_mode="HTML"
    )
    await send_to_log_chat(context, f"Մատյանի չատը ակտիվացված է: Chat ID: {chat_id}")

async def set_sheet_command(update: Update, context: CallbackContext):
    """Команда для установки ID Google Spreadsheet"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and len(ADMIN_IDS) > 0:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու իրավունք:")
        return
    
    # Получаем аргументы команды
    args = context.args
    if not args:
        await update.message.reply_text(
            "📊 Google Spreadsheet կարգավորելու համար օգտագործեք:\n"
            "<code>/set_sheet YOUR_SPREADSHEET_ID</code>\n\n"
            "ID-ն կարող եք գտնել աղյուսակի URL-ում:\n"
            "https://docs.google.com/spreadsheets/d/<b>SPREADSHEET_ID</b>/edit",
            parse_mode="HTML"
        )
        return
    
    spreadsheet_id = args[0].strip()
    
    # Проверяем доступность таблицы
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        if not sheets_info:
            await update.message.reply_text("❌ Չհաջողվեց աղյուսակին մուտք գործել: Ստուգեք ID-ն և մուտքի իրավունքները:")
            return
        
        # Сохраняем ID таблицы
        set_active_spreadsheet(spreadsheet_id)
        
        await update.message.reply_text(
            f"✅ Google Spreadsheet միացված է!\n"
            f"📊 Անվանում: <b>{spreadsheet_title}</b>\n"
            f"🆔 ID: <code>{spreadsheet_id}</code>\n"
            f"📋 Գտնված թերթիկներ: {len(sheets_info)}\n\n"
            f"Այժմ ընտրեք աշխատանքային թերթիկը /menu → 📋 Ընտրել թերթիկ",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Միացված է Google Spreadsheet: {spreadsheet_title} (ID: {spreadsheet_id})")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Աղյուսակին միացման սխալ:\n<code>{str(e)}</code>\n\n"
            f"Համոզվեք, որ:\n"
            f"• Աղյուսակի ID-ն ճիշտ է\n"
            f"• Ծառայության հաշիվը մուտք ունի աղյուսակին\n"
            f"• Credentials ֆայլը ճիշտ է",
            parse_mode="HTML"
        )

# === Обработчики кнопок ===

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "add_record":
        return await start_add_record(update, context)
    elif data == "select_spreadsheet":
        return await select_spreadsheet_menu(update, context)
    elif data == "select_sheet":
        return await select_sheet_menu(update, context)
    elif data == "status":
        return await show_status(update, context)
    elif data == "stats":
        return await show_stats(update, context)
    elif data.startswith("spreadsheet_"):
        return await select_spreadsheet(update, context)
    elif data.startswith("sheet_"):
        return await select_sheet(update, context)
    elif data.startswith("final_sheet_"):
        return await select_final_sheet(update, context)
    elif data.startswith("edit_"):
        return await handle_edit_button(update, context)
    elif data.startswith("delete_"):
        return await handle_delete_button(update, context)
    elif data.startswith("confirm_delete_"):
        return await confirm_delete(update, context)
    elif data.startswith("cancel_edit_"):
        record_id = data.replace("cancel_edit_", "")
        keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record_id}")]]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data == "back_to_menu":
        await query.edit_message_text("📋 Հիմնական ցանկ:", reply_markup=create_main_menu())

async def show_status(update: Update, context: CallbackContext):
    query = update.callback_query
    config = load_config()
    
    spreadsheet_id = config.get('active_spreadsheet_id')
    sheet_name = config.get('active_sheet_name')
    log_chat_id = config.get('log_chat_id')
    
    status_text = "📊 Ներկայիս կարգավիճակ:\n\n"
    
    if spreadsheet_id:
        status_text += f"✅ Միացված է աղյուսակ: <code>{spreadsheet_id[:10]}...</code>\n"
        if sheet_name:
            status_text += f"📋 Ակտիվ թերթիկ: <code>{sheet_name}</code>\n"
        else:
            status_text += "⚠️ Թերթիկը ընտրված չէ\n"
    else:
        status_text += "❌ Աղյուսակը միացված չէ\n"
    
    if log_chat_id:
        status_text += f"📝 Մատյանի չատ: <code>{log_chat_id}</code>\n"
    else:
        status_text += "📝 Մատյանի չատը կարգավորված չէ\n"
    
    # Добавляем кнопку "Назад"
    keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
    
    await query.edit_message_text(
        status_text, 
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_stats(update: Update, context: CallbackContext):
    """Показывает статистику базы данных"""
    query = update.callback_query
    
    stats = get_db_stats()
    if stats:
        stats_text = (
            f"📈 Տվյալների բազայի վիճակագրություն:\n\n"
            f"📝 Ընդհանուր գրառումներ: {stats['total_records']}\n"
            f"💰 Ընդհանուր գումար: {stats['total_amount']:,.2f}\n"
            f"📅 Վերջին 30 օրվա ընթացքում: {stats['recent_records']} գրառում"
        )
    else:
        stats_text = "❌ Վիճակագրություն ստանալու սխալ"
    
    keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
    
    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def select_sheet_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    
    spreadsheet_id = get_active_spreadsheet_id()
    if not spreadsheet_id:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Նախ պետք է միացնել աղյուսակը:\n"
            "Օգտագործեք /set_sheet հրամանը",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        
        if not sheets_info:
            keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
            await query.edit_message_text(
                "❌ Աղյուսակում թերթիկներ չկան:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        keyboard = []
        for info in sheets_info:
            keyboard.append([InlineKeyboardButton(
                f"📋 {info['title']}", 
                callback_data=f"sheet_{info['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            f"📋 Ընտրեք թերթիկը <b>{spreadsheet_title}</b> աղյուսակից:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            f"⚠️ Սխալ: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def select_sheet(update: Update, context: CallbackContext):
    """Выбирает активный лист"""
    query = update.callback_query
    sheet_name = query.data.replace("sheet_", "")
    
    # Сохраняем выбранный лист
    spreadsheet_id = get_active_spreadsheet_id()
    set_active_spreadsheet(spreadsheet_id, sheet_name)
    
    await query.edit_message_text(
        f"✅ Ընտրված է թերթիկ: <b>{sheet_name}</b>\n\n"
        f"Այժմ կարող եք գրառումներ ավելացնել!",
        parse_mode="HTML",
        reply_markup=create_main_menu()
    )
    
    await send_to_log_chat(context, f"Ընտրված է ակտիվ թերթիկ: {sheet_name}")

async def initialize_sheets_command(update: Update, context: CallbackContext):
    """Команда инициализации всех Google Sheets — только для админов"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու իրավունք:")
        return

    try:
        from google_connector import initialize_and_sync_sheets
        initialize_and_sync_sheets()
        await update.message.reply_text("✅ Բոլոր աղյուսակները հաջողությամբ մշակվեցին, ID-ները ավելացվեցին և բազան համաժամեցվեց:")
        await send_to_log_chat(context, "✅ Կատարվել է /initialize_sheets հրամանը — բոլոր աղյուսակները թարմացվել են:")
    except Exception as e:
        await update.message.reply_text(f"❌ Աղյուսակների նախաստեղծման սխալ: {e}")

# === Добавление записи ===

async def start_add_record(update: Update, context: CallbackContext):
    query = update.callback_query
    
    # Проверяем настройки
    if not get_active_spreadsheet_id() or not get_active_sheet_name():
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Նախ պետք է ընտրել աշխատանքային թերթիկը:\n"
            "Օգտագործեք 📋 Ընտրել թերթիկ",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    # Генерируем ID и устанавливаем текущую дату
    record_id = str(uuid.uuid4())[:8]
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    context.user_data['record'] = {
        'id': record_id,
        'date': current_date
    }
    
    await query.edit_message_text(
        f"➕ Նոր գրառման ավելացում\n"
        f"🆔 ID: <code>{record_id}</code>\n\n"
        f"📅 Ամսաթիվ (լռությամբ: {current_date})\n"
        f"Մուտքագրեք ամսաթիվը YYYY-MM-DD ֆորմատով կամ ուղարկեք '+' ընթացիկ ամսաթիվն օգտագործելու համար:",
        parse_mode="HTML"
    )
    
    return DATE

async def get_date(update: Update, context: CallbackContext):
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
                "❌ Ամսաթվի սխալ ֆորմատ: Օգտագործեք YYYY-MM-DD կամ ուղարկեք '+' ընթացիկ ամսաթվի համար:"
            )
            return DATE
    
    context.user_data['record']['date'] = date_value
    
    await update.message.reply_text(
        f"✅ Ամսաթիվ: {date_value}\n\n"
        f"🏪 Մուտքագրեք մատակարարը:"
    )
    
    return SUPPLIER

async def get_supplier(update: Update, context: CallbackContext):
    supplier = update.message.text.strip()
    context.user_data['record']['supplier'] = supplier
    
    await update.message.reply_text(
        f"✅ Մատակարար: {supplier}\n\n"
        f"🧭 Մուտքագրեք ուղղությունը:"
    )
    
    return DIRECTION

async def get_direction(update: Update, context: CallbackContext):
    direction = update.message.text.strip()
    context.user_data['record']['direction'] = direction
    
    await update.message.reply_text(
        f"✅ Ուղղություն: {direction}\n\n"
        f"📝 Մուտքագրեք ծախսի նկարագրությունը:"
    )
    
    return DESCRIPTION

async def get_description(update: Update, context: CallbackContext):
    description = update.message.text.strip()
    context.user_data['record']['description'] = description
    
    await update.message.reply_text(
        f"✅ Նկարագրություն: {description}\n\n"
        f"💰 Մուտքագրեք գումարը:"
    )
    
    return AMOUNT

async def get_amount(update: Update, context: CallbackContext):
    amount_input = update.message.text.strip()

    try:
        amount = float(amount_input)
        context.user_data['record']['amount'] = amount

        # Добавляем текущие активные таблицу и лист
        spreadsheet_id = get_active_spreadsheet_id()
        sheet_name = get_active_sheet_name()
        context.user_data['record']['spreadsheet_id'] = spreadsheet_id
        context.user_data['record']['sheet_name'] = sheet_name

        record = context.user_data['record']

        db_success = add_record_to_db(record)
        sheet_success = add_record_to_sheet(spreadsheet_id, sheet_name, record)

        result_text = "✅ Գրառումը ավելացվեց!\n\n"
        result_text += format_record_info(record) + "\n\n"

        if db_success and sheet_success:
            result_text += "✅ Պահպանված է ՏԲ-ում և Google Sheets-ում"
        elif db_success:
            result_text += "✅ Պահպանված է ՏԲ-ում\n⚠️ Google Sheets-ում պահպանման սխալ"
        elif sheet_success:
            result_text += "⚠️ ՏԲ-ում պահպանման սխալ\n✅ Պահpանված է Google Sheets-ում"
        else:
            result_text += "❌ ՏԲ-ում և Google Sheets-ում պահպանման սխալ"

        keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record['id']}")]]
        await update.message.reply_text(result_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))

        await send_to_log_chat(context, f"Ավելացվել է նոր գրառում ID: {record['id']}, գումար: {amount}")
        context.user_data.clear()

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Գումարի սխալ ֆորմատ: Մուտքագրեք թիվ (օրինակ: 1000.50):")
        return AMOUNT


# === Редактирование записей ===

async def handle_edit_button(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопок редактирования"""
    query = update.callback_query
    data = query.data
    
    if data.startswith("edit_record_"):
        # Показываем меню редактирования
        record_id = data.replace("edit_record_", "")
        return await show_edit_menu(update, context, record_id)
    
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
        
        await query.edit_message_text(
            f"✏️ Խմբագրում ID: <code>{record_id}</code> գրառման\n\n"
            f"Մուտքագրեք նոր արժեքը '{field_names.get(field, field)}' դաշտի համար:",
            parse_mode="HTML"
        )
        
        return EDIT_VALUE

async def show_edit_menu(update: Update, context: CallbackContext, record_id: str):
    """Показывает меню редактирования записи"""
    query = update.callback_query
    
    # Получаем запись из базы данных
    record = get_record_from_db(record_id)
    if not record:
        await query.edit_message_text("❌ Գրառումը չի գտնվել:")
        return ConversationHandler.END
    
    text = "✏️ Գրառման խմբագրում:\n\n"
    text += format_record_info(record)
    text += "\n\nԸնտրեք խմբագրման դաշտը:"
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=create_edit_menu(record_id)
    )

async def show_edit_menu_cancel(update: Update, context: CallbackContext, record_id: str):
    """Показывает меню редактирования записи (cancel)"""
    query = update.callback_query
    
    # Получаем запись из базы данных
    record = get_record_from_db(record_id)
    if not record:
        await query.edit_message_text("❌ Գրառումը չի գտնվել:")
        return ConversationHandler.END
    
    
    text += "✏️ Գրառման խմբագրում:\n\n"
    text += format_record_info(record)
    text += "\n\nԽմբագրման համար ընտրեք դաշտը:"
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=create_edit_menu(record_id)
    )

async def get_edit_value(update: Update, context: CallbackContext):
    """Получает новое значение для редактируемого поля"""
    new_value = update.message.text.strip()
    record_id = context.user_data.get('edit_record_id')
    field = context.user_data.get('edit_field')
    
    if not record_id or not field:
        await update.message.reply_text("❌ Խմբագրման սխալ:")
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
    record = get_record_from_db(record_id)
    spreadsheet_id = record.get('spreadsheet_id')
    sheet_name = record.get('sheet_name')
    sheet_success = update_record_in_sheet(spreadsheet_id, sheet_name, record_id, field, new_value)
    
     # Обновляем в базе данных
    db_success = update_record_in_db(record_id, field, new_value)
    
    # Результат
    if db_success and sheet_success:
        result_text = f"✅ '{field}' դաշտը թարմացվել է '{new_value}' արժեքով"
        result_text += "\n" + format_record_info(record) # Добавляем кнопки для редактирования
        
        
    elif db_success:
        result_text = f"✅ '{field}' դաշտը թարմացվել է տվյալների բազայում\n⚠️ Google Sheets-ում թարմացման սխալ"
    elif sheet_success:
        result_text = f"⚠️ Տվյալների բազայում թարմացման սխալ\n✅ '{field}' դաշտը թարմացվել է Google Sheets-ում"
    else:
        result_text = f"❌ '{field}' դաշտի թարմացման սխալ"
    keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record['id']}")]]
    await update.message.reply_text(result_text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    
    # Отправляем в лог-чат
    await send_to_log_chat(context, f"Թարմացվել է գրառում ID: {record_id}, դաշտ: {field}, նոր արժեք: {new_value}")
    
    # Очищаем данные пользователя
    context.user_data.clear()
    
    return ConversationHandler.END

# === Удаление записей ===

async def handle_delete_button(update: Update, context: CallbackContext):
    """Обрабатывает нажатие кнопки удаления"""
    query = update.callback_query
    record_id = query.data.replace("delete_", "")
    
    # Получаем информацию о записи
    record = get_record_from_db(record_id)
    if not record:
        await query.edit_message_text("❌ Գրառումը չի գտնվել:")
        return ConversationHandler.END
    
    text = "🗑 Ջնջման հաստատում:\n\n"
    text += format_record_info(record)
    text += "\n\n⚠️ Այս գործողությունը հնարավոր չէ չեղարկել!"
    
    keyboard = [
        [InlineKeyboardButton("🗑 Այո, ջնջել", callback_data=f"confirm_delete_{record_id}")],
        [InlineKeyboardButton("❌ Չեղարկել", callback_data="cancel_edit")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def confirm_delete(update: Update, context: CallbackContext):
    """Подтверждает удаление записи"""
    query = update.callback_query
    record_id = query.data.replace("confirm_delete_", "")
    
     # Удаляем из Google Sheets
    record = get_record_from_db(record_id)
    spreadsheet_id = record.get('spreadsheet_id')
    sheet_name = record.get('sheet_name')
    
    # Удаляем из базы данных
    db_success = delete_record_from_db(record_id)
    
   
    sheet_success = delete_record_from_sheet(spreadsheet_id, sheet_name, record_id)
    
    # Результат
    # Результат
    if db_success and sheet_success:
        result_text = f"✅ Գրառում ID: <code>{record_id}</code> ջնջվել է"
    elif db_success:
        result_text = f"✅ Գրառումը ջնջվել է տվյալների բազայից\n⚠️ Google Sheets-ից ջնջման սխալ"
    elif sheet_success:
        result_text = f"⚠️ Տվյալների բազայից ջնջման սխալ\n✅ Գրառումը ջնջվել է Google Sheets-ից"
    else:
        result_text = f"❌ Գրառում ID: <code>{record_id}</code> ջնջման սխալ"
    
    await query.edit_message_text(
        result_text,
        parse_mode="HTML",
        reply_markup=create_main_menu()
    )
    
    # Отправляем в лог-чат
    await send_to_log_chat(context, f"Ջնջվել է գրառում ID: {record_id}")
    
    return ConversationHandler.END

# === Обработчик отмены ===

async def cancel(update: Update, context: CallbackContext):
    """Отменяет текущую операцию"""
    await update.message.reply_text(
        "❌ Գործողությունը չեղարկվել է:",
        reply_markup=create_main_menu()
    )
    context.user_data.clear()
    return ConversationHandler.END

# === Обработчик ошибок ===

async def error_handler(update: object, context: CallbackContext) -> None:
    """Обрабатывает ошибки"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Отправляем ошибку в лог-чат
    if context.error:
        await send_to_log_chat(context, f"ՍԽԱԼ: {str(context.error)}")

# === Команда поиска записей ===

async def search_command(update: Update, context: CallbackContext):
    """Команда поиска записей"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "🔍 Գրառումների որոնում:\n"
            "Օգտագործեք: <code>/search [որոնման տեքստ]</code>\n\n"
            "Որոնումը կատարվում է հետևյալ դաշտերում: մատակարար, ուղղություն, նկարագրություն",
            parse_mode="HTML"
        )
        return
    
    query = " ".join(args)
    
    try:
        from database import search_records
        records = search_records(query, limit=25)
        
        if not records:
            await update.message.reply_text(
                f"🔍 '<b>{query}</b>' հարցման համար ոչինչ չի գտնվել:",
                parse_mode="HTML"
            )
            return
        
        result_text = f"🔍 Գտնվել է {len(records)} գրառում '<b>{query}</b>' հարցման համար:\n\n"
        
        for i, record in enumerate(records, 1):
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   📝 {record['description'][:50]}{'...' if len(record['description']) > 50 else ''}\n"
            result_text += f"   📋 {record['sheet_name']}\n\n"
        
        # Если записей много, предупреждаем
        if len(records) == 25:
            result_text += "ℹ️ Ցուցադրված են առաջին 25 արդյունքները: Ճշգրտեք հարցումը ավելի ճշգրիտ որոնման համար:"
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Որոնման սխալ: {e}")

# === Команда экспорта данных ===

async def export_command(update: Update, context: CallbackContext):
    """Команда экспорта данных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and len(ADMIN_IDS) > 0:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու իրավունք:")
        return
    
    try:
        from database import backup_db_to_dict
        backup_data = backup_db_to_dict()
        
        if not backup_data:
            await update.message.reply_text("❌ Պահեստային պատճենի ստեղծման սխալ:")
            return
        
        # Создаем JSON файл
        import json
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        # Отправляем файл
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📤 Տվյալների բազայի պահեստային պատճեն\n"
                       f"📊 Գրառումներ: {backup_data['stats']['total_records']}\n"
                       f"💰 Ընդհանուր գումար: {backup_data['stats']['total_amount']:,.2f}\n"
                       f"📅 Ստեղծման ամսաթիվ: {backup_data['backup_date']}"
            )
        
        # Удаляем временный файл
        os.remove(filename)
        
        await send_to_log_chat(context, f"Ստեղծվել է պահեստային պատճեն: {backup_data['stats']['total_records']} գրառում")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Արտահանման սխալ: {e}")

# === Команда показа последних записей ===

async def recent_command(update: Update, context: CallbackContext):
    """Показывает последние записи"""
    try:
        from database import get_all_records
        
        # Получаем количество записей из аргументов или по умолчанию 5
        args = context.args
        limit = 5
        if args:
            try:
                limit = min(int(args[0]), 1000)  # Максимум 1000 записей
            except ValueError:
                pass
        
        records = get_all_records(limit=limit)
        
        if not records:
            await update.message.reply_text("📝 Տվյալների բազայում գրառումներ չկան:")
            return
        
        result_text = f"📝 Վերջին {len(records)} գրառում:\n\n"
        
        for i, record in enumerate(records, 1):
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   🧭 {record['direction']}\n"
            result_text += f"   📝 {record['description']}\n"
            result_text += f"   📊 <code>{record['spreadsheet_id']}</code>\n"
            result_text += f"   📋  <code>{record['sheet_name']}</code>\n\n"
            
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Գրառումների ստացման սխալ: {e}")

# === Команда информации о записи ===

async def info_command(update: Update, context: CallbackContext):
    """Показывает детальную информацию о записи по ID"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "ℹ️ Գրառման մասին տեղեկություն:\n"
            "Օգտագործեք: <code>/info [գրառման ID]</code>",
            parse_mode="HTML"
        )
        return
    
    record_id = args[0].strip()
    
    try:
        record = get_record_from_db(record_id)
        
        if not record:
            await update.message.reply_text(
                f"❌ <code>{record_id}</code> ID-ով գրառում չի գտնվել:",
                parse_mode="HTML"
            )
            return
        
        result_text = "ℹ️ Գրառման մանրամասն տեղեկություն:\n\n"
        result_text += format_record_info(record)
        result_text += f"\n\n📅 Ստեղծվել է: {record.get('created_at', 'N/A')}"
        result_text += f"\n🔄 Թարմացվել է: {record.get('updated_at', 'N/A')}"
        
        # Создаем кнопку редактирования
        keyboard = [[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record_id}")]]
        
        await update.message.reply_text(
            result_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Տեղեկության ստացման սխալ: {e}")

# === Команда помощи ===

async def help_command(update: Update, context: CallbackContext):
    """Показывает справку по командам"""
    help_text = (
        "📖 <b>Հրամանների ուղեցույց:</b>\n\n"

        "<b>Հիմնական հրամաններ:</b>\n"
        "/start – բոտի գործարկում և հիմնական մենյու\n"
        "/menu – ցույց տալ գլխավոր մենյուն\n"
        "/help – այս ուղեցույցը\n\n"

        "<b>Գրառումների կառավարում:</b>\n"
        "/recent [N] – ցույց տալ վերջին N գրառումները (լռությամբ 5)\n"
        "/search [տեքստ] – գրառումների որոնում տեքստով\n"
        "/info [ID] – գրառման մանրամասն տեղեկություն\n\n"

        "<b>Ադմինիստրատորական հրամաններ:</b>\n"
        "/initialize_sheets – Google Sheets-ում աղյուսակների նախնական կարգավորում\n"
        "/set_sheet [ID] – Google Spreadsheet-ի միացում\n"
        "/set_log – ընթացիկ չատը որպես լոգ-չատ սահմանել\n"
        "/export – տվյալների բազայի արտահանում JSON ֆորմատով\n\n"

        "<b>Մենյուի միջոցով գրառումների հետ աշխատանք:</b>\n"
        "• ➕ Ավելացնել գրառում – նոր գրառման քայլ առ քայլ ավելացում\n"
        "• 📋 Ընտրել թերթ – աղյուսակում ակտիվ թերթի ընտրություն\n"
        "• 📊 Կարգավիճակ – բոտի ընթացիկ կարգավորումներ\n"
        "• 📈 Վիճակագրություն – տվյալների բազայի վիճակագրություն\n\n"

        "<b>Գրառման դաշտեր:</b>\n"
        "• ամսաթիվ (ամսաթիվ) – ամսաթիվ YYYY-MM-DD ձևաչափով\n"
        "• մատակարար (մատակարար) – մատակարարի անվանում\n"
        "• ուղղություն (ուղղություն) – ծախսի ուղղություն\n"
        "• ծախսի բնութագիր (նկարագրություն) – ծախսի նկարագրություն\n"
        "• Արժեք (գումար) – ծախսի գումար\n\n"

        "<b>Օգտագործման օրինակներ:</b>\n"
        "/recent 10 – ցույց տալ վերջին 10 գրառումները\n"
        "/search ապրանքներ – գտնել գրառումներ «ապրանքներ» բառով\n"
        "/info abc12345 – «abc12345» ID-ով գրառման տեղեկություն\n\n"

        "<i>Բոլոր գրառումները ավտոմատ կերպով համաժամացվում են Telegram-ի, Google Sheets-ի և տվյալների բազայի միջև:</i>"
    )

    await update.message.reply_text(help_text, parse_mode="HTML")



# === Настройка приложения ===

def main():
    """Основная функция запуска бота"""
    try:
        # Инициализация базы данных
        if not init_db():
            logger.error("Не удалось инициализировать базу данных!")
            return
        
        # Создание приложения
        application = Application.builder().token(TOKEN).build()
        
        # Настройка ConversationHandler для добавления записей
        add_record_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(start_add_record, pattern="^add_record$")],
            states={
                DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
                SUPPLIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_supplier)],
                DIRECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_direction)],
                DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_description)],
                AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
        )
        
        # Настройка ConversationHandler для редактирования записей
        edit_record_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_handler, pattern="^edit_")],
            states={
                EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_edit_value)],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(button_handler, pattern="^cancel_edit$")
            ],
        )
        
        # Регистрация обработчиков команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("set_log", set_log_command))
        application.add_handler(CommandHandler("set_sheet", set_sheet_command))
        application.add_handler(CommandHandler("search", search_command))
        application.add_handler(CommandHandler("export", export_command))
        application.add_handler(CommandHandler("recent", recent_command))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(CommandHandler("initialize_sheets", initialize_sheets_command))

        # Регистрация ConversationHandler'ов
        application.add_handler(add_record_conv)
        application.add_handler(edit_record_conv)
        
        # Регистрация обработчика кнопок (должен быть после ConversationHandler'ов)
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Регистрация обработчика ошибок
        application.add_error_handler(error_handler)
        
        # Запуск бота
        logger.info("🚀 Бот запущен!")
        print("🚀 Бот запущен! Нажмите Ctrl+C для остановки.")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        print(f"❌ Критическая ошибка: {e}")

async def select_spreadsheet_menu(update: Update, context: CallbackContext):
    """Показывает меню выбора Google Spreadsheet"""
    query = update.callback_query
    
    from google_connector import get_all_spreadsheets
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and len(ADMIN_IDS) > 0:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text("❌ Դուք չունեք այս հրամանը կատարելու իրավունք:",                 
                                    reply_markup=InlineKeyboardMarkup(keyboard))
        return

    try:
        spreadsheets = get_all_spreadsheets()
        
        if not spreadsheets:
            keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
            await query.edit_message_text(
                "❌ Մատչելի աղյուսակներ չեն գտնվել:\n"
                "Համոզվեք, որ ծառայության հաշիվը ունի աղյուսակների մուտքի իրավունք:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        keyboard = []
        for spreadsheet in spreadsheets[:10]:  # Показываем максимум 10 таблиц
            # Ограничиваем длину названия для кнопки
            name = spreadsheet['name'][:30] + "..." if len(spreadsheet['name']) > 30 else spreadsheet['name']
            keyboard.append([InlineKeyboardButton(
                f"📊 {name}", 
                callback_data=f"spreadsheet_{spreadsheet['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
        
        text = f"📊 Ընտրեք Google Spreadsheet ({len(spreadsheets)} մատչելի):"
        if len(spreadsheets) > 10:
            text += f"\n\nՑուցադրված են առաջին 10 աղյուսակները:"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            f"⚠️ Աղյուսակների ցանկի ստացման սխալ: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def select_spreadsheet(update: Update, context: CallbackContext):
    """Выбирает конкретную Google Spreadsheet и показывает её листы"""
    query = update.callback_query
    spreadsheet_id = query.data.replace("spreadsheet_", "")
    
    
    from google_connector import get_spreadsheet_info
    
    try:
        spreadsheet_info = get_spreadsheet_info(spreadsheet_id)
        
        if not spreadsheet_info:
            keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="select_spreadsheet")]]
            await query.edit_message_text(
                "❌ Չհաջողվեց ստանալ աղյուսակի մասին տեղեկություն:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        if not spreadsheet_info['sheets']:
            keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="select_spreadsheet")]]
            await query.edit_message_text(
                f"❌ '{spreadsheet_info['title']}' աղյուսակում թերթեր չկան:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Временно сохраняем выбранную таблицу
        context.user_data['selected_spreadsheet_id'] = spreadsheet_id
        context.user_data['selected_spreadsheet_title'] = spreadsheet_info['title']
        
        keyboard = []
        for sheet in spreadsheet_info['sheets']:
            # Показываем информацию о количестве строк
            sheet_info = f"{sheet['title']} ({sheet['row_count']} տող)"
            keyboard.append([InlineKeyboardButton(
                f"📋 {sheet_info}", 
                callback_data=f"final_sheet_{sheet['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Աղյուսակների ցանկ", callback_data="select_spreadsheet")])
        
        await query.edit_message_text(
            f"📊 Աղյուսակ: <b>{spreadsheet_info['title']}</b>\n"
            f"📋 Թերթեր: {spreadsheet_info['sheets_count']}\n\n"
            f"Ընտրեք աշխատանքի համար թերթ:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="select_spreadsheet")]]
        await query.edit_message_text(
            f"⚠️ Սխալ: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def select_final_sheet(update: Update, context: CallbackContext):
    """Окончательно выбирает лист и сохраняет настройки"""
    query = update.callback_query
    sheet_name = query.data.replace("final_sheet_", "")
    
    # Получаем данные из user_data
    spreadsheet_id = context.user_data.get('selected_spreadsheet_id')
    spreadsheet_title = context.user_data.get('selected_spreadsheet_title')
    
    if not spreadsheet_id:
        await query.edit_message_text("❌ Սխալ․ աղյուսակը ընտրված չէ:")
        return
    
    # Сохраняем выбранные настройки
    set_active_spreadsheet(spreadsheet_id, sheet_name)
    
    await query.edit_message_text(
        f"✅ Կարգավորումը ավարտված է!\n\n"
        f"📊 Աղյուսակ․ <b>{spreadsheet_title}</b>\n"
        f"📋 Թերթ․ <b>{sheet_name}</b>\n\n"
        f"Այժմ դուք կարող եք ավելացնել գրառումներ:",
        parse_mode="HTML",
        reply_markup=create_main_menu()
    )
    
    await send_to_log_chat(context, f"Выбрана таблица: {spreadsheet_title}, лист: {sheet_name}")
    
    # Очищаем временные данные
    context.user_data.pop('selected_spreadsheet_id', None)
    context.user_data.pop('selected_spreadsheet_title', None)

if __name__ == '__main__':
    main()