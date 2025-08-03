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
GOOGLE_CREDS_FILE = os.path.join(CREDENTIALS_DIR, 'coordinate-462818-3a816b937055.json')
GOOGLE_SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]
GOOGLE_SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']
GOOGLE_SHEET_WORKERS = 4  # Количество воркеров для работы с Google Sheets

LOCALIZATION_FILE = os.path.join(BASE_DIR, 'src/config/localization.json')



# Создаем директории если их нет
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CREDENTIALS_DIR, exist_ok=True)
