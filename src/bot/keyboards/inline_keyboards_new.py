"""
Инлайн клавиатуры для бота
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ...utils.config_utils import get_admin_ids

def create_main_menu(user_id=None):
    """Создает главное меню"""
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել գրառում", callback_data="add_record_menu")],
        [InlineKeyboardButton("📋 Ընտրել թերթիկ", callback_data="select_sheet")],
        [InlineKeyboardButton("📊 Կարգավիճակ", callback_data="status")],
        [InlineKeyboardButton("📈 Վիճակագրություն", callback_data="stats")],
        [InlineKeyboardButton("📊 Ընտրել աղյուսակ", callback_data="select_spreadsheet")]
    ]
    
    admin_ids = get_admin_ids()
    if user_id and user_id in admin_ids:
        keyboard.append([InlineKeyboardButton("💸 Վճարներ", callback_data="pay_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def create_add_record_menu():
    """Создает меню выбора типа добавления записи"""
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել գրառում", callback_data="add_record_select_sheet")],
        [InlineKeyboardButton("➕ Ավելացնել Բացթողում", callback_data="add_skip_record_select_sheet")],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_add_record_sheet_selection(sheets_info, record_type):
    """Создает меню выбора листа для добавления записи
    
    Args:
        sheets_info: список информации о листах
        record_type: тип записи ("record" или "skip")
    """
    keyboard = []
    for sheet in sheets_info:
        keyboard.append([InlineKeyboardButton(
            f"📋 {sheet['title']}", 
            callback_data=f"add_{record_type}_sheet_{sheet['title']}"
        )])
    
    keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="add_record_menu")])
    return InlineKeyboardMarkup(keyboard)

def create_supplier_choice_keyboard(display_name=None):
    """Создает клавиатуру выбора поставщика"""
    keyboard = []
    if display_name:
        keyboard.append([InlineKeyboardButton(f"👤 Օգտագործել իմ անունը ({display_name})", callback_data="use_my_name")])
    keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել Ֆիրմայի անունը", callback_data="use_firm_name")])
    # keyboard.append([InlineKeyboardButton("✏️ Մուտքագրել ձեռքով", callback_data="manual_input")])
    return InlineKeyboardMarkup(keyboard)

def create_edit_menu(record_id: str, is_admin: bool = False):
    """Создает меню для редактирования записи"""
    keyboard = [
        [InlineKeyboardButton("📅 Ամսաթիվ", callback_data=f"edit_date_{record_id}")],
        [InlineKeyboardButton("🏪 Մատակարար", callback_data=f"edit_supplier_{record_id}")],
        [InlineKeyboardButton("🧭 Ուղղություն", callback_data=f"edit_direction_{record_id}")],
        [InlineKeyboardButton("📝 Նկարագրություն", callback_data=f"edit_description_{record_id}")],
        [InlineKeyboardButton("💰 Գումար", callback_data=f"edit_amount_{record_id}")],
        [InlineKeyboardButton("🗑 Ջնջել", callback_data=f"delete_{record_id}")],
        [InlineKeyboardButton("❌ Չեղարկել", callback_data=f"cancel_edit_{record_id}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_spreadsheet_selection_keyboard(spreadsheets):
    """Создает клавиатуру выбора таблицы"""
    keyboard = []
    for spreadsheet in spreadsheets[:10]:  # Показываем максимум 10 таблиц
        # Ограничиваем длину названия для кнопки
        name = spreadsheet['name'][:30] + "..." if len(spreadsheet['name']) > 30 else spreadsheet['name']
        keyboard.append([InlineKeyboardButton(
            f"📊 {name}", 
            callback_data=f"spreadsheet_{spreadsheet['id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def create_sheet_selection_keyboard(sheets_info):
    """Создает клавиатуру выбора листа"""
    keyboard = []
    for info in sheets_info:
        keyboard.append([InlineKeyboardButton(
            f"📋 {info['title']}", 
            callback_data=f"sheet_{info['title']}"
        )])
    
    keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def create_final_sheet_selection_keyboard(sheets):
    """Создает клавиатуру окончательного выбора листа"""
    keyboard = []
    for sheet in sheets:
        # Показываем информацию о количестве строк
        sheet_info = f"{sheet['title']} ({sheet['row_count']} строк)"
        keyboard.append([InlineKeyboardButton(
            f"📋 {sheet_info}", 
            callback_data=f"final_sheet_{sheet['title']}"
        )])
    
    keyboard.append([InlineKeyboardButton("⬅️ Աղյուսակների ցուցակ", callback_data="select_spreadsheet")])
    return InlineKeyboardMarkup(keyboard)

def create_payment_menu_keyboard(users_with_names):
    """Создает клавиатуру меню платежей"""
    keyboard = []
    for user_data in users_with_names:
        display_name = user_data['display_name']
        keyboard.append([InlineKeyboardButton(display_name, callback_data=f"pay_user_{display_name}")])
    keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(keyboard)

def create_payment_actions_keyboard(display_name):
    """Создает клавиатуру действий с платежами"""
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել վճարում", callback_data=f"add_payment_{display_name}")],
        [InlineKeyboardButton("📊 Ստանալ սահմանի հաշվետվություն", callback_data=f"get_payment_report_{display_name}")],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="pay_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_back_button():
    """Создает простую кнопку назад"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]])

def create_reply_menu():
    """Создает Reply клавиатуру с кнопкой меню"""
    from telegram import ReplyKeyboardMarkup
    return ReplyKeyboardMarkup([["📋 Մենյու"]], resize_keyboard=True)
