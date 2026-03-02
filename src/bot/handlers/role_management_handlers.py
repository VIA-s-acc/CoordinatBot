"""
Обработчики для управления ролями пользователей (только для супер-админа)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from ...config.settings import UserRole, logger
from ...utils.config_utils import (
    is_super_admin, get_user_role, set_user_role, get_users_by_role,
    get_user_display_name, get_role_display_name, add_allowed_user,
    remove_allowed_user, load_users, is_user_allowed
)


# Conversation states
SELECT_USER_ACTION, SELECT_ROLE, INPUT_USER_ID, INPUT_DISPLAY_NAME = range(4)


async def role_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню управления ролями (только для супер-админа)"""
    user_id = update.effective_user.id

    if not is_super_admin(user_id):
        await update.message.reply_text("⛔ Դուք մուտք չունեք այս գործառույթին:")
        return

    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել օգտվող", callback_data="role_add_user")],
        [InlineKeyboardButton("👥 Օգտվողների ցանկ", callback_data="role_list_users")],
        [InlineKeyboardButton("✏️ Փոխել դերը", callback_data="role_change_role")],
        [InlineKeyboardButton("🗑 Ջնջել օգտվողին", callback_data="role_remove_user")],
        [InlineKeyboardButton("👁 Երկրորդային օգտվողներ", callback_data="role_view_secondary")],
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
