"""
Модуль для форматирования сообщений
"""
from typing import Dict

def format_record_info(record: Dict) -> str:
    """
    Форматирует информацию о записи для отображения
    """
    return (
        f"🆔 ID: <code>{record.get('id', 'N/A')}</code>\n"
        f"📅 Ամսաթիվ: <b>{record.get('date', 'N/A')}</b>\n"
        f"🏪 Մատակարար: <b>{record.get('supplier', 'N/A')}</b>\n"
        f"🧭 Ուղղություն: <b>{record.get('direction', 'N/A')}</b>\n"
        f"📝 Նկարագրություն: <b>{record.get('description', 'N/A')}</b>\n"
        f"💰 Գումար: <b>{record.get('amount', 0):,.2f}</b> դրամ\n"
        f"📊 Աղյուսակ: <code>{record.get('spreadsheet_id', 'N/A')}</code>\n"
        f"📋 Թերթ: <b>{record.get('sheet_name', 'N/A')}</b>"
    )

def format_payment_info(payment: Dict) -> str:
    """
    Форматирует информацию о платеже
    """
    return (
        f"💰 Վճարում: <b>{payment.get('amount', 0):,.2f}</b> դրամ\n"
        f"📅 Ժամանակահատված: {payment.get('date_from', 'N/A')} - {payment.get('date_to', 'N/A')}\n"
        f"📝 Մեկնաբանություն: {payment.get('comment', 'N/A')}"
    )
