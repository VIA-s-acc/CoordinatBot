"""
Обработчики для управления платежами (просмотр, редактирование, удаление)
Полностью переработанная версия с листаемыми списками
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from ...config.settings import UserRole
from ...utils.config_utils import (
    is_admin, is_super_admin, get_user_role, get_users_by_role,
    get_user_display_name, load_users
)
from ...database.database_manager import get_payments, delete_payment, update_payment, get_role_by_display_name

logger = logging.getLogger(__name__)

# Conversation states
EDIT_AMOUNT, EDIT_DATE_FROM, EDIT_DATE_TO, EDIT_COMMENT = range(4)

# Количество элементов на странице
ITEMS_PER_PAGE = 8


def get_user_role_by_display_name(display_name: str) -> str:
    """
    Определяет роль пользователя по display_name

    Args:
        display_name: Отображаемое имя пользователя

    Returns:
        Роль пользователя или UserRole.WORKER по умолчанию
    """
    users = load_users()
    for user_id_str, user_data in users.items():
        if user_data.get('display_name') == display_name:
            return user_data.get('role', UserRole.WORKER)
    return UserRole.WORKER


async def payments_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Главное меню платежей (только для админа)
    Показывает список воркеров с пагинацией
    """
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    # Получаем текущую страницу из callback_data или устанавливаем 0
    page = 0
    if query.data.startswith("payments_workers_page_"):
        page = int(query.data.replace("payments_workers_page_", ""))

    # Получаем всех воркеров
    worker_users = get_users_by_role(UserRole.WORKER)

    # Формируем список с платежами
    workers_with_payments = []
    for user_id_int in worker_users:
        display_name = get_user_display_name(user_id_int)
        if display_name:
            user_payments = get_payments(user_display_name=display_name)
            total_amount = sum(p['amount'] for p in user_payments)
            workers_with_payments.append({
                'name': display_name,
                'count': len(user_payments),
                'total': total_amount
            })

    # Сортируем по имени
    workers_with_payments.sort(key=lambda x: x['name'])

    # Пагинация
    total_pages = (len(workers_with_payments) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_workers = workers_with_payments[start_idx:end_idx]

    # Формируем клавиатуру
    keyboard = []

    # Кнопки для каждого воркера
    for worker in current_workers:
        button_text = f"👷 {worker['name']} - {worker['total']:,.0f} դրամ ({worker['count']})"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"worker_payments_{worker['name']}"
        )])

    # Кнопки пагинации
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"payments_workers_page_{page-1}"))
    if total_pages > 1:
        pagination_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("➡️", callback_data=f"payments_workers_page_{page+1}"))

    if pagination_buttons:
        keyboard.append(pagination_buttons)

    # Кнопки для вторичных и клиентов
    keyboard.extend([
        [InlineKeyboardButton("👁 Երկրորդային", callback_data="payments_secondary_list")],
        [InlineKeyboardButton("📥 Ստացած (Կլիենտներ)", callback_data="payments_clients_list")],
        [InlineKeyboardButton("🔙 Հետ", callback_data="back_to_menu")]
    ])

    message = (
        "💰 *Վճարումներ - Աշխատողներ*\n\n"
        f"Ընդամենը աշխատողներ: {len(workers_with_payments)}\n"
        "Ընտրեք աշխատողին՝ վճարումները դիտելու համար:"
    )

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def payments_secondary_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список вторичных пользователей"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    # Получаем страницу
    page = 0
    if query.data.startswith("payments_secondary_page_"):
        page = int(query.data.replace("payments_secondary_page_", ""))

    # Получаем вторичных пользователей
    secondary_users = get_users_by_role(UserRole.SECONDARY)

    users_with_payments = []
    for user_id_int in secondary_users:
        display_name = get_user_display_name(user_id_int)
        if display_name:
            user_payments = get_payments(user_display_name=display_name)
            total_amount = sum(p['amount'] for p in user_payments)
            users_with_payments.append({
                'name': display_name,
                'count': len(user_payments),
                'total': total_amount
            })

    users_with_payments.sort(key=lambda x: x['name'])

    if not users_with_payments:
        await query.edit_message_text(
            "📋 Երկրորդային օգտվողներ չկան:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
            ]])
        )
        return

    # Пагинация
    total_pages = (len(users_with_payments) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_users = users_with_payments[start_idx:end_idx]

    keyboard = []
    for user in current_users:
        button_text = f"👁 {user['name']} - {user['total']:,.0f} դրամ ({user['count']})"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"secondary_payments_{user['name']}"
        )])

    # Пагинация
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"payments_secondary_page_{page-1}"))
    if total_pages > 1:
        pagination_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("➡️", callback_data=f"payments_secondary_page_{page+1}"))

    if pagination_buttons:
        keyboard.append(pagination_buttons)

    keyboard.append([InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")])

    message = (
        "👁 *Երկրորդային օգտվողներ*\n\n"
        f"Ընդամենը: {len(users_with_payments)}"
    )

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def payments_clients_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список клиентов (Ստացած)"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    # Получаем страницу
    page = 0
    if query.data.startswith("payments_clients_page_"):
        page = int(query.data.replace("payments_clients_page_", ""))

    # Получаем клиентов
    client_users = get_users_by_role(UserRole.CLIENT)

    users_with_payments = []
    for user_id_int in client_users:
        display_name = get_user_display_name(user_id_int)
        if display_name:
            user_payments = get_payments(user_display_name=display_name)
            total_amount = sum(p['amount'] for p in user_payments)
            users_with_payments.append({
                'name': display_name,
                'count': len(user_payments),
                'total': total_amount
            })

    users_with_payments.sort(key=lambda x: x['name'])

    if not users_with_payments:
        await query.edit_message_text(
            "📋 Կլիենտներ չկան:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
            ]])
        )
        return

    # Пагинация
    total_pages = (len(users_with_payments) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_users = users_with_payments[start_idx:end_idx]

    keyboard = []
    for user in current_users:
        button_text = f"👤 {user['name']} - {user['total']:,.0f} դրամ ({user['count']})"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"client_payments_{user['name']}"
        )])

    # Пагинация
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"payments_clients_page_{page-1}"))
    if total_pages > 1:
        pagination_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("➡️", callback_data=f"payments_clients_page_{page+1}"))

    if pagination_buttons:
        keyboard.append(pagination_buttons)

    keyboard.append([InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")])

    message = (
        "📥 *Ստացած - Կլիենտներ*\n\n"
        f"Ընդամենը: {len(users_with_payments)}"
    )

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def user_payments_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показывает список платежей конкретного пользователя с пагинацией
    Обрабатывает callback: worker_payments_, secondary_payments_, client_payments_
    """
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    # Определяем тип пользователя и имя
    data = query.data
    if data.startswith("worker_payments_"):
        user_type = "worker"
        display_name = data.replace("worker_payments_", "").split("_page_")[0]
        back_callback = "pay_menu"
        title_emoji = "👷"
    elif data.startswith("secondary_payments_"):
        user_type = "secondary"
        display_name = data.replace("secondary_payments_", "").split("_page_")[0]
        back_callback = "payments_secondary_list"
        title_emoji = "👁"
    elif data.startswith("client_payments_"):
        user_type = "client"
        display_name = data.replace("client_payments_", "").split("_page_")[0]
        back_callback = "payments_clients_list"
        title_emoji = "👤"
    else:
        return

    # Получаем страницу
    page = 0
    if "_page_" in data:
        page = int(data.split("_page_")[1])

    # Получаем платежи пользователя
    payments = get_payments(user_display_name=display_name)

    if not payments:
        await query.edit_message_text(
            f"{title_emoji} *{display_name}*\n\nՎճարումներ չկան:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Ավելացնել", callback_data=f"add_payment_{display_name}")],
                [InlineKeyboardButton("🔙 Հետ", callback_data=back_callback)]
            ]),
            parse_mode='Markdown'
        )
        return

    # Сортируем по дате создания (новые сверху)
    payments.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    # Пагинация
    total_pages = (len(payments) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_payments = payments[start_idx:end_idx]

    # Статистика
    total_amount = sum(p['amount'] for p in payments)

    keyboard = []

    # Кнопки для каждого платежа
    for payment in current_payments:
        date_str = payment.get('date_to', '')[:10] if payment.get('date_to') else '—'
        button_text = f"{payment['amount']:,.0f} դրամ | {date_str}"
        if payment.get('comment'):
            button_text += f" | {payment['comment'][:20]}"

        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"payment_detail_{payment['id']}"
        )])

    # Пагинация
    pagination_buttons = []
    if page > 0:
        pagination_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"{user_type}_payments_{display_name}_page_{page-1}"))
    if total_pages > 1:
        pagination_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        pagination_buttons.append(InlineKeyboardButton("➡️", callback_data=f"{user_type}_payments_{display_name}_page_{page+1}"))

    if pagination_buttons:
        keyboard.append(pagination_buttons)

    # Кнопки действий
    keyboard.append([InlineKeyboardButton("➕ Ավելացնել", callback_data=f"add_payment_{display_name}")])
    keyboard.append([InlineKeyboardButton("📊 Ստանալ Սահմանային Հաշվետվություն", callback_data=f"get_summary_report_{display_name}")])
    keyboard.append([InlineKeyboardButton("🔙 Հետ", callback_data=back_callback)])

    # Сохраняем контекст для возврата
    context.user_data['payment_list_context'] = {
        'user_type': user_type,
        'display_name': display_name,
        'page': page
    }

    message = (
        f"{title_emoji} *{display_name}*\n\n"
        f"💵 Ընդամենը: {total_amount:,.0f} դրամ\n"
        f"📊 Վճարումներ: {len(payments)}\n\n"
        "Ընտրեք վճարումը՝ մանրամասները տեսնելու համար:"
    )

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def payment_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает детали платежа с кнопками редактирования/удаления"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    try:
        payment_id = int(query.data.replace("payment_detail_", ""))
    except ValueError:
        logger.error(f"Неверный формат callback_data: {query.data}")
        await query.edit_message_text("❌ Սխալ տվյալներ:")
        return

    # Получаем платеж из БД
    all_payments = get_payments()
    payment = next((p for p in all_payments if p['id'] == payment_id), None)

    if not payment:
        logger.warning(f"Платеж #{payment_id} не найден в БД (всего платежей: {len(all_payments)})")

        # Получаем контекст для возврата
        payment_context = context.user_data.get('payment_list_context')
        back_button = "pay_menu"
        if payment_context:
            user_type = payment_context['user_type']
            display_name = payment_context['display_name']
            page = payment_context['page']
            back_button = f"{user_type}_payments_{display_name}_page_{page}"

        await query.edit_message_text(
            f"❌ Վճարումը #{payment_id} չի գտնվել:\n\n"
            f"Հնարավոր է այն արդեն ջնջվել է:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data=back_button)
            ]])
        )
        return

    # Формируем сообщение с деталями
    message = (
        f"💰 *Վճարման մանրամասները*\n\n"
        f"🆔 ID: `{payment['id']}`\n"
        f"👤 Օգտվող: *{payment['user_display_name']}*\n"
        f"💵 Գումար: *{payment['amount']:,.0f} դրամ*\n"
        f"📅 Ստեղծվել է: {payment['created_at']}\n"
    )

    if payment.get('date_from'):
        message += f"📆 Սկիզբ: {payment['date_from']}\n"
    if payment.get('date_to'):
        message += f"📆 Ավարտ: {payment['date_to']}\n"
    if payment.get('comment'):
        message += f"💬 Մեկնաբանություն: {payment['comment']}\n"

    # Сохраняем ID платежа для редактирования
    context.user_data['editing_payment_id'] = payment_id

    # Кнопки управления
    keyboard = [
        [InlineKeyboardButton("✏️ Խմբագրել գումարը", callback_data=f"payment_edit_amount_{payment_id}")],
        [InlineKeyboardButton("📝 Խմբագրել մեկնաբանությունը", callback_data=f"payment_edit_comment_{payment_id}")],
        [InlineKeyboardButton("🗑 Ջնջել վճարումը", callback_data=f"payment_delete_confirm_{payment_id}")],
    ]

    # Кнопка назад в список платежей пользователя
    payment_context = context.user_data.get('payment_list_context')
    if payment_context:
        user_type = payment_context['user_type']
        display_name = payment_context['display_name']
        page = payment_context['page']
        keyboard.append([InlineKeyboardButton(
            "🔙 Հետ ցանկին",
            callback_data=f"{user_type}_payments_{display_name}_page_{page}"
        )])
    else:
        keyboard.append([InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")])

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def start_edit_payment_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает редактирование суммы платежа"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    try:
        payment_id = int(query.data.replace("payment_edit_amount_", ""))
    except ValueError:
        logger.error(f"Неверный формат callback для редактирования: {query.data}")
        await query.edit_message_text("❌ Սխալ տվյալներ:")
        return ConversationHandler.END

    # Проверяем, существует ли платеж
    all_payments = get_payments()
    payment = next((p for p in all_payments if p['id'] == payment_id), None)

    if not payment:
        logger.warning(f"Попытка редактировать несуществующий платеж #{payment_id}")
        await query.edit_message_text(
            f"❌ Վճարումը #{payment_id} չի գտնվել:\n\n"
            "Հնարավոր է այն արդեն ջնջվել է:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
            ]])
        )
        return ConversationHandler.END

    context.user_data['editing_payment_id'] = payment_id
    logger.info(f"Начато редактирование суммы платежа #{payment_id}")

    await query.edit_message_text(
        f"✏️ *Խմբագրել գումարը*\n\n"
        f"Վճարում #{payment_id}\n"
        f"Ընթացիկ գումար: *{payment['amount']:,.0f} դրամ*\n\n"
        f"Մուտքագրեք նոր գումարը (միայն թիվ):",
        parse_mode='Markdown'
    )

    return EDIT_AMOUNT


async def receive_new_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает новую сумму и обновляет платеж"""
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("⛔ Դուք մուտք չունեք այս գործառույթին:")
        return ConversationHandler.END

    try:
        new_amount = float(update.message.text.strip())
        payment_id = context.user_data.get('editing_payment_id')

        if not payment_id:
            await update.message.reply_text("❌ Սխալ: վճարման ID-ն չի գտնվել:")
            return ConversationHandler.END

        # Обновляем платеж
        success = update_payment(payment_id, amount=new_amount)

        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except:
            pass

        if success:
            message = (
                f"✅ *Գումարը փոփոխվել է*\n\n"
                f"Վճարում #{payment_id}\n"
                f"Նոր գումար: *{new_amount:,.0f} դրամ*"
            )
        else:
            message = f"❌ Չհաջողվեց փոփոխել վճարում #{payment_id}"

        await update.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Վերադառնալ", callback_data=f"payment_detail_{payment_id}")
            ]]),
            parse_mode='Markdown'
        )

        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            "❌ Սխալ ֆորմատ: Մուտքագրեք միայն թիվ:\n\n"
            "Օրինակ: 50000"
        )
        return EDIT_AMOUNT


async def start_edit_payment_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинает редактирование комментария платежа"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return ConversationHandler.END

    await query.answer()

    try:
        payment_id = int(query.data.replace("payment_edit_comment_", ""))
    except ValueError:
        logger.error(f"Неверный формат callback для редактирования комментария: {query.data}")
        await query.edit_message_text("❌ Սխալ տվյալներ:")
        return ConversationHandler.END

    # Проверяем, существует ли платеж
    all_payments = get_payments()
    payment = next((p for p in all_payments if p['id'] == payment_id), None)

    if not payment:
        logger.warning(f"Попытка редактировать комментарий несуществующего платежа #{payment_id}")
        await query.edit_message_text(
            f"❌ Վճարումը #{payment_id} չի գտնվել:\n\n"
            "Հնարավոր է այն արդեն ջնջվել է:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
            ]])
        )
        return ConversationHandler.END

    context.user_data['editing_payment_id'] = payment_id
    logger.info(f"Начато редактирование комментария платежа #{payment_id}")

    current_comment = payment.get('comment', '(չկա)')

    await query.edit_message_text(
        f"📝 *Խմբագրել մեկնաբանությունը*\n\n"
        f"Վճարում #{payment_id}\n"
        f"Ընթացիկ մեկնաբանություն: _{current_comment}_\n\n"
        f"Մուտքագրեք նոր մեկնաբանություն:",
        parse_mode='Markdown'
    )

    return EDIT_COMMENT


async def receive_new_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получает новый комментарий и обновляет платеж"""
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await update.message.reply_text("⛔ Դուք մուտք չունեք այս գործառույթին:")
        return ConversationHandler.END

    new_comment = update.message.text.strip()
    payment_id = context.user_data.get('editing_payment_id')

    if not payment_id:
        await update.message.reply_text("❌ Սխալ: վճարման ID-ն չի գտնվել:")
        return ConversationHandler.END

    # Обновляем платеж
    success = update_payment(payment_id, comment=new_comment)

    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except:
        pass

    if success:
        message = (
            f"✅ *Մեկնաբանությունը փոփոխվել է*\n\n"
            f"Վճարում #{payment_id}\n"
            f"Նոր մեկնաբանություն: {new_comment}"
        )
    else:
        message = f"❌ Չհաջողվեց փոփոխել վճարում #{payment_id}"

    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Վերադառնալ", callback_data=f"payment_detail_{payment_id}")
        ]]),
        parse_mode='Markdown'
    )

    return ConversationHandler.END


async def confirm_delete_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждает удаление платежа"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    payment_id = int(query.data.replace("payment_delete_confirm_", ""))

    # Получаем платеж для отображения информации
    all_payments = get_payments()
    payment = next((p for p in all_payments if p['id'] == payment_id), None)

    if not payment:
        await query.edit_message_text(
            "❌ Վճարումը չի գտնվել:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
            ]])
        )
        return

    keyboard = [
        [InlineKeyboardButton("✅ Այո, ջնջել", callback_data=f"payment_delete_execute_{payment_id}")],
        [InlineKeyboardButton("❌ Ոչ, չեղարկել", callback_data=f"payment_detail_{payment_id}")]
    ]

    message = (
        f"⚠️ *Հաստատել ջնջումը*\n\n"
        f"Վճարում #{payment_id}\n"
        f"👤 {payment['user_display_name']}\n"
        f"💵 {payment['amount']:,.0f} դրամ\n\n"
        f"❗️ Այս գործողությունը չի կարող հետարկվել:"
    )

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def execute_delete_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выполняет удаление платежа"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    payment_id = int(query.data.replace("payment_delete_execute_", ""))

    # Получаем информацию о платеже перед удалением
    all_payments = get_payments()
    payment = next((p for p in all_payments if p['id'] == payment_id), None)

    # Удаляем платеж
    success = delete_payment(payment_id)

    if success:
        await query.answer("✅ Վճարումը ջնջված է", show_alert=True)
        message = (
            f"✅ *Վճարումը ջնջված է*\n\n"
            f"Վճարում #{payment_id} հաջողությամբ ջնջվել է ՏԲ-ից և Google Sheets-ից:"
        )
    else:
        await query.answer("❌ Սխալ ջնջման ժամանակ", show_alert=True)
        message = f"❌ Չհաջողվեց ջնջել վճարում #{payment_id}"

    # Возвращаемся к списку платежей пользователя
    payment_context = context.user_data.get('payment_list_context')
    if payment_context and payment:
        user_type = payment_context['user_type']
        display_name = payment['user_display_name']
        page = payment_context['page']
        back_button = InlineKeyboardButton(
            "🔙 Վերադառնալ ցանկին",
            callback_data=f"{user_type}_payments_{display_name}_page_{page}"
        )
    else:
        back_button = InlineKeyboardButton("🔙 Վերադառնալ", callback_data="pay_menu")

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup([[back_button]]),
        parse_mode='Markdown'
    )


async def cancel_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отменяет редактирование"""
    payment_id = context.user_data.get('editing_payment_id')

    if payment_id:
        await update.message.reply_text(
            "❌ Խմբագրումը չեղարկվեց:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Վերադառնալ", callback_data=f"payment_detail_{payment_id}")
            ]])
        )
    else:
        await update.message.reply_text(
            "❌ Խմբագրումը չեղարկվեց:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Գլխավոր մենյու", callback_data="back_to_menu")
            ]])
        )

    return ConversationHandler.END


async def send_payments_only_report(update: Update, context: ContextTypes.DEFAULT_TYPE, display_name: str):
    """
    Отправляет Excel-отчет только по платежам (без records)
    Используется когда у пользователя нет расходов, но есть платежи
    """
    import pandas as pd
    from io import BytesIO
    from datetime import datetime

    try:
        # Получаем все платежи пользователя
        payments = get_payments(user_display_name=display_name)

        if not payments:
            await update.callback_query.edit_message_text(
                f"📊 {display_name}-ի համար վճարումներ չկան:",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
                ]])
            )
            return

        # Формируем DataFrame из платежей
        # get_payments() возвращает словари с ключами: id, user_display_name, spreadsheet_id,
        # sheet_name, amount, date_from, date_to, comment, created_at
        df_payments = pd.DataFrame(payments)

        # Переименовываем колонки для отображения
        df_payments = df_payments.rename(columns={
            'id': 'ID',
            'amount': 'Գումար',
            'date_from': 'Սկզբնական ամսաթիվ',
            'date_to': 'Վերջնական ամսաթիվ',
            'comment': 'Մեկնաբանություն',
            'created_at': 'Ստեղծման ամսաթիվ',
            'user_display_name': 'Օգտատեր',
            'spreadsheet_id': 'Աղյուսակի ID',
            'sheet_name': 'Թերթիկ'
        })

        # Выбираем только нужные колонки для отображения
        columns_to_show = ['ID', 'Գումար', 'Սկզբնական ամսաթիվ', 'Վերջնական ամսաթիվ', 'Մեկնաբանություն', 'Ստեղծման ամսաթիվ']
        df_payments = df_payments[columns_to_show]

        # Подсчитываем итоги
        total_paid = df_payments['Գումար'].sum()

        # Создаем сводку
        summary_data = [{
            'Ընդհանուր վճարումներ': len(payments),
            'Ընդհանուր գումար': total_paid
        }]
        df_summary = pd.DataFrame(summary_data)

        # Создаем Excel файл
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name='Ամփոփ', index=False)
            df_payments.to_excel(writer, sheet_name='Վճարումներ', index=False)

        output.seek(0)

        # Отправляем файл
        await update.callback_query.message.reply_document(
            document=output,
            filename=f"{display_name}_վճարումներ_հաշվետվություն.xlsx",
            caption=(
                f"📊 <b>Վճարումների հաշվետվություն {display_name}-ի համար</b>\n\n"
                f"💵 Ընդհանուր վճարումներ: {len(payments)}\n"
                f"💰 Ընդհանուր գումար: {total_paid:,.2f} դրամ\n\n"
                f"ℹ️ Ծախսերի գրառումներ չեն գտնվել:"
            ),
            parse_mode="HTML"
        )

        # Кнопка для возврата
        await update.callback_query.edit_message_text(
            f"✅ Հաշվետվությունը ուղարկված է {display_name}-ի համար",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
            ]])
        )

    except Exception as e:
        logger.error(f"Ошибка создания отчета по платежам для {display_name}: {e}")
        await update.callback_query.edit_message_text(
            f"❌ Սխալ հաշվետվության ստեղծման ժամանակ: {e}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
            ]])
        )


async def get_summary_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Формирует сводный отчет по платежам пользователя"""
    query = update.callback_query
    user_id = update.effective_user.id

    if not is_admin(user_id):
        await query.answer("⛔ Դուք մուտք չունեք այս գործառույթին:", show_alert=True)
        return

    await query.answer()

    # Извлекаем display_name из callback
    display_name = query.data.replace("get_summary_report_", "")

    # Определяем роль пользователя по display_name
    role = get_role_by_display_name(display_name)

    # Для WORKER пытаемся использовать полный отчет с records
    if role == UserRole.WORKER:
        from .payment_handlers import send_payment_report
        from ...database.database_manager import get_all_records

        # Проверяем, есть ли records у этого пользователя
        db_records = get_all_records()
        has_records = any(
            record.get('supplier', '').strip().lower() == display_name.lower()
            and record.get('amount', 0) > 0
            for record in db_records
        )

        if has_records:
            # Есть records - отправляем полный отчет
            await send_payment_report(update, context, display_name)
        else:
            # Нет records - отправляем только платежи
            await send_payments_only_report(update, context, display_name)
        return

    # Получаем все платежи пользователя
    payments = get_payments(user_display_name=display_name)

    if not payments:
        await query.edit_message_text(
            f"📊 *Սահմանային հաշվետվություն*\n\n"
            f"👤 {display_name}\n\n"
            f"Վճարումներ չկան:",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 Հետ", callback_data="pay_menu")
            ]]),
            parse_mode='Markdown'
        )
        return

    # Группируем платежи по месяцам
    from collections import defaultdict
    from datetime import datetime

    monthly_stats = defaultdict(lambda: {'count': 0, 'total': 0, 'payments': []})

    for payment in payments:
        # Парсим дату создания
        try:
            created_at = payment.get('created_at', '')
            if created_at:
                date_obj = datetime.strptime(created_at[:10], '%Y-%m-%d')
                month_key = date_obj.strftime('%Y-%m')  # 2025-11
            else:
                month_key = 'Неизвестно'
        except:
            month_key = 'Неизвестно'

        monthly_stats[month_key]['count'] += 1
        monthly_stats[month_key]['total'] += payment.get('amount', 0)
        monthly_stats[month_key]['payments'].append(payment)

    # Общая статистика
    total_amount = sum(p['amount'] for p in payments)
    total_count = len(payments)

    # Формируем сообщение
    message = (
        f"📊 *Սահմանային հաշվետվություն*\n\n"
        f"👤 *{display_name}*\n\n"
        f"📈 *Ընդհանուր:*\n"
        f"   • Վճարումներ: {total_count}\n"
        f"   • Ընդամենը: {total_amount:,.0f} դրամ\n"
        f"   • Միջին: {total_amount/total_count:,.0f} դրամ\n\n"
    )

    # Добавляем статистику по месяцам
    if len(monthly_stats) > 0:
        message += "📅 *Ըստ ամիսների:*\n"
        # Сортируем по месяцам (новые сверху)
        sorted_months = sorted(monthly_stats.keys(), reverse=True)

        for month in sorted_months[:6]:  # Показываем последние 6 месяцев
            stats = monthly_stats[month]
            message += (
                f"   • {month}: {stats['count']} վճ. → {stats['total']:,.0f} դրամ\n"
            )

    # Получаем контекст для кнопки возврата
    payment_context = context.user_data.get('payment_list_context')
    if payment_context:
        user_type = payment_context['user_type']
        page = payment_context['page']
        back_callback = f"{user_type}_payments_{display_name}_page_{page}"
    else:
        back_callback = "pay_menu"

    keyboard = [
        [InlineKeyboardButton("🔙 Հետ ցանկին", callback_data=back_callback)]
    ]

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
