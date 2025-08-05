"""
Обработчики платежей
"""
import logging
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ...config.settings import ADMIN_IDS
import os
from ...utils.config_utils import load_users, get_user_settings, send_to_log_chat
from ...database.database_manager import add_payment, get_payments, get_all_records
from ...utils.payment_utils import (
    normalize_date, merge_payment_intervals, get_user_id_by_display_name, send_message_to_user
)
from ...utils.date_utils import safe_parse_date_or_none
from ..keyboards.inline_keyboards import create_main_menu
from ..handlers.translation_handlers import _

logger = logging.getLogger(__name__)

# --- Новая команда администратора для отправки файлов из папки data ---
from telegram.constants import ChatAction

async def send_data_files_to_admin(update: Update, context: CallbackContext):
    """Команда администратора: отправляет все файлы из папки data админу"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Մուտքն արգելված է")
        return

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
    if not os.path.exists(data_dir):
        await update.message.reply_text("❌ data պանակը չի գտնվել:")
        return

    files = [f for f in os.listdir(data_dir) if os.path.isfile(os.path.join(data_dir, f))]
    if not files:
        await update.message.reply_text("❌ data պանակում ֆայլեր չկան:")
        return

    await update.message.reply_text(f"📂 Ուղարկում եմ {len(files)} ֆայլ(եր) data պանակից:")
    for fname in files:
        fpath = os.path.join(data_dir, fname)
        try:
            await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.UPLOAD_DOCUMENT)
            with open(fpath, 'rb') as f:
                await context.bot.send_document(chat_id=user_id, document=f, filename=fname)
        except Exception as e:
            logger.error(f"Ошибка отправки файла {fname}: {e}")
            await update.message.reply_text(f"❌ Սխալ {fname} ֆայլի ուղարկման ժամանակ: {e}")

# Состояния для ConversationHandler платежей
from ..states.conversation_states import (
    PAYMENT_AMOUNT, PAYMENT_PERIOD, PAYMENT_COMMENT
)


async def pay_menu_handler(update: Update, context: CallbackContext):
    """Обработчик меню платежей"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    # Меню работников
    users = load_users()
    keyboard = []
    for uid, udata in users.items():
        if udata.get('display_name'):
            keyboard.append([InlineKeyboardButton(
                udata['display_name'], 
                callback_data=f"pay_user_{udata['display_name']}"
            )])
    keyboard.append([InlineKeyboardButton("⬅️ Հետ", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        "👥 Ընտրեք աշխատակցին:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def pay_user_handler(update: Update, context: CallbackContext):
    """Обработчик выбора пользователя для платежа"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return
    
    display_name = query.data.replace("pay_user_", "")
    keyboard = [
        [InlineKeyboardButton("➕ Ավելացնել վճարում", callback_data=f"add_payment_{display_name}")],
        [InlineKeyboardButton("📊 Ստանալ սահմանի հաշվետվություն", callback_data=f"get_payment_report_{display_name}")],
        [InlineKeyboardButton("⬅️ Հետ", callback_data="pay_menu")]
    ]
    
    await query.edit_message_text(
        f"💰 Ընտրեք գործողությունը {display_name}-ի համար:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_add_payment(update: Update, context: CallbackContext):
    """Начинает процесс добавления платежа"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer("❌ Մուտքն արգելված է")
        return ConversationHandler.END
    
    display_name = query.data.replace("add_payment_", "")
    context.user_data['pay_user'] = display_name
    context.user_data['messages_to_delete'] = []
    
    msg = await query.edit_message_text(
        f"💰 Ավելացնել վճարում {display_name}-ի համար\n\n"
        f"💵 Մուտքագրեք վճարման գումարը:"
    )
    context.user_data['last_bot_message_id'] = msg.message_id
    
    return PAYMENT_AMOUNT

async def get_payment_amount(update: Update, context: CallbackContext):
    """Получает сумму платежа"""
    try:
        amount = float(update.message.text.strip())
        
        # Удаляем все сообщения, которые нужно удалить
        ids_to_delete = context.user_data.get('messages_to_delete', [])
        for msg_id in ids_to_delete:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
            except Exception:
                pass
        context.user_data['messages_to_delete'] = []
        
        # Удаляем сообщение пользователя
        try:
            await update.message.delete()
        except Exception:
            pass
        
        # Удаляем последнее сообщение бота
        last_bot_msg_id = context.user_data.get('last_bot_message_id')
        if last_bot_msg_id:
            try:
                await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
            except Exception:
                pass
        
        context.user_data['pay_amount'] = amount
        
        curr_date = datetime.now().strftime('%Y-%m-%d')
        context.user_data['pay_date_from'] = curr_date
        context.user_data['pay_date_to'] = curr_date
        
        msg = await update.effective_chat.send_message(
            "📝 Մուտքագրեք մեկնաբանություն (կամ ուղարկեք + բացակայող մեկնաբանության համար):"
        )
        context.user_data['last_bot_message_id'] = msg.message_id
        
        return PAYMENT_COMMENT
        
    except ValueError:
        err_msg = await update.message.reply_text("❌ Սխալ գումար: Մուտքագրեք թիվ:")
        context.user_data.setdefault('messages_to_delete', []).extend([
            err_msg.message_id,
            update.message.message_id
        ])
        return PAYMENT_AMOUNT

async def get_payment_period(update: Update, context: CallbackContext):
    """Получает период платежа"""
    curr_date = datetime.now().strftime('%Y-%m-%d')
    period = update.message.text.strip()
    
    if period == "+":
        date_from, date_to = None, None
    else:
        parts = period.split()
        date_from = parts[0] if len(parts) > 0 else None
        date_to = parts[1] if len(parts) > 1 else None
        
    if date_from == "+":
        date_from = curr_date
    if date_to == "+":
        date_to = curr_date
        
    def check_is_date(date_str):
        try:
            pd.to_datetime(date_str, format='%Y-%m-%d', errors='raise')
            return True
        except ValueError:
            return False
    
    if date_from and not check_is_date(date_from):
        err_msg = await update.message.reply_text("❌ Սխալ ամսաթիվ: Մուտքագրեք ամսաթիվը ձևաչափով 2024-01-01:")
        context.user_data.setdefault('messages_to_delete', []).extend([
            err_msg.message_id,
            update.message.message_id
        ])
        return PAYMENT_PERIOD
        
    elif date_to and not check_is_date(date_to):
        err_msg = await update.message.reply_text("❌ Սխալ ամսաթիվ: Մուտքագրեք ամսաթիվը ձևաչափով 2024-01-01:")
        context.user_data.setdefault('messages_to_delete', []).extend([
            err_msg.message_id,
            update.message.message_id
        ])
        return PAYMENT_PERIOD
        
    if date_from and date_to and pd.to_datetime(date_from) > pd.to_datetime(date_to):
        date_from, date_to = date_to, date_from
    
    # Удаляем все сообщения, которые нужно удалить
    ids_to_delete = context.user_data.get('messages_to_delete', [])
    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception:
            pass
    context.user_data['messages_to_delete'] = []
    
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception:
        pass
    
    # Удаляем последнее сообщение бота
    last_bot_msg_id = context.user_data.get('last_bot_message_id')
    if last_bot_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
        except Exception:
            pass
        
    context.user_data['pay_date_from'] = date_from
    context.user_data['pay_date_to'] = date_to
    
    msg = await update.effective_chat.send_message("📝 Մուտքագրեք մեկնաբանություն (կամ ուղարկեք +):")
    context.user_data['last_bot_message_id'] = msg.message_id
    return PAYMENT_COMMENT

async def get_payment_comment(update: Update, context: CallbackContext):
    """Получает комментарий к платежу и сохраняет его"""
    user_id = update.effective_user.id
    comment = update.message.text.strip()
    
    if comment == "+":
        comment = ""
    
    # Удаляем все сообщения, которые нужно удалить
    ids_to_delete = context.user_data.get('messages_to_delete', [])
    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception:
            pass
    context.user_data['messages_to_delete'] = []
    
    # Удаляем сообщение пользователя
    try:
        await update.message.delete()
    except Exception:
        pass
    
    # Удаляем последнее сообщение бота
    last_bot_msg_id = context.user_data.get('last_bot_message_id')
    if last_bot_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
        except Exception:
            pass
        
    display_name = context.user_data['pay_user']
    amount = context.user_data['pay_amount']
    date_from = context.user_data['pay_date_from']
    date_to = context.user_data['pay_date_to']
    
    user_settings = get_user_settings(user_id)
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    sheet_name = user_settings.get('active_sheet_name')
    
    # Добавляем платеж в базу данных
    success = add_payment(display_name, spreadsheet_id, sheet_name, amount, date_from, date_to, comment)
    
    if success:
        # Получаем ID получателя
        recipient_id = await get_user_id_by_display_name(display_name)
        sender_id = update.effective_user.id
        users = load_users()
        sender_name = users.get(str(sender_id), {}).get('display_name', 'Админ')
        
        # Формируем сообщение о платеже
        payment_text = (
            f"💰 <b>Վճարման տեղեկություն</b>\n\n"
            f"📊 Փոխանցող: {sender_name}\n"
            f"👤 Ստացող: {display_name}\n"
            f"🗓 Ամսաթիվ: {date_from}\n"
            f"💵 Գումար: {amount:,.2f} դրամ\n"
            f"📝 Նկարագրություն: {comment or 'Առանց մեկնաբանության'}\n"
        )
        
        keyboard = [[InlineKeyboardButton("✅ Վերադառնալ աշխատակցին", callback_data=f"pay_user_{display_name}")]]
        
        await update.effective_chat.send_message(
            "✅ Վճարումը հաջողությամբ ավելացված է:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Отправляем уведомление получателю
        if recipient_id:
            await send_message_to_user(context, recipient_id, payment_text)
            await send_message_to_user(context, sender_id, payment_text)
            
        # Логируем в лог-чат
        await send_to_log_chat(context, f"Ավելացված է վճարում: {display_name} - {amount:,.2f} դրամ")
        
    else:
        await update.effective_chat.send_message("❌ Սխալ վճարումն ավելացնելիս:")
    
    # Очищаем данные пользователя
    context.user_data.clear()
    return ConversationHandler.END

async def send_payment_report(update: Update, context: CallbackContext, display_name: str):
    """
    Формирует и отправляет Excel-отчет с разбивкой по промежуткам выплат для заданного работника
    """
    try:
        # Получаем все записи из БД и фильтруем по пользователю
        db_records = get_all_records()
        filtered_records = []

        for record in db_records:
            if record['amount'] == 0:
                continue

            # Очистка и фильтрация по поставщику (все варианты)
            supplier = record['supplier'].strip() if 'supplier' in record else ""
            if supplier.lower() != display_name.lower():
                continue

            # Нормализуем дату
            try:
                record['date'] = normalize_date(record['date'])
            except Exception as e:
                logger.error(f"Ошибка нормализации даты для записи {record}: {e}")
                continue

            # Применяем фильтры по датам в зависимости от пользователя
            try:
                # Безопасное парсинг даты с поддержкой разных форматов
                record_date = safe_parse_date_or_none(record['date'])
                
                if record_date is None:
                    logger.warning(f"Не удалось распарсить дату '{record['date']}' для записи от {supplier}, пропускаем")
                    continue
                    
                record['date'] = record_date
            except Exception as e:
                logger.error(f"Ошибка парсинга даты '{record.get('date')}' для записи от {supplier}: {e}, пропускаем")
                continue
            if record['supplier'] == "Նարեկ":
                start_date = datetime.strptime("2025-05-10", '%Y-%m-%d').date()
            else:
                start_date = datetime.strptime("2024-12-05", '%Y-%m-%d').date()
            if record_date >= start_date:
                filtered_records.append(record)
            else:
                logger.info(f"Запись от {supplier} (дата: {record_date}) не проходит фильтрацию по дате")

        if not filtered_records:
            user_id = update.effective_user.id
            back_button = InlineKeyboardButton("⬅️ Հետ", callback_data=f"pay_user_{display_name}" if user_id in ADMIN_IDS else "back_to_menu")
            await update.callback_query.edit_message_text(
                f"📊 {display_name}-ի համար գրառումներ չեն գտնվել:",
                reply_markup=InlineKeyboardMarkup([[back_button]])
            )
            return

        # Группируем по листам
        sheets = {}
        for rec in filtered_records:
            spreadsheet_id = rec.get('spreadsheet_id', '—')
            sheet_name = rec.get('sheet_name', '—')
            key = (spreadsheet_id, sheet_name)
            sheets.setdefault(key, []).append(rec)

        # Формируем и отправляем отчеты по каждому листу отдельно
        from openpyxl import Workbook
        from io import BytesIO
        import pandas as pd

        all_summaries = []
        for (spreadsheet_id, sheet_name), records in sheets.items():
            df = pd.DataFrame(records)
            if not df.empty:
                df['date'] = pd.to_datetime(df['date'], format='%d.%m.%Y', errors='coerce')
            else:
                df['date'] = pd.to_datetime([])

            df_amount_total = df['amount'].sum() if not df.empty else 0
            total_row = ['—'] * len(df.columns)

            if 'amount' in df.columns:
                amount_idx = df.columns.get_loc('amount')
                total_row[amount_idx] = df_amount_total
            df.loc["Իտոգ"] = total_row

            payments = get_payments(display_name, spreadsheet_id, sheet_name)
            total_paid_sheet = 0
            df_pay_sheet = pd.DataFrame()

            if payments:
                df_pay_raw_sheet = pd.DataFrame(payments, columns=['amount', 'date_from', 'date_to', 'comment', 'created_at'])
                df_pay_raw_sheet['amount'] = pd.to_numeric(df_pay_raw_sheet['amount'], errors='coerce').fillna(0)
                df_pay_raw_sheet['date_from'] = pd.to_datetime(df_pay_raw_sheet['date_from'], format='%d.%m.%Y', errors='coerce')
                df_pay_raw_sheet['date_to'] = pd.to_datetime(df_pay_raw_sheet['date_to'], format='%d.%m.%Y', errors='coerce')
                df_pay_sheet = merge_payment_intervals(df_pay_raw_sheet[['amount', 'date_from', 'date_to']])
                total_paid_sheet = df_pay_raw_sheet['amount'].sum()

            total_left_sheet = df_amount_total - total_paid_sheet
            all_summaries.append({
                'Աղյուսակ': spreadsheet_id,
                'Թեթր': sheet_name,
                'Ծախս': df_amount_total,
                "Վճար": total_paid_sheet,  
                'Մնացորդ': total_left_sheet
            })

            summary = pd.DataFrame([{
                'Ընդհանուր ծախս': df_amount_total,
                'Ընդհանուր վճար': total_paid_sheet,
                'Մնացորդ': total_left_sheet
            }])

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Ծախսեր', index=False)
                summary.to_excel(writer, sheet_name='Ամփոփ', index=False)
                if not df_pay_sheet.empty:
                    df_pay_sheet.to_excel(writer, sheet_name='Վճարումներ', index=False)
                else:
                    empty_payments = pd.DataFrame(columns=['amount', 'date_from', 'date_to'])
                    empty_payments.to_excel(writer, sheet_name='Վճարումներ', index=False)
            output.seek(0)

            await update.callback_query.message.reply_document(
                document=output,
                filename=f"{display_name}_{sheet_name}_report.xlsx",
                caption=(
                    f"📋 Թերթ: {sheet_name}\n"
                    f"💰 Ընդհանուր ծախս: {df_amount_total:,.2f} դրամ\n"
                    f"💵 Ընդհանուր վճար: {total_paid_sheet:,.2f} դրամ\n"
                    f"💸 Մնացորդ: {total_left_sheet:,.2f} դրամ"
                )
            )

        # Итоговая таблица по всем листам
        if all_summaries:
            df_total = pd.DataFrame(all_summaries)
            total_expenses_all = df_total['Ծախս'].sum()
            total_paid_all = df_total['Վճար'].sum()
            total_left_all = total_expenses_all - total_paid_all
            total_row = ['—'] * len(df_total.columns)

            if 'Ծախս' in df_total.columns:
                total_row[df_total.columns.get_loc('Ծախս')] = total_expenses_all
            if 'Վճար' in df_total.columns:
                total_row[df_total.columns.get_loc('Վճար')] = total_paid_all
            if 'Մնացորդ' in df_total.columns:
                total_row[df_total.columns.get_loc('Մնացորդ')] = total_left_all
            df_total.loc['Իտոգ'] = total_row

            all_payments = []
            for (spreadsheet_id, sheet_name), records in sheets.items():
                payments = get_payments(display_name, spreadsheet_id, sheet_name)
                if payments:
                    for payment in payments:
                        payment_data = list(payment) + [spreadsheet_id, sheet_name]
                        all_payments.append(payment_data)

            output_total = BytesIO()
            with pd.ExcelWriter(output_total, engine='openpyxl') as writer:
                df_total.to_excel(writer, sheet_name='Ամփոփ', index=False)
                if all_payments:
                    df_all_payments = pd.DataFrame(all_payments, columns=['amount', 'date_from', 'date_to', 'comment', 'created_at', 'spreadsheet_id', 'sheet_name'])
                    df_all_payments.to_excel(writer, sheet_name='Բոլոր վճարումները', index=False)
                else:
                    empty_all_payments = pd.DataFrame(columns=['amount', 'date_from', 'date_to', 'comment', 'created_at', 'spreadsheet_id', 'sheet_name'])
                    empty_all_payments.to_excel(writer, sheet_name='Բոլոր վճարումները', index=False)

            output_total.seek(0)

            await update.callback_query.message.reply_document(
                document=output_total,
                filename=f"{display_name}_ԸՆԴՀԱՆՈՒՐ_հաշվետվություն.xlsx",
                caption=(
                    f"📊 <b>Ընդհանուր հաշվետվություն {display_name}-ի համար</b>\n\n"
                    f"💰 Ընդհանուր ծախս: {total_expenses_all:,.2f} դրամ\n"
                    f"💵 Ընդհանուր վճար: {total_paid_all:,.2f} դրամ\n"
                    f"💸 Ընդհանուր մնացորդ: {total_left_all:,.2f} դրամ\n\n"
                    f"📋 Թերթիկների քանակ: {len(sheets)}"
                ),
                parse_mode="HTML"
            )

        # Кнопка для возврата
        user_id = update.effective_user.id
        back_button = InlineKeyboardButton("⬅️ Հետ", callback_data=f"pay_user_{display_name}" if user_id in ADMIN_IDS else "back_to_menu")
        keyboard = [[back_button]]
        await update.callback_query.edit_message_text(
            f"✅ Հաշվետվությունները ուղարկված են {display_name}-ի համար",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        await send_to_log_chat(context, f"Ստեղծվել են վճարային հաշվետվություններ {display_name}-ի համար")
        
    except Exception as e:
        logger.error(f"Ошибка создания отчета для {display_name}: {e}")
        user_id = update.effective_user.id
        back_button = InlineKeyboardButton("⬅️ Հետ", callback_data=f"pay_user_{display_name}" if user_id in ADMIN_IDS else "back_to_menu")
        keyboard = [[back_button]]
        await update.callback_query.edit_message_text(
            f"❌ Հաշվետվություն ստեղծելու սխալ: {e}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def cancel_payment(update: Update, context: CallbackContext):
    """Отменяет процесс добавления платежа"""
    user_id = update.effective_user.id
    
    # Удаляем все сообщения, которые нужно удалить
    ids_to_delete = context.user_data.get('messages_to_delete', [])
    for msg_id in ids_to_delete:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=msg_id)
        except Exception:
            pass
    
    # Удаляем последнее сообщение бота
    last_bot_msg_id = context.user_data.get('last_bot_message_id')
    if last_bot_msg_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=last_bot_msg_id)
        except Exception:
            pass
    
    # Удаляем сообщение пользователя, если это текстовое сообщение
    if update.message:
        try:
            await update.message.delete()
        except Exception:
            pass
    
    context.user_data.clear()
    
    await update.effective_chat.send_message(
        "❌ Վճարման ավելացումը չեղարկված է:",
        reply_markup=create_main_menu(user_id)
    )
    
    return ConversationHandler.END
