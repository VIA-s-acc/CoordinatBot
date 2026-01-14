"""
Модуль для интеграции с Google Sheets
"""
import gspread
from oauth2client.service_account import ServiceAccountCredentials

from google.oauth2 import service_account
from googleapiclient.discovery import build
import datetime
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from ..config.settings import GOOGLE_CREDS_FILE, GOOGLE_SCOPE, GOOGLE_SCOPES, logger
from ..utils.date_utils import safe_parse_date_or_none


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
            
            def safe_sort_key(record):
                """Безопасная функция для сортировки по дате"""
                date_str = record.get('ամսաթիվ', '')
                if not date_str:
                    return datetime.min
                try:
                    parsed_date = safe_parse_date_or_none(date_str)
                    return datetime.combine(parsed_date, datetime.min.time()) if parsed_date else datetime.min
                except Exception:
                    return datetime.min
            
            all_records.sort(key=safe_sort_key)

            # Находим правильную позицию для вставки
            insert_row = len(all_records) + 2  # Если не найдем место, добавим в конец

            if formatted_date:
                try:
                    new_date = safe_parse_date_or_none(formatted_date)
                    if new_date:
                        for i, existing_record in enumerate(all_records):
                            existing_date_str = existing_record.get('ամսաթիվ', '')
                            if existing_date_str:
                                existing_date = safe_parse_date_or_none(existing_date_str)
                                if existing_date and new_date < existing_date:
                                    insert_row = i + 2  # +2 потому что записи начинаются с 2-й строки
                                    break
                except Exception as e:
                    logger.warning(f"Ошибка при поиске позиции для вставки: {e}")

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
                logger.error(f"Лист {sheet_name} не найден")
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
            
            logger.debug(f"Ищем запись с ID: '{record_id}' в {len(records)} записях")
            
            for i, row in enumerate(records, start=2):
                row_id = str(row.get('ID', '')).strip()
                logger.debug(f"Проверяем запись {i}: ID='{row_id}'")
                if row_id == record_id:
                    record_found = True
                    record_row = i
                    current_record = row
                    logger.info(f"Найдена запись {record_id} в строке {record_row}")
                    break
            
            if not record_found:
                logger.error(f"Запись {record_id} не найдена для обновления. Доступные ID: {[str(r.get('ID', '')).strip() for r in records[:5]]}")
                return False
            
            # Подготавливаем новое значение в зависимости от поля
            formatted_value = new_value
            if field == 'date' and new_value:
                try:
                    # Безопасное парсинг даты
                    parsed_date = safe_parse_date_or_none(new_value)
                    if parsed_date:
                        # Конвертируем в формат dd.mm.yy для записи в таблицу
                        formatted_value = parsed_date.strftime('%d.%m.%y')
                        logger.info(f"Конвертировали дату '{new_value}' в '{formatted_value}'")
                    else:
                        logger.warning(f"Не удалось конвертировать дату: {new_value}")
                        formatted_value = str(new_value)
                except Exception as e:
                    logger.error(f"Ошибка конвертации даты {new_value}: {e}")
                    formatted_value = str(new_value)
            
            # Обновляем поле в записи
            headers = worksheet.row_values(1)
            if sheet_field not in headers:
                logger.error(f"Поле {sheet_field} не найдено в заголовках: {headers}")
                return False
            
            col_index = headers.index(sheet_field) + 1
            worksheet.update_cell(record_row, col_index, formatted_value)
            logger.info(f"Запись {record_id} обновлена: поле '{sheet_field}' = '{formatted_value}'")
            
            # Если обновили дату, проверяем нужна ли пересортировка
            if field == 'date':
                logger.info(f"Проверяем необходимость пересортировки после обновления даты для записи {record_id}")
                
                # Получаем обновленные записи для проверки порядка
                updated_records = worksheet.get_all_records()
                
                # Проверяем, нарушен ли порядок сортировки по дате
                need_resort = False
                prev_date = None
                
                for record in updated_records:
                    date_str = record.get('ամսաթիվ', '')
                    if date_str:
                        current_date = safe_parse_date_or_none(date_str)
                        if current_date and prev_date and current_date < prev_date:
                            need_resort = True
                            logger.info(f"Обнаружено нарушение порядка дат: {current_date} < {prev_date}")
                            break
                        prev_date = current_date
                
                # Пересортировка только если действительно нужна
                if need_resort:
                    logger.info(f"Выполняем пересортировку листа после обновления даты для записи {record_id}")
                    self.sort_sheet_by_date(spreadsheet_id, sheet_name)
                else:
                    logger.info(f"Пересортировка не требуется - порядок дат корректен")
            
            return True

        except Exception as e:
            logger.error(f"Ошибка обновления записи {record_id} в Google Sheets: {e}", exc_info=True)
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
        """Сортирует все записи в листе по дате без удаления данных"""
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
                    parsed_date = safe_parse_date_or_none(date_str)
                    if parsed_date:
                        return datetime.combine(parsed_date, datetime.min.time())
                return datetime.min

            sorted_records = sorted(all_records, key=get_sort_key)

            # Подготавливаем данные для пакетного обновления
            sorted_data = []
            for record in sorted_records:
                row = [
                    record.get('ID', ''),
                    record.get('ամսաթիվ', ''),
                    record.get('մատակարար', ''),
                    record.get('ուղղություն', ''),
                    record.get('ծախսի բնութագիր', ''),
                    record.get('Արժեք', 0)
                ]
                sorted_data.append(row)

            # Пакетное обновление всех записей начиная со строки 2
            if sorted_data:
                # Определяем диапазон для обновления (от A2 до последней нужной ячейки)
                start_row = 2
                end_row = start_row + len(sorted_data) - 1
                end_col = 6  # У нас 6 колонок (ID, дата, поставщик, направление, описание, сумма)
                
                # Формат диапазона: A2:F{end_row}
                range_name = f"A{start_row}:F{end_row}"
                
                logger.info(f"Обновляем диапазон {range_name} с {len(sorted_data)} записями")
                worksheet.update(range_name, sorted_data, value_input_option='USER_ENTERED')
                
                logger.info(f"Лист {sheet_name} отсортирован по дате пакетным обновлением ({len(sorted_records)} записей)")
            else:
                logger.warning("Нет данных для обновления после сортировки")

            return True

        except Exception as e:
            logger.error(f"Ошибка сортировки листа по дате: {e}", exc_info=True)
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
