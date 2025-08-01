"""
Модуль для форматирования сообщений
"""
from typing import Dict
from datetime import datetime

def format_record_info(record: Dict) -> str:
    """
    Форматирует информацию о записи для отображения
    """
    date_str = record.get('date', 'N/A')
    if date_str and date_str != 'N/A':
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")
        except Exception:
            formatted_date = date_str
    else:
        formatted_date = 'N/A'
    amount = record.get('amount', 0)
    # Форматируем сумму без .00, но с разделителем тысяч
    if isinstance(amount, float) and amount.is_integer():
        amount_str = f"{int(amount):,}".replace(",", ",")
    else:
        amount_str = f"{amount:,}".replace(",", ",")
    return (
        f"🆔 ID: <code>{record.get('id', 'N/A')}</code>\n"
        f"📅: <b>{formatted_date}</b>\n"
        f"🏪: <b>{record.get('supplier', 'N/A')}</b>\n"
        f"🧭: <b>{record.get('direction', 'N/A')}</b>\n"
        f"📝: <b>{record.get('description', 'N/A')}</b>\n"
        f"💰: <b>{amount_str}</b> դրամ\n"
        f"📋: <b>{record.get('sheet_name', 'N/A')}</b>"
    )

def format_payment_info(payment: Dict) -> str:
    """
    Форматирует информацию о платеже
    """
    return (
        f"💰 Վճարում: <b>{payment.get('amount', 0)}</b> դրամ\n"
        f"📅 Ժամանակահատված: {payment.get('date_from', 'N/A')} - {payment.get('date_to', 'N/A')}\n"
        f"📝 Մեկնաբանություն: {payment.get('comment', 'N/A')}"
    )
