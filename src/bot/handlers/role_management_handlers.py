"""
Обработчики для управления ролями пользователей (только для супер-админа)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from html import escape

from ...config.settings import (
    UserRole, logger,
    DEFAULT_BRIGADE_SPREADSHEET_ID, DEFAULT_SHOP_SPREADSHEET_ID,
    DEFAULT_BRIGADE_SHEET_NAME, DEFAULT_SHOP_SHEET_NAME
)
from ...utils.config_utils import (
    is_super_admin, get_user_role, set_user_role, get_users_by_role,
    get_user_display_name, get_role_display_name, add_allowed_user,
    remove_allowed_user, load_users, is_user_allowed,
    load_brigades_shops, save_brigades_shops
)


# Conversation states
SELECT_USER_ACTION, SELECT_ROLE, INPUT_USER_ID, INPUT_DISPLAY_NAME = range(4)
INPUT_ENTITY_NAME, INPUT_ENTITY_SPREADSHEET, INPUT_ENTITY_SHEET, INPUT_ENTITY_OWNER, INPUT_ENTITY_EDIT_VALUE = range(10, 15)


def _entity_type_label(entity_type: str) -> str:
    return "Բրիգադ" if entity_type == "brigade" else "Խանութ"


def _default_spreadsheet_for_entity(entity_type: str):
    return DEFAULT_BRIGADE_SPREADSHEET_ID if entity_type == 'brigade' else DEFAULT_SHOP_SPREADSHEET_ID


def _default_sheet_name_for_entity(entity_type: str):
    return DEFAULT_BRIGADE_SHEET_NAME if entity_type == 'brigade' else DEFAULT_SHOP_SHEET_NAME


async def role_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню управления ролями (только для супер-админа)"""
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await update.message.reply_text("⛔ Դուք մուտք չունեք այս գործառույթին:")
        return

    keyboard = [
        [
            InlineKeyboardButton("➕ Ավելացնել օգտվող", callback_data="role_add_user"),
            InlineKeyboardButton("👥 Օգտվողների ցանկ", callback_data="role_list_users"),
        ],
        [
            InlineKeyboardButton("✏️ Փոխել դերը", callback_data="role_change_role"),
            InlineKeyboardButton("🗑 Ջնջել օգտվողին", callback_data="role_remove_user"),
        ],
        [InlineKeyboardButton("👁 Երկրորդային օգտվողներ", callback_data="role_view_secondary")],
        [InlineKeyboardButton("🏗️🏪 Կառավարել բրիգադ/խանութ", callback_data="entity_menu")],
        [InlineKeyboardButton("🔙 Հետ", callback_data="back_to_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = (
        "👨‍💼 *Դերերի և օգտվողների կառավարում*\n\n"
        "Հասանելի գործողություններ:"
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def list_all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список всех пользователей с их ролями"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    users = load_users()
    if not users:
        await query.edit_message_text(
            "📋 Օգտվողների ցանկը դատարկ է:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")
            ]])
        )
        return

    message_lines = ["👥 *Список всех пользователей:*\n"]

    for user_id_str, user_data in users.items():
        display_name = user_data.get('display_name', 'Без имени')
        role = get_user_role(int(user_id_str))
        role_name = get_role_display_name(role) if role else 'Не задана'

        message_lines.append(
            f"• *{display_name}* (`{user_id_str}`)\n"
            f"  Роль: {role_name}"
        )

    message_text = "\n".join(message_lines)

    keyboard = [[InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def view_secondary_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список вторичных пользователей (read-only)"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    secondary_users = get_users_by_role(UserRole.SECONDARY)

    if not secondary_users:
        await query.edit_message_text(
            "👁 *Вторичные пользователи*\n\n"
            "Список пуст. Нет пользователей с ролью 'Вторичный'.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")
            ]]),
            parse_mode='Markdown'
        )
        return

    message_lines = ["👁 *Вторичные пользователи (только просмотр):*\n"]

    for sec_user_id in secondary_users:
        display_name = get_user_display_name(sec_user_id) or 'Без имени'
        message_lines.append(f"• *{display_name}* (`{sec_user_id}`)")

    message_text = "\n".join(message_lines)

    keyboard = [[InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def start_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс добавления нового пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="role_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "➕ *Добавление нового пользователя*\n\n"
        "Введите Telegram User ID пользователя:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    return INPUT_USER_ID


async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает User ID и запрашивает отображаемое имя"""
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await update.message.reply_text("⛔ Դուք մուտք չունեք այս գործառույթին:")
        return ConversationHandler.END

    try:
        new_user_id = int(update.message.text.strip())
        context.user_data['new_user_id'] = new_user_id

        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="role_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"✅ User ID: `{new_user_id}`\n\n"
            "Теперь введите отображаемое имя пользователя (на армянском):",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        return INPUT_DISPLAY_NAME

    except ValueError:
        keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="role_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "❌ Неверный формат. Пожалуйста, введите числовой User ID.",
            reply_markup=reply_markup
        )
        return INPUT_USER_ID


async def receive_display_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает отображаемое имя и предлагает выбрать роль"""
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await update.message.reply_text("⛔ Դուք մուտք չունեք այս գործառույթին:")
        return ConversationHandler.END

    display_name = update.message.text.strip()
    context.user_data['new_user_display_name'] = display_name

    keyboard = [
        [InlineKeyboardButton("Ադմինիստրատոր", callback_data=f"setrole_{UserRole.ADMIN}")],
        [InlineKeyboardButton("Աշխատող", callback_data=f"setrole_{UserRole.WORKER}")],
        [InlineKeyboardButton("Երկրորդային", callback_data=f"setrole_{UserRole.SECONDARY}")],
        [InlineKeyboardButton("Կլիենտ", callback_data=f"setrole_{UserRole.CLIENT}")],
        [InlineKeyboardButton("Խանութի տեր/բրիգադի", callback_data=f"setrole_{UserRole.SHOP_OWNER}")],
        [InlineKeyboardButton("🔙 Отмена", callback_data="role_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"✅ Имя: *{display_name}*\n\n"
        "Выберите роль для пользователя:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

    return SELECT_ROLE


async def set_role_for_new_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Устанавливает роль для нового пользователя и завершает добавление"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    role = query.data.replace("setrole_", "")
    new_user_id = context.user_data.get('new_user_id')
    display_name = context.user_data.get('new_user_display_name')

    if not new_user_id or not display_name:
        await query.edit_message_text("❌ Ошибка: данные пользователя не найдены.")
        return ConversationHandler.END

    # Добавляем пользователя в allowed_users
    add_allowed_user(new_user_id)

    # Устанавливаем роль и display_name
    set_user_role(new_user_id, role)

    from ...utils.config_utils import update_user_settings

    # Устанавливаем display_name для пользователя
    update_user_settings(new_user_id, {'display_name': display_name})

    role_display = get_role_display_name(role)

    await query.edit_message_text(
        f"✅ *Пользователь успешно добавлен!*\n\n"
        f"• Имя: {display_name}\n"
        f"• User ID: `{new_user_id}`\n"
        f"• Роль: {role_display}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")
        ]]),
        parse_mode='Markdown'
    )

    # Очищаем временные данные
    context.user_data.pop('new_user_id', None)
    context.user_data.pop('new_user_display_name', None)

    return ConversationHandler.END


async def start_change_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс изменения роли пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    users = load_users()
    if not users:
        await query.edit_message_text(
            "📋 Օգտվողների ցանկը դատարկ է:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")
            ]])
        )
        return

    keyboard = []
    for user_id_str, user_data in users.items():
        display_name = user_data.get('display_name') or f'User {user_id_str}'
        # Пропускаем пользователей с очень коротким именем (может быть артефакт)
        if len(display_name.strip()) == 0:
            display_name = f'User {user_id_str}'
        keyboard.append([InlineKeyboardButton(
            display_name,
            callback_data=f"changerole_user_{user_id_str}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "✏️ *Изменение роли*\n\n"
        "Выберите пользователя:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def select_new_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает меню выбора новой роли для пользователя"""
    query = update.callback_query
    admin_id = update.effective_user.id

    if not is_super_admin(admin_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    user_id_str = query.data.replace("changerole_user_", "")
    user_id = int(user_id_str)

    display_name = get_user_display_name(user_id) or f'User {user_id}'
    current_role = get_user_role(user_id)
    current_role_display = get_role_display_name(current_role) if current_role else 'Не задана'

    keyboard = [
        [InlineKeyboardButton("Ադմինիստրատոր", callback_data=f"newrole_{user_id}_{UserRole.ADMIN}")],
        [InlineKeyboardButton("Աշխատող", callback_data=f"newrole_{user_id}_{UserRole.WORKER}")],
        [InlineKeyboardButton("Երկրորդային", callback_data=f"newrole_{user_id}_{UserRole.SECONDARY}")],
        [InlineKeyboardButton("Կլիենտ", callback_data=f"newrole_{user_id}_{UserRole.CLIENT}")],
        [InlineKeyboardButton("Խանութի տեր/բրիգադի", callback_data=f"newrole_{user_id}_{UserRole.SHOP_OWNER}")],
        [InlineKeyboardButton("🔙 Հետ", callback_data="role_change_role")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f"✏️ *Изменение роли пользователя*\n\n"
        f"• Пользователь: {display_name}\n"
        f"• Текущая роль: {current_role_display}\n\n"
        "Выберите новую роль:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def apply_new_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Применяет новую роль к пользователю"""
    query = update.callback_query
    admin_id = update.effective_user.id

    if not is_super_admin(admin_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    payload = query.data.replace("newrole_", "", 1)
    first_sep = payload.find("_")
    user_id = int(payload[:first_sep])
    new_role = payload[first_sep + 1:]

    set_user_role(user_id, new_role)

    display_name = get_user_display_name(user_id) or f'User {user_id}'
    role_display = get_role_display_name(new_role)

    await query.edit_message_text(
        f"✅ *Роль успешно изменена!*\n\n"
        f"• Пользователь: {display_name}\n"
        f"• Новая роль: {role_display}",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")
        ]]),
        parse_mode='Markdown'
    )


async def start_remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает процесс удаления пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    users = load_users()
    if not users:
        await query.edit_message_text(
            "📋 Օգտվողների ցանկը դատարկ է:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")
            ]])
        )
        return

    keyboard = []
    for user_id_str, user_data in users.items():
        display_name = user_data.get('display_name') or f'User {user_id_str}'
        # Пропускаем пользователей с очень коротким именем
        if len(display_name.strip()) == 0:
            display_name = f'User {user_id_str}'
        keyboard.append([InlineKeyboardButton(
            display_name,
            callback_data=f"removeuser_confirm_{user_id_str}"
        )])

    keyboard.append([InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        "🗑 *Удаление пользователя*\n\n"
        "⚠️ Выберите пользователя для удаления:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def confirm_remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет пользователя из системы"""
    query = update.callback_query
    admin_id = update.effective_user.id

    if not is_super_admin(admin_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    user_id_str = query.data.replace("removeuser_confirm_", "")
    user_id = int(user_id_str)

    display_name = get_user_display_name(user_id) or f'User {user_id}'

    # Удаляем из allowed_users
    remove_allowed_user(user_id)

    # Удаляем из users.json
    users = load_users()
    if user_id_str in users:
        del users[user_id_str]
        from ...utils.config_utils import save_users
        save_users(users)

    await query.edit_message_text(
        f"✅ *Пользователь удален!*\n\n"
        f"• {display_name} (`{user_id}`)\n\n"
        "Пользователь больше не имеет доступа к боту.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")
        ]]),
        parse_mode='Markdown'
    )


async def cancel_role_operation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет операцию и возвращает в меню"""
    await role_management_menu(update, context)
    return ConversationHandler.END


async def entity_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню управления бригадами и магазинами (только для супер-админа)"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        if query:
            await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    if query:
        await query.answer()

    keyboard = [
        [
            InlineKeyboardButton("➕ Բրիգադ", callback_data="entity_add_brigade"),
            InlineKeyboardButton("➕ Խանութ", callback_data="entity_add_shop"),
        ],
        [
            InlineKeyboardButton("📋 Բրիգադներ", callback_data="entity_list_brigades"),
            InlineKeyboardButton("📋 Խանութներ", callback_data="entity_list_shops"),
        ],
        [
            InlineKeyboardButton("✏️ Խմբագրել բրիգադ", callback_data="entity_edit_brigade_menu"),
            InlineKeyboardButton("✏️ Խմբագրել խանութ", callback_data="entity_edit_shop_menu"),
        ],
        [
            InlineKeyboardButton("🗑 Ջնջել բրիգադ", callback_data="entity_delete_brigade_menu"),
            InlineKeyboardButton("🗑 Ջնջել խանութ", callback_data="entity_delete_shop_menu"),
        ],
        [InlineKeyboardButton("🔙 Հետ", callback_data="role_menu")]
    ]

    text = (
        "🏗️🏪 *Կառավարել բրիգադ/խանութ*\n\n"
        "Ընտրեք գործողությունը:"
    )

    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def start_add_entity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Старт диалога добавления бригады/магазина"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    entity_type = "brigade" if query.data == "entity_add_brigade" else "shop"
    context.user_data['entity_type'] = entity_type

    keyboard = [[InlineKeyboardButton("❌ Չեղարկել", callback_data="entity_menu")]]
    await query.edit_message_text(
        f"➕ *Ավելացնել {_entity_type_label(entity_type)}*\n\n"
        "1) Մուտքագրեք անվանումը:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

    return INPUT_ENTITY_NAME


async def receive_entity_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает название сущности"""
    user_id = update.effective_user.id
    if not is_super_admin(user_id):
        return ConversationHandler.END

    entity_name = update.message.text.strip()
    if not entity_name:
        await update.message.reply_text("❌ Անվանումը չի կարող դատարկ լինել:")
        return INPUT_ENTITY_NAME

    context.user_data['entity_name'] = entity_name
    await update.message.reply_text(
        "2) Մուտքագրեք `spreadsheet_id` (Google Sheet ID)\n"
        "Կամ ուղարկեք `-`՝ օգտագործելու .env default արժեքը:",
        parse_mode='Markdown'
    )
    return INPUT_ENTITY_SPREADSHEET


async def receive_entity_spreadsheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает spreadsheet_id"""
    user_id = update.effective_user.id
    if not is_super_admin(user_id):
        return ConversationHandler.END

    spreadsheet_id = update.message.text.strip()
    if spreadsheet_id in ("-", ""):
        entity_type = context.user_data.get('entity_type')
        spreadsheet_id = _default_spreadsheet_for_entity(entity_type)
        if not spreadsheet_id:
            await update.message.reply_text(
                "❌ Default spreadsheet_id չի գտնվել .env-ում:\n"
                "Սահմանեք `DEFAULT_BRIGADE_SPREADSHEET_ID` կամ `DEFAULT_SHOP_SPREADSHEET_ID`,\n"
                "կամ մուտքագրեք spreadsheet_id ձեռքով.",
                parse_mode='Markdown'
            )
            return INPUT_ENTITY_SPREADSHEET

    context.user_data['entity_spreadsheet_id'] = spreadsheet_id
    await update.message.reply_text(
        "3) Մուտքագրեք `sheet_name`\n"
        "Կամ ուղարկեք `-`՝ .env default կամ entity name օգտագործելու համար (ավտո-ստեղծվում է եթե չկա):",
        parse_mode='Markdown'
    )
    return INPUT_ENTITY_SHEET


async def receive_entity_sheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает sheet_name"""
    user_id = update.effective_user.id
    if not is_super_admin(user_id):
        return ConversationHandler.END

    sheet_name = update.message.text.strip()
    if sheet_name in ("-", ""):
        entity_type = context.user_data.get('entity_type')
        sheet_name = (_default_sheet_name_for_entity(entity_type) or context.user_data.get('entity_name', '')).strip()

    if not sheet_name:
        await update.message.reply_text("❌ `sheet_name` չի կարող դատարկ լինել:", parse_mode='Markdown')
        return INPUT_ENTITY_SHEET

    context.user_data['entity_sheet_name'] = sheet_name
    await update.message.reply_text(
        "4) Մուտքագրեք `owner_id` (թիվ) կամ `-`, եթե owner չկա:"
    )
    return INPUT_ENTITY_OWNER


async def receive_entity_owner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает owner_id и сохраняет сущность"""
    user_id = update.effective_user.id
    if not is_super_admin(user_id):
        return ConversationHandler.END

    owner_raw = update.message.text.strip()
    owner_id = None
    if owner_raw not in ("-", "", "none", "None"):
        try:
            owner_id = int(owner_raw)
        except ValueError:
            await update.message.reply_text("❌ `owner_id` պետք է լինի թիվ կամ `-`:", parse_mode='Markdown')
            return INPUT_ENTITY_OWNER

    entity_type = context.user_data.get('entity_type')
    entity_name = context.user_data.get('entity_name')
    spreadsheet_id = context.user_data.get('entity_spreadsheet_id')
    sheet_name = context.user_data.get('entity_sheet_name')

    if not all([entity_type, entity_name, spreadsheet_id, sheet_name]):
        await update.message.reply_text("❌ Սխալ: տվյալները թերի են:")
        return ConversationHandler.END

    config = load_brigades_shops()
    key = 'brigades' if entity_type == 'brigade' else 'shops'
    entities = config.get(key, [])

    duplicate = next((item for item in entities if str(item.get('name', '')).strip().lower() == entity_name.lower()), None)
    if duplicate:
        await update.message.reply_text(
            f"⚠️ {_entity_type_label(entity_type)} '{entity_name}' արդեն կա:\n"
            f"Փոխեք անունը կամ ջնջեք հինը:"
        )
        return INPUT_ENTITY_NAME

    new_entity = {
        'name': entity_name,
        'spreadsheet_id': spreadsheet_id,
        'sheet_name': sheet_name,
        'owner_id': owner_id
    }
    entities.append(new_entity)
    config[key] = entities
    save_brigades_shops(config)

    context.user_data.pop('entity_type', None)
    context.user_data.pop('entity_name', None)
    context.user_data.pop('entity_spreadsheet_id', None)
    context.user_data.pop('entity_sheet_name', None)

    safe_entity_name = escape(str(entity_name))
    safe_spreadsheet_id = escape(str(spreadsheet_id))
    safe_sheet_name = escape(str(sheet_name))
    safe_owner_id = escape(str(owner_id if owner_id is not None else '-'))

    await update.message.reply_text(
        f"✅ <b>{escape(_entity_type_label(entity_type))} ավելացված է</b>\n\n"
        f"• Անուն: {safe_entity_name}\n"
        f"• spreadsheet_id: <code>{safe_spreadsheet_id}</code>\n"
        f"• sheet_name: <code>{safe_sheet_name}</code>\n"
        f"• owner_id: <code>{safe_owner_id}</code>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏗️🏪 Սուբյեկտների մենյու", callback_data="entity_menu")]]),
        parse_mode='HTML'
    )

    return ConversationHandler.END


async def list_entities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список бригад/магазинов"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    entity_type = 'brigade' if query.data == 'entity_list_brigades' else 'shop'
    config = load_brigades_shops()
    key = 'brigades' if entity_type == 'brigade' else 'shops'
    entities = config.get(key, [])

    if not entities:
        await query.edit_message_text(
            f"📋 {_entity_type_label(entity_type)}ներ չկան:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Հետ", callback_data="entity_menu")]])
        )
        return

    lines = [f"📋 *{_entity_type_label(entity_type)}ների ցանկ*\n"]
    for index, item in enumerate(entities, start=1):
        lines.append(
            f"{index}. *{item.get('name', '-')}*\n"
            f"   • sheet: `{item.get('sheet_name', '-')}`\n"
            f"   • owner_id: `{item.get('owner_id', '-')}`"
        )

    await query.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Հետ", callback_data="entity_menu")]]),
        parse_mode='Markdown'
    )


async def start_delete_entity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список сущностей для удаления"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    entity_type = 'brigade' if query.data == 'entity_delete_brigade_menu' else 'shop'
    key = 'brigades' if entity_type == 'brigade' else 'shops'
    entities = load_brigades_shops().get(key, [])

    if not entities:
        await query.edit_message_text(
            f"📋 {_entity_type_label(entity_type)}ներ չկան:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Հետ", callback_data="entity_menu")]])
        )
        return

    keyboard = []
    for index, item in enumerate(entities):
        keyboard.append([
            InlineKeyboardButton(
                f"🗑 {item.get('name', f'#{index + 1}')}",
                callback_data=f"entity_delete_{entity_type}_{index}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Հետ", callback_data="entity_menu")])

    await query.edit_message_text(
        f"🗑 *Ընտրեք {_entity_type_label(entity_type)}ը ջնջման համար*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def execute_delete_entity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет выбранную сущность"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    payload = query.data.replace("entity_delete_", "", 1)
    try:
        entity_type, index_text = payload.rsplit("_", 1)
        index = int(index_text)
    except ValueError:
        await query.edit_message_text("❌ Սխալ callback format")
        return

    config = load_brigades_shops()
    key = 'brigades' if entity_type == 'brigade' else 'shops'
    entities = config.get(key, [])

    if index < 0 or index >= len(entities):
        await query.edit_message_text("❌ Սխալ ինդեքս")
        return

    removed = entities.pop(index)
    config[key] = entities
    save_brigades_shops(config)

    await query.edit_message_text(
        f"✅ Ջնջված է: *{removed.get('name', '-')}*",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Հետ", callback_data="entity_menu")]]),
        parse_mode='Markdown'
    )


async def start_edit_entity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список сущностей для редактирования"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    entity_type = 'brigade' if query.data == 'entity_edit_brigade_menu' else 'shop'
    key = 'brigades' if entity_type == 'brigade' else 'shops'
    entities = load_brigades_shops().get(key, [])

    if not entities:
        await query.edit_message_text(
            f"📋 {_entity_type_label(entity_type)}ներ չկան:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Հետ", callback_data="entity_menu")]])
        )
        return

    keyboard = []
    for index, item in enumerate(entities):
        keyboard.append([
            InlineKeyboardButton(
                f"✏️ {item.get('name', f'#{index + 1}')}",
                callback_data=f"entity_edit_select_{entity_type}_{index}"
            )
        ])
    keyboard.append([InlineKeyboardButton("🔙 Հետ", callback_data="entity_menu")])

    await query.edit_message_text(
        f"✏️ *Ընտրեք {_entity_type_label(entity_type)}ը խմբագրման համար*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def select_entity_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор поля для редактирования сущности"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    payload = query.data.replace("entity_edit_select_", "", 1)
    entity_type, index_text = payload.rsplit("_", 1)
    index = int(index_text)

    key = 'brigades' if entity_type == 'brigade' else 'shops'
    entities = load_brigades_shops().get(key, [])
    if index < 0 or index >= len(entities):
        await query.edit_message_text("❌ Սխալ ինդեքս")
        return

    entity = entities[index]
    context.user_data['entity_edit_type'] = entity_type
    context.user_data['entity_edit_index'] = index

    keyboard = [
        [InlineKeyboardButton("🏷 Անուն", callback_data="entity_edit_field_name")],
        [InlineKeyboardButton("🆔 spreadsheet_id", callback_data="entity_edit_field_spreadsheet_id")],
        [InlineKeyboardButton("📄 sheet_name", callback_data="entity_edit_field_sheet_name")],
        [InlineKeyboardButton("👤 owner_id", callback_data="entity_edit_field_owner_id")],
        [InlineKeyboardButton("🔙 Հետ", callback_data=f"entity_edit_{entity_type}_menu")]
    ]

    await query.edit_message_text(
        f"✏️ {entity.get('name', '-')}\n\n"
        "Ընտրեք դաշտը, որը պետք է փոփոխել:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def start_edit_entity_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрашивает новое значение для выбранного поля"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    field = query.data.replace("entity_edit_field_", "", 1)
    context.user_data['entity_edit_field'] = field

    hint = "Նոր արժեքը մուտքագրեք:"
    if field == 'owner_id':
        hint = "Նոր owner_id մուտքագրեք (թիվ), կամ `-`՝ մաքրելու համար:"
    elif field == 'sheet_name':
        hint = "Նոր sheet_name մուտքագրեք, կամ `-`՝ entity name օգտագործելու համար:"

    await query.edit_message_text(
        f"✏️ *Խմբագրում: {field}*\n\n{hint}",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Չեղարկել", callback_data="entity_menu")]])
    )
    return INPUT_ENTITY_EDIT_VALUE


async def apply_entity_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Применяет новое значение к полю сущности"""
    user_id = update.effective_user.id
    if not is_super_admin(user_id):
        return ConversationHandler.END

    entity_type = context.user_data.get('entity_edit_type')
    index = context.user_data.get('entity_edit_index')
    field = context.user_data.get('entity_edit_field')
    new_value = update.message.text.strip()

    if entity_type not in ('brigade', 'shop') or index is None or not field:
        await update.message.reply_text("❌ Սխալ: խմբագրման կոնտեքստը կորել է")
        return ConversationHandler.END

    config = load_brigades_shops()
    key = 'brigades' if entity_type == 'brigade' else 'shops'
    entities = config.get(key, [])

    if index < 0 or index >= len(entities):
        await update.message.reply_text("❌ Սխալ ինդեքս")
        return ConversationHandler.END

    entity = entities[index]

    if field == 'owner_id':
        if new_value in ('-', '', 'none', 'None'):
            parsed_value = None
        else:
            try:
                parsed_value = int(new_value)
            except ValueError:
                await update.message.reply_text("❌ owner_id պետք է լինի թիվ կամ `-`", parse_mode='Markdown')
                return INPUT_ENTITY_EDIT_VALUE
    elif field == 'sheet_name' and new_value in ('-', ''):
        parsed_value = (_default_sheet_name_for_entity(entity_type) or entity.get('name', '')).strip()
        if not parsed_value:
            await update.message.reply_text("❌ sheet_name չի կարող դատարկ լինել")
            return INPUT_ENTITY_EDIT_VALUE
    else:
        parsed_value = new_value
        if not parsed_value:
            await update.message.reply_text("❌ Դատարկ արժեք չի թույլատրվում")
            return INPUT_ENTITY_EDIT_VALUE

    entity[field] = parsed_value
    entities[index] = entity
    config[key] = entities
    save_brigades_shops(config)

    context.user_data.pop('entity_edit_type', None)
    context.user_data.pop('entity_edit_index', None)
    context.user_data.pop('entity_edit_field', None)

    safe_entity_name = escape(str(entity.get('name', '-')))
    safe_field = escape(str(field))
    safe_value = escape(str(parsed_value if parsed_value is not None else '-'))

    await update.message.reply_text(
        f"✅ <b>Թարմացվել է</b>\n\n"
        f"• {safe_entity_name}\n"
        f"• {safe_field}: <code>{safe_value}</code>",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏗️🏪 Սուբյեկտների մենյու", callback_data="entity_menu")]])
    )

    return ConversationHandler.END
