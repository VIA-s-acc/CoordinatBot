"""
Обработчики команд администратора
"""
import json
import os

from datetime import datetime
from telegram import Update
from telegram.ext import CallbackContext

from ...config.settings import ADMIN_IDS, logger
from telegram.constants import ChatAction
from ...utils.date_utils import safe_parse_date_or_none
from ...utils.config_utils import (
    is_user_allowed, load_users, save_users, 
    load_allowed_users, add_allowed_user, remove_allowed_user,
    set_log_chat, set_report_settings, send_to_log_chat
)
from ...database.database_manager import backup_db_to_dict, get_record_from_db, add_record_to_db
from ...google_integration.sheets_manager import get_all_spreadsheets, get_worksheets_info, open_sheet_by_id
from ...google_integration.sync_manager import full_sync
from ..keyboards.inline_keyboards import create_main_menu
from .edit_handlers import get_user_id_by_name


async def send_data_files_command(update: Update, context: CallbackContext):
    """Команда для отправки всех файлов из папки data администратору"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return

    # Определяем путь к данным в зависимости от режима
    if os.environ.get('DEPLOY_MODE') == 'true':
        data_dir = '/app_data'
    else:
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data'))
    
    if not os.path.exists(data_dir):
        await update.message.reply_text(f"❌ Չի գտնված {data_dir}-ը")
        return

    files = [f for f in os.listdir(data_dir) if os.path.isfile(os.path.join(data_dir, f))]
    if not files:
        await update.message.reply_text(f"ℹ️ {data_dir}-ում ֆայլ չկա.")
        return

    await update.message.reply_text(f"📤 Ուղարկում եմ {len(files)} ֆայլ {data_dir}-ից...")
    for fname in files:
        fpath = os.path.join(data_dir, fname)
        try:
            await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.UPLOAD_DOCUMENT)
            with open(fpath, 'rb') as f:
                await context.bot.send_document(chat_id=user_id, document=f, filename=fname)
        except Exception as e:
            await update.message.reply_text(f"❌ չստացվեց {fname}: {e}")
    await update.message.reply_text("✅ բոլոր ֆայլերը ուղարկված են.")

async def set_log_command(update: Update, context: CallbackContext):
    """Команда установки лог-чата"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    chat_id = update.effective_chat.id
    set_log_chat(chat_id)
    
    await update.message.reply_text(
        f"✅ Գրանցամատյանի զրույցը սահմանված է:\n"
        f"Chat ID: <code>{chat_id}</code>\n"
        f"Բոլոր գրանցումները կուղարկվեն այս զրույց:",
        parse_mode="HTML"
    )
    await send_to_log_chat(context, f"Գրանցամատյանի զրույցը ակտիվացված է: Chat ID: {chat_id}")

async def set_report_command(update: Update, context: CallbackContext):
    """Команда для настройки отчетов в чате"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    chat_id = update.effective_chat.id
    
    # Получаем аргументы команды
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "📊 Չատում հաշվետվություններ սահմանելու համար օգտագործեք:\n"
            "<code>/set_report SPREADSHEET_ID SHEET_NAME</code>\n\n"
            "Օրինակ՝ /set_report abc12345 Չատի հաշվետվություն",
            parse_mode="HTML"
        )
        return
    
    spreadsheet_id = args[0].strip()
    sheet_name = ' '.join(args[1:]).strip()
    
    # Проверяем доступность таблицы
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        if not sheets_info:
            await update.message.reply_text("❌ Հնարավոր չէ մուտք գործել աղյուսակ: Ստուգեք ID-ն և մուտքի իրավունքները:")
            return
        
        # Проверяем существует ли лист
        sheet_exists = any(sheet['title'] == sheet_name for sheet in sheets_info)
        if not sheet_exists:
            await update.message.reply_text(
                f"❌ Թերթիկ '{sheet_name}' չի գտնվել աղյուսակում:",
                parse_mode="HTML"
            )
            return
        
        # Сохраняем настройки
        set_report_settings(chat_id, {
            'spreadsheet_id': spreadsheet_id,
            'sheet_name': sheet_name,
            'spreadsheet_title': spreadsheet_title
        })
        
        await update.message.reply_text(
            f"✅ Չատի հաշվետվությունները միացված են:\n"
            f"📊 Աղյուսակ: <b>{spreadsheet_title}</b>\n"
            f"📋 Թերթիկ: <b>{sheet_name}</b>\n\n"
            f"Այժմ բոլոր գործողությունները կգրանցվեն այս թերթիկում:",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Միացված է հաշվետվություններ չատի համար: {spreadsheet_title} > {sheet_name}")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Սխալ հաշվետվություններ միացնելիս:\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )

async def allow_user_command(update: Update, context: CallbackContext):
    """Добавляет пользователя в список разрешенных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "👥 Օգտագործողին թույլատրելու համար օգտագործեք:\n"
            "<code>/allow_user [user_id]</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        new_user_id = int(args[0])
        add_allowed_user(new_user_id)
        
        # Добавляем пользователя в users.json если его еще нет
        users = load_users()
        user_id_str = str(new_user_id)
        if user_id_str not in users:
            users[user_id_str] = {
                'active_sheet_name': None,
                'name': f'User {new_user_id}',
                'display_name': None
            }
            save_users(users)
        
        await update.message.reply_text(
            f"✅ Օգտագործող {new_user_id} ավելացված է թույլատրված ցանկում:",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Ավելացված է նոր օգտագործող: {new_user_id}")
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ օգտագործողի ID ձևաչափ:")

async def disallow_user_command(update: Update, context: CallbackContext):
    """Удаляет пользователя из списка разрешенных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text(
            "👥 Օգտագործողին արգելելու համար օգտագործեք:\n"
            "<code>/disallow_user [user_id]</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        target_user_id = int(args[0])
        
        # Не даем удалить админов
        if target_user_id in ADMIN_IDS:
            await update.message.reply_text("❌ Հնարավոր չէ արգելել ադմինիստրատորին:")
            return
        
        if remove_allowed_user(target_user_id):
            await update.message.reply_text(
                f"✅ Օգտագործող {target_user_id} հեռացված է թույլատրված ցանկից:",
                parse_mode="HTML"
            )
            await send_to_log_chat(context, f"Հեռացված է օգտագործող: {target_user_id}")
        else:
            await update.message.reply_text(
                f"⚠️ Օգտագործող {target_user_id} չի գտնվել թույլատրված ցանկում:",
                parse_mode="HTML"
            )
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ օգտագործողի ID ձևաչափ:")

async def allowed_users_command(update: Update, context: CallbackContext):
    """Показывает список разрешенных пользователей"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    try:
        allowed_users = load_allowed_users()
        users = load_users()
        
        if not allowed_users:
            await update.message.reply_text("📝 Թույլատրված օգտագործողներ չկան:")
            return
        
        result_text = f"👥 Թույլատրված օգտագործողներ ({len(allowed_users)}):\n\n"
        
        for i, uid in enumerate(allowed_users, 1):
            user_info = users.get(str(uid), {})
            name = user_info.get('name', f'User {uid}')
            display_name = user_info.get('display_name')
            
            result_text += f"{i}. <code>{uid}</code> - {name}"
            if display_name:
                result_text += f" ({display_name})"
            if uid in ADMIN_IDS:
                result_text += " 👨‍💼"
            result_text += "\n"
        
        await update.message.reply_text(result_text, parse_mode="HTML")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ցանկը ստանալու սխալ: {e}")

async def set_user_name_command(update: Update, context: CallbackContext):
    """Устанавливает отображаемое имя пользователя"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "👤 Օգտագործողի անուն սահմանելու համար օգտագործեք:\n"
            "<code>/set_user_name [user_id] [display_name]</code>\n\n"
            "Օրինակ: <code>/set_user_name 123456789 Արամ</code>",
            parse_mode="HTML"
        )
        return
    
    try:
        target_user_id = int(args[0])
        display_name = ' '.join(args[1:]).strip()
        
        users = load_users()
        user_id_str = str(target_user_id)
        
        if user_id_str not in users:
            users[user_id_str] = {
                'active_sheet_name': None,
                'name': f'User {target_user_id}',
                'display_name': display_name
            }
        else:
            users[user_id_str]['display_name'] = display_name
        
        save_users(users)
        
        await update.message.reply_text(
            f"✅ Օգտագործող {target_user_id}-ի անունը սահմանված է:\n"
            f"<b>{display_name}</b>",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Օգտագործողի անուն սահմանված է: {target_user_id} -> {display_name}")
        
    except ValueError:
        await update.message.reply_text("❌ Սխալ օգտագործողի ID ձևաչափ:")

async def export_command(update: Update, context: CallbackContext):
    """Команда экспорта данных"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return
    
    try:
        backup_data = backup_db_to_dict()
        
        if not backup_data:
            await update.message.reply_text("❌ Պահուստային պատճենի ստեղծման սխալ:")
            return
        
        # Создаем JSON файл
        filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=2, ensure_ascii=False)
        
        # Отправляем файл
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📤 Տվյալների բազայի պահուստային պատճեն\n"
                       f"📊 Գրառումներ: {backup_data['stats']['total_records']}\n"
                       f"💰 Ընդհանուր գումար: {backup_data['stats']['total_amount']:,.2f}\n"
                       f"📅 Ստեղծման ամսաթիվ: {backup_data['backup_date']}"
            )
        
        # Удаляем временный файл
        os.remove(filename)
        
        await send_to_log_chat(context, f"Ստեղծվել է պահուստային պատճեն: {backup_data['stats']['total_records']} գրառում")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Արտահանման սխալ: {e}")

async def sync_sheets_command(update: Update, context: CallbackContext):
    """Выполняет полную синхронизацию всех Google Sheets с БД"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return

    try:
        await update.message.reply_text("🔄 Սկսվել է լրիվ համաժամեցում բոլոր աղյուսակների հետ...")

        # Выполняем полную синхронизацию
        stats = await full_sync()

        # Формируем отчет
        result_text = (
            f"✅ Լրիվ համաժամեցումն ավարտված է:\n\n"
            f"📊 Մշակված աղյուսակներ: {stats['processed_sheets']}\n"
            f"📋 Համաժամեցված գրառումներ: {stats['synced_records']}\n"
            f"🆕 Նոր գրառումներ: {stats['new_records']}\n"
        )

        if stats['errors'] > 0:
            result_text += f"❌ Սխալներ: {stats['errors']}\n"

        await update.message.reply_text(result_text, parse_mode="HTML")

        await send_to_log_chat(context, f"Լրիվ համաժամեցում: {stats['processed_sheets']} աղյուսակ, {stats['new_records']} նոր գրառում")

    except Exception as e:
        logger.error(f"Ошибка полной синхронизации: {e}")
        await update.message.reply_text(f"❌ Սխալ լրիվ համաժամեցման ժամանակ: {e}")


def initialize_and_sync_sheets():
    import uuid

    headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
    spreadsheets = get_all_spreadsheets()

    for spreadsheet in spreadsheets:
        spreadsheet_id = spreadsheet['id']
        spreadsheet_name = spreadsheet['name']
        logger.info(f"🔄 Обработка таблицы: {spreadsheet_name} ({spreadsheet_id})")

        sheet = open_sheet_by_id(spreadsheet_id)
        if not sheet:
            logger.error(f"❌ Не удалось открыть таблицу: {spreadsheet_name}")
            continue

        for worksheet in sheet.worksheets():
            sheet_name = worksheet.title
            logger.info(f"  📋 Лист: {sheet_name}")

            try:
                rows = worksheet.get_all_records()
                new_rows = []
                last_valid_date = None
                for row in rows:
                    if all(not str(value).strip() for value in row.values()):
                        continue

                    row_id = str(row.get('ID', '')).strip()
                    if not row_id:
                        row_id = "cb-" + str(uuid.uuid4())[:8]

                    # 🗓 Обработка даты
                    raw_date = str(row.get('ամսաթիվ', '')).strip()
                    if raw_date:
                        normalized_date = raw_date.replace("․", ".").strip()
                        last_valid_date = normalized_date
                    elif last_valid_date:
                        normalized_date = last_valid_date
                    else:
                        normalized_date = ""

                    # 💰 Обработка суммы
                    raw_amount = str(row.get('Արժեք', '0'))
                    cleaned_amount = (
                        raw_amount.replace('\xa0', '')
                                  .replace('\u202f', '')
                                  .replace(' ', '')
                                  .replace(',', '.')
                                  .strip()
                    )

                    # Если cleaned_amount пуст, то присваиваем 0.0
                    if not cleaned_amount:
                        amount = 0.0
                        logger.warning(f"⚠️ Пустое значение в колонке суммы для строки {row}")
                    else:
                        try:
                            amount = float(cleaned_amount)
                        except ValueError:
                            amount = 0.0
                            logger.warning(f"⚠️ Невозможно преобразовать сумму '{raw_amount}' → 0.0")

                    # 📦 Подготовка записи
                    user_id = get_user_id_by_name(row.get('մատակարար', ''))
                    record = {
                        'id': row_id,
                        'date': normalized_date,
                        'supplier': str(row.get('մատակարար', '')).strip(),
                        'direction': str(row.get('ուղղություն', '')).strip(),
                        'description': str(row.get('ծախսի բնութագիր', '')).strip(),
                        'amount': amount,
                        'spreadsheet_id': spreadsheet_id,
                        'sheet_name': sheet_name,
                        'user_id': user_id if user_id != 0 else None
                    }

                    if not get_record_from_db(row_id):
                        success = add_record_to_db(record)
                        if success:
                            logger.info(f"    ➕ Добавлена запись в БД: {row_id}")
                        else:
                            logger.warning(f"    ⚠️ Не удалось добавить запись в БД: {row_id}")
                    new_rows.append([
                        row_id,
                        normalized_date,
                        record['supplier'],
                        record['direction'],
                        record['description'],
                        amount
                    ])

                # Обновление листа одним вызовом
                all_data = [headers] + new_rows
                worksheet.clear()
                worksheet.update(f"A1:F{len(all_data)}", all_data)

                logger.info(f"    ✅ Лист {sheet_name} пересоздан ({len(new_rows)} строк)")

            except Exception as e:
                logger.error(f"    ❌ Ошибка при обработке листа {sheet_name}: {e}")



async def initialize_sheets_command(update: Update, context: CallbackContext):
    """Команда инициализации всех Google Sheets — միայն ադմինների համար"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return

    try:
        initialize_and_sync_sheets()
        await update.message.reply_text("✅ Բոլոր աղյուսակները հաջողությամբ մշակված են, ID-ները ավելացված են և բազան համաժամացված է:")
        await send_to_log_chat(context, "✅ Կատարվել է /initialize_sheets հրամանը - բոլոր աղյուսակները թարմացված են:")
    except Exception as e:
        await update.message.reply_text(f"❌ Սխալ աղյուսակները նախապատրաստելիս: {e}")

async def set_sheet_command(update: Update, context: CallbackContext):
    """Команда для установки ID Google Spreadsheet"""
    user_id = update.effective_user.id
    if not is_user_allowed(user_id):
        return
    
    # Получаем аргументы команды
    args = context.args
    if not args:
        await update.message.reply_text(
            "📊 Google Spreadsheet սահմանելու համար օգտագործեք:\n"
            "<code>/set_sheet YOUR_SPREADSHEET_ID</code>\n\n"
            "ID-ն կարելի է գտնել աղյուսակի հղումով:\n"
            "https://docs.google.com/spreadsheets/d/<b>SPREADSHEET_ID</b>/edit",
            parse_mode="HTML"
        )
        return
    
    spreadsheet_id = args[0].strip()
    
    # Проверяем доступность таблицы
    try:
        sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
        if not sheets_info:
            await update.message.reply_text("❌ Հնարավոր չէ մուտք գործել աղյուսակ: Ստուգեք ID-ն և մուտքի իրավունքները:")
            return
        
        # ACTIVE_SPREADSHEET_ID теперь задаётся через .env, здесь только информируем
        # (функциональность изменения через бот удалена)
        
        await update.message.reply_text(
            f"✅ Google Spreadsheet միացված է:\n"
            f"📊 Անվանում: <b>{spreadsheet_title}</b>\n"
            f"🆔 ID: <code>{spreadsheet_id}</code>\n"
            f"📋 Գտնված թերթիկներ: {len(sheets_info)}\n\n"
            f"Այժմ ընտրեք թերթիկ աշխատելու համար /menu → 📋 Ընտրել թերթիկ",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Միացված է Google Spreadsheet: {spreadsheet_title} (ID: {spreadsheet_id})")
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Սխալ աղյուսակին միանալիս:\n<code>{str(e)}</code>\n\n"
            f"Համոզվեք, որ:\n"
            f"• Աղյուսակի ID-ն ճիշտ է\n"
            f"• Ծառայության հաշիվը մուտքի իրավունք ունի\n"
            f"• Credentials ֆայլը ճիշտ է",
            parse_mode="HTML"
        )

async def set_report_sheet_handler(update: Update, context: CallbackContext):
    """Обработчик для настройки листа отчетов"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Մուտքն արգելված է")
        return
    
    # Проверяем, есть ли сообщение с параметрами
    if update.message:
        text = update.message.text.strip()
        parts = text.split()
        
        if len(parts) < 3:
            await update.message.reply_text(
                "📊 Հաշվետվության կարգավորման համար օգտագործեք:\n"
                "<spreadsheet_id> <sheet_name>\n\n"
                "Օրինակ: abc12345 Հաշվետվություններ",
                parse_mode="HTML"
            )
            return
            
        spreadsheet_id = parts[1]
        sheet_name = ' '.join(parts[2:])
        
        try:
            # Проверяем доступность таблицы
            sheets_info, spreadsheet_title = get_worksheets_info(spreadsheet_id)
            if not sheets_info:
                await update.message.reply_text("❌ Հնարավոր չէ մուտք գործել աղյուսակ")
                return
                
            # Проверяем существование листа
            sheet_exists = any(sheet['title'] == sheet_name for sheet in sheets_info)
            if not sheet_exists:
                await update.message.reply_text(f"❌ Թերթիկ '{sheet_name}' չի գտնվել")
                return
            
            # Настраиваем отчеты для текущего чата
            chat_id = update.effective_chat.id
            set_report_settings(chat_id, {
                'spreadsheet_id': spreadsheet_id,
                'sheet_name': sheet_name,
                'spreadsheet_title': spreadsheet_title
            })
            
            await update.message.reply_text(
                f"✅ Հաշվետվությունները կարգավորված են:\n"
                f"📊 Աղյուսակ: <b>{spreadsheet_title}</b>\n"
                f"📋 Թերթիկ: <b>{sheet_name}</b>\n\n"
                f"Բոլոր գործողությունները կգրանցվեն այս թերթիկում:",
                parse_mode="HTML",
                reply_markup=create_main_menu(user_id)
            )
            
            await send_to_log_chat(context, f"Կարգավորված են հաշվետվություններ: {spreadsheet_title} > {sheet_name}")
            
        except Exception as e:
            await update.message.reply_text(
                f"❌ Հաշվետվությունների կարգավորման սխալ: {e}",
                reply_markup=create_main_menu(user_id)
            )
    else:
        await update.message.reply_text(
            "📊 Հաշվետվությունների կարգավորման համար օգտագործեք:\n"
            "/set_report <spreadsheet_id> <sheet_name>",
            parse_mode="HTML",
            reply_markup=create_main_menu(user_id)
        )


async def add_backup_chat_command(update: Update, context: CallbackContext):
    """
    Команда для назначения текущего чата для автоматических бэкапов
    Использование: /add_backup_chat
    """
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return

    chat_id = update.effective_chat.id

    # Сохраняем chat_id в переменную окружения через config файл
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), '.env')

    try:
        # Читаем существующий .env файл
        env_vars = {}
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()

        # Обновляем BACKUP_CHAT_ID
        env_vars['BACKUP_CHAT_ID'] = str(chat_id)

        # Записываем обратно
        with open(env_path, 'w', encoding='utf-8') as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")

        # Обновляем текущую конфигурацию в памяти
        from ...config import settings
        settings.BACKUP_CHAT_ID = chat_id

        await update.message.reply_text(
            f"✅ <b>Բեքափ չատ սահմանված է</b>\n\n"
            f"📋 Chat ID: <code>{chat_id}</code>\n"
            f"🕐 Ինտերվալ: {settings.BACKUP_INTERVAL_HOURS} ժամ\n\n"
            f"Ավտոմատ բեքափերը կուղարկվեն այս չատ:\n"
            f"• data/ պանակի բոլոր ֆայլերը\n"
            f"• Ամեն {settings.BACKUP_INTERVAL_HOURS} ժամը մեկ",
            parse_mode="HTML"
        )

        await send_to_log_chat(context, f"🔧 Բեքափ չատ սահմանված է: Chat ID: {chat_id}")

        # Отправляем тестовый бэкап
        await update.message.reply_text("📤 Ուղարկում եմ թեսթային բեքափ...")
        await send_backup_to_chat(context, chat_id, test_mode=True)

    except Exception as e:
        logger.error(f"Ошибка при установке backup chat: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Սխալ բեքափ չատ սահմանելիս:\n<code>{str(e)}</code>",
            parse_mode="HTML"
        )


async def send_backup_to_chat(context: CallbackContext, chat_id: int, test_mode: bool = False):
    """
    Отправляет файлы из папки data в указанный чат

    Args:
        context: Контекст бота
        chat_id: ID чата для отправки
        test_mode: Если True, добавляет пометку "Test"
    """
    # Определяем путь к данным в зависимости от режима
    if os.environ.get('DEPLOY_MODE') == 'true':
        data_dir = '/app_data'
    else:
        from ...config.settings import DATA_DIR
        data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data'))

    try:
        if not os.path.exists(data_dir):
            logger.error(f"Папка data не найдена: {data_dir}")
            return

        files = [f for f in os.listdir(data_dir) if os.path.isfile(os.path.join(data_dir, f))]

        if not files:
            logger.warning("В папке data нет файлов для бэкапа")
            return

        # Создаем сообщение-заголовок
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_label = " [TEST]" if test_mode else ""

        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🔄 <b>Ավտոմատ Բեքափ{test_label}-dir-{data_dir}</b>\n\n"
                f"📅 Ամսաթիվ: {timestamp}\n"
                f"📁 Ֆայլեր: {len(files)}\n"
                f"━━━━━━━━━━━━━━━"
            ),
            parse_mode="HTML"
        )

        # Отправляем файлы
        for fname in files:
            fpath = os.path.join(data_dir, fname)
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)
                with open(fpath, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=fname,
                        caption=f"📄 {fname}"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки файла {fname} в бэкап чат: {e}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Չհաջողվեց ուղարկել {fname}: {e}"
                )

        # Итоговое сообщение
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"✅ Բեքափը ավարտված է: {len(files)} ֆայլ ուղարկված է",
            parse_mode="HTML"
        )

        logger.info(f"Backup sent to chat {chat_id}: {len(files)} files")

    except Exception as e:
        logger.error(f"Ошибка при отправке бэкапа в чат {chat_id}: {e}", exc_info=True)
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Սխալ բեքափ ուղարկելիս: {e}"
            )
        except:
            pass


async def scheduled_backup_job(context: CallbackContext):
    """
    Функция для периодического автоматического бэкапа
    Вызывается по расписанию
    """
    from ...config.settings import BACKUP_CHAT_ID

    if not BACKUP_CHAT_ID:
        logger.warning("BACKUP_CHAT_ID не установлен, пропускаем автоматический бэкап")
        return

    logger.info(f"Запуск автоматического бэкапа в чат {BACKUP_CHAT_ID}")

    try:
        await send_backup_to_chat(context, BACKUP_CHAT_ID, test_mode=False)
    except Exception as e:
        logger.error(f"Ошибка при выполнении автоматического бэкапа: {e}", exc_info=True)
