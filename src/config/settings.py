"""
Конфигурация приложения
"""
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Telegram Bot Token
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# ID администраторов
ADMIN_IDS = [
    int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',')
    if x.strip().isdigit()
]

# ID супер-администратора (может управлять ролями через бота)
SUPER_ADMIN_ID = int(os.getenv('SUPER_ADMIN_ID', '0')) if os.getenv('SUPER_ADMIN_ID') else None

# Роли пользователей
class UserRole:
    SUPER_ADMIN = 'super_admin'  # Супер-администратор (управление ролями)
    ADMIN = 'admin'               # Администратор (текущие админы)
    WORKER = 'worker'             # Работник (текущие обычные пользователи)
    SECONDARY = 'secondary'       # Вторичный (только просмотр платежей)
    CLIENT = 'client'             # Клиент (только получение уведомлений)

# Пути к файлам
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CREDENTIALS_DIR = os.path.join(BASE_DIR, 'credentials')

# Пути к файлам данных
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
ALLOWED_USERS_FILE = os.path.join(DATA_DIR, 'allowed_users.json')
BOT_CONFIG_FILE = os.path.join(DATA_DIR, 'bot_config.json')
DATABASE_PATH = os.path.join(DATA_DIR, 'expenses.db')

# Google Sheets конфигурация
GOOGLE_CREDS_FILE = os.path.join(CREDENTIALS_DIR, 'coordinate-462818-c4649309a873.json')
GOOGLE_SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']
GOOGLE_SHEET_WORKERS = 2  # Количество воркеров для работы с Google Sheets

# ID таблицы для хранения платежей (отдельная от основной)
PAYMENTS_SPREADSHEET_ID = os.getenv('PAYMENTS_SPREADSHEET_ID')

# ID чата для автоматических бэкапов
BACKUP_CHAT_ID = os.getenv('BACKUP_CHAT_ID')
if BACKUP_CHAT_ID and BACKUP_CHAT_ID.strip():
    try:
        BACKUP_CHAT_ID = int(BACKUP_CHAT_ID)
    except ValueError:
        BACKUP_CHAT_ID = None
else:
    BACKUP_CHAT_ID = None

# Интервал автоматического бэкапа (в часах)
BACKUP_INTERVAL_HOURS = float(os.getenv('BACKUP_INTERVAL_HOURS', '4'))

LOCALIZATION_FILE = os.path.join(BASE_DIR, 'src/config/localization.json')



# Создаем директории если их нет
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CREDENTIALS_DIR, exist_ok=True)
