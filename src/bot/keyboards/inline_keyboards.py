"""
Инлайн клавиатуры для бота
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from ...config.settings import ADMIN_IDS, UserRole, logger
from ...utils.config_utils import (
    load_users, get_user_role, is_super_admin, is_admin,
    can_add_records, can_view_payments, is_client, is_secondary, is_shop_owner
)

def create_main_menu(user_id=None):
    """Создает главное меню"""
    # Клиенты не имеют доступа к меню
    if is_client(user_id):
        try:
            from ...utils.localization import _
            no_access_text = _("notifications.access_denied", user_id)
        except Exception:
            no_access_text = "⛔ У вас нет доступа к меню"
        keyboard = [
            [InlineKeyboardButton(no_access_text, callback_data="no_access")]
        ]
        return InlineKeyboardMarkup(keyboard)

    if is_shop_owner(user_id):
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("💼 Պարտքերի մնացորդ", callback_data="owner_debt_balance")]
        ])

    keyboard = []

    if can_add_records(user_id):
        keyboard.extend([
            [
                InlineKeyboardButton("💸 Ծախս", callback_data="expense_menu"),
            ],
            [
                InlineKeyboardButton("🧾 Պարտք", callback_data="debt_menu"),
                InlineKeyboardButton("💳 Պարտքի մարում", callback_data="repayment_menu"),
            ],
            [
                InlineKeyboardButton("💰 Վճարներ", callback_data="payments_menu"),
            ],
        ])

    if can_view_payments(user_id) and not can_add_records(user_id):
        keyboard.append([InlineKeyboardButton("💰 Վճարներ", callback_data="my_payments")])

    # Супер-админ: управление ролями
    if is_super_admin(user_id):
        try:
            from ...utils.localization import _
            role_mgmt_text = _("users.main_menu", user_id)
        except Exception:
            role_mgmt_text = "👥 Управление ролями"
        keyboard.append([
            InlineKeyboardButton(role_mgmt_text, callback_data="role_menu"),
        ])

    # Вторичные пользователи: только просмотр
    if is_secondary(user_id):
        try:
            from ...utils.localization import _
            view_payments_text = _("menu.table", user_id)
        except Exception:
            view_payments_text = "👁 Просмотр платежей"
        keyboard.insert(0, [
            InlineKeyboardButton(view_payments_text, callback_data="view_payments_secondary")
        ])
    
    return InlineKeyboardMarkup(keyboard)


def create_expense_type_menu():
    """Подменю раздела расходов: Бригада / Магазин / Иное"""
    keyboard = [
        [
            InlineKeyboardButton("🏗️ Բրիգադ", callback_data="expense_entity_type_brigade"),
            InlineKeyboardButton("🏪 Խանութ", callback_data="expense_entity_type_shop"),
        ],
        [InlineKeyboardButton("📦 Այլ", callback_data="expense_other")],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)


def create_entity_selection_menu(entities, prefix: str, back_callback: str = "expense_menu"):
    """Универсальная клавиатура выбора сущности из конфигурации"""
    keyboard = []
    row = []
    for idx, entity in enumerate(entities):
        title = entity.get('name') or f"Entity {idx + 1}"
        row.append(InlineKeyboardButton(f"📌 {title}", callback_data=f"{prefix}_{idx}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)


def create_debt_type_menu(operation: str):
    """Меню выбора типа сущности для долга/погашения"""
    keyboard = [
        [
            InlineKeyboardButton("🏗️ Բրիգադ", callback_data=f"debt_entity_type_{operation}_brigade"),
            InlineKeyboardButton("🏪 Խանութ", callback_data=f"debt_entity_type_{operation}_shop"),
        ],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_analytics_menu(user_id=None):
    """Создает меню аналитики"""
    try:
        from ...utils.localization import _
        general_text = _("analytics.general", user_id)
        users_text = _("analytics.users", user_id)
        financial_text = _("analytics.financial", user_id)
        periods_text = _("analytics.periods", user_id)
        export_text = _("analytics.export", user_id)
        detailed_text = _("analytics.detailed", user_id)
        back_text = _("menu.back", user_id)
    except:
        # Fallback на статичный текст
        general_text = "📊 Общая аналитика"
        users_text = "👥 Пользователи"
        financial_text = "💰 Финансовая аналитика"
        periods_text = "📅 По периодам"
        export_text = "📊 Экспорт"
        detailed_text = "📊 Детальная аналитика"
        back_text = "⬅️ Назад"
    
    keyboard = [
        # Основные виды аналитики - по 2 в ряд
        [
            InlineKeyboardButton(general_text, callback_data="general_analytics"),
            InlineKeyboardButton(users_text, callback_data="user_analytics")
        ],
        [
            InlineKeyboardButton(financial_text, callback_data="financial_analytics"),
            InlineKeyboardButton(periods_text, callback_data="period_analytics")
        ],
        # Дополнительные функции
        [
            InlineKeyboardButton(detailed_text, callback_data="detailed_analytics"),
            InlineKeyboardButton(export_text, callback_data="export_analytics_menu")
        ],
        # Навигация
        [InlineKeyboardButton(back_text, callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_settings_menu(user_id=None):
    """Создает меню настроек"""
    # Попытка получить локализованный текст
    try:
        from ...utils.localization import _
        language_text = _("settings.language", user_id)
        notifications_text = _("settings.notifications", user_id)
        limits_text = _("settings.limits", user_id)
        backup_text = _("settings.backup", user_id)
        users_text = _("settings.users", user_id)
        system_info_text = _("settings.system_info", user_id)
        translation_text = _("settings.translation_management", user_id)
        back_text = _("menu.back", user_id)
    except:
        # Fallback на статичный текст
        language_text = "🌐 Язык"
        notifications_text = "🔔 Уведомления"
        limits_text = "💰 Лимиты"
        backup_text = "💾 Резервные копии"
        users_text = "👥 Пользователи"
        system_info_text = "🔧 Системная информация"
        translation_text = "🌍 Управление переводами"
        back_text = "⬅️ Назад"
    
    keyboard = [
        [
            InlineKeyboardButton(language_text, callback_data="language_menu"),
            InlineKeyboardButton(notifications_text, callback_data="notification_settings")
        ],
        [
            InlineKeyboardButton(limits_text, callback_data="limits_settings"),
            InlineKeyboardButton(backup_text, callback_data="backup_menu")
        ]
    ]
    
    # Админские функции
    if user_id and user_id in ADMIN_IDS:
        keyboard.extend([
            [
                InlineKeyboardButton(users_text, callback_data="user_management"),
                InlineKeyboardButton(system_info_text, callback_data="system_info")
            ],
            [InlineKeyboardButton(translation_text, callback_data="translation_management")]
        ])
    
    keyboard.append([InlineKeyboardButton(back_text, callback_data="back_to_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def create_add_record_menu():
    """Создает меню выбора типа добавления записи"""
    keyboard = [
        [
            InlineKeyboardButton("➕ Ավելացնել գրառում", callback_data="add_record_select_sheet"),
            InlineKeyboardButton("🧾 Ավելացնել Բացթողում", callback_data="add_skip_record_select_sheet"),
        ],
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
    logger.info(f"Creating sheet selection keyboard with {len(sheets_info)} sheets for record_type: {record_type}")
    
    for sheet in sheets_info:
        callback_data = f"add_{record_type}_sheet_{sheet['title']}"
        logger.info(f"Creating button with callback_data: {callback_data}")
        keyboard.append([InlineKeyboardButton(
            f"📋 {sheet['title']}", 
            callback_data=callback_data
        )])
    
    keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
    logger.info(f"Created keyboard with {len(keyboard)} rows")
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
        # [InlineKeyboardButton("🏪 Մատակարար", callback_data=f"edit_supplier_{record_id}")],
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
        [
            InlineKeyboardButton("➕ Ավելացնել վճարում", callback_data=f"add_payment_{display_name}"),
            InlineKeyboardButton("📊 Սահմանային հաշվետվություն", callback_data=f"get_payment_report_{display_name}"),
        ],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="pay_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_payment_actions_keyboard(display_name):
    """Создает клавиатуру действий с платежами"""
    keyboard = [
        [
            InlineKeyboardButton("➕ Ավելացնել վճարում", callback_data=f"add_payment_{display_name}"),
            InlineKeyboardButton("📊 Սահմանային հաշվետվություն", callback_data=f"get_payment_report_{display_name}"),
        ],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="pay_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_back_button():
    """Создает простую кнопку назад"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")]])

def create_back_to_menu_keyboard():
    """Создает клавиатуру с кнопкой возврата в главное меню"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Գլխավոր Մենյու", callback_data="main_menu")]])

def create_edit_record_keyboard(record_id):
    """Создает клавиатуру для редактирования записи"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Խմբագրել", callback_data=f"edit_record_{record_id}")]])

def create_reply_menu():
    """Создает Reply клавиатуру с кнопкой меню"""
    from telegram import ReplyKeyboardMarkup
    return ReplyKeyboardMarkup([["📋 Մենյու"]], resize_keyboard=True)

def create_export_analytics_menu(user_id=None):
    """Создает меню экспорта аналитики"""
    try:
        from ...utils.localization import _
        general_export = _("analytics.export_general", user_id) if hasattr(_, "__call__") else "📊 Экспорт общей аналитики"
        user_export = _("analytics.export_users", user_id) if hasattr(_, "__call__") else "👥 Экспорт по пользователям"
        financial_export = _("analytics.export_financial", user_id) if hasattr(_, "__call__") else "💰 Экспорт финансовой аналитики"
        period_export = _("analytics.export_periods", user_id) if hasattr(_, "__call__") else "📅 Экспорт по периодам"
        back_text = _("menu.back", user_id) if hasattr(_, "__call__") else "⬅️ Назад"
    except:
        # Fallback на статичный текст
        general_export = "📊 Экспорт общей аналитики"
        user_export = "👥 Экспорт по пользователям"
        financial_export = "💰 Экспорт финансовой аналитики"
        period_export = "📅 Экспорт по периодам"
        back_text = "⬅️ Назад"
    
    keyboard = [
        [InlineKeyboardButton(general_export, callback_data="export_general_analytics")],
        [InlineKeyboardButton(user_export, callback_data="export_user_analytics")],
        [InlineKeyboardButton(financial_export, callback_data="export_financial_analytics")],
        [InlineKeyboardButton(period_export, callback_data="export_period_analytics")],
        [InlineKeyboardButton(back_text, callback_data="analytics_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_users_management_menu(user_id=None):
    """Создает меню управления пользователями"""
    try:
        from ...utils.localization import _
        list_users = _("users.list", user_id)
        add_user = _("users.add", user_id)
        permissions = _("users.permissions", user_id)
        stats = _("users.stats", user_id)
        add_admin = _("users.add_admin", user_id)
        remove_admin = _("users.remove_admin", user_id)
        back_text = _("menu.back", user_id)
    except:
        # Fallback на статичный текст
        list_users = "👥 Список пользователей"
        add_user = "➕ Добавить пользователя"
        permissions = "🔧 Права доступа"
        stats = "📊 Статистика пользователей"
        add_admin = "👑 Добавить админа"
        remove_admin = "👤 Убрать админа"
        back_text = "⬅️ Назад"
    
    keyboard = [
        # Основные функции управления
        [
            InlineKeyboardButton(list_users, callback_data="list_users"),
            InlineKeyboardButton(add_user, callback_data="add_user")
        ],
        [
            InlineKeyboardButton(permissions, callback_data="user_permissions"),
            InlineKeyboardButton(stats, callback_data="user_stats")
        ],
        # Админские функции
        [
            InlineKeyboardButton(add_admin, callback_data="add_admin"),
            InlineKeyboardButton(remove_admin, callback_data="remove_admin")
        ],
        # Навигация
        [InlineKeyboardButton(back_text, callback_data="settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_translation_management_menu(user_id=None):
    """Создает меню управления переводами"""
    try:
        from ...utils.localization import _
        add_translation = _("translation.add_translation", user_id)
        add_language = _("translation.add_language", user_id)
        list_translations = _("translation.list_translations", user_id)
        reload_translations = _("translation.reload_translations", user_id)
        back_text = _("menu.back", user_id)
    except:
        # Fallback на статичный текст
        add_translation = "➕ Добавить перевод"
        add_language = "🌐 Добавить язык"
        list_translations = "📋 Список переводов"
        reload_translations = "🔄 Перезагрузить переводы"
        back_text = "⬅️ Назад"
    
    keyboard = [
        [InlineKeyboardButton(add_translation, callback_data="add_translation")],
        [InlineKeyboardButton(add_language, callback_data="add_language")],
        [InlineKeyboardButton(list_translations, callback_data="list_translations")],
        [InlineKeyboardButton(reload_translations, callback_data="reload_translations")],
        [InlineKeyboardButton(back_text, callback_data="settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_backup_menu(user_id=None):
    """Создает меню резервного копирования"""
    try:
        from ...utils.localization import _
        create_text = _("backup.create", user_id)
        list_text = _("backup.list", user_id)
        restore_text = _("backup.restore", user_id)
        cleanup_text = _("backup.cleanup", user_id)
        back_text = _("menu.back", user_id)
    except:
        # Fallback на статичный текст
        create_text = "💾 Создать резервную копию"
        list_text = "📁 Список копий"
        restore_text = "🔄 Восстановить"
        cleanup_text = "🗑️ Очистить старые"
        back_text = "⬅️ Назад"
    
    keyboard = [
        [InlineKeyboardButton(create_text, callback_data="create_backup")],
        [
            InlineKeyboardButton(list_text, callback_data="list_backups"),
            InlineKeyboardButton(restore_text, callback_data="restore_backup")
        ],
        [InlineKeyboardButton(cleanup_text, callback_data="cleanup_backups")],
        [InlineKeyboardButton(back_text, callback_data="settings_menu")]
    ]
    
    return InlineKeyboardMarkup(keyboard)
