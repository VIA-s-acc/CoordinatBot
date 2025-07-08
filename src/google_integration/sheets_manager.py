"""
Модуль для интеграции с Google Sheets
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from ..config.settings import GOOGLE_CREDS_FILE, GOOGLE_SCOPE, GOOGLE_SCOPES

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    """Класс для управления Google Sheets"""
    
    def __init__(self, creds_file: str = GOOGLE_CREDS_FILE):
        self.creds_file = creds_file
        self._client = None
    
    def get_client(self):
        """Получает авторизованного клиента Google Sheets"""
        if self._client is None:
            try:
                creds = ServiceAccountCredentials.from_json_keyfile_name(
                    self.creds_file, GOOGLE_SCOPE
                )
                self._client = gspread.authorize(creds)
            except Exception as e:
                logger.error(f"Ошибка авторизации Google Sheets: {e}")
                return None
        return self._client

    def list_spreadsheets(self):
        """Получает список всех доступных спредшитов"""
        try:
            client = self.get_client()
            if client:
                return client.list_spreadsheet_files()
            return []
        except Exception as e:
            logger.error(f"Ошибка получения списка спредшитов: {e}")
            return []

    def get_all_spreadsheets(self):
        """Получает все спредшиты с дополнительной информацией"""
        try:
            creds = service_account.Credentials.from_service_account_file(
                self.creds_file, scopes=GOOGLE_SCOPES
            )
            service = build('drive', 'v3', credentials=creds)
            
            results = service.files().list(
                q="mimeType='application/vnd.google-apps.spreadsheet'",
                fields="files(id, name, modifiedTime, size)"
            ).execute()
            
            return results.get('files', [])
        except Exception as e:
            logger.error(f"Ошибка получения списка спредшитов через Drive API: {e}")
            return []

    def open_sheet_by_id(self, spreadsheet_id: str):
        """Открывает спредшит по ID"""
        try:
            client = self.get_client()
            if client:
                return client.open_by_key(spreadsheet_id)
            return None
        except Exception as e:
            logger.error(f"Ошибка открытия спредшита {spreadsheet_id}: {e}")
            return None

    def get_worksheets_info(self, spreadsheet_id: str) -> Tuple[List[Dict], str]:
        """Получает информацию о всех листах в спредшите"""
        try:
            sheet = self.open_sheet_by_id(spreadsheet_id)
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

    def get_worksheet_by_name(self, spreadsheet_id: str, sheet_name: str):
        """Получает конкретный лист по имени"""
        try:
            sheet = self.open_sheet_by_id(spreadsheet_id)
            if sheet:
                return sheet.worksheet(sheet_name)
            return None
        except Exception as e:
            logger.error(f"Ошибка получения листа {sheet_name}: {e}")
            return None

    def get_spreadsheet_info(self, spreadsheet_id: str) -> Optional[Dict]:
        """Получает подробную информацию о спредшите"""
        try:
            sheet = self.open_sheet_by_id(spreadsheet_id)
            if not sheet:
                return None
            
            worksheets = sheet.worksheets()
            sheets_info = []
            
            for worksheet in worksheets:
                sheets_info.append({
                    'title': worksheet.title,
                    'row_count': worksheet.row_count,
                    'col_count': worksheet.col_count
                })
            
            return {
                'title': sheet.title,
                'id': spreadsheet_id,
                'sheets': sheets_info,
                'sheets_count': len(sheets_info)
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о спредшите: {e}")
            return None

    def ensure_headers(self, worksheet, headers: List[str]):
        """Проверяет и устанавливает заголовки в первой строке листа"""
        try:
            current_headers = worksheet.row_values(1)
            if current_headers != headers:
                logger.info("🔁 Обновление заголовков на листе")
                worksheet.update("A1:F1", [headers])
        except Exception as e:
            logger.error(f"❌ Ошибка при установке заголовков: {e}")

    def add_record_to_sheet(self, spreadsheet_id: str, sheet_name: str, record: Dict) -> bool:
        """Добавляет запись в Google Sheet"""
        try:
            worksheet = self.get_worksheet_by_name(spreadsheet_id, sheet_name)
            if not worksheet:
                logger.error(f"Лист {sheet_name} не найден")
                return False

            headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
            self.ensure_headers(worksheet, headers)

            new_row = [
                record.get('id', ''),
                record.get('date', ''),
                record.get('supplier', ''),
                record.get('direction', ''),
                record.get('description', ''),
                record.get('amount', 0)
            ]

            worksheet.append_row(new_row)
            logger.info(f"Запись {record.get('id')} добавлена в Google Sheets")
            return True

        except Exception as e:
            logger.error(f"Ошибка добавления записи в Google Sheets: {e}")
            return False

    def update_record_in_sheet(self, spreadsheet_id: str, sheet_name: str, 
                             record_id: str, field: str, new_value) -> bool:
        """Обновляет запись в Google Sheet"""
        try:
            worksheet = self.get_worksheet_by_name(spreadsheet_id, sheet_name)
            if not worksheet:
                return False

            records = worksheet.get_all_records()
            
            field_mapping = {
                'date': 'ամսաթիվ',
                'supplier': 'մատակարար',
                'direction': 'ուղղություն',
                'description': 'ծախսի բնութագիր',
                'amount': 'Արժեք'
            }
            
            sheet_field = field_mapping.get(field, field)
            
            for i, row in enumerate(records, start=2):
                if str(row.get('ID', '')).strip() == record_id:
                    headers = worksheet.row_values(1)
                    if sheet_field in headers:
                        col_index = headers.index(sheet_field) + 1
                        worksheet.update_cell(i, col_index, new_value)
                        logger.info(f"Запись {record_id} обновлена в Google Sheets")
                        return True
            
            return False

        except Exception as e:
            logger.error(f"Ошибка обновления записи в Google Sheets: {e}")
            return False

    def delete_record_from_sheet(self, spreadsheet_id: str, sheet_name: str, record_id: str) -> bool:
        """Удаляет запись из Google Sheet"""
        try:
            worksheet = self.get_worksheet_by_name(spreadsheet_id, sheet_name)
            if not worksheet:
                return False

            records = worksheet.get_all_records()
            
            for i, row in enumerate(records, start=2):
                if str(row.get('ID', '')).strip() == record_id:
                    worksheet.delete_rows(i)
                    logger.info(f"Запись {record_id} удалена из Google Sheets")
                    return True
            
            return False

        except Exception as e:
            logger.error(f"Ошибка удаления записи из Google Sheets: {e}")
            return False

    def initialize_sheet_headers(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """Инициализирует заголовки в листе"""
        try:
            worksheet = self.get_worksheet_by_name(spreadsheet_id, sheet_name)
            if not worksheet:
                return False

            headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
            self.ensure_headers(worksheet, headers)
            
            return True

        except Exception as e:
            logger.error(f"Ошибка инициализации заголовков: {e}")
            return False

# Создаем глобальный экземпляр менеджера Google Sheets
sheets_manager = GoogleSheetsManager()

# Экспортируем функции для обратной совместимости
def get_client():
    return sheets_manager.get_client()

def list_spreadsheets():
    return sheets_manager.list_spreadsheets()

def get_all_spreadsheets():
    return sheets_manager.get_all_spreadsheets()

def open_sheet_by_id(spreadsheet_id: str):
    return sheets_manager.open_sheet_by_id(spreadsheet_id)

def get_worksheets_info(spreadsheet_id: str):
    return sheets_manager.get_worksheets_info(spreadsheet_id)

def get_worksheet_by_name(spreadsheet_id: str, sheet_name: str):
    return sheets_manager.get_worksheet_by_name(spreadsheet_id, sheet_name)

def get_spreadsheet_info(spreadsheet_id: str):
    return sheets_manager.get_spreadsheet_info(spreadsheet_id)

def add_record_to_sheet(spreadsheet_id: str, sheet_name: str, record: Dict) -> bool:
    return sheets_manager.add_record_to_sheet(spreadsheet_id, sheet_name, record)

def update_record_in_sheet(spreadsheet_id: str, sheet_name: str, 
                          record_id: str, field: str, new_value) -> bool:
    return sheets_manager.update_record_in_sheet(spreadsheet_id, sheet_name, 
                                               record_id, field, new_value)

def delete_record_from_sheet(spreadsheet_id: str, sheet_name: str, record_id: str) -> bool:
    return sheets_manager.delete_record_from_sheet(spreadsheet_id, sheet_name, record_id)

def initialize_sheet_headers(spreadsheet_id: str, sheet_name: str) -> bool:
    return sheets_manager.initialize_sheet_headers(spreadsheet_id, sheet_name)
