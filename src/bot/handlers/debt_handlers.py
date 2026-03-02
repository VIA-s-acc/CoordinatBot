"""
Обработчики операций Пարտք / Պարտքի մարում и баланса владельца.
"""
import uuid
from datetime import datetime

from telegram import Update
from telegram.ext import CallbackContext

from ...config.settings import ACTIVE_SPREADSHEET_ID, logger
from ...database.database_manager import add_record_to_db, get_all_records
from ...google_integration.async_sheets_worker import add_record_async
from ...utils.config_utils import (
    get_entities_by_type,
    get_entity_by_index,
    get_owner_entity,
    get_user_settings,
    load_bot_config,
)


def _format_amount(amount: float) -> str:
    return f"{amount:,.0f}"


async def start_debt_text_flow(update: Update, context: CallbackContext, operation: str, entity_type: str, entity_index: int, project_sheet_name: str = None):
    """Запускает текстовый flow для долга/погашения после выбора сущности."""
    query = update.callback_query
    entity = get_entity_by_index(entity_type, entity_index)

    if not entity:
        await query.edit_message_text("❌ Ուղղությունը չի գտնվել.")
        return

    context.user_data['debt_flow'] = {
        'operation': operation,
        'entity_type': entity_type,
        'entity': entity,
        'project_sheet_name': project_sheet_name,
        'step': 'description'
    }

    operation_title = "Պարտք" if operation == 'debt' else "Պարտքի մարում"
    await query.edit_message_text(
        f"🧾 {operation_title}\n"
        f"🏷 Ուղղություն: {entity.get('name', 'N/A')}\n\n"
        f"📋 Նախագիծ: {project_sheet_name or '—'}\n\n"
        f"📝 Մուտքագրեք գործողության նկարագրությունը:"
    )


async def process_debt_flow_message(update: Update, context: CallbackContext) -> bool:
    """Обрабатывает текстовые шаги flow для долга/погашения.

    Returns:
        True если сообщение обработано этим flow, иначе False.
    """
    flow = context.user_data.get('debt_flow')
    if not flow:
        return False

    text = (update.message.text or '').strip()
    step = flow.get('step')

    if step == 'description':
        flow['description'] = text
        flow['step'] = 'amount'
        await update.message.reply_text("💰 Մուտքագրեք գումարը:")
        return True

    if step != 'amount':
        return False

    try:
        amount = float(text.replace(',', ''))
    except ValueError:
        await update.message.reply_text("❌ Սխալ գումարային արժեք. Մուտքագրեք թիվ:")
        return True

    entity = flow.get('entity', {})
    operation = flow.get('operation')
    description = flow.get('description', '')
    project_sheet = flow.get('project_sheet_name') or "—"

    signed_amount = -abs(amount) if operation == 'debt' else abs(amount)
    operation_title = "Պարտք" if operation == 'debt' else "Պարտքի մարում"

    user_id = update.effective_user.id
    user_settings = get_user_settings(user_id)
    supplier = user_settings.get('display_name') or update.effective_user.full_name

    target_spreadsheet = entity.get('spreadsheet_id')
    target_sheet = entity.get('sheet_name') or entity.get('name')

    if not target_spreadsheet or not target_sheet:
        await update.message.reply_text("❌ Ուղղության համար չի լրացվել spreadsheet_id/sheet_name.")
        context.user_data.pop('debt_flow', None)
        return True

    base = {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'supplier': supplier,
        'direction': entity.get('name', ''),
        'description': f"{description} | Նախագիծ: {project_sheet}",
        'amount': signed_amount,
        'user_id': user_id,
        'operation_type': operation,
        'coefficient': -1 if operation == 'debt' else 1,
    }

    records_to_write = [
        {
            **base,
            'id': f"cb-{str(uuid.uuid4())[:8]}",
            'spreadsheet_id': target_spreadsheet,
            'sheet_name': target_sheet,
        }
    ]

    if operation == 'repayment' and ACTIVE_SPREADSHEET_ID:
        project_sheet = flow.get('project_sheet_name') or user_settings.get('active_sheet_name') or target_sheet
        records_to_write.append({
            **base,
            'id': f"cb-{str(uuid.uuid4())[:8]}",
            'spreadsheet_id': ACTIVE_SPREADSHEET_ID,
            'sheet_name': project_sheet,
        })

    for record in records_to_write:
        add_record_to_db(record)
        add_record_async(
            spreadsheet_id=record['spreadsheet_id'],
            sheet_name=record['sheet_name'],
            record=record,
        )

    await _send_debt_tickets(context, operation_title, amount, description, entity, supplier, project_sheet)

    await update.message.reply_text(
        f"✅ Գործողությունը պահպանվել է\n"
        f"📌 Տեսակ: {operation_title}\n"
        f"🏷  Ուղղություն: {entity.get('name', 'N/A')}\n"
        f"📋 Նախագիծ: {project_sheet}\n"
        f"💰 Գումար: {_format_amount(abs(amount))}",
    )

    context.user_data.pop('debt_flow', None)
    return True


async def _send_debt_tickets(context: CallbackContext, title: str, amount: float, description: str, entity: dict, supplier: str, project_sheet: str):
    """Отправляет тикет в проектные чаты и владельцу сущности (если назначен)."""
    config = load_bot_config()
    report_chats = config.get('report_chats', {})

    message = (
        f"📢 <b>{title}</b>\n"
        f"🏷 Ուղղություն: <b>{entity.get('name', 'N/A')}</b>\n"
        f"📋 Նախագիծ: <b>{project_sheet or '—'}</b>\n"
        f"👤 Օգտագործող: <b>{supplier}</b>\n"
        f"💰 Գումար: <b>{_format_amount(abs(amount))}</b>\n"
        f"📝 Նկատարկում: <b>{description or '—'}</b>"
    )

    for chat_id in report_chats.keys():
        try:
            await context.bot.send_message(chat_id=int(chat_id), text=message, parse_mode='HTML')
        except Exception as exc:
            logger.warning(f"Failed to send debt ticket to report chat {chat_id}: {exc}")

    owner_id = entity.get('owner_id')
    if owner_id:
        try:
            await context.bot.send_message(chat_id=int(owner_id), text=message, parse_mode='HTML')
        except Exception as exc:
            logger.warning(f"Failed to send debt ticket to owner {owner_id}: {exc}")


async def show_owner_balance(update: Update, context: CallbackContext):
    """Показывает владельцу сумму долга по назначенной сущности."""
    user_id = update.effective_user.id
    owner_entity_info = get_owner_entity(user_id)

    if not owner_entity_info:
        target = update.callback_query if update.callback_query else update.message
        if update.callback_query:
            await target.answer()
            await target.edit_message_text("ℹ️ Ձեր համար ոչ մի բրիգադա/խանութ չի նշանակվել.")
        else:
            await target.reply_text("ℹ️ Ձեր համար ոչ մի բրիգադա/խանութ չի նշանակվել.")
        return

    entity = owner_entity_info['entity']
    spreadsheet_id = entity.get('spreadsheet_id')
    sheet_name = entity.get('sheet_name')

    total = 0.0
    for record in get_all_records():
        if record.get('spreadsheet_id') != spreadsheet_id:
            continue
        if record.get('sheet_name') != sheet_name:
            continue
        if record.get('operation_type') not in ('debt', 'repayment'):
            continue
        total += float(record.get('amount', 0) or 0)

    text = (
        f"💼 Ձեր համար նշանակված սուբյեկտի համար ընդհատված գումարը\n"
        f"🏷 {entity.get('name', 'N/A')}\n"
        f"💰 Ընդհատված գումար (Պարտք + Պարտքի մարում): <b>{_format_amount(total)}</b>"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode='HTML')
    else:
        await update.message.reply_text(text, parse_mode='HTML')
