import json
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext
from google_connector import list_spreadsheets, open_sheet_by_id
import os 
# === Конфигурация ===
TOKEN = os.environ.get('TOKEN')
CONFIG_FILE = 'config.json'
spreadsheet_map = {}

# === Вспомогательные функции ===

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def get_active_spreadsheet_id():
    return load_config().get('active_spreadsheet_id')

def set_active_spreadsheet_id(spreadsheet_id: str):
    config = load_config()
    config['active_spreadsheet_id'] = spreadsheet_id
    save_config(config)

# === Обработчики ===

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(
        "👋 Добро пожаловать!\n"
        "Используйте /list_tables для просмотра доступных таблиц.\n"
        "Используйте /connect_id <N> для подключения к нужной."
    )

async def list_tables(update: Update, context: CallbackContext):
    global spreadsheet_map
    try:
        files = list_spreadsheets()
        if not files:
            await update.message.reply_text("❌ Нет доступных таблиц.")
            return

        spreadsheet_map = {str(i): f for i, f in enumerate(files, 1)}
        reply = "📄 Список таблиц:\n"
        for idx, f in spreadsheet_map.items():
            reply += f"{idx}. {f['name']} (ID: `{f['id']}`)\n"
        reply += "\nИспользуйте: /connect_id <номер>"
        await update.message.reply_text(reply, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"⚠️ Ошибка: {e}")

async def connect_id(update: Update, context: CallbackContext):
    global spreadsheet_map
    if not context.args:
        await update.message.reply_text("⚠️ Укажите номер таблицы. Пример: /connect_id 1")
        return

    idx = context.args[0]
    selected = spreadsheet_map.get(idx)

    if not selected:
        await update.message.reply_text("❌ Неверный номер.")
        return

    try:
        sheet = open_sheet_by_id(selected['id'])
        first_tab = sheet.worksheets()[0].title
        set_active_spreadsheet_id(selected['id'])
        await update.message.reply_text(
            f"✅ Подключено: *{selected['name']}*\n"
            f"Первый лист: `{first_tab}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Не удалось подключиться: {e}")

# === Запуск ===

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list_tables", list_tables))
    app.add_handler(CommandHandler("connect_id", connect_id))
    print("Бот запущен.")
    app.run_polling()

if __name__ == '__main__':
    main()
