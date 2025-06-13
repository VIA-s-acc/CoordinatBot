import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build

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
            return sheet.worksheet(sheet_name)
        return None
    except Exception as e:
        logger.error(f"Ошибка получения листа {sheet_name}: {e}")
        return None

def ensure_headers(worksheet, headers):
    """Проверяет и устанавливает заголовки на листе"""
    try:
        # Получаем первую строку
        first_row = worksheet.row_values(1) if worksheet.row_count > 0 else []
        
        # Если заголовков нет или они не совпадают, устанавливаем их
        if not first_row or first_row != headers:
            worksheet.clear()
            worksheet.append_row(headers)
            logger.info(f"Заголовки установлены на листе {worksheet.title}")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка установки заголовков: {e}")
        return False

def add_record_to_sheet(spreadsheet_id: str, sheet_name: str, record: dict):
    """Добавляет запись в Google Sheet"""
    try:
        worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
        if not worksheet:
            return False
        
        # Определяем заголовки
        headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
        
        # Проверяем и устанавливаем заголовки
        ensure_headers(worksheet, headers)
        
        # Формируем строку данных
        row_data = [
            record.get('id', ''),
            record.get('date', ''),
            record.get('supplier', ''),
            record.get('direction', ''),
            record.get('description', ''),
            record.get('amount', 0)
        ]
        
        # Добавляем строку
        worksheet.append_row(row_data)
        logger.info(f"Запись {record.get('id')} добавлена в Google Sheet")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка добавления записи в Google Sheet: {e}")
        return False

def update_record_in_sheet(spreadsheet_id: str, sheet_name: str, record_id: str, field: str, new_value):
    """Обновляет конкретное поле записи в Google Sheet"""
    try:
        worksheet = get_worksheet_by_name(spreadsheet_id, sheet_name)
        if not worksheet:
            return False
        
        # Получаем все записи
        records = worksheet.get_all_records()
        
        # Ищем запись по ID
        for i, record in enumerate(records):
            if str(record.get('ID', '')) == record_id:
                # Определяем номер строки (i+2, так как +1 для заголовка и +1 для индексации с 1)
                row_num = i + 2
                
                # Определяем номер столбца для поля
                headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
                field_map = {
                    'date': 'ամսաթիվ',
                    'supplier': 'մատակարար',
                    'direction': 'ուղղություն',
                    'description': 'ծախսի բնութագիր',
                    'amount': 'Արժեք'
                }
                
                header_name = field_map.get(field)
                if header_name and header_name in headers:
                    col_num = headers.index(header_name) + 1
                    worksheet.update_cell(row_num, col_num, new_value)
                    logger.info(f"Обновлено поле {field} записи {record_id} в Google Sheet")
                    return True
        
        logger.warning(f"Запись {record_id} не найдена в Google Sheet")
        return False
        
    except Exception as e:
        logger.error(f"Ошибка обновления записи в Google Sheet: {e}")
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