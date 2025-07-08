"""
Инлайн клавиатуры для бота
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ...config.settings import ADMIN_IDS
from ...utils.config_utils import load_users

def create_main_menu(user_id=None):
    """Создает главное меню"""
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել գրառում", callback_data="add_record_menu")],
        [InlineKeyboardButton("📋 Ընտրել թերթիկ", callback_data="select_sheet")],
        [InlineKeyboardButton("📊 Կարգավիճակ", callback_data="status")],
        [InlineKeyboardButton("📈 Վիճակագրություն", callback_data="stats")],
        [InlineKeyboardButton("📊 Ընտրել աղյուսակ", callback_data="select_spreadsheet")]
    ]
    
    if user_id and user_id in ADMIN_IDS:
        keyboard.extend([
            [InlineKeyboardButton("💸 Վճարներ", callback_data="pay_menu")],
            [InlineKeyboardButton("📊 Аналитика", callback_data="analytics_menu")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu")]
        ])
    else:
        # Для обычных пользователей - кнопка просмотра их платежей
        keyboard.append([InlineKeyboardButton("💰 Իմ վճարումները", callback_data="my_payments")])
    
    return InlineKeyboardMarkup(keyboard)

def create_analytics_menu():
    """Создает меню аналитики"""
    keyboard = [
        [InlineKeyboardButton("📊 Общая аналитика", callback_data="general_analytics")],
        [InlineKeyboardButton("💰 Аналитика платежей", callback_data="payment_analytics")],
        [InlineKeyboardButton("📈 Тренды", callback_data="trends_report")],
        [InlineKeyboardButton("📋 Еженедельный отчет", callback_data="weekly_report")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_settings_menu():
    """Создает меню настроек"""
    keyboard = [
        [InlineKeyboardButton("👥 Настройки пользователей", callback_data="user_settings_menu")],
        [InlineKeyboardButton("🔔 Настройки уведомлений", callback_data="notification_settings")],
        [InlineKeyboardButton("💾 Резервные копии", callback_data="backup_menu")],
        [InlineKeyboardButton("🧹 Очистка данных", callback_data="cleanup_menu")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_add_record_menu():
    """Создает меню выбора типа добавления записи"""
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել գրառում", callback_data="add_record")],
        [InlineKeyboardButton("➕ Ավելացնել Բացթողում", callback_data="add_skip_record")],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_supplier_choice_keyboard(display_name=None):
    """Создает клавиатуру выбора поставщика"""
    keyboard = []
    if display_name:
        keyboard.append([InlineKeyboardButton(f"👤 Օգտագործել իմ անունը ({display_name})", callback_data="use_my_name")])
    keyboard.append([InlineKeyboardButton(f"🏢 Օգտագործել Ֆիրմայի անունը", callback_data="use_firm_name")])
    keyboard.append([InlineKeyboardButton("✏️ Մուտքագրել ձեռքով", callback_data="manual_input")])
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

# --- Новая функция для меню работников ---
def create_workers_menu():
    """Создает клавиатуру для выбора работника (для админов)"""
    users = load_users()
    keyboard = []
    for uid, udata in users.items():
        display_name = udata.get('display_name')
        if display_name:
            keyboard.append([InlineKeyboardButton(display_name, callback_data=f"pay_user_{display_name}")])
    keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
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


# Совместимость: create_payment_menu для button_handlers.py
def create_payment_menu(display_name):
    """Создает меню действий с платежами для выбранного работника"""
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել վճարում", callback_data=f"add_payment_{display_name}")],
        [InlineKeyboardButton("📊 Ստանալ սահմանի հաշվետվություն", callback_data=f"get_payment_report_{display_name}")],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="pay_menu")]
    ]
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

def create_back_to_menu_keyboard():
    """Создает клавиатуру с кнопкой возврата в главное меню"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Գլխավոր Մենյու", callback_data="main_menu")]])

def create_reply_menu():
    """Создает Reply клавиатуру с кнопкой меню"""
    from telegram import ReplyKeyboardMarkup
    return ReplyKeyboardMarkup([["📋 Մենյու"]], resize_keyboard=True)
