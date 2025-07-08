"""
Утилиты для работы с конфигурацией и пользователями
"""
import json
import logging
from typing import Dict, List, Optional
from ..config.settings import USERS_FILE, ALLOWED_USERS_FILE, BOT_CONFIG_FILE

logger = logging.getLogger(__name__)

def load_json_file(file_path: str, default_value=None):
    """
    Загружает JSON файл с обработкой ошибок
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"Файл {file_path} не найден, создаем новый")
        if default_value is not None:
            save_json_file(file_path, default_value)
        return default_value or {}
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка декодирования JSON в файле {file_path}: {e}")
        return default_value or {}

def save_json_file(file_path: str, data):
    """
    Сохраняет данные в JSON файл
    """
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Ошибка сохранения JSON файла {file_path}: {e}")
        return False

# Функции для работы с конфигурацией бота
def load_bot_config():
    """Загружает конфигурацию бота"""
    return load_json_file(BOT_CONFIG_FILE, {'log_chat_id': None, 'report_chats': {}})

def save_bot_config(config):
    """Сохраняет конфигурацию бота"""
    return save_json_file(BOT_CONFIG_FILE, config)

def get_log_chat_id():
    """Получает ID чата для логов"""
    return load_bot_config().get('log_chat_id')

def set_log_chat(chat_id: int):
    """Устанавливает чат для логов"""
    config = load_bot_config()
    config['log_chat_id'] = chat_id
    save_bot_config(config)

def get_report_settings(chat_id: int):
    """Получает настройки отчетов для чата"""
    config = load_bot_config()
    return config.get('report_chats', {}).get(str(chat_id))

def set_report_settings(chat_id: int, settings: dict):
    """Устанавливает настройки отчетов для чата"""
    config = load_bot_config()
    if 'report_chats' not in config:
        config['report_chats'] = {}
    config['report_chats'][str(chat_id)] = settings
    save_bot_config(config)

# Функции для работы с пользователями
def load_users():
    """Загружает данные пользователей"""
    return load_json_file(USERS_FILE, {})

def save_users(users_data):
    """Сохраняет данные пользователей"""
    return save_json_file(USERS_FILE, users_data)

def get_user_settings(user_id: int):
    """Получает настройки пользователя"""
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        # Создаем запись для нового пользователя
        users[user_id_str] = {
            'active_spreadsheet_id': None,
            'active_sheet_name': None,
            'display_name': None
        }
        save_users(users)
    
    return users[user_id_str]

def update_user_settings(user_id: int, settings: dict):
    """Обновляет настройки пользователя"""
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        users[user_id_str] = {}
    
    users[user_id_str].update(settings)
    save_users(users)

# Функции для работы с разрешенными пользователями
def load_allowed_users():
    """Загружает список разрешенных пользователей"""
    return load_json_file(ALLOWED_USERS_FILE, [])

def save_allowed_users(allowed_list):
    """Сохраняет список разрешенных пользователей"""
    return save_json_file(ALLOWED_USERS_FILE, allowed_list)

def is_user_allowed(user_id: int) -> bool:
    """Проверяет, разрешен ли пользователь"""
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

# Функция для получения display_name пользователя
def get_user_display_name(user_id: int) -> str:
    """Возвращает display_name пользователя по user_id, если задано"""
    users = load_users()
    user_id_str = str(user_id)
    user = users.get(user_id_str)
    if user:
        return user.get('display_name')
    return None
# --- Асинхронная функция для отправки сообщений в лог-чат ---
from telegram.ext import CallbackContext

async def send_to_log_chat(context: CallbackContext, message: str):
    """Отправляет сообщение в лог-чат, если он настроен"""
    log_chat_id = get_log_chat_id()
    if log_chat_id:
        try:
            await context.bot.send_message(chat_id=log_chat_id, text=message)
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в лог-чат: {e}")