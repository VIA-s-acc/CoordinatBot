"""
Кеширование данных о листах Google Sheets для быстрого доступа
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from ..config.settings import logger


class SheetsCache:
    """Класс для кеширования данных о листах"""
    
    def __init__(self, cache_duration_minutes: int = 30):
        self.cache_duration = timedelta(minutes=cache_duration_minutes)
        self.lock = threading.Lock()
        
        # Кеш для листов (spreadsheet_id -> (sheets_info, spreadsheet_title, timestamp))
        self._sheets_cache: Dict[str, Tuple[List[Dict], str, datetime]] = {}
        
        # Кеш для списка таблиц (spreadsheets, timestamp)
        self._spreadsheets_cache: Optional[Tuple[List[Dict], datetime]] = None
        
        # Пул потоков для асинхронной загрузки
        self._executor = ThreadPoolExecutor(max_workers=2)
        
        logger.info(f"Sheets cache initialized with refresh period of {cache_duration_minutes} minutes")
    
    def _is_cache_expired(self, timestamp: datetime) -> bool:
        """Проверяет, устарел ли кеш"""
        return datetime.now() - timestamp > self.cache_duration
    
    def _load_sheets_info_sync(self, spreadsheet_id: str) -> Tuple[List[Dict], str]:
        """Синхронная загрузка данных о листах"""
        try:
            # Ленивый импорт для избежания циклических зависимостей
            from ..google_integration.sheets_manager import get_worksheets_info
            
            logger.info(f"Loading sheets data for {spreadsheet_id}")
            return get_worksheets_info(spreadsheet_id)
            
        except Exception as e:
            logger.error(f"Error loading sheets data for {spreadsheet_id}: {e}")
            return [], "Ошибка загрузки"
    
    def _load_spreadsheets_sync(self) -> List[Dict]:
        """Синхронная загрузка списка таблиц"""
        try:
            # Ленивый импорт для избежания циклических зависимостей
            from ..google_integration.sheets_manager import get_all_spreadsheets
            
            logger.info("Loading list of spreadsheets")
            return get_all_spreadsheets()
            
        except Exception as e:
            logger.error(f"Error loading list of spreadsheets: {e}")
            return []
    
    def get_sheets_info(self, spreadsheet_id: str, force_refresh: bool = False) -> Tuple[List[Dict], str]:
        """
        Получает информацию о листах из кеша или API
        
        Args:
            spreadsheet_id: ID таблицы
            force_refresh: принудительное обновление кеша
            
        Returns:
            Tuple[List[Dict], str]: (sheets_info, spreadsheet_title)
        """
        with self.lock:
            # Проверяем кеш
            if not force_refresh and spreadsheet_id in self._sheets_cache:
                sheets_info, spreadsheet_title, timestamp = self._sheets_cache[spreadsheet_id]
                
                if not self._is_cache_expired(timestamp):
                    logger.debug(f"Returning sheets data from cache for {spreadsheet_id}")
                    return sheets_info, spreadsheet_title
                else:
                    logger.debug(f"Cache expired for {spreadsheet_id}, refreshing...")
            
            # Получаем данные из API с тайм-аутом
            try:
                # Используем пул потоков с тайм-аутом 10 секунд
                future = self._executor.submit(self._load_sheets_info_sync, spreadsheet_id)
                sheets_info, spreadsheet_title = future.result(timeout=10)
                
                # Сохраняем в кеш
                self._sheets_cache[spreadsheet_id] = (sheets_info, spreadsheet_title, datetime.now())
                
                logger.info(f"Sheets data cached for {spreadsheet_id}: {len(sheets_info)} sheets")
                return sheets_info, spreadsheet_title
                
            except FutureTimeoutError:
                logger.warning(f"Timeout while loading sheets data for {spreadsheet_id}")
                
                # Если есть устаревший кеш, возвращаем его
                if spreadsheet_id in self._sheets_cache:
                    sheets_info, spreadsheet_title, _ = self._sheets_cache[spreadsheet_id]
                    logger.warning(f"Returning expired cache for {spreadsheet_id}")
                    return sheets_info, spreadsheet_title
                
                # Если кеша нет, возвращаем пустые данные
                return [], "Таблица недоступна"
                
            except Exception as e:
                logger.error(f"Error loading sheets data for {spreadsheet_id}: {e}")
                
                # Если есть устаревший кеш, возвращаем его
                if spreadsheet_id in self._sheets_cache:
                    sheets_info, spreadsheet_title, _ = self._sheets_cache[spreadsheet_id]
                    logger.warning(f"Returning expired cache for {spreadsheet_id}")
                    return sheets_info, spreadsheet_title
                
                # Если кеша нет, возвращаем пустые данные
                return [], "Неизвестная таблица"
    
    def get_spreadsheets(self, force_refresh: bool = False) -> List[Dict]:
        """
        Получает список таблиц из кеша или API
        
        Args:
            force_refresh: принудительное обновление кеша
            
        Returns:
            List[Dict]: список таблиц
        """
        with self.lock:
            # Проверяем кеш
            if not force_refresh and self._spreadsheets_cache:
                spreadsheets, timestamp = self._spreadsheets_cache
                
                if not self._is_cache_expired(timestamp):
                    logger.debug("Returning list of spreadsheets from cache")
                    return spreadsheets
                else:
                    logger.debug("Spreadsheets cache expired, refreshing...")
            
            # Получаем данные из API с тайм-аутом
            try:
                # Используем пул потоков с тайм-аутом 10 секунд
                future = self._executor.submit(self._load_spreadsheets_sync)
                spreadsheets = future.result(timeout=10)
                
                # Сохраняем в кеш
                self._spreadsheets_cache = (spreadsheets, datetime.now())
                
                logger.info(f"Spreadsheets list cached: {len(spreadsheets)} spreadsheets")
                return spreadsheets
                
            except FutureTimeoutError:
                logger.warning("Timeout while loading list of spreadsheets")
                
                # Если есть устаревший кеш, возвращаем его
                if self._spreadsheets_cache:
                    spreadsheets, _ = self._spreadsheets_cache
                    logger.warning("Returning expired spreadsheets cache")
                    return spreadsheets
                
                # Если кеша нет, возвращаем пустой список
                return []
                
            except Exception as e:
                logger.error(f"Error loading list of spreadsheets: {e}")
                
                # Если есть устаревший кеш, возвращаем его
                if self._spreadsheets_cache:
                    spreadsheets, _ = self._spreadsheets_cache
                    logger.warning("Returning expired spreadsheets cache")
                    return spreadsheets
                
                # Если кеша нет, возвращаем пустой список
                return []
    
    def invalidate_sheets_cache(self, spreadsheet_id: str):
        """Инвалидирует кеш для конкретной таблицы"""
        with self.lock:
            if spreadsheet_id in self._sheets_cache:
                del self._sheets_cache[spreadsheet_id]
                logger.info(f"Cache invalidated for {spreadsheet_id}")
    
    def invalidate_spreadsheets_cache(self):
        """Инвалидирует кеш списка таблиц"""
        with self.lock:
            self._spreadsheets_cache = None
            logger.info("Spreadsheets cache invalidated")
    
    def clear_cache(self):
        """Очищает весь кеш"""
        with self.lock:
            self._sheets_cache.clear()
            self._spreadsheets_cache = None
            logger.info("Entire cache cleared")
    
    def shutdown(self):
        """Корректно завершает работу кеша"""
        if hasattr(self, '_executor') and self._executor:
            self._executor.shutdown(wait=True)
            logger.info("Cache shutdown completed successfully")
    
    def get_cache_stats(self) -> Dict:
        """Возвращает статистику кеша"""
        with self.lock:
            stats = {
                "sheets_cached": len(self._sheets_cache),
                "spreadsheets_cached": 1 if self._spreadsheets_cache else 0,
                "cache_duration_minutes": self.cache_duration.total_seconds() / 60
            }
            
            # Добавляем информацию о времени последнего обновления
            if self._spreadsheets_cache:
                _, timestamp = self._spreadsheets_cache
                stats["spreadsheets_last_updated"] = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            
            sheets_info = []
            for spreadsheet_id, (sheets, title, timestamp) in self._sheets_cache.items():
                sheets_info.append({
                    "spreadsheet_id": spreadsheet_id,
                    "title": title,
                    "sheets_count": len(sheets),
                    "last_updated": timestamp.strftime("%Y-%m-%d %H:%M:%S")
                })
            
            stats["sheets_info"] = sheets_info
            return stats

# Глобальный экземпляр кеша (ленивая инициализация)
_sheets_cache_instance = None

def _get_cache_instance():
    """Получает экземпляр кеша с ленивой инициализацией"""
    global _sheets_cache_instance
    if _sheets_cache_instance is None:
        _sheets_cache_instance = SheetsCache()
    return _sheets_cache_instance

# Функции-обертки для удобства использования
def get_cached_sheets_info(spreadsheet_id: str, force_refresh: bool = False) -> Tuple[List[Dict], str]:
    """Получает информацию о листах из кеша"""
    return _get_cache_instance().get_sheets_info(spreadsheet_id, force_refresh)

def get_cached_spreadsheets(force_refresh: bool = False) -> List[Dict]:
    """Получает список таблиц из кеша"""
    return _get_cache_instance().get_spreadsheets(force_refresh)

def invalidate_sheets_cache(spreadsheet_id: str):
    """Инвалидирует кеш для конкретной таблицы"""
    _get_cache_instance().invalidate_sheets_cache(spreadsheet_id)

def invalidate_spreadsheets_cache():
    """Инвалидирует кеш списка таблиц"""
    _get_cache_instance().invalidate_spreadsheets_cache()

def clear_all_cache():
    """Очищает весь кеш"""
    _get_cache_instance().clear_cache()

def get_cache_statistics() -> Dict:
    """Возвращает статистику кеша"""
    return _get_cache_instance().get_cache_stats()
