import json
import logging
import os
from openpyxl import Workbook
from io import BytesIO
from database import get_payments, get_all_records
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, CallbackContext
from google_connector import (get_worksheets_info, add_record_to_sheet, 
                            update_record_in_sheet, delete_record_from_sheet, 
                            get_record_by_id, get_all_spreadsheets, get_spreadsheet_info, initialize_and_sync_sheets, get_worksheet_by_name)
from database import init_db, add_record_to_db, update_record_in_db, delete_record_from_db, get_record_from_db, get_db_stats, add_payment
import uuid
import re
import re

import re

def normalize_date(date_str: str) -> str:
    # Удалить пробелы и завершающие точки
    date_str = date_str.strip().rstrip('.')

    # Найти все группы цифр
    parts = re.findall(r'\d+', date_str)

    if len(parts) == 3:
        # Например: ["08", "18", "23"]
        day, month, year = parts
    elif len(parts) == 1 and len(parts[0]) == 6:
        # Например: "081823"
        digits = parts[0]
        day, month, year = digits[0:2], digits[2:4], digits[4:6]
    elif len(parts) == 2 and len(parts[0]) == 2 and len(parts[1]) == 4:
        # Например: "08.1823"
        day = parts[0]
        month = parts[1][:2]
        year = parts[1][2:]
    else:
        raise ValueError(f"Unrecognized date format: {date_str}")

    # Дополнить нулями
    day = day.zfill(2)
    month = month.zfill(2)
    year = year.zfill(2)

    # Попробуем интерпретировать и заодно проверим валидность
    d, m = int(day), int(month)

    # Если месяц > 12 и день <= 12 — вероятно, перепутано местами
    if m > 12 and d <= 12:
        day, month = month, day
        d, m = int(day), int(month)

    # Проверка после возможной перестановки
    if not (1 <= d <= 31 and 1 <= m <= 12):
        raise ValueError(f"Invalid calendar date: {day}.{month}.{year}")

    return f"{day}.{month}.{year}"


# === Конֆիգուրացիա ===
from dotenv import load_dotenv
load_dotenv()
TOKEN = os.getenv('TOKEN')
if not TOKEN:
    raise ValueError("TOKEN-ը չի գտնվել: Ավելացրեք այն .env ֆայլում")

# Ֆայլեր տվյալների պահպանման համար
USERS_FILE = 'users.json'
ALLOWED_USERS_FILE = 'allowed_users.json'
BOT_CONFIG_FILE = 'bot_config.json'

# ID ադմինիստրատորների (могут добавлять новых пользователей)
ADMIN_IDS = [714158870, 1023627246]

# Состояния для ConversationHandler
(DATE, SUPPLIER_CHOICE, SUPPLIER_MANUAL, DIRECTION, DESCRIPTION, AMOUNT, 
 EDIT_FIELD, EDIT_VALUE, CONFIRM_DELETE, SET_REPORT_SHEET) = range(10)

# === Настройка логирования ===
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# === Вспомогательные функции ===

def load_bot_config():
    """Загружает конфигурацию бота"""
    try:
        with open(BOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Добавляем отчеты, если их нет
            if 'report_chats' not in config:
                config['report_chats'] = {}
            return config
    except FileNotFoundError:
        return {
            'log_chat_id': None,
            'report_chats': {}
        }

def save_bot_config(config):
    """Сохраняет конфигурацию бота"""
    with open(BOT_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def get_log_chat_id():
    """Возвращает ID чата для логов"""
    return load_bot_config().get('log_chat_id')

def set_log_chat(chat_id: int):
    """Устанавливает ID чата для логов"""
    config = load_bot_config()
    config['log_chat_id'] = chat_id
    save_bot_config(config)

def get_report_settings(chat_id: int):
    """Возвращает настройки отчетов для чата"""
    config = load_bot_config()
    return config['report_chats'].get(str(chat_id), {})

def set_report_settings(chat_id: int, settings: dict):
    """Устанавливает настройки отчетов для чата"""
    config = load_bot_config()
    config['report_chats'][str(chat_id)] = settings
    save_bot_config(config)

def load_users():
    """Загружает данные пользователей"""
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_users(users_data):
    """Сохраняет данные пользователей"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users_data, f, indent=2, ensure_ascii=False)

def get_user_settings(user_id: int):
    """Возвращает настройки пользователя"""
    users = load_users()
    user_id_str = str(user_id)
    return users.get(user_id_str, {
        'active_spreadsheet_id': None,
        'active_sheet_name': None,
        'name': None,
        'display_name': None  # Добавлено отображаемое имя
    })

def update_user_settings(user_id: int, settings: dict):
    """Обновляет настройки пользователя"""
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        users[user_id_str] = {}
    
    users[user_id_str].update(settings)
    save_users(users)

def load_allowed_users():
    """Զանգռում է թույլատրված օգտվողների ցուցակը"""
    try:
        with open(ALLOWED_USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_allowed_users(allowed_list):
    """Պահպանել թույլատրված օգտվողների ցուցակը"""
    with open(ALLOWED_USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(allowed_list, f, indent=2)

def is_user_allowed(user_id: int) -> bool:
    """Проверяет, есть ли пользователь в списке разрешенных"""
    return user_id in load_allowed_users()

def add_allowed_user(user_id: int):
    """Добавляет пользователя в список разрешенных"""
    allowed = load_allowed_users()
    if user_id not in allowed:
        allowed.append(user_id)
        save_allowed_users(allowed)

def remove_allowed_user(user_id: int):
    """Удаляет пользователя из списка разрешенных"""
    allowed = load_allowed_users()
    if user_id in allowed:
        allowed.remove(user_id)
        save_allowed_users(allowed)

async def send_to_log_chat(context: CallbackContext, message: str):
    """Отправляет сообщение в лог-чат"""
    log_chat_id = get_log_chat_id()
    if log_chat_id:
        try:
            await context.bot.send_message(chat_id=log_chat_id, text=f"📝 ԳՐԱՆՑՄԱՏՅԱՆ: {message}")
        except Exception as e:
            logger.error(f"Սխալ գրանցամատյան ուղարկելիս: {e}")
def merge_payment_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Merge overlapping or adjacent payment intervals summing amounts.

    Args:
        df: DataFrame with columns ['amount', 'date_from', 'date_to'].
            date_from, date_to can be None or timestamps.

    Returns:
        DataFrame with merged intervals and summed amounts.
        NaT is used instead of min/max timestamps for open intervals.
    """
    df = df.copy()
    df['date_from'] = pd.to_datetime(df['date_from'], errors='coerce').fillna(pd.Timestamp.min)
    df['date_to'] = pd.to_datetime(df['date_to'], errors='coerce').fillna(pd.Timestamp.max)
    df = df.sort_values(by='date_from').reset_index(drop=True)

    merged = []
    current_from = df.loc[0, 'date_from']
    current_to = df.loc[0, 'date_to']
    current_amount = df.loc[0, 'amount']

    for i in range(1, len(df)):
        row = df.loc[i]
        start = row['date_from']
        end = row['date_to']
        amt = row['amount']

        # If intervals overlap or touch
        if start <= current_to:
            current_to = max(current_to, end)
            current_amount += amt
        else:
            merged.append({
                'date_from': current_from,
                'date_to': current_to,
                'amount': current_amount
            })
            current_from = start
            current_to = end
            current_amount = amt

    merged.append({
        'date_from': current_from,
        'date_to': current_to,
        'amount': current_amount
    })

    result = pd.DataFrame(merged)
    # Replace extreme timestamps back to NaT to mark open intervals
    result['date_from'] = result['date_from'].replace(pd.Timestamp.min, pd.NaT)
    result['date_to'] = result['date_to'].replace(pd.Timestamp.max, pd.NaT)
    return result


def format_date_for_interval(d):
    if pd.isna(d):
        return '-'
    return d.strftime('%Y-%m-%d')

async def send_report(context: CallbackContext, action: str, record: dict, user: dict):
    """Отправляет отчет о действии в настроенные чаты"""
    config = load_bot_config()
    report_chats = config.get('report_chats', {})
    
    if not report_chats:
        return
    
    user_name = user.get('display_name') or user.get('name') or f"User {user['id']}"

    if action == "Խմբագրում":
        report_text = (
            f"📢 🟥<b>ԽՄԲԱԳՐՈՒՄ</b> ID: <code> {record["id"]} </code>  🟥\n\n"
            f"👤 Օգտագործող: <b>{user_name}</b> \n"
            f"🔧 Գործողություն: <b>{action}</b>\n\n"
        ) + format_record_info(record) + "\n\n" 
    elif action == "Բացթողում":
        date = record.get('date', 'N/A')
        report_text = (
            f"📢 🟡<b>ԲԱՑԹՈՂՈՒՄ: {date} ամսաթվով</b>🟡\n\n"
            f"👤 Օգտագործող: <b>{user_name}</b>\n"
            f"🔧 Գործողություն: <b>{action}</b>\n\n"
        ) + format_record_info(record) + "\n\n" 
    else:
        report_text = (
            f"📢 <b>ՎԵՐՋԻՆ ԳՈՐԾՈՂՈՒԹՅՈՒՆ</b>\n\n"
            f"👤 Օգտագործող: <b>{user_name}</b>\n"
            f"🔧 Գործողություն: <b>{action}</b>\n\n"
        ) + format_record_info(record)
        
        
    for chat_id, settings in report_chats.items():
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=report_text,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Սխալ հաշվետվություն ուղարկելիս {chat_id}: {e}")


async def my_report_command(update: Update, context: CallbackContext):
    """Показывает отчет пользователя по расходам за период"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return

    user_settings = get_user_settings(user_id)
    display_name = user_settings.get('display_name')
    if not display_name:
        await update.message.reply_text("❌ Ձեր անունը չի սահմանված։")
        return

    args = context.args
    date_from = args[0] if len(args) > 0 else None
    date_to = args[1] if len(args) > 1 else None

    from database import get_all_records

    # Собираем все записи по имени пользователя
    records = get_all_records()
    filtered = []
    for rec in records:
        if str(rec.get('supplier', '')).strip() != display_name:
            continue
        rec_date = rec.get('date', '')
        if date_from and rec_date < date_from:
            continue
        if date_to and rec_date > date_to:
            continue
        filtered.append(rec)

    if not filtered:
        await update.message.reply_text("Ձեր անունով գրառումներ չեն գտնվել նշված ժամանակահատվածում։")
        return

    # Группировка по листам
    sheets = {}
    total = 0
    for rec in filtered:
        sheet = rec.get('sheet_name', '—')
        sheets.setdefault(sheet, []).append(rec)
        total += rec.get('amount', 0)

    text = f"🧾 <b>Ձեր ծախսերի հաշվետվությունը</b>\n"
    if date_from or date_to:
        text += f"🗓 {date_from or 'սկզբից'} — {date_to or 'մինչ այժմ'}\n"
    for sheet, recs in sheets.items():
        s = sum(r.get('amount', 0) for r in recs)
        text += f"\n<b>Թերթիկ՝ {sheet}</b>: {s:,.2f} դրամ ({len(recs)} գրառում)"
    text += f"\n\n<b>Ընդհանուր՝ {total:,.2f} դրամ</b>"

    await update.message.reply_text(text, parse_mode="HTML")

def create_main_menu(user_id=None):
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել գրառում", callback_data="add_record_menu")],
        [InlineKeyboardButton("📋 Ընտրել թերթիկ", callback_data="select_sheet")],
        [InlineKeyboardButton("📊 Կարգավիճակ", callback_data="status")],
        [InlineKeyboardButton("📈 Վիճակագրություն", callback_data="stats")],
        [InlineKeyboardButton("📊 Ընտրել աղյուսակ", callback_data="select_spreadsheet")]
    ]
    if user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("💸 Վճարներ", callback_data="pay_menu")])
    return InlineKeyboardMarkup(keyboard)

def create_add_record_menu():
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել գրառում", callback_data="add_record")],
        [InlineKeyboardButton("➕ Ավելացնել Բացթողում", callback_data="add_skip_record")],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_edit_menu(record_id: str, is_admin: bool = False):
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

def get_user_records(user_id: int) -> list:
    """Возвращает список ID записей пользователя"""
    users = load_users()
    user_id_str = str(user_id)
    if user_id_str in users and 'reports' in users[user_id_str]:
        return users[user_id_str]['reports']
    return []

def get_user_id_by_record_id(record_id: str) -> int:
    """Возвращает ID пользователя по ID записи"""
    users = load_users()
    for user_id_str, user_data in users.items():
        if 'reports' in user_data and str(record_id) in user_data['reports']:
            return int(user_id_str)
    # Если не найдено — ищем по имени в БД
    from database import get_record_from_db
    rec = get_record_from_db(record_id)
    if rec:
        supplier = rec.get('supplier')
        # ищем пользователя с таким display_name
        for user_id_str, user_data in users.items():
            if user_data.get('display_name') == supplier:
                return int(user_id_str)
    return 0

def format_record_info(record: dict) -> str:
    """Форматирует информацию о записи"""
    user_id = get_user_id_by_record_id(record.get('id'))
    user_settings = get_user_settings(user_id)
    user_name = user_settings.get('display_name') or user_settings.get('name') or "Անհայտ"
    
    return (
        f"🆔 ID: <code>{record.get('id', 'N/A')}</code>\n"
        f"👤 Ստեղծող: <b>{user_name}</b>\n"
        f"📅 Ամսաթիվ: <b>{record.get('date', 'N/A')}</b>\n"
        f"🏪 Մատակարար: <b>{record.get('supplier', 'N/A')}</b>\n"
        f"🧭 Ուղղություն: <b>{record.get('direction', 'N/A')}</b>\n"
        f"📝 Նկարագրություն: <b>{record.get('description', 'N/A')}</b>\n"
        f"💰 Գումար: <b>{record.get('amount', 0):,.2f}</b>\n"
        f"📊 Աղյուսակ: <code>{record.get('spreadsheet_id', '—')}</code>\n"
        f"📋 Թերթիկ: <code>{record.get('sheet_name', '—')}</code>"
    )


# === Обработчики команд ===
async def text_menu_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    await clear_user_data(update, context)
    
    # Отправляем Inline-меню при нажатии на Reply-кнопку
    await update.message.reply_text(
        "📋 Հիմնական ընտրացանկ:",
        reply_markup=create_main_menu(user_id)
    )
    
def create_reply_menu():
    return ReplyKeyboardMarkup([["📋 Մենյու"]], resize_keyboard=True)

async def start(update: Update, context: CallbackContext):
    # Инициализируем базу данных при запуске
    init_db()
    
    user = update.effective_user
    user_id = user.id
    user_name = user.full_name
    
    # Добавляем пользователя в систему
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        users[user_id_str] = {
            'active_spreadsheet_id': None,
            'active_sheet_name': None,
            'name': user_name,
            'display_name': None  # Добавлено отображаемое имя
        }
        save_users(users)
    # Проверяем разрешен ли пользователь
    if not is_user_allowed(user_id):
        await update.message.reply_text(
            "⛔️ Դուք չունեք մուտքի թույլտվություն: Անդրադարձեք ադմինիստրատորին:"
        )
        return
    
    await update.message.reply_text(
        "Օգտագործեք կոճակը ստորև՝ հիմնական ընտրացանկը բացելու համար:",
        reply_markup=create_reply_menu()
    )
    await update.message.reply_text(
        "👋 Բարի գալուստ ծախսերի հաշվառման բոտ:\n\n"
        "Հնարավորություններ:\n"
        "• ➕ Գրառումների ավելացում Google Sheets-ում\n"
        "• ✏️ Գրառումների խմբագրում և ջնջում\n"
        "• 📊 Համաժամեցում տվյալների բազայի հետ\n"
        "• 📝 Գործողությունների գրանցում\n\n",
        reply_markup=create_main_menu(user_id)
    )
    
    

async def menu_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    await clear_user_data(update, context)

    # Отправляем Inline-меню
    await update.message.reply_text(
        "📋 Հիմնական ընտրացանկ:",
        reply_markup=create_main_menu(user_id)
    )
    


async def set_log_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    chat_id = update.effective_chat.id
    set_log_chat(chat_id)
    await update.message.reply_text(
        f"✅ Գրանցամատյանի զրույցը սահմանված է:\n"
        f"Chat ID: <code>{chat_id}</code>\n"
        f"Բոլոր գրանցումները կուղարկվեն այս զրույց:",
        parse_mode="HTML"
    )
    await send_to_log_chat(context, f"Գրանցամատյանի զրույցը ակտիվացված է: Chat ID: {chat_id}")

async def set_report_command(update: Update, context: CallbackContext):
    """Команда для настройки отчетов в чате"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    chat_id = update.effective_chat.id
    
    # Получаем аргументы команды
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📊 Չատում հաշվետվություններ սահմանելու համար օգտագործեք:\n"
            "<code>/set_report SPREADSHEET_ID SHEET_NAME</code>\n\n"
            "Օրինակ՝ /set_report abc12345 Չատի հաշվետվություն",
            parse_mode="HTML"
        )
        return
    
    spreadsheet_id = args[0].strip()
    sheet_name = ' '.join(args[1:]).strip()
    
    # Проверяем доступность таблицы
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        if not sheets_info:
            await update.message.reply_text("❌ Հնարավոր չէ մուտք գործել աղյուսակ: Ստուգեք ID-ն և մուտքի իրավունքները:")
            return
        
        # Проверяем существует ли лист
        sheet_exists = any(sheet['title'] == sheet_name for sheet in sheets_info)
        if not sheet_exists:
            await update.message.reply_text(
                f"❌ Թերթիկ '{sheet_name}' չի գտնվել աղյուսակում:",
                parse_mode="HTML"
            )
            return
        
        # Сохраняем настройки
        set_report_settings(chat_id, {
            'spreadsheet_id': spreadsheet_id,
            'sheet_name': sheet_name,
            'spreadsheet_title': spreadsheet_title
        })
        
        await update.message.reply_text(
            f"✅ Չատի հաշվետվությունները միացված են:\n"
            f"📊 Աղյուսակ: <b>{spreadsheet_title}</b>\n"
            f"📋 Թերթիկ: <b>{sheet_name}</b>\n\n"
            f"Այժմ բոլոր գործողությունները կգրանցվեն այս թերթիկում:",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Միացված է հաշվետվություններ չատի համար: {spreadsheet_title} > {sheet_name}")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Սխալ հաշվետվություններ միացնելիս:\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )

async def set_sheet_command(update: Update, context: CallbackContext):
    """Команда для установки ID Google Spreadsheet"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    # Получаем аргументы команды
    args = context.args
    if not args:
        await update.message.reply_text(
            "📊 Google Spreadsheet սահմանելու համար օգտագործեք:\n"
            "<code>/set_sheet YOUR_SPREADSHEET_ID</code>\n\n"
            "ID-ն կարելի է գտնել աղյուսակի հղումով:\n"
            "https://docs.google.com/spreadsheets/d/<b>SPREADSHEET_ID</b>/edit",
            parse_mode="HTML"
        )
        return
    
    spreadsheet_id = args[0].strip()
    
    # Проверяем доступность таблицы
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        if not sheets_info:
            await update.message.reply_text("❌ Հնարավոր չէ մուտք գործել աղյուսակ: Ստուգեք ID-ն և մուտքի իրավունքները:")
            return
        
        # Сохраняем ID таблицы для пользователя
        update_user_settings(user_id, {'active_spreadsheet_id': spreadsheet_id})
        
        await update.message.reply_text(
            f"✅ Google Spreadsheet միացված է:\n"
            f"📊 Անվանում: <b>{spreadsheet_title}</b>\n"
            f"🆔 ID: <code>{spreadsheet_id}</code>\n"
            f"📋 Գտնված թերթիկներ: {len(sheets_info)}\n\n"
            f"Այժմ ընտրեք թերթիկ աշխատելու համար /menu → 📋 Ընտրել թերթիկ",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Միացված է Google Spreadsheet: {spreadsheet_title} (ID: {spreadsheet_id})")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Սխալ աղյուսակին միանալիս:\n<code>{str(e)}</code>\n\n"
            f"Համոզվեք, որ:\n"
            f"• Աղյուսակի ID-ն ճիշտ է\n"
            f"• Ծառայության հաշիվը մուտքի իրավունք ունի\n"
            f"• Credentials ֆայլը ճիշտ է",
            parse_mode="HTML"
        )


async def sync_sheets_command(update: Update, context: CallbackContext, used_by_admin: bool = False):
    """Синхронизирует данные из Google Sheets в БД и приводит к формату бота"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and used_by_admin is False:
        
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return

    user_settings = get_user_settings(user_id)
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    sheet_name = user_settings.get('active_sheet_name')
    if not spreadsheet_id or not sheet_name:
        if used_by_admin is False:
            await update.message.reply_text("❌ Նախ պետք է ընտրել աղյուսակ և թերթիկ:")
        return


    worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
    if not worksheet:
        if used_by_admin is False:
            await update.message.reply_text("❌ Չհաջողվեց բացել թերթիկը:")
        return

    rows = worksheet.get_all_records()
    added, updated = 0, 0
    for row in rows:
        # Приводим к формату бота
        record_id = str(row.get('ID', '')).strip()
        if not record_id:
            continue  # пропускаем строки без ID

        # Приведение даты к YYYY-MM-DD
        raw_date = str(row.get('ամսաթիվ', '')).replace("․", ".").strip()
        try:
            if "." in raw_date:
                date_obj = datetime.strptime(raw_date, "%d.%m.%y")
                date_fmt = date_obj.strftime("%Y-%m-%d")
            else:
                date_fmt = raw_date
        except Exception:
            date_fmt = raw_date

        # Приведение суммы к float
        try:
            amount = float(str(row.get('Արժեք', '0')).replace(',', '.').replace(' ', ''))
        except Exception:
            amount = 0.0

        record = {
            'id': record_id,
            'date': date_fmt,
            'supplier': str(row.get('մատակարար', '')).strip(),
            'direction': str(row.get('ուղղություն', '')).strip(),
            'description': str(row.get('ծախսի բնութագիր', '')).strip(),
            'amount': amount,
            'spreadsheet_id': spreadsheet_id,
            'sheet_name': sheet_name
        }

        db_record = get_record_from_db(record_id)
        if not db_record:
            if add_record_to_db(record):
                added += 1
        else:
            # Можно добавить сравнение и обновление, если хотите
            updated += 1
    if used_by_admin is False:
        await update.message.reply_text(
            f"✅ Սինխրոնիզացիա ավարտված է:\n"
            f"Ավելացված է {added} նոր գրառում, {updated} արդեն կար:",
            parse_mode="HTML"
        )
    
async def start_add_skip_record(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return


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
    record_id = "cb-"+str(uuid.uuid4())[:8]
    current_date = datetime.now().strftime("%Y-%m-%d")
    context.user_data['record'] = {
        'id': record_id,
        'date': current_date,  # по умолчанию текущая дата, но пользователь может выбрать другую
        'user_id': user_id,
        'skip_mode': True  # <--- Добавляем флаг для выделения в логах
    }

    # Просим ввести дату вручную или отправить "+" для текущей
    await query.edit_message_text(
        f"➕ Ավելացնել Բացթողում\n"
        f"🆔 ID: <code>{record_id}</code>\n\n"
        f"📅 Մուտքագրեք ամսաթիվը (YYYY-MM-DD) կամ ուղարկեք <b>+</b>՝ ընթացիկ ամսաթվի համար:",
        parse_mode="HTML"
    )
    return DATE  # Переходим к состоянию DATE, как в обычном добавлении
# === Обработчики кнопок ===

async def button_handler(update: Update, context: CallbackContext):
    """
    Обработчик кнопок, запускается при нажатии на любую кнопку в боте.
    """
    
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    data = query.data
    if data == "add_record_menu":
        # Показываем выбор типа добавления
        await query.edit_message_text(
            "Ընտրեք գործողությունը՝",
            reply_markup=create_add_record_menu()
        )
    if data == "add_record":
        return await start_add_record(update, context)
    elif data == "add_skip_record":
        return await start_add_skip_record(update, context)
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
    elif data == "use_my_name":
        return await use_my_name(update, context)
    elif data == "use_firm_name":
        return await use_firm_name(update, context)
    elif data == "manual_input":
        return await manual_input(update, context)
    elif data == "back_to_menu":
        await query.edit_message_text("📋 Հիմնական ընտրացանկ:", reply_markup=create_main_menu(user_id))
    if data == "pay_menu" and user_id in ADMIN_IDS:
        # Меню работников
        users = load_users()
        keyboard = []
        for uid, udata in users.items():
            if udata.get('display_name'):
                keyboard.append([InlineKeyboardButton(udata['display_name'], callback_data=f"pay_user_{udata['display_name']}")])
        keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
        await query.edit_message_text("Ընտրեք աշխատակցին:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("pay_user_") and user_id in ADMIN_IDS:
        display_name = data.replace("pay_user_", "")
        keyboard = [
            [InlineKeyboardButton("➕ Ավելացնել վճարում", callback_data=f"add_payment_{display_name}")],
            [InlineKeyboardButton("📊 Ստանալ սահմանի հաշվետվություն", callback_data=f"get_payment_report_{display_name}")],
            [InlineKeyboardButton("⬅️ Հետ", callback_data="pay_menu")]
        ]
        await query.edit_message_text(f"Ընտրեք գործողությունը {display_name}-ի համար:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("add_payment_") and user_id in ADMIN_IDS:
        display_name = data.replace("add_payment_", "")
        context.user_data['pay_user'] = display_name
        await query.edit_message_text(f"Մուտքագրեք վճարման գումարը:")
        context.user_data['pay_step'] = 'amount'
        return
    elif data.startswith("get_payment_report_") and user_id in ADMIN_IDS:
        display_name = data.replace("get_payment_report_", "")
        await send_payment_report(update, context, display_name)
        return

async def show_status(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    user_settings = get_user_settings(user_id)
    
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    sheet_name = user_settings.get('active_sheet_name')
    log_chat_id = get_log_chat_id()
    
    status_text = "📊 Ընթացիկ կարգավիճակ:\n\n"
    
    if spreadsheet_id:
        status_text += f"✅ Միացված աղյուսակ: <code>{spreadsheet_id}</code>\n"
        if sheet_name:
            status_text += f"📋 Ակտիվ թերթիկ: <code>{sheet_name}</code>\n"
        else:
            status_text += "⚠️ Թերթիկը չի ընտրվել\n"
    else:
        status_text += "❌ Աղյուսակը չի միացված\n"
    
    if log_chat_id:
        status_text += f"📝 Գրանցամատյանի զրույց: <code>{log_chat_id}</code>\n"
    else:
        status_text += "📝 Գրանցամատյանի զրույցը չի սահմանված\n"
    
    # Добавляем информацию о отчетах
    report_settings = get_report_settings(update.effective_chat.id)
    if report_settings:
        status_text += (
            f"\n📢 Չատի հաշվետվություններ:\n"
            f"📊 Աղյուսակ: <code>{report_settings.get('spreadsheet_id', 'N/A')}</code>\n"
            f"📋 Թերթիկ: <b>{report_settings.get('sheet_name', 'N/A')}</b>\n"
        )
    
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
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    stats = get_db_stats()
    if stats:
        stats_text = (
            f"📈 Տվյալների բազայի վիճակագրություն:\n\n"
            f"📝 Ընդհանուր գրառումներ: {stats['total_records']}\n"
            f"💰 Ընդհանուր գումար: {stats['total_amount']:,.2f}\n"
            f"📅 Վերջին 30 օրում: {stats['recent_records']} գրառում"
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
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    user_settings = get_user_settings(user_id)
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    
    if not spreadsheet_id:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Նախ պետք է միացնել աղյուսակը:\n"
            "Օգտագործեք /set_sheet հրամանը",
            reply_markup=InlineKeyboardMarkup(keyboard))
        return
    
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        
        if not sheets_info:
            keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
            await query.edit_message_text(
                "❌ Աղյուսակում թերթիկներ չկան:",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        keyboard = []
        for info in sheets_info:
            keyboard.append([InlineKeyboardButton(
                f"📋 {info['title']}", 
                callback_data=f"sheet_{info['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            f"📋 Ընտրեք թերթիկ <b>{spreadsheet_title}</b> աղյուսակից:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            f"⚠️ Սխալ: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard))
        

async def select_sheet(update: Update, context: CallbackContext):
    """Выбирает активный лист"""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    sheet_name = query.data.replace("sheet_", "")
    
    # Сохраняем выбранный лист для пользователя
    user_settings = get_user_settings(user_id)
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    update_user_settings(user_id, {'active_sheet_name': sheet_name})
    
    await query.edit_message_text(
        f"✅ Ընտրված թերթիկ: <b>{sheet_name}</b>\n\n"
        f"Այժմ կարող եք գրառումներ ավելացնել:",
        parse_mode="HTML",
        reply_markup=create_main_menu(user_id)
    )
    
    await send_to_log_chat(context, f"Ընտրվել է ակտիվ թերթիկ: {sheet_name}")

async def initialize_sheets_command(update: Update, context: CallbackContext):
    """Команда инициализации всех Google Sheets — միայն ադմինների համար"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return

    try:
        from google_connector import initialize_and_sync_sheets
        initialize_and_sync_sheets()
        await update.message.reply_text("✅ Բոլոր աղյուսակները հաջողությամբ մշակված են, ID-ները ավելացված են և բազան համաժամացված է:")
        await send_to_log_chat(context, "✅ Կատարվել է /initialize_sheets հրամանը - բոլոր աղյուսակները թարմացված են:")
    except Exception as e:
        await update.message.reply_text(f"❌ Սխալ աղյուսակները նախապատրաստելիս: {e}")

# === Добавление записи ===

async def start_add_record(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return  
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
    record_id = "cb-"+str(uuid.uuid4())[:8]
    current_date = datetime.now().strftime("%Y-%m-%d")
    context.user_data['record'] = {
        'id': record_id,
        'date': current_date,  # Автоматически используем текущую дату
        'user_id': user_id     # Сохраняем ID пользователя
    }
    
    # Сразу переходим к выбору поставщика
    user_settings = get_user_settings(user_id)
    display_name = user_settings.get('display_name')
    
    keyboard = []
    if display_name:
        keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել իմ անունը ({display_name})", callback_data="use_my_name")])
        keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել Ֆիրմայի անունը", callback_data="use_firm_name")])
    # keyboard.append([InlineKeyboardButton("✏️ Մուտքագրել ձեռքով", callback_data="manual_input")])
    
    await query.edit_message_text(
        f"➕ Ավելացնել նոր գրառում\n"
        f"🆔 ID: <code>{record_id}</code>\n"
        f"📅 Ամսաթիվ: <b>{current_date}</b>\n\n"
        f"🏪 Ընտրեք մատակարարի տեսակը:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SUPPLIER_CHOICE  # Пропускаем состояние DATE

async def get_date(update: Update, context: CallbackContext):
    print('get_date called')

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
        keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել իմ անունը ({display_name})", callback_data="use_my_name")])
        keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել Ֆիրմայի անունը", callback_data="use_firm_name")])
    # keyboard.append([InlineKeyboardButton("✏️ Մուտքագրել ձեռքով", callback_data="manual_input")])
    
    await update.message.reply_text(
        "🏪 Ընտրեք մատակարարի տեսակը:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return SUPPLIER_CHOICE

async def use_firm_name(update: Update, context: CallbackContext):
    """Использовать имя пользователя как поставщика"""
    query = update.callback_query
    await query.answer()
    
    
    context.user_data['record']['supplier'] = "Ֆ"
    
    await query.edit_message_text(
        f"✅ Մատակարար: Ֆ\n\n"
        f"🧭 Մուտքագրեք ուղղությունը (ուղղություն):"
    )
    
    return DIRECTION

async def use_my_name(update: Update, context: CallbackContext):
    """Использовать имя пользователя как поставщика"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    user_settings = get_user_settings(user_id)
    display_name = user_settings.get('display_name')
    
    # if not display_name:
    #     await query.edit_message_text("❌ Ձեր անունը չի սահմանված: Խնդրում ենք մուտքագրել ձեռքով:")
    #     return SUPPLIER_MANUAL
    
    if not display_name:
        await query.edit_message_text("❌ Ձեր անունը չի սահմանված: Օգտագործվելու է Ֆիրմայի անունը:")
        display_name = "Ֆ"
        return DIRECTION
    
    context.user_data['record']['supplier'] = display_name
    
    await query.edit_message_text(
        f"✅ Մատակարար: {display_name}\n\n"
        f"🧭 Մուտքագրեք ուղղությունը (ուղղություն):"
    )
    
    return DIRECTION

async def manual_input(update: Update, context: CallbackContext):
    """Ручной ввод поставщика"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("🏪 Մուտքագրեք մատակարարին (մատակարար):")
    
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
        f"🧭 Մուտքագրեք ուղղությունը (ուղղություն):"
    )
    
    return DIRECTION

async def get_direction(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    direction = update.message.text.strip()
    context.user_data['record']['direction'] = direction
    
    await update.message.reply_text(
        f"✅ Ուղղություն: {direction}\n\n"
        f"📝 Մուտքագրեք ծախսի նկարագրությունը (ծախսի բնութագիր):"
    )
    
    return DESCRIPTION

async def get_description(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    description = update.message.text.strip()
    context.user_data['record']['description'] = description
    
    await update.message.reply_text(
        f"✅ Նկարագրություն: {description}\n\n"
        f"💰 Մուտքագրեք գումարը (Արժեք):"
    )
    
    return AMOUNT

async def get_amount(update: Update, context: CallbackContext):
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
        
        await clear_user_data(update, context)

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("❌ Գումարի սխալ ձևաչափ: Մուտքագրեք թիվ (օրինակ՝ 1000.50):")
        return AMOUNT


# === Редактирование записей ===

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
    await sync_sheets_command(update, context, used_by_admin=True)
    sheet_success = update_record_in_sheet(spreadsheet_id, sheet_name, record_id, field, new_value)
    
    # Обновляем в базе данных
    db_success = update_record_in_db(record_id, field, new_value)
    # Результат
    if db_success and sheet_success:
        result_text = f"✅ '{field}' դաշտը թարմացված է '{new_value}' արժեքով"
        record = get_record_from_db(record_id)
        result_text += "\n\n" + format_record_info(record) # Добавляем кнопки для редактирования
        
        
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
    await clear_user_data(update, context)

    
    return ConversationHandler.END

# === Удаление записей ===

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
    
    # Проверяем права доступа        user_id_rec = get_user_id_by_record_id(record_id)
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
    if not is_user_allowed(user_id):
        return
    
    record_id = query.data.replace("confirm_delete_", "")
    
     # Удаляем из Google Sheets
    record = get_record_from_db(record_id)
    if not record:
        await query.edit_message_text("❌ Գրառումը չի գտնվել:")
        return
    
    spreadsheet_id = record.get('spreadsheet_id')
    sheet_name = record.get('sheet_name')
    
    # Удаляем из базы данных
    db_success = delete_record_from_db(record_id)
    
   
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

# === Обработчик отмены ===

async def cancel(update: Update, context: CallbackContext):
    """Отменяет текущую операцию"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return ConversationHandler.END
    
    await update.message.reply_text(
        "❌ Գործողությունը չեղարկված է:",
        reply_markup=create_main_menu(user_id)
    )
    await clear_user_data(update, context)
    return ConversationHandler.END

# === Обработчик ошибок ===

async def error_handler(update: object, context: CallbackContext) -> None:
    """Обрабатывает ошибки"""
    logger.error(f"Բացառություն թարմացումը մշակելիս: {context.error}")
    import traceback
    logger.error(traceback.format_exc())
    
    # Отправляем ошибку в лог-чат
    if context.error:
        await send_to_log_chat(context, f"ՍԽԱԼ: {str(context.error)}")

# === Команда поиска записей ===

async def search_command(update: Update, context: CallbackContext):
    """Команда поиска записей"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "🔍 Գրառումների որոնում:\n"
            "Օգտագործեք: <code>/search [տեքստի որոնում]</code>\n\n"
            "Որոնումն իրականացվում է հետևյալ դաշտերով՝ մատակարար, ուղղություն, նկարագրություն",
            parse_mode="HTML"
        )
        return
    
    query = " ".join(args)
    
    try:
        from database import search_records
        records = search_records(query)
        
        if not records:
            await update.message.reply_text(
                f"🔍 '{query}' հարցման համար ոչինչ չի գտնվել:",
                parse_mode="HTML"
            )
            return
        
        result_text = f"🔍 Գտնվել է {len(records)} գրառում '{query}' հարցման համար:\n\n"
        
        for i, record in enumerate(records, 1):
            if i > 25:
                break
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   📝 {record['description'][:50]}{'...' if len(record['description']) > 50 else ''}\n"
            result_text += f"   📋 {record['sheet_name']}\n\n"
        
        # Если записей много, предупреждаем
        if len(records) == 25:
            result_text += "ℹ️ Ցուցադրված են առաջին 25 արդյունքները: Հստակեցրեք հարցումը ավելի ճշգրիտ որոնման համար:"
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Որոնման սխալ: {e}")

# === Команда экспорта данных ===

async def export_command(update: Update, context: CallbackContext):
    """Команда экспорта данных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    try:
        from database import backup_db_to_dict
        backup_data = backup_db_to_dict()
        
        if not backup_data:
            await update.message.reply_text("❌ Ошибка создания резервной копии.")
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
                caption=f"📤 Տվյալների բազայի резервная копия\n"
                       f"📊 Գրառումներ: {backup_data['stats']['total_records']}\n"
                       f"💰 Ընդհանուր գումար: {backup_data['stats']['total_amount']:,.2f}\n"
                       f"📅 Ստեղծման ամսաթիվ: {backup_data['backup_date']}"
            )
        
        # Удаляем временный файл
        os.remove(filename)
        
        await send_to_log_chat(context, f"Создана резервная копия: {backup_data['stats']['total_records']} записей")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Արտահանման սխալ: {e}")

# === Команда показа վերջին записերի ===

async def recent_command(update: Update, context: CallbackContext):
    """Показывает последние записи"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
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
        
        result_text = f"📝 Последние {len(records)} записей:\n\n"
        
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
        await update.message.reply_text(f"❌ Գրառումներ ստանալու սխալ: {e}")

# === Команда информации о записи ===

async def info_command(update: Update, context: CallbackContext):
    """Показывает детальную информацию о записи по ID"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "ℹ️ Գրառման մասին տեղեկատվություն:\n"
            "Օգտագործեք: <code>/info [ID записи]</code>",
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
        
        result_text = "ℹ️ Գրառման մանրամասն տեղեկատվություն:\n\n"
        result_text += format_record_info(record)
        result_text += f"\n\n📅 Ստեղծված է: {record.get('created_at', 'N/A')}"
        result_text += f"\n🔄 Թարմացված է: {record.get('updated_at', 'N/A')}"
        
        # Создаем кнопку редактирования (если пользователь имеет права)
        keyboard = []
        user_id_rec = get_user_id_by_record_id(record_id)
        if user_id in ADMIN_IDS or user_id_rec == user_id:
            keyboard.append([InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record_id}")])
        
        await update.message.reply_text(
            result_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Տեղեկատվություն ստանալու սխալ: {e}")

# === Команда помощи ===

async def help_command(update: Update, context: CallbackContext):
    """Показывает справку по командам"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    help_text = (
        "📖 <b>Հրամանների օգնություն:</b>\n\n"

        "<b>Հիմնական հրամաններ:</b>\n"
        "/start – բոտի մեկնարկ և հիմնական ընտրացանկ\n"
        "/menu – ցույց տալ հիմնական ընտրացանկը\n"
        "/help – այս օգնությունը\n\n"

        "<b>Գրառումների կառավարում:</b>\n"
        "/recent [N] – ցույց տալ վերջին N գրառումները (լռելյայն 5)\n"
        "/search [տեքստ] – գրառումների որոնում տեքստով\n"
        "/info [ID] – գրառման մանրամասն տեղեկատվություն\n\n"

        "<b>Ադմինիստրատորի հրամաններ:</b>\n"
        "/initialize_sheets – աղյուսակների նախապատրաստում Google Sheets-ում\n"
        "/set_sheet [ID] – միացնել Google Spreadsheet\n"
        "/set_log – ընթացիկ զրույցը սահմանել որպես գրանցամատյան\n"
        "/set_report [ID] [անուն] – չատում հաշվետվություններ միացնել\n"
        "/export – տվյալների բազայի արտահանում JSON-ով\n"
        "/allow_user [ID] – օգտագործողին ավելացնել թույլատրելի ցուցակում\n"
        "/disallow_user [ID] – օգտագործողին հեռացնել թույլատրելի ցուցակից\n"
        "/allowed_users – ցուցադրել թույլատրելի օգտագործողների ցուցակը\n"
        "/set_user_name [ID] [անուն] – օգտագործողին անուն նշանակել\n"
        "/sync_sheets – <b>սինխրոնիզացիա Google Sheets-ի հետ (ավելացված կամ փոփոխված գրառումները բերում է բոտի բազա և ձևաչափ)</b>\n\n"

        "<b>Գրառումների հետ աշխատանք ընտրացանկի միջոցով:</b>\n"
        "• ➕ Ավելացնել գրառում – նոր գրառման ավելացման քայլեր\n"
        "• 📋 Ընտրել թերթիկ – աղյուսակում ակտիվ թերթիկի ընտրություն\n"
        "• 📊 Կարգավիճակ – բոտի ընթացիկ կարգավորումները\n"
        "• 📈 Վիճակագրություն – տվյալների բազայի վիճակագրություն\n\n"

        "<b>Գրառման դաշտեր:</b>\n"
        "• ամսաթիվ (date) – ամսաթիվ YYYY-MM-DD ձևաչափով\n"
        "• մատակարար (supplier) – մատակարարի անվանում\n"
        "• ուղղություն (direction) – ծախսի ուղղություն\n"
        "• ծախսի բնութագիր (description) – ծախսի նկարագրություն\n"
        "• Գումար (amount) – ծախսի գումար\n\n"

        "<b>Օգտագործման օրինակներ:</b>\n"
        "/recent 10 – ցույց տալ վերջին 10 գրառումները\n"
        "/search մթերք – գտնել «մթերք» բառով գրառումներ\n"
        "/info abc12345 – տեղեկատվություն «abc12345» ID-ով գրառման մասին\n\n"

        "<i>Բոլոր գրառումները ավտոմատ համաժամեցվում են Telegram-ի, Google Sheets-ի և տվյալների բազայի միջև:</i>"
    )

    await update.message.reply_text(help_text, parse_mode="HTML")

# === Админские команды для управления пользователями ===

async def allow_user_command(update: Update, context: CallbackContext):
    """Добавляет пользователя в список разрешенных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "👥 Օգտագործողին թույլատրելու համար օգտագործեք:\n"
            "<code>/allow_user [user_id]</code>"
        )
        return
    
    try:
        new_user_id = int(args[0])
        add_allowed_user(new_user_id)
        
        # Добавляем пользователя в users.json если его еще нет
        users = load_users()
        user_id_str = str(new_user_id)
        if user_id_str not in users:
            users[user_id_str] = {
                'active_spreadsheet_id': None,
                'active_sheet_name': None,
                'name': f"User {new_user_id}",
                'display_name': None
            }
            save_users(users)
        
        await update.message.reply_text(
            f"✅ Օգտագործող ID <code>{new_user_id}</code> ավելացված է թույլատրելի ցուցակում:",
            parse_mode="HTML"
        )
        await send_to_log_chat(context, f"Добавлен новый пользователь: ID {new_user_id}")
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ user_id ձևաչափ: Մուտքագրեք թիվ")

async def disallow_user_command(update: Update, context: CallbackContext):
    """Удаляет пользователя из списка разрешенных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "👥 Օգտագործողին արգելելու համար օգտագործեք:\n"
            "<code>/disallow_user [user_id]</code>"
        )
        return
    
    try:
        user_id_to_remove = int(args[0])
        remove_allowed_user(user_id_to_remove)
        await update.message.reply_text(
            f"✅ Օգտագործող ID <code>{user_id_to_remove}</code> հեռացված է թույլատրելի ցուցակից:",
            parse_mode="HTML"
        )
        await send_to_log_chat(context, f"Пользователь удален из разрешенных: ID {user_id_to_remove}")
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ user_id ձևաչափ: Մուտքագրեք թիվ")

async def allowed_users_command(update: Update, context: CallbackContext):
    """Показывает список разрешенных пользователей"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    allowed = load_allowed_users()
    users = load_users()
    
    if not allowed:
        await update.message.reply_text("ℹ️ Թույլատրելի օգտագործողներ չկան:")
        return
    
    text = "👥 Թույլատրելի օգտագործողների ցուցակ:\n\n"
    for idx, user_id in enumerate(allowed, 1):
        user_info = users.get(str(user_id), {})
        user_name = user_info.get('name', 'Անհայտ')
        display_name = user_info.get('display_name', 'Չկա')
        text += f"{idx}. ID: <code>{user_id}</code>\n"
        text += f"   👤 Տրված անուն: <b>{display_name}</b>\n"
        text += f"   👤 Telegram անուն: {user_name}\n\n"
    
    await update.message.reply_text(text, parse_mode="HTML")

async def set_user_name_command(update: Update, context: CallbackContext):
    """Назначает отображаемое имя пользователю"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "👤 Օգտագործողին անուն նշանակելու համար օգտագործեք:\n"
            "<code>/set_user_name [user_id] [անուն]</code>"
        )
        return
    
    try:
        target_user_id = int(args[0])
        display_name = ' '.join(args[1:])
        
        # Обновляем пользователя
        users = load_users()
        user_id_str = str(target_user_id)
        
        if user_id_str not in users:
            users[user_id_str] = {}
            
        users[user_id_str]['display_name'] = display_name
        save_users(users)
        
        await update.message.reply_text(
            f"✅ Օգտագործող ID <code>{target_user_id}</code> սահմանված է նոր անունը: <b>{display_name}</b>",
            parse_mode="HTML"
        )
        await send_to_log_chat(context, f"Админ установил имя пользователя {target_user_id}: {display_name}")
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ user_id ձևաչափ: Մուտքագրեք թիվ")

# === Менյու ընտրության աղյուսակ ===

async def select_spreadsheet_menu(update: Update, context: CallbackContext):
    """Показывает меню выбора Google Spreadsheet"""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    from google_connector import get_all_spreadsheets
    
    try:
        spreadsheets = get_all_spreadsheets()
        
        if not spreadsheets:
            keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
            await query.edit_message_text(
                "❌ Հասանելի աղյուսակներ չեն գտնված.\n",
                reply_markup=InlineKeyboardMarkup(keyboard))
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
        
        text = f"📊 Ընտրեք Google Spreadsheet ({len(spreadsheets)} Հասանելի):"
        if len(spreadsheets) > 10:
            text += f"\n\nՑուցադրված են առաջին 10."
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard))
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]]
        await query.edit_message_text(
            f"⚠️ Աղյուսակները չեն ստացված: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard))
        

async def select_spreadsheet(update: Update, context: CallbackContext):
    """Выбирает конкретную Google Spreadsheet и показывает её листы"""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    spreadsheet_id = query.data.replace("spreadsheet_", "")
    
    from google_connector import get_spreadsheet_info
    
    try:
        spreadsheet_info = get_spreadsheet_info(spreadsheet_id)
        
        if not spreadsheet_info:
            keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="select_spreadsheet")]]
            await query.edit_message_text(
                "❌ Չստացվեց աղյուսակի ինֆորմացիան ստանալ.",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        if not spreadsheet_info['sheets']:
            keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="select_spreadsheet")]]
            await query.edit_message_text(
                f"❌ Աղյուսակ'{spreadsheet_info['title']}'-ում թերթեր չեն գտնվել.",
                reply_markup=InlineKeyboardMarkup(keyboard))
            return
        
        # Сохраняем выбранную таблицу для пользователя
        update_user_settings(user_id, {'active_spreadsheet_id': spreadsheet_id})
        
        keyboard = []
        for sheet in spreadsheet_info['sheets']:
            # Показываем информацию о количестве строк
            sheet_info = f"{sheet['title']} ({sheet['row_count']} строк)"
            keyboard.append([InlineKeyboardButton(
                f"📋 {sheet_info}", 
                callback_data=f"final_sheet_{sheet['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Աղյուսակների ցուցակ", callback_data="select_spreadsheet")])
        
        await query.edit_message_text(
            f"📊 Աղյուսակ: <b>{spreadsheet_info['title']}</b>\n"
            f"📋 Թերթեր: {spreadsheet_info['sheets_count']}\n\n"
            f"Ընտրեք թերթիկը, որին կուզեք գրառումներ ավելացնել:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Հետ", callback_data="select_spreadsheet")]]
        await query.edit_message_text(
            f"⚠️ Սխալ: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard))
        

async def select_final_sheet(update: Update, context: CallbackContext):
    """Окончательно выбирает лист и сохраняет настройки"""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    sheet_name = query.data.replace("final_sheet_", "")
    
    # Обновляем настройки пользователя
    update_user_settings(user_id, {'active_sheet_name': sheet_name})
    
    user_settings = get_user_settings(user_id)
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    
    await query.edit_message_text(
        f"✅ Կարգավորումը ավարտվածա!\n\n"
        f"📋 Ակտիվ թերթիկ: <b>{sheet_name}</b>\n\n"
        f"Այժմ կարող եք գրառումներ ավելացնել:",
        parse_mode="HTML",
        reply_markup=create_main_menu(user_id)
    )
    
    await send_to_log_chat(context, f"Пользователь {user_id} выбрал лист: {sheet_name}")

async def message_handler(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    step = context.user_data.get('pay_step')
    if step == 'amount':
        try:
            amount = float(update.message.text.strip())
            context.user_data['pay_amount'] = amount
            curr_date = datetime.now().strftime('%Y-%m-%d') 
            context.user_data['pay_date_from'] = curr_date
            context.user_data['pay_date_to'] = curr_date
            context.user_data['pay_step'] = 'comment'
            await update.message.reply_text("Մուտքագրեք մեկնաբանություն (կամ ուղարկեք +):")
        except ValueError:
            await update.message.reply_text("❌ Սխալ գումար: Մուտքագրեք թիվ:")
    elif step == 'period':
        curr_date = datetime.now().strftime('%Y-%m-%d')
        period = update.message.text.strip()
        if period == "+":
            date_from, date_to = None, None
        else:
            parts = period.split()
            date_from = parts[0] if len(parts) > 0 else None
            date_to = parts[1] if len(parts) > 1 else None
        if date_from == "+":
            date_from = curr_date
        if date_to == "+":
            date_to = curr_date   
        def checkIsDate(date_str):
            try:
                pd.to_datetime(date_str, format='%Y-%m-%d', errors='raise')
                return True
            except ValueError:
                return False
        if date_from and not checkIsDate(date_from):
            await update.message.reply_text("❌ Սխալ ամսաթիվ: Մուտքագրեք ամսաթիվը ձևաչափով 2024-01-01:")
            step = 'period'
        elif date_to and not checkIsDate(date_to):
            await update.message.reply_text("❌ Սխալ ամսաթիվ: Մուտքագրեք ամսաթիվը ձևաչափով 2024-01-01:")
            step = 'period'
        if date_from and date_to and pd.to_datetime(date_from) > pd.to_datetime(date_to):
            date_from, date_to = date_to, date_from
            
        context.user_data['pay_date_from'] = date_from
        context.user_data['pay_date_to'] = date_to
        context.user_data['pay_step'] = 'comment'
        await update.message.reply_text("Մուտքագրեք մեկնաբանություն (կամ ուղարկեք +):")
    elif step == 'comment':
        comment = update.message.text.strip()
        if comment == "+":
            comment = ""
        display_name = context.user_data['pay_user']
        amount = context.user_data['pay_amount']
        date_from = context.user_data['pay_date_from']
        date_to = context.user_data['pay_date_to']
        user_settings = get_user_settings(user_id)
        spreadsheet_id = user_settings.get('active_spreadsheet_id')
        sheet_name = user_settings.get('active_sheet_name')
        add_payment(display_name, spreadsheet_id, sheet_name, amount, date_from, date_to, comment)
        uId = await getUserIdByDisplayName(display_name)
        senderId = update.effective_user.id
        users = load_users()
        senderName = users[str(senderId)]['display_name']
        payment_text = "💰 <b> Վճարման տեղեկություն </b>\n\n"
        payment_text += f"📊 Փոխանցող: {senderName}\n"
        payment_text += f"👤 Ստացող: {display_name}\n"
        payment_text += f"🗓 Ամսաթիվ: {date_from}\n"
        payment_text += f"💵 Գումար: {amount:,.2f} դրամ\n"
        payment_text += f"📝 Նկարագրություն: {comment}\n"
        
        
        keyboard = [[InlineKeyboardButton("✅ Վերադառնալ աշխատակցին", callback_data=f"pay_user_{display_name}")]]
        await update.message.reply_text("✅ Վճարումը ավելացված է։", 
                                        reply_markup=InlineKeyboardMarkup(keyboard))
        await clear_user_data(update, context)
        await sendMessageToUser(update, context, uId, payment_text, reply_markup=None)


async def clear_user_data(update: Update, context: CallbackContext):
    """Очищает данные пользователя"""
    spreadsheet_id = context.user_data.get('active_spreadsheet_id')
    sheet_name = context.user_data.get('active_sheet_name')
    context.user_data.clear()
    context.user_data['active_spreadsheet_id'] = spreadsheet_id
    context.user_data['active_sheet_name'] = sheet_name
   
   
async def sendMessageToUser(update, context, user_id, text, reply_markup=None):
    """Отправляет сообщение пользователю по ID"""
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
        await send_to_log_chat(context, f"Ошибка отправки сообщения пользователю {user_id}: {e}")
        
# === Настройка приложения ===
async def send_payment_report(update, context, display_name):
    """
    Формирует и отправляет Excel-отчет с разбивкой по промежуткам выплат для заданного работника.
    В конце добавляется итоговая таблица по всем листам.
    """
    all_summaries = []
    
    # 1. Синхронизация данных из Google Sheets в БД
    # spreadsheets = get_all_spreadsheets()
    # for spreadsheet in spreadsheets:
    #     spreadsheet_id = spreadsheet['id']
    #     for sheets in get_worksheets_info(spreadsheet_id):
    #         for sheet in sheets:
    #             if isinstance(sheet, str):
    #                 break
    #             sheet_name = sheet.get('title') or sheet.get('name')
    #             worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
    #             if not worksheet:
    #                 continue
    #             rows = worksheet.get_all_records()
    #             for row in rows:
    #                 if str(row.get('մատակարար', '')).strip() == display_name:
    #                     record_id = str(row.get('ID', '')).strip()
    #                     if not get_record_from_db(record_id):
    #                         try:
    #                             amount = float(str(row.get('Արժեք', '0')).replace(',', '.').replace(' ', ''))
    #                         except Exception:
    #                             amount = 0.0
    #                         record = {
    #                             'id': record_id,
    #                             'date': str(row.get('ամսաթիվ', '')).replace("․", ".").strip(),
    #                             'supplier': display_name,
    #                             'direction': str(row.get('ուղղություն', '')).strip(),
    #                             'description': str(row.get('ծախսի բնութագիր', '')).strip(),
    #                             'amount': amount,
    #                             'spreadsheet_id': spreadsheet_id,
    #                             'sheet_name': sheet_name
    #                         }
    #                         add_record_to_db(record)

    # 2. Получаем все записи из БД и группируем по листам
    db_records = get_all_records()
    filtered_recrods = []
    sum_ = 0
    for record in db_records:
        if record['amount'] == 0:
            continue
        if record['supplier'] != display_name:
            continue
        record['date'] = normalize_date(record['date'])
        if record['supplier'] == "Նարեկ" and (datetime.strptime(record['date'], '%d.%m.%y').date() >= datetime.strptime("2025-05-10", '%Y-%m-%d').date()):
            filtered_recrods.append(record)
        elif record['supplier'] != "Նարեկ" and (datetime.strptime(record['date'], '%d.%m.%y').date() >= datetime.strptime("2024-12-05", '%Y-%m-%d').date()):
                filtered_recrods.append(record)
        else:
            pass

    sheets = {}
    for rec in filtered_recrods:
        if rec.get('supplier') == display_name:
            spreadsheet_id = rec.get('spreadsheet_id', '—')
            sheet_name = rec.get('sheet_name', '—')
            key = (spreadsheet_id, sheet_name)
            sheets.setdefault(key, []).append(rec)
            
    # 3. Формируем и отправляем отчет по каждому листу
    for (spreadsheet_id, sheet_name), records in sheets.items():
        
        df = pd.DataFrame(records)
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'], errors='coerce', dayfirst=True)
        else:
            df['date'] = pd.to_datetime([])
        
        
        df_amount_total = df['amount'].sum() if not df.empty else 0

        df.loc["Իտոգ"] = [
          '—', '—', '—', '—', '—', df_amount_total, '—', '—', '—', '—'  
        ]

        # Остаток по невыплаченным расходам
        paid_dates = []
        
        # Сохраняем для итоговой сводки
        all_summaries.append({
            'Աղյուսակ': spreadsheet_id,
            'Թեթր': sheet_name,
            'Ծախս': df_amount_total,
            "Վճար": '—',  
            'Մնացորդ': '—'
        })

        summary = pd.DataFrame([{
            'Ընդհանուր ծախս': df_amount_total,
        }])

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='All Expenses', index=False)
            summary.to_excel(writer, sheet_name='Summary', index=False)
        output.seek(0)

        await update.effective_message.reply_document(
            document=output,
            filename=f"{display_name}_{sheet_name}_report.xlsx",
            caption=(
                f"Թերթ: {sheet_name}\n"
                f"Ընդհանուր ծախս: {df_amount_total:,.2f}\n"
            )
        )
        
    

 
    # 4. Итоговая таблица по всем листам
    if all_summaries:
        df_total = pd.DataFrame(all_summaries)
        total_expenses_all = df_total['Ծախս'].sum()
        payments = get_payments(display_name, spreadsheet_id, sheet_name)
        if not payments:
            total_paid_all = 0
        else:
            df_pay_raw = pd.DataFrame(
                payments, 
                columns=['amount', 'date_from', 'date_to', 'comment', 'created_at']
            )

            # Приводим типы
            df_pay_raw['amount'] = pd.to_numeric(df_pay_raw['amount'], errors='coerce').fillna(0)
            df_pay_raw['date_from'] = pd.to_datetime(df_pay_raw['date_from'], errors='coerce')
            df_pay_raw['date_to'] = pd.to_datetime(df_pay_raw['date_to'], errors='coerce')

            # Слияние интервалов и агрегирование
            df_pay = merge_payment_intervals(df_pay_raw[['amount', 'date_from', 'date_to']])

            # Итоговая сумма после объединения
            total_paid_all = df_pay['amount'].sum()
        total_left_all = total_expenses_all - total_paid_all
        df_total.loc['Իտոգ'] = [
            '—', '—',
            total_expenses_all,
            total_paid_all,
            total_left_all
        ]

        output_total = BytesIO()
        with pd.ExcelWriter(output_total, engine='openpyxl') as writer:
            df_total.to_excel(writer, sheet_name='Իտոգներ', index=False)
        output_total.seek(0)
        
        await update.effective_message.reply_document(
            document=output_total,
            filename=f"{display_name}_TOTAL_report.xlsx",
            caption=(
                f"Ընդհանոր ծախսեր:\n"
                f"• Ընդհանուր ծախս: {total_expenses_all:,.2f}\n"
                f"• Ընդհանուր Վճար: {total_paid_all:,.2f}\n"
                f"• Ընդհանուր մնացորդ: {total_left_all:,.2f}"
            )
        )
async def getUserIdByDisplayName(display_name):
    """Получает ID пользователя по его отображаемому имени"""
    users = load_users()
    for user_id, info in users.items():
        if info.get('display_name') == display_name:
            return int(user_id)
    return None
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
            entry_points=[
                CallbackQueryHandler(start_add_record, pattern="^add_record$"),
                CallbackQueryHandler(start_add_skip_record, pattern="^add_skip_record$"),  # <--- добавьте это!
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
                MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler)  # Добавляем fallback для меню
            ],
        )
        
        # Настройка ConversationHandler для редактирования записей
        edit_record_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(button_handler, pattern="^edit_")],
            states={
                EDIT_VALUE: [MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, get_edit_value)],
            },
            fallbacks=[
                CommandHandler("cancel", cancel),
                CallbackQueryHandler(button_handler, pattern="^cancel_edit_"),
                MessageHandler(filters.Text(["📋 Մենյու"]), text_menu_handler)  # Добавляем fallback для меню
            ],
        )
        application.add_handler(MessageHandler(filters.TEXT & ~filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, message_handler))   
        # Регистрация обработчиков команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("set_log", set_log_command))
        application.add_handler(CommandHandler("set_sheet", set_sheet_command))
        application.add_handler(CommandHandler("set_report", set_report_command))
        application.add_handler(CommandHandler("search", search_command))
        application.add_handler(CommandHandler("export", export_command))
        application.add_handler(CommandHandler("recent", recent_command))
        application.add_handler(CommandHandler("info", info_command))
        application.add_handler(CommandHandler("initialize_sheets", initialize_sheets_command))
        application.add_handler(CommandHandler("allow_user", allow_user_command))
        application.add_handler(CommandHandler("disallow_user", disallow_user_command))
        application.add_handler(CommandHandler("allowed_users", allowed_users_command))
        application.add_handler(CommandHandler("set_user_name", set_user_name_command))
        application.add_handler(CommandHandler("sync_sheets", sync_sheets_command))
        application.add_handler(CommandHandler("my_report", my_report_command))
    
        # Регистрация ConversationHandler'ов
        application.add_handler(add_record_conv)
        application.add_handler(edit_record_conv)
        
        # Регистрация обработчика кнопок (должен быть после ConversationHandler'ов)
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.Text(["📋 Մենյու"]) & ~filters.COMMAND, text_menu_handler))
        
        # Регистрация обработчика ошибок
        application.add_error_handler(error_handler)
        
        # Запуск бота
        logger.info("🚀 Бот запущен!")
        print("🚀 Бот запущен! Нажмите Ctrl+C для остановки.")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Критическая ошибка при запуске бота: {e}")
        print(f"❌ Критическая ошибка: {e}")

if __name__ == '__main__':
    # Ինքնուրույն ստուգում, թե արդյոք ֆայլերը գոյություն ունեն, եթե ոչ՝ ստեղծում է
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