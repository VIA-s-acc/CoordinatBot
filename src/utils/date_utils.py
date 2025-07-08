"""
Утилиты для работы с датами
"""
import re
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def normalize_date(date_str: str) -> str:
    """
    Нормализует строку даты в формат DD.MM.YY
    """
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

def validate_date(date_str: str) -> bool:
    """
    Проверяет корректность даты
    """
    try:
        # Пытаемся распарсить дату в разных форматах
        formats = ['%Y-%m-%d', '%d.%m.%Y', '%d.%m.%y']
        
        for fmt in formats:
            try:
                datetime.strptime(date_str, fmt)
                return True
            except ValueError:
                continue
        
        return False
    except Exception:
        return False

def format_date_for_interval(date_obj):
    """
    Форматирует дату для интервала
    """
    if date_obj is None:
        return "не указана"
    try:
        return date_obj.strftime('%d.%m.%y')
    except Exception:
        return str(date_obj)
