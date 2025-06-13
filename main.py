import json
import logging
import os
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters, CallbackContext
from google_connector import (get_worksheets_info, add_record_to_sheet, 
                            update_record_in_sheet, delete_record_from_sheet, 
                            get_record_by_id, get_all_spreadsheets, get_spreadsheet_info)
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
        [InlineKeyboardButton("📊 Выбрать таблицу", callback_data="select_spreadsheet")],
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

def format_record_info(record: dict) -> str:
    """Форматирует информацию о записи"""
    return (
        f"🆔 ID: <code>{record.get('id', 'N/A')}</code>\n"
        f"📅 Дата: <b>{record.get('date', 'N/A')}</b>\n"
        f"🏪 Поставщик: <b>{record.get('supplier', 'N/A')}</b>\n"
        f"🧭 Направление: <b>{record.get('direction', 'N/A')}</b>\n"
        f"📝 Описание: <b>{record.get('description', 'N/A')}</b>\n"
        f"💰 Сумма: <b>{record.get('amount', 0):,.2f}</b>"
    )

# === Обработчики команд ===

async def start(update: Update, context: CallbackContext):
    # Инициализируем базу данных при запуске
    init_db()
    
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
    amount_input = update.message.text.strip()
    
    try:
        amount = float(amount_input)
        context.user_data['record']['amount'] = amount
        
        # Получаем полную запись
        record = context.user_data['record']
        
        # Сохраняем в базу данных
        db_success = add_record_to_db(record)
        
        # Сохраняем в Google Sheets
        spreadsheet_id = get_active_spreadsheet_id()
        sheet_name = get_active_sheet_name()
        sheet_success = add_record_to_sheet(spreadsheet_id, sheet_name, record)
        
        # Форматируем результат
        result_text = "✅ Запись добавлена!\n\n"
        result_text += format_record_info(record)
        result_text += "\n\n"
        
        if db_success and sheet_success:
            result_text += "✅ Сохранено в БД и Google Sheets"
        elif db_success:
            result_text += "✅ Сохранено в БД\n⚠️ Ошибка сохранения в Google Sheets"
        elif sheet_success:
            result_text += "⚠️ Ошибка сохранения в БД\n✅ Сохранено в Google Sheets"
        else:
            result_text += "❌ Ошибка сохранения в БД и Google Sheets"
        
        # Создаем кнопку редактирования
        keyboard = [[InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_record_{record['id']}")]]
        
        await update.message.reply_text(
            result_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Отправляем в лог-чат
        await send_to_log_chat(context, f"Добавлена новая запись ID: {record['id']}, сумма: {amount}")
        
        # Очищаем данные пользователя
        context.user_data.clear()
        
        return ConversationHandler.END
        
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат суммы. Введите число (например: 1000 или 1000.50):"
        )
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
            'date': 'дату (YYYY-MM-DD)',
            'supplier': 'поставщика',
            'direction': 'направление',
            'description': 'описание',
            'amount': 'сумму'
        }
        
        await query.edit_message_text(
            f"✏️ Редактирование записи ID: <code>{record_id}</code>\n\n"
            f"Введите новое значение для поля '{field_names.get(field, field)}':",
            parse_mode="HTML"
        )
        
        return EDIT_VALUE

async def show_edit_menu(update: Update, context: CallbackContext, record_id: str):
    """Показывает меню редактирования записи"""
    query = update.callback_query
    
    # Получаем запись из базы данных
    record = get_record_from_db(record_id)
    if not record:
        await query.edit_message_text("❌ Запись не найдена.")
        return ConversationHandler.END
    
    text = "✏️ Редактирование записи:\n\n"
    text += format_record_info(record)
    text += "\n\nВыберите поле для редактирования:"
    
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
        await update.message.reply_text("❌ Ошибка редактирования.")
        return ConversationHandler.END
    
    # Валидация данных
    if field == 'date':
        try:
            datetime.strptime(new_value, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат даты. Используйте YYYY-MM-DD."
            )
            return EDIT_VALUE
    elif field == 'amount':
        try:
            new_value = float(new_value)
        except ValueError:
            await update.message.reply_text(
                "❌ Неверный формат суммы. Введите число."
            )
            return EDIT_VALUE
    
    # Обновляем в базе данных
    db_success = update_record_in_db(record_id, field, new_value)
    
    # Обновляем в Google Sheets
    spreadsheet_id = get_active_spreadsheet_id()
    sheet_name = get_active_sheet_name()
    sheet_success = update_record_in_sheet(spreadsheet_id, sheet_name, record_id, field, new_value)
    
    # Результат
    if db_success and sheet_success:
        result_text = f"✅ Поле '{field}' обновлено на '{new_value}'"
    elif db_success:
        result_text = f"✅ Поле '{field}' обновлено в БД\n⚠️ Ошибка обновления в Google Sheets"
    elif sheet_success:
        result_text = f"⚠️ Ошибка обновления в БД\n✅ Поле '{field}' обновлено в Google Sheets"
    else:
        result_text = f"❌ Ошибка обновления поля '{field}'"
    
    await update.message.reply_text(result_text)
    
    # Отправляем в лог-чат
    await send_to_log_chat(context, f"Обновлена запись ID: {record_id}, поле: {field}, новое значение: {new_value}")
    
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
        await query.edit_message_text("❌ Запись не найдена.")
        return ConversationHandler.END
    
    text = "🗑 Подтверждение удаления:\n\n"
    text += format_record_info(record)
    text += "\n\n⚠️ Это действие нельзя отменить!"
    
    keyboard = [
        [InlineKeyboardButton("🗑 Да, удалить", callback_data=f"confirm_delete_{record_id}")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_edit")]
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
    
    # Удаляем из базы данных
    db_success = delete_record_from_db(record_id)
    
    # Удаляем из Google Sheets
    spreadsheet_id = get_active_spreadsheet_id()
    sheet_name = get_active_sheet_name()
    sheet_success = delete_record_from_sheet(spreadsheet_id, sheet_name, record_id)
    
    # Результат
    # Результат
    if db_success and sheet_success:
        result_text = f"✅ Запись ID: <code>{record_id}</code> удалена"
    elif db_success:
        result_text = f"✅ Запись удалена из БД\n⚠️ Ошибка удаления из Google Sheets"
    elif sheet_success:
        result_text = f"⚠️ Ошибка удаления из БД\n✅ Запись удалена из Google Sheets"
    else:
        result_text = f"❌ Ошибка удаления записи ID: <code>{record_id}</code>"
    
    await query.edit_message_text(
        result_text,
        parse_mode="HTML",
        reply_markup=create_main_menu()
    )
    
    # Отправляем в лог-чат
    await send_to_log_chat(context, f"Удалена запись ID: {record_id}")
    
    return ConversationHandler.END

# === Обработчик отмены ===

async def cancel(update: Update, context: CallbackContext):
    """Отменяет текущую операцию"""
    await update.message.reply_text(
        "❌ Операция отменена.",
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
        await send_to_log_chat(context, f"ОШИБКА: {str(context.error)}")

# === Команда поиска записей ===

async def search_command(update: Update, context: CallbackContext):
    """Команда поиска записей"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "🔍 Поиск записей:\n"
            "Используйте: <code>/search [текст для поиска]</code>\n\n"
            "Поиск производится по полям: поставщик, направление, описание",
            parse_mode="HTML"
        )
        return
    
    query = " ".join(args)
    
    try:
        from database import search_records
        records = search_records(query, limit=10)
        
        if not records:
            await update.message.reply_text(
                f"🔍 По запросу '<b>{query}</b>' ничего не найдено.",
                parse_mode="HTML"
            )
            return
        
        result_text = f"🔍 Найдено {len(records)} записей по запросу '<b>{query}</b>':\n\n"
        
        for i, record in enumerate(records, 1):
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   📝 {record['description'][:50]}{'...' if len(record['description']) > 50 else ''}\n\n"
        
        # Если записей много, предупреждаем
        if len(records) == 10:
            result_text += "ℹ️ Показаны первые 10 результатов. Уточните запрос для более точного поиска."
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка поиска: {e}")

# === Команда экспорта данных ===

async def export_command(update: Update, context: CallbackContext):
    """Команда экспорта данных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS and len(ADMIN_IDS) > 0:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
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
                caption=f"📤 Резервная копия базы данных\n"
                       f"📊 Записей: {backup_data['stats']['total_records']}\n"
                       f"💰 Общая сумма: {backup_data['stats']['total_amount']:,.2f}\n"
                       f"📅 Дата создания: {backup_data['backup_date']}"
            )
        
        # Удаляем временный файл
        os.remove(filename)
        
        await send_to_log_chat(context, f"Создана резервная копия: {backup_data['stats']['total_records']} записей")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка экспорта: {e}")

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
            await update.message.reply_text("📝 Записей в базе данных нет.")
            return
        
        result_text = f"📝 Последние {len(records)} записей:\n\n"
        
        for i, record in enumerate(records, 1):
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   🧭 {record['direction']}\n"
            result_text += f"   📝 {record['description']}\n\n"
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения записей: {e}")

# === Команда информации о записи ===

async def info_command(update: Update, context: CallbackContext):
    """Показывает детальную информацию о записи по ID"""
    args = context.args
    if not args:
        await update.message.reply_text(
            "ℹ️ Информация о записи:\n"
            "Используйте: <code>/info [ID записи]</code>",
            parse_mode="HTML"
        )
        return
    
    record_id = args[0].strip()
    
    try:
        record = get_record_from_db(record_id)
        
        if not record:
            await update.message.reply_text(
                f"❌ Запись с ID <code>{record_id}</code> не найдена.",
                parse_mode="HTML"
            )
            return
        
        result_text = "ℹ️ Детальная информация о записи:\n\n"
        result_text += format_record_info(record)
        result_text += f"\n\n📅 Создана: {record.get('created_at', 'N/A')}"
        result_text += f"\n🔄 Обновлена: {record.get('updated_at', 'N/A')}"
        
        # Создаем кнопку редактирования
        keyboard = [[InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_record_{record_id}")]]
        
        await update.message.reply_text(
            result_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка получения информации: {e}")

# === Команда помощи ===

async def help_command(update: Update, context: CallbackContext):
    """Показывает справку по командам"""
    help_text = """
📖 **Справка по командам:**

**Основные команды:**
/start - запуск бота и основное меню
/menu - показать главное меню
/help - эта справка

**Управление записями:**
/recent [N] - показать последние N записей (по умолчанию 5)
/search [текст] - поиск записей по тексту
/info [ID] - детальная информация о записи

**Команды администратора:**
/set_sheet [ID] - подключить Google Spreadsheet
/set_log - установить текущий чат как лог-чат
/export - экспорт базы данных в JSON

**Работа с записями через меню:**
• ➕ Добавить запись - пошаговое добавление новой записи
• 📋 Выбрать лист - выбор активного листа в таблице
• 📊 Статус - текущие настройки бота
• 📈 Статистика - статистика базы данных

**Поля записи:**
• ամսաթիվ (дата) - дата в формате YYYY-MM-DD
• մատակարար (поставщик) - название поставщика
• ուղղություն (направление) - направление расхода
• ծախսի բնութագիր (описание) - описание расхода
• Արժեք (сумма) - сумма расхода

**Примеры использования:**
/recent 10 - показать последние 10 записей
/search продукты - найти записи со словом "продукты"
/info abc12345 - информация о записи с ID "abc12345"

Все записи автоматически синхронизируются между Telegram, Google Sheets и базой данных.
"""
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

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
    
    try:
        spreadsheets = get_all_spreadsheets()
        
        if not spreadsheets:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
            await query.edit_message_text(
                "❌ Доступные таблицы не найдены.\n"
                "Убедитесь, что сервисный аккаунт имеет доступ к таблицам.",
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
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")])
        
        text = f"📊 Выберите Google Spreadsheet ({len(spreadsheets)} доступно):"
        if len(spreadsheets) > 10:
            text += f"\n\nПоказаны первые 10 таблиц."
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]]
        await query.edit_message_text(
            f"⚠️ Ошибка получения списка таблиц: {e}",
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
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="select_spreadsheet")]]
            await query.edit_message_text(
                "❌ Не удалось получить информацию о таблице.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        if not spreadsheet_info['sheets']:
            keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="select_spreadsheet")]]
            await query.edit_message_text(
                f"❌ В таблице '{spreadsheet_info['title']}' нет листов.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return
        
        # Временно сохраняем выбранную таблицу
        context.user_data['selected_spreadsheet_id'] = spreadsheet_id
        context.user_data['selected_spreadsheet_title'] = spreadsheet_info['title']
        
        keyboard = []
        for sheet in spreadsheet_info['sheets']:
            # Показываем информацию о количестве строк
            sheet_info = f"{sheet['title']} ({sheet['row_count']} строк)"
            keyboard.append([InlineKeyboardButton(
                f"📋 {sheet_info}", 
                callback_data=f"final_sheet_{sheet['title']}"
            )])
        
        keyboard.append([InlineKeyboardButton("⬅️ К списку таблиц", callback_data="select_spreadsheet")])
        
        await query.edit_message_text(
            f"📊 Таблица: <b>{spreadsheet_info['title']}</b>\n"
            f"📋 Листов: {spreadsheet_info['sheets_count']}\n\n"
            f"Выберите лист для работы:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
    except Exception as e:
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="select_spreadsheet")]]
        await query.edit_message_text(
            f"⚠️ Ошибка: {e}",
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
        await query.edit_message_text("❌ Ошибка: таблица не выбрана.")
        return
    
    # Сохраняем выбранные настройки
    set_active_spreadsheet(spreadsheet_id, sheet_name)
    
    await query.edit_message_text(
        f"✅ Настройка завершена!\n\n"
        f"📊 Таблица: <b>{spreadsheet_title}</b>\n"
        f"📋 Лист: <b>{sheet_name}</b>\n\n"
        f"Теперь вы можете добавлять записи!",
        parse_mode="HTML",
        reply_markup=create_main_menu()
    )
    
    await send_to_log_chat(context, f"Выбрана таблица: {spreadsheet_title}, лист: {sheet_name}")
    
    # Очищаем временные данные
    context.user_data.pop('selected_spreadsheet_id', None)
    context.user_data.pop('selected_spreadsheet_title', None)

if __name__ == '__main__':
    main()