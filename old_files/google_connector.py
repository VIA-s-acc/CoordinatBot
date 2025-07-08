import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
from google.oauth2 import service_account
from database import add_record_to_db
from googleapiclient.discovery import build
import datetime
import uuid
from datetime import datetime

SCOPE = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

CREDS_FILE = 'coordinate-462818-8da128264452.json'

logger = logging.getLogger(__name__)

def get_client():
    """Получает авторизованного клиента Google Sheets"""
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE)
        return gspread.authorize(creds)
    except Exception as e:
        logger.error(f"Ошибка авторизации Google Sheets: {e}")
        return None

def list_spreadsheets():
    """Получает список всех доступных спредшитов"""
    try:
        client = get_client()
        if client:
            return client.list_spreadsheet_files()
        return []
    except Exception as e:
        logger.error(f"Ошибка получения списка спредшитов: {e}")
        return []

def open_sheet_by_id(spreadsheet_id: str):
    """Открывает спредшит по ID"""
    try:
        client = get_client()
        if client:
            return client.open_by_key(spreadsheet_id)
        return None
    except Exception as e:
        logger.error(f"Ошибка открытия спредшита {spreadsheet_id}: {e}")
        return None

def get_worksheets_info(spreadsheet_id: str):
    """Получает информацию о всех листах в спредшите"""
    try:
        sheet = open_sheet_by_id(spreadsheet_id)
        if not sheet:
            return [], "Unknown"
        
        worksheets = sheet.worksheets()
        sheets_info = []
        
        for worksheet in worksheets:
            info = {
                'title': worksheet.title,
                'id': worksheet.id,
                'row_count': worksheet.row_count,
                'col_count': worksheet.col_count,
                'url': worksheet.url
            }
            sheets_info.append(info)
        
        return sheets_info, sheet.title
    except Exception as e:
        logger.error(f"Ошибка получения информации о листах: {e}")
        return [], "Error"

def get_worksheet_by_name(spreadsheet_id: str, sheet_name: str):
    """Получает конкретный лист по имени"""
    try:
        sheet = open_sheet_by_id(spreadsheet_id)
        if sheet:
            # for ws in sheet.worksheets():
            #     logger.info(f"📄 Лист: {ws.title}, ID: {ws.id}")
            return sheet.worksheet(sheet_name)
        return None
    except Exception as e:
        logger.error(f"Ошибка получения листа {sheet_name}: {e}")
        return None

def ensure_headers(worksheet, headers):
    """
    Проверяет и устанавливает заголовки в первой строке листа, если они отсутствуют или неполные.
    """
    try:
        current_headers = worksheet.row_values(1)
        if current_headers != headers:
            logger.info("🔁 Обновление заголовков на листе")
            worksheet.update("A1:F1", [headers])
    except Exception as e:
        logger.error(f"❌ Ошибка при установке заголовков: {e}")
        raise
    
from datetime import datetime

def add_record_to_sheet(spreadsheet_id: str, sheet_name: str, record: dict) -> bool:
    """
    Добавляет запись в указанный лист Google Sheet.
    Если дата новшго рекорда раньше, чем у существующих, вставляет в правильное место,
    сдвигая остальные записи вниз, чтобы сохранить сортировку по дате.
    
    :param spreadsheet_id: ID Google-таблицы
    :param sheet_name: название листа
    :param record: словарь с полями ['id', 'date', 'supplier', 'direction', 'description', 'amount']
    :return: True, если запись успешно добавлена, иначе False
    """
    try:
        logger.info(f"📄 Поиск листа '{sheet_name}' в таблице {spreadsheet_id}")
        worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
        if not worksheet:
            logger.error(f"❌ Лист '{sheet_name}' не найден в таблице '{spreadsheet_id}'")
            return False
        
        # Шапка
        headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
        ensure_headers(worksheet, headers)
        
        # Форматируем дату входной записи
        raw_date = str(record.get('date', '')).strip()
        try:
            date_obj_new = datetime.strptime(raw_date, "%Y-%m-%d")
            formatted_date = date_obj_new.strftime("%d.%m.%y")  # для записи в лист
        except Exception as e:
            logger.warning(f"⚠️ Некорректный формат даты: {raw_date}, ошибка: {e}")
            formatted_date = raw_date
            date_obj_new = None  # если не получилось распарсить, вставим в конец
        
        # Подготавливаем строку для вставки
        row_data = [
            str(record.get('id', '')).strip(),
            formatted_date,
            str(record.get('supplier', '')).strip(),
            str(record.get('direction', '')).strip(),
            str(record.get('description', '')).strip(),
            float(record.get('amount', 0))
        ]
        
        # Получаем все данные листа, включая шапку
        all_values = worksheet.get_all_values()
        
        # Если лист пустой (только заголовок или совсем пуст)
        if len(all_values) <= 1:
            # просто добавляем в конец
            worksheet.append_row(row_data, value_input_option="USER_ENTERED")
            logger.info(f"✅ Запись добавлена в пустой лист или после шапки.")
            return True
        
        # Парсим даты из листа (начиная со 2-й строки, т.к. 1-я - шапка)
        def parse_date(date_str):
            
            try:
                clean_str = date_str.replace("․", ".").strip()
                return datetime.strptime(clean_str, "%d.%m.%y")
            except:
                return None
        
        # Создаем список кортежей (индекс строки в листе, дата) для сортировки
        indexed_dates = []
        for idx, row in enumerate(all_values[1:], start=2):  # строки с 2-й
            
            dt = parse_date(row[1]) if len(row) > 1 else None
            indexed_dates.append((idx, dt))

        # Если дата новой записи не распарсилась, добавляем в конец
        if date_obj_new is None:
            worksheet.append_row(row_data, value_input_option="USER_ENTERED")
            logger.info(f"✅ Дата не распарсена, запись добавлена в конец.")
            return True
        
        # Ищем позицию для вставки по возрастанию даты
        insert_index = None
        for idx, dt in indexed_dates:
            if dt is None:
                # Если в листе дата не парсится, ставим новую запись перед этим
                insert_index = idx
                break
            if date_obj_new < dt:
                insert_index = idx
                break
        
        if insert_index is None:
            # Дата больше всех — добавляем в конец
            worksheet.append_row(row_data, value_input_option="USER_ENTERED")
            logger.info(f"✅ Запись с самой большой датой добавлена в конец.")
            return True
        
        # Вставляем новую строку на позицию insert_index (сдвигая вниз)
        worksheet.insert_row(row_data, index=insert_index, value_input_option="USER_ENTERED")
        logger.info(f"✅ Запись вставлена в позицию {insert_index}, сдвинув остальные вниз.")
        return True

    except Exception as e:
        import traceback
        logger.error(f"❌ Ошибка добавления записи в Google Sheet: {e}")
        logger.error(traceback.format_exc())
        return False
    
def initialize_and_sync_sheets():
    """
    Проходит по всем Google-таблицам и их листам,
    добавляет недостающие ID, вставляет записи в БД (если их нет),
    и пересоздаёт листы с полным набором данных и заголовками — через batch update.
    """
    import uuid
    import logging
    from database import get_record_from_db, add_record_to_db
    from google_connector import (
        get_all_spreadsheets,
        open_sheet_by_id
    )

    logger = logging.getLogger(__name__)
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
                        row_id = "cb-"+str(uuid.uuid4())[:8]

                    # 🗓 Обработка даты
                    raw_date = str(row.get('ամսաթիվ', '')).strip()
                    if raw_date:
                        # Обновляем last_valid_date, но предварительно нормализуем символы
                        normalized_date = raw_date.replace("․", ".").strip()
                        last_valid_date = normalized_date
                    elif last_valid_date:
                        # Наследуем дату
                        normalized_date = last_valid_date
                    else:
                        # Если нет даже предыдущей даты — оставляем пусто
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
                    try:
                        amount = float(cleaned_amount)
                    except ValueError:
                        amount = 0.0
                        logger.warning(f"⚠️ Невозможно преобразовать сумму '{raw_amount}' → 0.0")

                    # 📦 Подготовка записи
                    record = {
                        'id': row_id,
                        'date': normalized_date,
                        'supplier': str(row.get('մատակարար', '')).strip(),
                        'direction': str(row.get('ուղղություն', '')).strip(),
                        'description': str(row.get('ծախսի բնութագիր', '')).strip(),
                        'amount': amount,
                        'spreadsheet_id': spreadsheet_id,
                        'sheet_name': sheet_name
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


from datetime import datetime

def update_record_in_sheet(spreadsheet_id: str, sheet_name: str, record_id: str, field: str, new_value):
    """
    Обновляет конкретное поле записи в Google Sheet.
    Если обновляется дата, перемещает строку так, чтобы сохранить сортировку по дате.
    """
    try:
        worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
        if not worksheet:
            logger.error(f"Лист '{sheet_name}' не найден в таблице '{spreadsheet_id}'")
            return False
        
        headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
        field_map = {
            'date': 'ամսաթիվ',
            'supplier': 'մատակարար',
            'direction': 'ուղղություն',
            'description': 'ծախսի բնութագիր',
            'amount': 'Արժեք'
        }
        
        header_name = field_map.get(field)
        if not header_name or header_name not in headers:
            logger.error(f"Неверное поле для обновления: {field}")
            return False
        
        records = worksheet.get_all_records()
        
        # Найдем индекс записи и номер строки (учитывая шапку)
        record_index = None
        for i, rec in enumerate(records):
            if str(rec.get('ID', '')) == record_id:
                record_index = i
                break
        
        if record_index is None:
            logger.warning(f"Запись с ID={record_id} не найдена")
            return False
        
        row_num = record_index + 2  # +1 шапка, +1 индексация с 1
        col_num = headers.index(header_name) + 1
        
        # Обновляем ячейку
        worksheet.update_cell(row_num, col_num, new_value)
        logger.info(f"Обновлено поле '{field}' записи {record_id}")
        
        # Если обновили дату — нужно переместить строку для сохранения сортировки
        if field == 'date':
            # Парсим новую дату в формате "ДД.ММ.ГГ"
            try:
                new_date_obj = datetime.strptime(new_value, "%Y-%m-%d")
                new_date_obj = new_date_obj.strftime("%d.%m.%y")
            except Exception as e:
                logger.warning(f"Невозможно распарсить новую дату '{new_value}': {e}")
                return True  # Просто обновили, без сдвига
            
            # Получаем ВСЕ строки (включая заголовок)
            all_values = worksheet.get_all_values()
            
            # Извлекаем обновлённую строку (текущая строка на листе)
            updated_row = all_values[row_num - 1]
            
            # Удаляем эту строку
            worksheet.delete_row(row_num)
            logger.info(f"Удалена строка {row_num} для перемещения")
            
            # Функция для парсинга даты из листа
            def parse_date(date_str):
                try:
                    return datetime.strptime(date_str, "%d.%m.%y")
                except:
                    return None
            
            # Формируем список (индекс строки, дата) для поиска места вставки
            indexed_dates = []
            for idx, row in enumerate(all_values[1:], start=2):
                if idx == row_num:
                    # Уже удалили эту строку — пропускаем
                    continue
                dt = parse_date(row[1]) if len(row) > 1 else None
                indexed_dates.append((idx, dt))
            
            # Ищем индекс для вставки по возрастанию даты
            new_date_obj = datetime.strptime(new_date_obj, "%d.%m.%y")
            insert_index = None
            for idx, dt in indexed_dates:
                if dt is None or new_date_obj < dt:
                    insert_index = idx
                    break
            
            if insert_index is None:
                # Вставляем в конец
                worksheet.append_row(updated_row, value_input_option="USER_ENTERED")
                logger.info(f"Строка вставлена в конец листа")
            else:
                worksheet.insert_row(updated_row, index=insert_index, value_input_option="USER_ENTERED")
                logger.info(f"Строка вставлена на позицию {insert_index}")
        
        return True
    
    except Exception as e:
        import traceback
        logger.error(f"Ошибка обновления записи в Google Sheet: {e}")
        logger.error(traceback.format_exc())
        return False

def delete_record_from_sheet(spreadsheet_id: str, sheet_name: str, record_id: str):
    """Удаляет запись из Google Sheet"""
    try:
        worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
        if not worksheet:
            return False
        
        # Получаем все записи
        records = worksheet.get_all_records()
        
        # Ищем запись по ID
        for i, record in enumerate(records):
            if str(record.get('ID', '')) == record_id:
                # Удаляем строку (i+2, так как +1 для заголовка и +1 для индексации с 1)
                row_num = i + 2
                worksheet.delete_rows(row_num)
                logger.info(f"Запись {record_id} удалена из Google Sheet")
                return True
        
        logger.warning(f"Запись {record_id} не найдена в Google Sheet для удаления")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка удаления записи из Google Sheet: {e}")
        return False

def get_record_by_id(spreadsheet_id: str, sheet_name: str, record_id: str):
    """Получает запись по ID из Google Sheet"""
    try:
        worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
        if not worksheet:
            return None
        
        # Получаем все записи
        records = worksheet.get_all_records()
        
        # Ищем запись по ID
        for record in records:
            if str(record.get('ID', '')) == record_id:
                # Преобразуем заголовки к стандартному виду
                normalized_record = {
                    'id': record.get('ID', ''),
                    'date': record.get('ամսաթիվ', ''),
                    'supplier': record.get('մատակարար', ''),
                    'direction': record.get('ուղղություն', ''),
                    'description': record.get('ծախսի բնութագիր', ''),
                    'amount': record.get('Արժեք', 0)
                }
                return normalized_record
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка получения записи {record_id} из Google Sheet: {e}")
        

def get_all_spreadsheets():
    """Получает список всех Google Spreadsheets через Google Drive API"""
    try:
        creds = service_account.Credentials.from_service_account_file(
            CREDS_FILE, scopes=SCOPES
        )
        service = build('drive', 'v3', credentials=creds)

        query = "mimeType='application/vnd.google-apps.spreadsheet'"
        results = service.files().list(
            q=query,
            pageSize=1000,
            fields="files(id, name)"
        ).execute()

        items = results.get('files', [])
        spreadsheets = []
        for file in items:
            spreadsheets.append({
                'id': file['id'],
                'name': file['name'],
                'url': f"https://docs.google.com/spreadsheets/d/{file['id']}/edit"
            })

        print(f"Найдено {len(spreadsheets)} таблиц")
        return spreadsheets

    except Exception as e:
        print(f"Ошибка получения списка таблиц: {e}")
        return []

def get_spreadsheet_info(spreadsheet_id: str):
    """Получает подробную информацию о конкретной таблице"""
    try:
        sheet = open_sheet_by_id(spreadsheet_id)
        if not sheet:
            return None
        
        worksheets = sheet.worksheets()
        sheets_info = []
        
        for worksheet in worksheets:
            info = {
                'title': worksheet.title,
                'id': worksheet.id,
                'row_count': worksheet.row_count,
                'col_count': worksheet.col_count,
                'url': worksheet.url
            }
            sheets_info.append(info)
        
        spreadsheet_info = {
            'id': spreadsheet_id,
            'title': sheet.title,
            'url': sheet.url,
            'sheets': sheets_info,
            'sheets_count': len(sheets_info)
        }
        
        return spreadsheet_info
        
    except Exception as e:
        logger.error(f"Ошибка получения информации о таблице {spreadsheet_id}: {e}")
        return None