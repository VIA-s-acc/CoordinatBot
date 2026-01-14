"""
Команды поиска и информации
"""

from telegram import Update
from telegram.ext import CallbackContext

from ..keyboards.inline_keyboards import create_edit_record_keyboard
from ...utils.config_utils import is_user_allowed, get_user_settings
from ...database.database_manager import search_records, get_all_records, get_record_from_db
from ...config.settings import logger


async def search_command(update: Update, context: CallbackContext):
    """Команда поиска записей"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "🔍 Գրառումների որոնում:\n"
            "Օգտագործեք: <code>/search [տեքստի որոնում]</code>\n\n"
            "Որոնումն իրականացվում է հետևյալ դաշտերով՝ մատակարար, ուղղություն, նկարագրություն",
            parse_mode="HTML"
        )
        return
    
    query = " ".join(args)
    
    try:
        records = search_records(query)
        
        if not records:
            await update.message.reply_text(
                f"🔍 '{query}' հարցման համար ոչինչ չի գտնվել:",
                parse_mode="HTML"
            )
            return
        
        result_text = f"🔍 Գտնվել է {len(records)} գրառում '{query}' հարցման համար:\n\n"
        
        for i, record in enumerate(records, 1):
            if i > 25:
                break
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   📝 {record['description'][:50]}{'...' if len(record['description']) > 50 else ''}\n"
            result_text += f"   📋 {record.get('sheet_name', 'N/A')}\n\n"
        
        # Если записей много, предупреждаем
        if len(records) > 25:
            result_text += "ℹ️ Ցուցադրված են առաջին 25 արդյունքները: Հստակեցրեք հարցումը ավելի ճշգրիտ որոնման համար:"
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Որոնման սխալ: {e}")

async def recent_command(update: Update, context: CallbackContext):
    """Показывает последние записи"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    try:
        # Получаем количество записей из аргументов или по умолчанию 5
        args = context.args
        limit = 5
        if args:
            try:
                limit = min(int(args[0]), 50)  # Максимум 50 записей
            except ValueError:
                pass
        
        records = get_all_records(limit=limit)
        
        if not records:
            await update.message.reply_text("📝 Տվյալների բազայում գրառումներ չկան:")
            return
        
        result_text = f"📝 Վերջին {len(records)} գրառումները:\n\n"
        
        for i, record in enumerate(records, 1):
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   🧭 {record['direction']}\n"
            result_text += f"   📝 {record['description']}\n"
            result_text += f"   📊 <code>{record.get('spreadsheet_id', 'N/A')}</code>\n"
            result_text += f"   📋 <code>{record.get('sheet_name', 'N/A')}</code>\n\n"
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Գրառումներ ստանալու սխալ: {e}")

async def info_command(update: Update, context: CallbackContext):
    """Показывает детальную информацию о записи по ID"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "ℹ️ Գրառման մանրամասն տեղեկությունների համար օգտագործեք:\n"
            "<code>/info [ID]</code>\n\n"
            "Օրինակ: <code>/info cb-12345678</code>",
            parse_mode="HTML"
        )
        return
    
    record_id = args[0].strip()
    
    try:
        record = get_record_from_db(record_id)
        
        if not record:
            await update.message.reply_text(
                f"❌ Գրառում ID: <code>{record_id}</code> չի գտնվել:",
                parse_mode="HTML"
            )
            return
        
        # Форматируем информацию о записи
        info_text = (
            f"ℹ️ <b>Գրառման մանրամասն տեղեկություններ:</b>\n\n"
            f"🆔 ID: <code>{record['id']}</code>\n"
            f"📅 Ամսաթիվ: <b>{record['date']}</b>\n"
            f"🏪 Մատակարար: <b>{record['supplier']}</b>\n"
            f"🧭 Ուղղություն: <b>{record['direction']}</b>\n"
            f"📝 Նկարագրություն: <b>{record['description']}</b>\n"
            f"💰 Գումար: <b>{record['amount']:,.2f} դրամ</b>\n"
            f"📊 Աղյուսակ: <code>{record.get('spreadsheet_id', 'N/A')}</code>\n"
            f"📋 Թերթիկ: <b>{record.get('sheet_name', 'N/A')}</b>\n"
        )
        
        # Добавляем информацию о времени создания, если есть
        if 'created_at' in record:
            info_text += f"🕒 Ստեղծվել է: <b>{record['created_at']}</b>\n"

        await update.message.reply_text(
            info_text,
            parse_mode="HTML",
            reply_markup=create_edit_record_keyboard(record_id)
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Տեղեկություններ ստանալու սխալ: {e}")

async def my_report_command(update: Update, context: CallbackContext):
    """Показывает отчет пользователя по расходам за период"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return

    user_settings = get_user_settings(user_id)
    display_name = user_settings.get('display_name')
    if not display_name:
        await update.message.reply_text("❌ Ձեր անունը չի սահմանված։")
        return

    args = context.args
    date_from = args[0] if len(args) > 0 else None
    date_to = args[1] if len(args) > 1 else None

    try:
        # Собираем все записи по имени пользователя
        records = get_all_records()
        filtered = []
        for rec in records:
            if str(rec.get('supplier', '')).strip() != display_name:
                continue
            rec_date = rec.get('date', '')
            if date_from and rec_date < date_from:
                continue
            if date_to and rec_date > date_to:
                continue
            filtered.append(rec)

        if not filtered:
            await update.message.reply_text("Ձեր անունով գրառումներ չեն գտնվել նշված ժամանակահատվածում։")
            return

        # Группировка по листам
        sheets = {}
        total = 0
        for rec in filtered:
            sheet = rec.get('sheet_name', '—')
            sheets.setdefault(sheet, []).append(rec)
            total += rec.get('amount', 0)

        text = f"🧾 <b>Ձեր ծախսերի հաշվետվությունը</b>\n"
        if date_from or date_to:
            text += f"🗓 {date_from or 'սկզբից'} — {date_to or 'մինչ այժմ'}\n"
        
        for sheet, recs in sheets.items():
            s = sum(r.get('amount', 0) for r in recs)
            text += f"\n<b>Թերթիկ՝ {sheet}</b>: {s:,.2f} դրամ ({len(recs)} գրառում)"
        
        text += f"\n\n<b>Ընդհանուր՝ {total:,.2f} դրամ</b>"

        await update.message.reply_text(text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Հաշվետվություն ստեղծելու սխալ: {e}")
