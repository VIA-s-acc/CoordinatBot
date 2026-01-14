"""
Утилиты для работы с датами
"""
import re
from datetime import datetime

from ..config.settings import logger


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


def safe_parse_date(date_str: str) -> datetime.date:
    """
    Безопасно парсит дату в разных форматах
    
    Args:
        date_str: Строка с датой
        
    Returns:
        datetime.date объект или None если парсинг не удался
        
    Raises:
        ValueError: Если дату не удалось распарсить ни в одном формате
    """
    if not date_str or not isinstance(date_str, str):
        raise ValueError(f"Пустая или неверная дата: {date_str}")
    
    date_str = date_str.strip()
    if not date_str:
        raise ValueError("Пустая дата после обрезки пробелов")
    
    # Список поддерживаемых форматов дат
    date_formats = [
        '%d.%m.%y',    # 10.10.24
        '%d.%m.%Y',    # 10.10.2024
        '%Y-%m-%d',    # 2024-10-10
        '%d-%m-%Y',    # 10-10-2024
        '%d-%m-%y',    # 10-10-24
        '%d/%m/%Y',    # 10/10/2024
        '%d/%m/%y',    # 10/10/24
        '%d․%m․%y',    # 10․10․24 (армянские точки)
        '%d․%m․%Y',    # 10․10․2024 (армянские точки)
    ]
    
    for fmt in date_formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt).date()
            
            # Проверяем год: если меньше 50, то это 21 век, иначе 20 век
            if parsed_date.year < 50:
                parsed_date = parsed_date.replace(year=parsed_date.year + 2000)
            elif parsed_date.year < 100:
                parsed_date = parsed_date.replace(year=parsed_date.year + 1900)
                
            logger.debug(f"Успешно распарсили дату '{date_str}' как {parsed_date} с форматом {fmt}")
            return parsed_date
        except ValueError:
            continue
    
    # Если ни один формат не подошел
    raise ValueError(f"Не удалось распарсить дату '{date_str}' ни в одном из поддерживаемых форматов")


def safe_parse_date_or_none(date_str: str) -> datetime.date:
    """
    Безопасно парсит дату, возвращая None вместо исключения
    
    Args:
        date_str: Строка с датой
        
    Returns:
        datetime.date объект или None если парсинг не удался
    """
    try:
        return safe_parse_date(date_str)
    except Exception as e:
        logger.warning(f"Не удалось распарсить дату '{date_str}': {e}")
        return None
