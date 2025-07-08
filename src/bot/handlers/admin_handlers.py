"""
Обработчики команд администратора
"""
import json
import os
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import CallbackContext

from ...config.settings import ADMIN_IDS
from ...utils.config_utils import (
    is_user_allowed, load_users, save_users, 
    load_allowed_users, save_allowed_users,
    add_allowed_user, remove_allowed_user,
    set_log_chat, set_report_settings, send_to_log_chat
)
from ...database.database_manager import backup_db_to_dict, search_records, get_all_records, get_record_from_db
from ...google_integration.sheets_manager import initialize_sheet_headers, get_all_spreadsheets, get_worksheets_info
from ..keyboards.inline_keyboards import create_main_menu

logger = logging.getLogger(__name__)

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
                'active_spreadsheet_id': None,
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
                'active_spreadsheet_id': None,
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
    """Синхронизирует данные из Google Sheets в БД"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return

    from ...utils.config_utils import get_user_settings
    from ...google_integration.sheets_manager import get_worksheet_by_name
    from ...database.database_manager import add_record_to_db, get_record_from_db
    
    user_settings = get_user_settings(user_id)
    spreadsheet_id = user_settings.get('active_spreadsheet_id')
    sheet_name = user_settings.get('active_sheet_name')
    
    if not spreadsheet_id or not sheet_name:
        await update.message.reply_text("❌ Նախ պետք է ընտրել աղյուսակ և թերթիկ:")
        return

    try:
        worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
        if not worksheet:
            await update.message.reply_text("❌ Չհաջողվեց բացել թերթիկը:")
            return

        rows = worksheet.get_all_records()
        added, updated = 0, 0
        
        for row in rows:
            # Приводим к формату бота
            record_id = str(row.get('ID', '')).strip()
            if not record_id:
                continue  # пропускаем строки без ID

            # Приведение даты к YYYY-MM-DD
            raw_date = str(row.get('ամսաթիվ', '')).replace("․", ".").strip()
            try:
                if "." in raw_date:
                    date_obj = datetime.strptime(raw_date, "%d.%m.%y")
                    date_fmt = date_obj.strftime("%Y-%m-%d")
                else:
                    date_fmt = raw_date
            except Exception:
                date_fmt = raw_date

            # Приведение суммы к float
            try:
                amount = float(str(row.get('Արժեք', '0')).replace(',', '.').replace(' ', ''))
            except Exception:
                amount = 0.0

            record = {
                'id': record_id,
                'date': date_fmt,
                'supplier': str(row.get('մատակարար', '')).strip(),
                'direction': str(row.get('ուղղություն', '')).strip(),
                'description': str(row.get('ծախսի բնութագիր', '')).strip(),
                'amount': amount,
                'spreadsheet_id': spreadsheet_id,
                'sheet_name': sheet_name
            }

            db_record = get_record_from_db(record_id)
            if not db_record:
                if add_record_to_db(record):
                    added += 1
            else:
                # Можно добавить сравнение и обновление, если хотите
                updated += 1
        
        await update.message.reply_text(
            f"✅ Սինխրոնիզացիա ավարտված է:\n"
            f"Ավելացված է {added} նոր գրառում, {updated} արդեն կար:",
            parse_mode="HTML"
        )
        
        await send_to_log_chat(context, f"Google Sheets համաժամեցում: +{added} նոր, {updated} այլ")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Սինխրոնիզացիայի սխալ: {e}")

async def initialize_sheets_command(update: Update, context: CallbackContext):
    """Команда инициализации всех Google Sheets"""
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Դուք չունեք այս հրամանը կատարելու թույլտվություն:")
        return

    try:
        from ...google_integration.sheets_manager import initialize_sheet_headers
        
        # Получаем все доступные таблицы
        spreadsheets = get_all_spreadsheets()
        
        if not spreadsheets:
            await update.message.reply_text("❌ Доступных таблиц не найдено")
            return
            
        initialized_count = 0
        total_sheets = 0
        
        for spreadsheet in spreadsheets:
            spreadsheet_id = spreadsheet['id']
            spreadsheet_title = spreadsheet.get('name', 'Без названия')
            
            try:
                sheets_info, _ = get_worksheets_info(spreadsheet_id)
                
                for sheet in sheets_info:
                    sheet_name = sheet['title']
                    success = initialize_sheet_headers(spreadsheet_id, sheet_name)
                    
                    if success:
                        initialized_count += 1
                    total_sheets += 1
                    
            except Exception as e:
                logger.error(f"Ошибка инициализации таблицы {spreadsheet_title}: {e}")
                continue
        
        await update.message.reply_text(
            f"✅ Инициализация завершена:\n"
            f"📊 Обработано таблиц: {len(spreadsheets)}\n"
            f"📋 Инициализировано листов: {initialized_count}/{total_sheets}\n"
            f"✅ Все заголовки обновлены в соответствии с форматом бота"
        )
        
        await send_to_log_chat(context, f"✅ Инициализировано {initialized_count}/{total_sheets} листов в {len(spreadsheets)} таблицах")
        
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
        
        from ...utils.config_utils import update_user_settings
        # Сохраняем ID таблицы для пользователя
        update_user_settings(user_id, {'active_spreadsheet_id': spreadsheet_id})
        
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
