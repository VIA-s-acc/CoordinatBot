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
        """Добавляет запись в Google Sheet с сортировкой по дате, используя пакетную вставку."""
        try:
            # Получаем рабочий лист
            worksheet = self.get_worksheet_by_name(spreadsheet_id, sheet_name)
            if not worksheet:
                logger.error(f"Лист {sheet_name} не найден")
                return False

            headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
            self.ensure_headers(worksheet, headers)

            # Конвертируем дату из YYYY-MM-DD в dd.mm.yy формат
            formatted_date = record.get('date', '')
            if formatted_date:
                try:
                    # Парсим дату в формате YYYY-MM-DD
                    date_obj = datetime.strptime(formatted_date, '%Y-%m-%d')
                    formatted_date = date_obj.strftime('%d.%m.%y')
                except ValueError:
                    logger.warning(f"Неверный формат даты: {formatted_date}")
                    formatted_date = record.get('date', '')

            new_row = [
                record.get('id', ''),
                formatted_date,
                record.get('supplier', ''),
                record.get('direction', ''),
                record.get('description', ''),
                record.get('amount', 0)
            ]

            # Получаем все записи и сортируем по дате
            all_records = worksheet.get_all_records()
            all_records.sort(key=lambda x: datetime.strptime(x['ամսաթիվ'], '%d.%m.%y') if x['ամսաթիվ'] else datetime.min)

            # Находим правильную позицию для вставки
            insert_row = len(all_records) + 2  # Если не найдем место, добавим в конец

            if formatted_date:
                new_date = datetime.strptime(formatted_date, '%d.%m.%y')
                for i, existing_record in enumerate(all_records):
                    existing_date_str = existing_record.get('ամսաթիվ', '')
                    if existing_date_str:
                        try:
                            existing_date = datetime.strptime(existing_date_str, '%d.%m.%y')
                            if new_date < existing_date:
                                insert_row = i + 2  # +2 потому что записи начинаются с 2-й строки
                                break
                        except ValueError:
                            continue

            # Пакетная запись новой строки в таблицу
            worksheet.insert_row(new_row, insert_row)
            logger.info(f"Запись {record.get('id')} вставлена в позицию {insert_row} с сортировкой по дате")

            return True

        except Exception as e:
            logger.error(f"Ошибка добавления записи в Google Sheets: {e}")
            return False


    def update_record_in_sheet(self, spreadsheet_id: str, sheet_name: str, 
                             record_id: str, field: str, new_value) -> bool:
        """Обновляет запись в Google Sheet с пересортировкой при изменении даты"""
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
            
            # Находим запись для обновления
            record_found = False
            record_row = None
            current_record = None
            
            for i, row in enumerate(records, start=2):
                if str(row.get('ID', '')).strip() == record_id:
                    record_found = True
                    record_row = i
                    current_record = row
                    break
            
            if not record_found:
                logger.error(f"Запись {record_id} не найдена для обновления")
                return False
            
            # Если обновляется дата, нужно переместить запись в правильную позицию
            if field == 'date' and new_value:
                try:
                    # Парсим новую дату (в формате YYYY-MM-DD)
                    new_date = datetime.strptime(new_value, '%Y-%m-%d')
                    
                    # Конвертируем в формат dd.mm.yy для записи в таблицу
                    formatted_new_date = new_date.strftime('%d.%m.%y')
                    
                    # Создаем обновленную запись
                    updated_record = current_record.copy()
                    updated_record[sheet_field] = formatted_new_date
                    
                    # Удаляем старую запись
                    worksheet.delete_rows(record_row)
                    
                    # Получаем обновленный список записей (без удаленной)
                    updated_records = worksheet.get_all_records()
                    
                    # Находим правильную позицию для вставки
                    insert_row = len(updated_records) + 2  # По умолчанию в конец
                    
                    for i, existing_record in enumerate(updated_records):
                        existing_date_str = existing_record.get('ամսաթիվ', '')
                        if existing_date_str:
                            try:
                                # Парсим существующую дату в формате dd.mm.yy
                                existing_date = datetime.strptime(existing_date_str, '%d.%m.%y')
                                # Корректируем год если нужно
                                if existing_date.year < 2000:
                                    existing_date = existing_date.replace(year=existing_date.year + 100)
                                if new_date < existing_date:
                                    insert_row = i + 2
                                    break
                            except ValueError:
                                continue
                    
                    # Вставляем обновленную запись в правильную позицию
                    new_row = [
                        updated_record.get('ID', ''),
                        updated_record.get('ամսաթիվ', ''),
                        updated_record.get('մատակարար', ''),
                        updated_record.get('ուղղություն', ''),
                        updated_record.get('ծախսի բնութագիր', ''),
                        updated_record.get('Արժեք', 0)
                    ]
                    
                    worksheet.insert_row(new_row, insert_row)
                    logger.info(f"Запись {record_id} перемещена в позицию {insert_row} после обновления даты")
                    
                except ValueError:
                    # Если дата не может быть распарсена, просто обновляем на месте
                    headers = worksheet.row_values(1)
                    if sheet_field in headers:
                        col_index = headers.index(sheet_field) + 1
                        worksheet.update_cell(record_row, col_index, new_value)
                        logger.info(f"Запись {record_id} обновлена на месте (неверный формат даты)")
                    
            else:
                # Обычное обновление поля без перемещения
                # Если обновляется дата, конвертируем формат
                if field == 'date' and new_value:
                    try:
                        # Парсим дату в формате YYYY-MM-DD
                        date_obj = datetime.strptime(new_value, '%Y-%m-%d')
                        # Конвертируем в формат dd.mm.yy
                        new_value = date_obj.strftime('%d.%m.%y')
                    except ValueError:
                        logger.warning(f"Неверный формат даты: {new_value}")
                
                headers = worksheet.row_values(1)
                if sheet_field in headers:
                    col_index = headers.index(sheet_field) + 1
                    worksheet.update_cell(record_row, col_index, new_value)
                    logger.info(f"Запись {record_id} обновлена в Google Sheets")
                else:
                    logger.error(f"Поле {sheet_field} не найдено в заголовках")
                    return False
            
            return True

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

    def sort_sheet_by_date(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """Сортирует все записи в листе по дате"""
        try:
            worksheet = self.get_worksheet_by_name(spreadsheet_id, sheet_name)
            if not worksheet:
                logger.error(f"Лист {sheet_name} не найден")
                return False

            # Получаем все записи
            all_records = worksheet.get_all_records()
            if not all_records:
                logger.info("Нет записей для сортировки")
                return True

            # Сортируем записи по дате
            def get_sort_key(record):
                date_str = record.get('ամսաթիվ', '')
                if date_str:
                    try:
                        # Парсим дату в формате dd.mm.yy
                        parsed_date = datetime.strptime(date_str, '%d.%m.%y')
                        # Корректируем год: если год меньше 2000, добавляем 100 лет
                        # Это гарантирует, что все года будут в 21 веке (2000-2099)
                        if parsed_date.year < 2000:
                            parsed_date = parsed_date.replace(year=parsed_date.year + 100)
                        return parsed_date
                    except ValueError:
                        try:
                            # Пробуем альтернативный формат с армянскими точками
                            parsed_date = datetime.strptime(date_str, '%d․%m․%y')
                            if parsed_date.year < 2000:
                                parsed_date = parsed_date.replace(year=parsed_date.year + 100)
                            return parsed_date
                        except ValueError:
                            return datetime.min  # Невалидные даты отправляем в начало
                return datetime.min

            sorted_records = sorted(all_records, key=get_sort_key)

            # Очищаем лист (кроме заголовков)
            if len(all_records) > 0:
                worksheet.delete_rows(2, len(all_records))

            # Добавляем отсортированные записи
            for record in sorted_records:
                row = [
                    record.get('ID', ''),
                    record.get('ամսաթիվ', ''),
                    record.get('մատակարար', ''),
                    record.get('ուղղություն', ''),
                    record.get('ծախսի բնութագիր', ''),
                    record.get('Արժեք', 0)
                ]
                worksheet.append_row(row)

            logger.info(f"Лист {sheet_name} отсортирован по дате ({len(sorted_records)} записей)")
            return True

        except Exception as e:
            logger.error(f"Ошибка сортировки листа по дате: {e}")
            return False

    def initialize_sheet_headers(self, spreadsheet_id: str, sheet_name: str) -> bool:
        """Инициализирует заголовки в листе"""
        try:
            # Get the worksheet by name
            worksheet = self.get_worksheet_by_name(spreadsheet_id, sheet_name)
            # If the worksheet does not exist, return False
            if not worksheet:
                return False

            # Define the headers
            headers = ['ID', 'ամսաթիվ', 'մատակարար', 'ուղղություն', 'ծախսի բնութագիր', 'Արժեք']
            # Ensure the headers are in the worksheet
            self.ensure_headers(worksheet, headers)
            
            # Return True if successful
            return True

        except Exception as e:
            # Log the error
            logger.error(f"Ошибка инициализации заголовков: {e}")
            # Return False if there is an error
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

def sort_sheet_by_date(spreadsheet_id: str, sheet_name: str) -> bool:
    return sheets_manager.sort_sheet_by_date(spreadsheet_id, sheet_name)
