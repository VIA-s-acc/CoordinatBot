"""
Расширенный менеджер для Google Sheets с полной синхронизацией
"""
import logging
from typing import Dict, Optional
from .sheets_manager import GoogleSheetsManager
from ..database.database_manager import DatabaseManager, get_all_records
from ..utils.date_utils import normalize_date

logger = logging.getLogger(__name__)

class SyncManager:
    """Менеджер синхронизации между Google Sheets и локальной БД"""
    
    def __init__(self, sheets_manager: GoogleSheetsManager, db_manager: DatabaseManager):
        self.sheets = sheets_manager
        self.db = db_manager
    
    async def full_sync(self) -> Dict[str, int]:
        """
        Полная синхронизация всех таблиц и листов
        Возвращает статистику синхронизации
        """
        stats = {
            'processed_sheets': 0,
            'synced_records': 0,
            'new_records': 0,
            'errors': 0
        }
        
        try:
            # Получаем все доступные таблицы
            spreadsheets = self.sheets.get_all_spreadsheets()
            
            for spreadsheet in spreadsheets:
                spreadsheet_id = spreadsheet['id']
                
                try:
                    # Получаем информацию о листах
                    sheets_info, title = self.sheets.get_worksheets_info(spreadsheet_id)
                    
                    for sheet_info in sheets_info:
                        if isinstance(sheet_info, dict):
                            sheet_name = sheet_info.get('title') or sheet_info.get('name')
                            await self.sync_sheet(spreadsheet_id, sheet_name, stats)
                            stats['processed_sheets'] += 1
                        
                except Exception as e:
                    logger.error(f"Ошибка синхронизации таблицы {spreadsheet_id}: {e}")
                    stats['errors'] += 1
                    
        except Exception as e:
            logger.error(f"Ошибка полной синхронизации: {e}")
            stats['errors'] += 1
        
        return stats
    
    async def sync_sheet(self, spreadsheet_id: str, sheet_name: str, stats: Dict[str, int]):
        """Синхронизирует конкретный лист"""
        try:
            worksheet = self.sheets.get_worksheet_by_name(spreadsheet_id, sheet_name)
            if not worksheet:
                logger.warning(f"Лист {sheet_name} не найден")
                return
            
            # Получаем все записи с листа
            rows = worksheet.get_all_records()
            
            for row in rows:
                if self.is_valid_record(row):
                    record_id = str(row.get('ID', '')).strip()
                    
                    # Проверяем, есть ли запись в БД
                    if not self.db.get_record(record_id):
                        # Создаем новую запись
                        record = self.sheet_row_to_record(row, spreadsheet_id, sheet_name)
                        if record and self.db.add_record(record):
                            stats['new_records'] += 1
                            logger.info(f"Добавлена новая запись: {record_id}")
                    
                    stats['synced_records'] += 1
                    
        except Exception as e:
            logger.error(f"Ошибка синхронизации листа {sheet_name}: {e}")
            stats['errors'] += 1
    
    def is_valid_record(self, row: Dict) -> bool:
        """Проверяет, является ли строка валидной записью"""
        return (
            row.get('ID') and 
            row.get('մատակարար') and 
            row.get('Արժեք')
        )
    
    def sheet_row_to_record(self, row: Dict, spreadsheet_id: str, sheet_name: str) -> Optional[Dict]:
        """Преобразует строку из Google Sheets в формат записи БД"""
        try:
            # Парсим сумму
            amount_str = str(row.get('Արժեք', '0')).replace(',', '.').replace(' ', '')
            try:
                amount = float(amount_str)
            except ValueError:
                amount = 0.0
            
            # Нормализуем дату
            date_str = str(row.get('ամսաթիվ', '')).strip()
            normalized_date = normalize_date(date_str) if date_str else ''
            
            record = {
                'id': str(row.get('ID', '')).strip(),
                'date': normalized_date,
                'supplier': str(row.get('մատակարար', '')).strip(),
                'direction': str(row.get('ուղղություն', '')).strip(),
                'description': str(row.get('ծախսի բնութագիր', '')).strip(),
                'amount': amount,
                'spreadsheet_id': spreadsheet_id,
                'sheet_name': sheet_name,
                'user_id': None  # Будет определен позже
            }
            
            return record
            
        except Exception as e:
            logger.error(f"Ошибка преобразования строки: {e}")
            return None
    
    async def sync_db_to_sheets(self) -> Dict[str, int]:
        """
        Синхронизирует записи из БД в Google Sheets
        (для записей, которых нет в таблицах)
        """
        stats = {
            'processed_records': 0,
            'synced_records': 0,
            'errors': 0
        }
        
        try:
            # Получаем все записи из БД
            db_records = get_all_records()
            
            for record in db_records:
                try:
                    spreadsheet_id = record.get('spreadsheet_id')
                    sheet_name = record.get('sheet_name')
                    
                    if spreadsheet_id and sheet_name:
                        # Проверяем, есть ли запись в Google Sheets
                        if not await self.record_exists_in_sheet(spreadsheet_id, sheet_name, record['id']):
                            # Добавляем запись в Google Sheets
                            if self.sheets.add_record_to_sheet(spreadsheet_id, sheet_name, record):
                                stats['synced_records'] += 1
                                logger.info(f"Синхронизирована запись {record['id']} в Google Sheets")
                    
                    stats['processed_records'] += 1
                    
                except Exception as e:
                    logger.error(f"Ошибка синхронизации записи {record.get('id')}: {e}")
                    stats['errors'] += 1
                    
        except Exception as e:
            logger.error(f"Ошибка синхронизации БД в Sheets: {e}")
            stats['errors'] += 1
        
        return stats
    
    async def record_exists_in_sheet(self, spreadsheet_id: str, sheet_name: str, record_id: str) -> bool:
        """Проверяет, существует ли запись в Google Sheets"""
        try:
            worksheet = self.sheets.get_worksheet_by_name(spreadsheet_id, sheet_name)
            if not worksheet:
                return False
            
            records = worksheet.get_all_records()
            for row in records:
                if str(row.get('ID', '')).strip() == record_id:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка проверки существования записи: {e}")
            return False
    
    async def initialize_all_sheets(self) -> Dict[str, int]:
        """Инициализирует заголовки во всех листах"""
        stats = {
            'processed_sheets': 0,
            'initialized_sheets': 0,
            'errors': 0
        }
        
        try:
            spreadsheets = self.sheets.get_all_spreadsheets()
            
            for spreadsheet in spreadsheets:
                spreadsheet_id = spreadsheet['id']
                
                try:
                    sheets_info, title = self.sheets.get_worksheets_info(spreadsheet_id)
                    
                    for sheet_info in sheets_info:
                        if isinstance(sheet_info, dict):
                            sheet_name = sheet_info.get('title') or sheet_info.get('name')
                            
                            if self.sheets.initialize_sheet_headers(spreadsheet_id, sheet_name):
                                stats['initialized_sheets'] += 1
                            
                            stats['processed_sheets'] += 1
                            
                except Exception as e:
                    logger.error(f"Ошибка инициализации таблицы {spreadsheet_id}: {e}")
                    stats['errors'] += 1
                    
        except Exception as e:
            logger.error(f"Ошибка инициализации всех листов: {e}")
            stats['errors'] += 1
        
        return stats

# Создаем глобальный экземпляр менеджера синхронизации
from .sheets_manager import sheets_manager
from ..database.database_manager import db_manager

sync_manager = SyncManager(sheets_manager, db_manager)

# Экспортируем функции для обратной совместимости
async def full_sync():
    return await sync_manager.full_sync()

async def sync_db_to_sheets():
    return await sync_manager.sync_db_to_sheets()

async def initialize_all_sheets():
    return await sync_manager.initialize_all_sheets()
