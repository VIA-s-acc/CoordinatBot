"""
Основные команды бота
"""
import logging
import sys
import os

# Добавляем корневую папку в path для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import CallbackContext
from src.bot.keyboards.inline_keyboards import create_main_menu, create_back_to_menu_keyboard
from src.utils.config_utils import is_user_allowed, get_user_settings, load_users, save_users
from src.config.settings import ADMIN_IDS
from src.database.database_manager import init_db

logger = logging.getLogger(__name__)

def create_reply_menu():
    """Создает основное Reply-меню"""
    return ReplyKeyboardMarkup([["📋 Մենյու"]], resize_keyboard=True)

async def clear_user_data(update: Update, context: CallbackContext):
    """Очищает пользовательские данные"""
    if context.user_data:
        context.user_data.clear()

async def start(update: Update, context: CallbackContext):
    """Обработчик команды /start"""
    # Инициализируем базу данных при запуске
    init_db()
    
    user = update.effective_user
    user_id = user.id
    user_name = user.full_name
    
    # Добавляем пользователя в систему
    users = load_users()
    user_id_str = str(user_id)
    
    if user_id_str not in users:
        users[user_id_str] = {
            'active_spreadsheet_id': None,
            'active_sheet_name': None,
            'name': user_name,
            'display_name': None
        }
        save_users(users)
    
    # Проверяем разрешен ли пользователь
    if not is_user_allowed(user_id):
        await update.message.reply_text(
            "⛔️ Դուք չունեք մուտքի թույլտվություն: Անդրադարձեք ադմինիստրատորին:"
        )
        return
    
    # Отправляем Reply-меню
    await update.message.reply_text(
        "Օգտագործեք կոճակը ստորև՝ հիմնական ընտրացանկը բացելու համար:",
        reply_markup=create_reply_menu()
    )
    
    # Получаем настройки пользователя для проверки конфигурации
    user_settings = get_user_settings(user_id)
    
    welcome_text = (
        f"👋 Բարև, {user_name}!\n\n"
        "🤖 Ես կօգնեմ ձեզ կառավարել ծախսերը և աշխատել Google Sheets-ի հետ:\n\n"
        "📝 Ես կարող եմ՝\n"
        "• ➕ Ավելացնել նոր ծախսի գրառումներ\n"
        "• ✏️ Խմբագրել և ջնջել գրառումներ\n"
        "• 🔄 Համաժամեցնել տվյալները Google Sheets-ի հետ\n"
        "• 📊 Ցուցադրել վիճակագրություն և հաշվետվություններ\n"
        "• 🔍 Որոնել գրառումներ\n\n"
    )
    
    # Проверяем настройки пользователя
    if not user_settings.get('active_spreadsheet_id') or not user_settings.get('active_sheet_name'):
        welcome_text += (
            "⚠️ <b>Կարգավորում անհրաժեշտ է!</b>\n"
            "Սկսելու համար ընտրեք Google Spreadsheet և թերթիկ:\n\n"
        )
    else:
        welcome_text += (
            "✅ <b>Կարգավորումը ավարտված է!</b>\n"
            "Դուք պատրաստ եք աշխատել:\n\n"
        )
    
    welcome_text += "Օգտագործեք ցանկը ստորև՝ սկսելու համար:"
    
    await update.message.reply_text(
        welcome_text,
        parse_mode="HTML",
        reply_markup=create_main_menu(user_id)
    )

async def menu_command(update: Update, context: CallbackContext):
    """Обработчик команды /menu"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    await clear_user_data(update, context)

    # Отправляем Inline-меню
    await update.message.reply_text(
        "📋 Հիմնական ընտրացանկ:",
        reply_markup=create_main_menu(user_id)
    )

async def text_menu_handler(update: Update, context: CallbackContext):
    """Обработчик текстовой кнопки 'Меню'"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    await clear_user_data(update, context)
    
    # Отправляем Inline-меню при нажатии на Reply-кнопку
    await update.message.reply_text(
        "📋 Հիմնական ընտրացանկ:",
        reply_markup=create_main_menu(user_id)
    )

async def help_command(update: Update, context: CallbackContext):
    """Обработчик команды /help"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    help_text = (
        "🔧 <b>Օգնություն - Հասանելի հրամաններ:</b>\n\n"
        
        "👤 <b>Օգտագործողի հրամաններ:</b>\n"
        "• /start - Բոտի սկսում\n"
        "• /menu - Հիմնական ընտրացանկ\n"
        "• /help - Այս օգնության հաղորդագրությունը\n"
        "• /search [տեքստ] - Գրառումների որոնում\n"
        "• /recent [քանակ] - Վերջին գրառումները\n"
        "• /info [ID] - Գրառման մանրամասն տեղեկություններ\n"
        "• /my_report [սկիզբ] [վերջ] - Ձեր ծախսերի հաշվետվություն\n\n"
        
        "🏪 <b>Գործողություններ:</b>\n"
        "• 📋 Մենյու - Հիմնական ցանկ\n"
        "• ➕ Ավելացնել գրառում - Նոր ծախսի գրառում\n"
        "• ✏️ Խմբագրել - Գրառման խմբագրում\n"
        "• 🔍 Որոնել - Գրառումների որոնում\n"
        "• 📊 Վիճակագրություն - Ընդհանուր վիճակագրություն\n\n"
    )
    
    if user_id in ADMIN_IDS:
        help_text += (
            "👨‍💼 <b>Ադմինիստրատորի հրամաններ:</b>\n"
            "• /set_log - Գրանցամատյանի չատի սահմանում\n"
            "• /set_report [sheet_id] [sheet_name] - Հաշվետվությունների չատի սահմանում\n"
            "• /allow_user [user_id] - Օգտագործողի թույլտվություն\n"
            "• /disallow_user [user_id] - Օգտագործողի արգելք\n"
            "• /allowed_users - Թույլատրված օգտագործողների ցանկ\n"
            "• /set_user_name [user_id] [name] - Օգտագործողի անվան սահմանում\n"
            "• /export - Տվյալների արտահանում\n"
            "• /sync_sheets - Google Sheets-ի համաժամեցում\n"
            "• /initialize_sheets - Բոլոր աղյուսակների նախապատրաստում\n\n"
            "• /send_data_files - Տվյալների ֆայլերի ուղարկում ադմինիստրատորին\n"
        )
    
    help_text += (
        "💡 <b>Խորհուրդներ:</b>\n"
        "• Նախ ընտրեք Google Spreadsheet և թերթիկ\n"
        "• Օգտագործեք ամսաթիվը YYYY-MM-DD ձևաչափով\n"
        "• Գումարները մուտքագրեք թվերով (օրինակ՝ 1000.50)\n"
        "• Օգտագործեք /cancel՝ գործողությունը չեղարկելու համար\n\n"
        
        "❓ Հարցեր ունեցող դեպքում դիմեք ադմինիստրատորին:"
    )
    
    await update.message.reply_text(
        help_text,
        parse_mode="HTML",
        reply_markup=create_back_to_menu_keyboard()
    )

async def message_handler(update: Update, context: CallbackContext):
    """Обработчик обычных сообщений"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    # Обработка ввода ID пользователя для админов
    if user_id in ADMIN_IDS and context.user_data.get('waiting_for_user_id'):
        from .button_handlers import handle_user_id_input
        await handle_user_id_input(update, context)
        return
    
    # Обработка платежей для админов
    if user_id in ADMIN_IDS and context.user_data.get('pay_step'):
        await handle_payment_step(update, context)
        return
    
    # Если пользователь не в процессе диалога, предлагаем меню
    await update.message.reply_text(
        "🤖 Օգտագործեք ցանկը ցուցադրված գործողությունների համար:",
        reply_markup=create_main_menu(user_id)
    )

async def handle_payment_step(update: Update, context: CallbackContext):
    """Обработчик шагов платежа для админов"""
    user_id = update.effective_user.id
    step = context.user_data.get('pay_step')
    
    if step == 'amount':
        try:
            amount = float(update.message.text.strip())
            context.user_data['pay_amount'] = amount
            context.user_data['pay_step'] = 'comment'
            
            display_name = context.user_data.get('pay_user')
            await update.message.reply_text(
                f"💰 Գումար: {amount:,.2f} դրամ\n"
                f"👤 Ստացող: {display_name}\n\n"
                f"📝 Մուտքագրեք մեկնաբանություն (կամ /skip՝ բաց թողնելու համար):"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Սխալ գումարի ձևաչափ: Մուտքագրեք թիվ:")
    
    elif step == 'comment':
        comment = update.message.text.strip() if update.message.text != '/skip' else ""
        
        display_name = context.user_data.get('pay_user')
        amount = context.user_data.get('pay_amount')
        
        # Здесь должна быть логика сохранения платежа
        # Пока что просто показываем результат
        
        result_text = (
            f"✅ Վճարումը գրանցված է:\n\n"
            f"👤 Ստացող: {display_name}\n"
            f"💰 Գումար: {amount:,.2f} դրամ\n"
            f"📝 Մեկնաբանություն: {comment or 'Չկա'}\n"
            f"📅 Ամսաթիվ: Այժմ"
        )
        
        await update.message.reply_text(
            result_text,
            reply_markup=create_main_menu(user_id)
        )
        
        # Очищаем данные
        context.user_data.clear()
