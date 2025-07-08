"""
Команды для работы с записями
"""
import logging
from telegram import Update
from telegram.ext import CallbackContext
from ...utils.config_utils import is_user_allowed
from ...database.database_manager import search_records, get_all_records, get_record_from_db
from ...utils.formatting import format_record_info

logger = logging.getLogger(__name__)

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
                result_text += f"\n... և {len(records) - 25} ավելին"
                break
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   📝 {record['description'][:50]}{'...' if len(record['description']) > 50 else ''}\n"
            result_text += f"   📋 {record['sheet_name']}\n\n"
        
        if len(records) == 25:
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
                limit = min(int(args[0]), 1000)  # Максимум 1000 записей
            except ValueError:
                pass
        
        records = get_all_records(limit=limit)
        
        if not records:
            await update.message.reply_text("📝 Տվյալների բազայում գրառումներ չկան:")
            return
        
        result_text = f"📝 Последние {len(records)} записей:\n\n"
        
        for i, record in enumerate(records, 1):
            result_text += f"{i}. ID: <code>{record['id']}</code>\n"
            result_text += f"   📅 {record['date']} | 💰 {record['amount']:,.2f}\n"
            result_text += f"   🏪 {record['supplier']}\n"
            result_text += f"   🧭 {record['direction']}\n"
            result_text += f"   📝 {record['description']}\n"
            result_text += f"   📊 <code>{record['spreadsheet_id']}</code>\n"
            result_text += f"   📋  <code>{record['sheet_name']}</code>\n\n"
            
        
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
            "ℹ️ Գրառման մասին տեղեկատվություն:\n"
            "Օգտագործեք: <code>/info [ID записи]</code>",
            parse_mode="HTML"
        )
        return
    
    record_id = args[0].strip()
    
    try:
        record = get_record_from_db(record_id)
        
        if not record:
            await update.message.reply_text(
                f"❌ <code>{record_id}</code> ID-ով գրառում չի գտնվել:",
                parse_mode="HTML"
            )
            return
        
        result_text = "ℹ️ Գրառման մանրամասն տեղեկատվություն:\n\n"
        result_text += format_record_info(record)
        result_text += f"\n\n📅 Ստեղծված է: {record.get('created_at', 'N/A')}"
        result_text += f"\n🔄 Թարմացված է: {record.get('updated_at', 'N/A')}"
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Տեղեկատվություն ստանալու սխալ: {e}")
