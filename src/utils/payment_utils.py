"""
Утилиты для работы с платежами
"""
import re
import pandas as pd
from datetime import datetime
from typing import Optional, Dict, List

def normalize_date(date_str: str) -> str:
    """
    Нормализует строку даты в формат DD.MM.YY
    """
    # Удалить пробелы и завершающие точки
    date_str = date_str.strip().rstrip('.')

    # Если дата в формате YYYY-MM-DD, преобразуем её в DD.MM.YY
    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%d.%m.%y')

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

def merge_payment_intervals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Объединяет пересекающиеся или смежные интервалы платежей, суммируя суммы.

    Args:
        df: DataFrame с колонками ['amount', 'date_from', 'date_to'].
            date_from, date_to могут быть None или timestamps.

    Returns:
        DataFrame с объединенными интервалами и суммированными суммами.
        NaT используется вместо min/max timestamps для открытых интервалов.
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

        # Если интервалы пересекаются или касаются
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
    # Заменяем экстремальные timestamps обратно на NaT для обозначения открытых интервалов
    result['date_from'] = result['date_from'].replace(pd.Timestamp.min, pd.NaT)
    result['date_to'] = result['date_to'].replace(pd.Timestamp.max, pd.NaT)
    return result

def format_date_for_interval(d):
    """Форматирует дату для интервала"""
    if pd.isna(d):
        return '-'
    return d.strftime('%Y-%m-%d')

async def get_user_id_by_display_name(display_name: str) -> Optional[int]:
    """Получает ID пользователя по его отображаемому имени"""
    from ..utils.config_utils import load_users
    
    users = load_users()
    for user_id, info in users.items():
        if info.get('display_name') == display_name:
            return int(user_id)
    return None

async def send_message_to_user(context, user_id: int, text: str, reply_markup=None):
    """Отправляет сообщение пользователю по ID"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка отправки сообщения пользователю {user_id}: {e}")
        from ..utils.config_utils import send_to_log_chat
        await send_to_log_chat(context, f"Ошибка отправки сообщения пользователю {user_id}: {e}")
