import json
import logging
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, CallbackContext
from google_connector import get_worksheets_info, add_record_to_sheet, update_record_in_sheet, delete_record_from_sheet, get_record_by_id
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
        [InlineKeyboardButton("➕ Добавить запись", callback_data="add_record")],
        [InlineKeyboardButton("📋 Выбрать лист", callback_data="select_sheet")],
        [InlineKeyboardButton("📊 Статус", callback_data="status")],
        [InlineKeyboardButton("📈 Статистика", callback_data="stats")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_edit_menu(record_id: str):
    """Создает меню для редактирования записи"""
    keyboard = [
        [InlineKeyboardButton("📅 Дата", callback_data=f"edit_date_{record_id}")],
        [InlineKeyboardButton("🏪 Поставщик", callback_data=f"edit_supplier_{record_id}")],
        [InlineKeyboardButton("🧭 Направление", callback_data=f"edit_direction_{record_id}")],
        [InlineKeyboardButton("📝 Описание", callback_data=f"edit_description_{record_id}")],
        [InlineKeyboardButton("💰 Сумма", callback_data=f"edit_amount_{record_id}")],
        [InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{record_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_edit")]
    ]
    return InlineKeyboardMarkup(keyboard)

# === Обработчики команд ===

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "👋 Добро пожаловать в бот учёта расходов!\n\n"
        "Функции:\n"
        "• ➕ Добавление записей в Google Sheets\n"
        "• ✏️ Редактирование и удаление записей\n"
        "• 📊 Синхронизация с базой данных\n"
        "• 📝 Логирование действий\n\n"
        "Команды:\n"
        "/menu - основное меню\n"
        "/set_log - установить лог-чат (только админы)\n"
        "/set_sheet - установить Google Sheet ID",
        reply_markup=create_main_menu()
    )

async def menu_command(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "📋 Главное меню:",
        reply_markup=create_main_menu()
    )

async def set_log_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and len(ADMIN_IDS) > 0:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    chat_id = update.effective_chat.id
    set_log_chat(chat_id)
    await update.message.reply_text(
        f"✅ Лог-чат установлен!\n"
        f"Chat ID: <code>{chat_id}</code>\n"
        f"Все логи будут отправляться в этот чат.",
        parse_mode="HTML"
    )
    await send_to_log_chat(context, f"Лог-чат активирован. Chat ID: {chat_id}")

async def set_sheet_command(update: Update, context: CallbackContext):
    """Команда для установки ID Google Spreadsheet"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and len(ADMIN_IDS) > 0:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    # Получаем аргументы команды
    args = context.args
    if not args:
        await update.message.reply_text(
            "📊 Для установки Google Spreadsheet используйте:\n"
            "<code>/set_sheet YOUR_SPREADSHEET_ID</code>\n\n"
            "ID можно найти в URL таблицы:\n"
            "https://docs.google.com/spreadsheets/d/<b>SPREADSHEET_ID</b>/edit",
            parse_mode="HTML"
        )
        return
    
    spreadsheet_id = args[0].strip()
    
    # Проверяем доступность таблицы
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        if not sheets_info:
            await update.message.reply_text("❌ Не удалось получить доступ к таблице. Проверьте ID и права доступа.")
            return
        
        # Сохраняем ID таблицы
        set_active_spreadsheet(spreadsheet_id)
        
        await update.message.reply_text(
            f"✅ Google Spreadsheet подключена!\n"
            f"📊 Название: <b>{spreadsheet_title}</b>\n"
            f"🆔 ID: <code>{spreadsheet_id}</code>\n"
            f"📋 Найдено листов: {len(sheets_info)}\n\n"
            f"Теперь выберите лист для работы через /menu → 📋 Выбрать лист",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Подключена Google Spreadsheet: {spreadsheet_title} (ID: {spreadsheet_id})")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка подключения к таблице:\n<code>{str(e)}</code>\n\n"
            f"Убедитесь, что:\n"
            f"• ID таблицы корректный\n"
            f"• Сервисный аккаунт имеет доступ к таблице\n"
            f"• Файл credentials корректный",
            parse_mode="HTML"
        )

# === Обработчики кнопок ===

async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "add_record":
        return await start_add_record(update, context)
    elif data == "select_sheet":
        return await select_sheet_menu(update, context)
    elif data == "status":
        return await show_status(update, context)
    elif data == "stats":
        return await show_stats(update, context)
    elif data.startswith("sheet_"):
        return await select_sheet(update, context)
    elif data.startswith("edit_"):
        return await handle_edit_button(update, context)
    elif data.startswith("delete_"):
        return await handle_delete_button(update, context)
    elif data.startswith("confirm_delete_"):
        return await confirm_delete(update, context)
    elif data == "cancel_edit":
        await query.edit_message_text("❌ Редактирование отменено.")
        return ConversationHandler.END
    elif data == "back_to_menu":
        await query.edit_message_text("📋 Главное меню:", reply_markup=create_main_menu())

async def show_status(update: Update, context: CallbackContext):
    query = update.callback_query
    config = load_config()
    
    spreadsheet_id = config.get('active_spreadsheet_id')
    sheet_name = config.get('active_sheet_name')
    log_chat_id = config.get('log_chat_id')
    
    status_text = "📊 Текущий статус:\n\n"
    
    if spreadsheet_id:
        status_text += f"✅ Подключена таблица: <code>{spreadsheet_id[:10]}...</code>\n"
        if sheet_name:
            status_text += f"📋 Активный лист: <code>{sheet_name}</code>\n"
        else:
            status_text += "⚠️ Лист не выбран\n"
    else:
        status_text += "❌ Таблица не подключена\n"
    
    if log_chat_id:
        status_text += f"📝 Лог-чат: <code>{log_chat_id}</code>\n"
    else:
        status_text += "📝 Лог-чат не установлен\n"
    
    # Добавляем кнопку "Назад"
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
    
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
            f"📈 Статистика базы данных:\n\n"
            f"📝 Всего записей: {stats['total_records']}\n"
            f"💰 Общая сумма: {stats['total_amount']:,.2f}\n"
            f"📅 За последние 30 дней: {stats['recent_records']} записей"
        )
    else:
        stats_text = "❌ Ошибка получения статистики"
    
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
    
    await query.edit_message_text(
        stats_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def select_sheet_menu(update: Update, context: CallbackContext):
    query = update.callback_query
    
    spreadsheet_id = get_active_spreadsheet_id()
    if not spreadsheet_id:
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Сначала нужно подключить таблицу.\n"
            "Используйте команду /set_sheet",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        
        if not sheets_info:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
            await query.edit_message_text(
                "❌ В таблице нет листов.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        keyboard = []
        for info in sheets_info:
            keyboard.append([InlineKeyboardButton(
                f"📋 {info['title']}", 
                callback_data=f"sheet_{info['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            f"📋 Выберите лист из таблицы <b>{spreadsheet_title}</b>:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
        await query.edit_message_text(
            f"⚠️ Ошибка: {e}",
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
        f"✅ Выбран лист: <b>{sheet_name}</b>\n\n"
        f"Теперь вы можете добавлять записи!",
        parse_mode="HTML",
        reply_markup=create_main_menu()
    )
    
    await send_to_log_chat(context, f"Выбран активный лист: {sheet_name}")

# === Добавление записи ===

async def start_add_record(update: Update, context: CallbackContext):
    query = update.callback_query
    
    # Проверяем настройки
    if not get_active_spreadsheet_id() or not get_active_sheet_name():
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
        await query.edit_message_text(
            "❌ Сначала нужно выбрать лист для работы.\n"
            "Используйте 📋 Выбрать лист",
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
        f"➕ Добавление новой записи\n"
        f"🆔 ID: <code>{record_id}</code>\n\n"
        f"📅 Дата (по умолчанию: {current_date})\n"
        f"Введите дату в формате YYYY-MM-DD или отправьте '+' для использования текущей даты:",
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
                "❌ Неверный формат даты. Используйте YYYY-MM-DD или отправьте '+' для текущей даты."
            )
            return DATE
    
    context.user_data['record']['date'] = date_value
    
    await update.message.reply_text(
        f"✅ Дата: {date_value}\n\n"
        f"🏪 Введите поставщика (մատակարար):"
    )
    
    return SUPPLIER

async def get_supplier(update: Update, context: CallbackContext):
    supplier = update.message.text.strip()
    context.user_data['record']['supplier'] = supplier
    
    await update.message.reply_text(
        f"✅ Поставщик: {supplier}\n\n"
        f"🧭 Введите направление (ուղղություն):"
    )
    
    return DIRECTION

async def get_direction(update: Update, context: CallbackContext):
    direction = update.message.text.strip()
    context.user_data['record']['direction'] = direction
    
    await update.message.reply_text(
        f"✅ Направление: {direction}\n\n"
        f"📝 Введите описание расхода (ծախսի բնութագիր):"
    )
    
    return DESCRIPTION

async def get_description(update: Update, context: CallbackContext):
    description = update.message.text.strip()
    context.user_data['record']['description'] = description
    
    await update.message.reply_text(
        f"✅ Описание: {description}\n\n"
        f"💰 Введите сумму (Արժեք):"
    )
    
    return AMOUNT

async def get_amount(update: Update, context: CallbackContext):
    amount_text = update.message.text.strip()
    
    try:
        amount = float(amount_text)
        context.user_data['record']['amount'] = amount
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат суммы. Введите число (например: 1000 или 1000.50):"
        )
        return AMOUNT
    
    # Сохраняем запись
    record = context.user_data['record']
    
    try:
        # Добавляем в Google Sheets
        spreadsheet_id = get_active_spreadsheet_id()
        sheet_name = get_active_sheet_name()
        
        sheet_success = add_record_to_sheet(spreadsheet_id, sheet_name, record)
        
        # Добавляем в базу данных
        db_success = add_record_to_db(record)
        
        # Формируем сообщение о результате
        if sheet_success and db_success:
            status = "✅ Запись успешно добавлена в Google Sheets и базу данных!"
            log_message = f"Добавлена запись ID: {record['id']}"
        elif sheet_success:
            status = "⚠️ Запись добавлена в Google Sheets, но возникла ошибка с базой данных."
            log_message = f"Запись ID: {record['id']} добавлена только в Google Sheets"
        elif db_success:
            status = "⚠️ Запись добавлена в базу данных, но возникла ошибка с Google Sheets."
            log_message = f"Запись ID: {record['id']} добавлена только в БД"
        else:
            status = "❌ Ошибка при сохранении записи!"
            log_message = f"Ошибка сохранения записи ID: {record['id']}"
        
        # Отправляем результат с кнопкой ред