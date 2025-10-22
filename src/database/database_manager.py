"""
Модуль для работы с базой данных
"""
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from ..config.settings import DATABASE_PATH

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Класс для управления базой данных"""
    
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
    
    def init_db(self) -> bool:
        """Инициализация базы данных и миграция схемы"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Создание таблиц, если не существуют
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    date TEXT NOT NULL,
                    supplier TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    description TEXT NOT NULL,
                    amount REAL NOT NULL,
                    spreadsheet_id TEXT,
                    sheet_name TEXT,
                    user_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_display_name TEXT NOT NULL,
                    spreadsheet_id TEXT,
                    sheet_name TEXT,
                    amount REAL NOT NULL,
                    date_from TEXT,
                    date_to TEXT,
                    comment TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # --- Миграция: добавление user_id, если его нет ---
            cursor.execute("PRAGMA table_info(records)")
            columns = [row[1] for row in cursor.fetchall()]
            if "user_id" not in columns:
                cursor.execute("ALTER TABLE records ADD COLUMN user_id INTEGER")
                logger.info("Миграция: добавлен столбец user_id в таблицу records")

            conn.commit()
            conn.close()
            logger.info("База данных инициализирована и миграция выполнена успешно")
            return True

        except Exception as e:
            logger.error(f"Ошибка инициализации/миграции базы данных: {e}")
            return False

    def add_record(self, record: Dict) -> bool:
        """Добавляет запись в базу данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO records (
                    id, date, supplier, direction, description, amount,
                    spreadsheet_id, sheet_name, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                record.get('id'),
                record.get('date'),
                record.get('supplier'),
                record.get('direction'),
                record.get('description'),
                record.get('amount', 0),
                record.get('spreadsheet_id'),
                record.get('sheet_name'),
                record.get('user_id')
            ))

            conn.commit()
            conn.close()
            logger.info(f"Запись {record.get('id')} добавлена в БД")
            return True

        except Exception as e:
            logger.error(f"Ошибка добавления записи в БД: {e}")
            return False

    def update_record(self, record_id: str, field: str, new_value) -> bool:
        """Обновляет запись в базе данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            allowed_fields = ['date', 'supplier', 'direction', 'description', 'amount']
            if field not in allowed_fields:
                logger.error(f"Недопустимое поле для обновления: {field}")
                return False
            
            cursor.execute(f'''
                UPDATE records 
                SET {field} = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (new_value, record_id))
            
            conn.commit()
            conn.close()
            logger.info(f"Запись {record_id} обновлена: {field} = {new_value}")
            return True

        except Exception as e:
            logger.error(f"Ошибка обновления записи в БД: {e}")
            return False

    def delete_record(self, record_id: str) -> bool:
        """Удаляет запись из базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM records WHERE id = ?', (record_id,))
            
            conn.commit()
            conn.close()
            logger.info(f"Запись {record_id} удалена из БД")
            return True

        except Exception as e:
            logger.error(f"Ошибка удаления записи из БД: {e}")
            return False

    def get_record(self, record_id: str) -> Optional[Dict]:
        """Получает запись по ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM records WHERE id = ?', (record_id,))
            row = cursor.fetchone()
            
            conn.close()
            
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return None

        except Exception as e:
            logger.error(f"Ошибка получения записи из БД: {e}")
            return None

    def get_all_records(self, limit: Optional[int] = None) -> List[Dict]:
        """Получает все записи из базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            query = 'SELECT * FROM records ORDER BY created_at DESC'
            if limit:
                query += f' LIMIT {limit}'
            
            cursor.execute(query)
            rows = cursor.fetchall()
            
            if rows:
                columns = [desc[0] for desc in cursor.description]
                records = [dict(zip(columns, row)) for row in rows]
            else:
                records = []
            
            conn.close()
            return records

        except Exception as e:
            logger.error(f"Ошибка получения записей из БД: {e}")
            return []

    def search_records(self, query: str) -> List[Dict]:
        """Поиск записей по тексту"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            search_query = f'%{query}%'
            cursor.execute('''
                SELECT * FROM records 
                WHERE supplier LIKE ? OR direction LIKE ? OR description LIKE ?
                ORDER BY created_at DESC
                LIMIT 25
            ''', (search_query, search_query, search_query))
            
            rows = cursor.fetchall()
            
            if rows:
                columns = [desc[0] for desc in cursor.description]
                records = [dict(zip(columns, row)) for row in rows]
            else:
                records = []
            
            conn.close()
            return records

        except Exception as e:
            logger.error(f"Ошибка поиска записей в БД: {e}")
            return []

    def get_db_stats(self) -> Optional[Dict]:
        """Получает статистику базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT COUNT(*), SUM(amount) FROM records')
            count, total_amount = cursor.fetchone()
            
            conn.close()
            
            return {
                'total_records': count or 0,
                'total_amount': total_amount or 0
            }

        except Exception as e:
            logger.error(f"Ошибка получения статистики БД: {e}")
            return None

    def backup_to_dict(self) -> Optional[Dict]:
        """Создает резервную копию базы данных в виде словаря"""
        try:
            records = self.get_all_records()
            stats = self.get_db_stats()
            
            return {
                'backup_date': datetime.now().isoformat(),
                'records': records,
                'stats': stats
            }

        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            return None

    def get_user_id_by_record_id(self, record_id: str) -> Optional[int]:
        """Получает ID пользователя по ID записи"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT user_id FROM records WHERE id = ?', (record_id,))
            result = cursor.fetchone()
            
            conn.close()
            
            return result[0] if result else None

        except Exception as e:
            logger.error(f"Ошибка получения user_id для записи {record_id}: {e}")
            return None

    # Методы для работы с платежами
    def add_payment(self, user_display_name: str, spreadsheet_id: str = None,
                   sheet_name: str = None, amount: float = 0,
                   date_from: str = None, date_to: str = None,
                   comment: str = None) -> int:
        """
        Добавляет платеж

        Returns:
            ID добавленного платежа или 0 в случае ошибки
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO payments (
                    user_display_name, spreadsheet_id, sheet_name, amount,
                    date_from, date_to, comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_display_name, spreadsheet_id, sheet_name, amount,
                  date_from, date_to, comment))

            payment_id = cursor.lastrowid
            conn.commit()
            conn.close()
            logger.info(f"Платеж #{payment_id} добавлен: {amount} для {user_display_name}")
            return payment_id

        except Exception as e:
            logger.error(f"Ошибка добавления платежа: {e}")
            return 0

    def add_payments_batch(self, payments: List[Dict]) -> int:
        """
        Выполняет груповую вставку платежей в таблицу payments.

        Args:
            payments: список словарей с ключами user_display_name, spreadsheet_id, sheet_name,
                      amount, date_from, date_to, comment

        Returns:
            Количество успешно вставленных записей.
        """
        if not payments:
            return 0

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            values = []
            for p in payments:
                values.append((
                    p.get('user_display_name'),
                    p.get('spreadsheet_id'),
                    p.get('sheet_name'),
                    p.get('amount', 0),
                    p.get('date_from'),
                    p.get('date_to'),
                    p.get('comment')
                ))

            cursor.executemany('''
                INSERT INTO payments (
                    user_display_name, spreadsheet_id, sheet_name, amount,
                    date_from, date_to, comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', values)

            inserted = cursor.rowcount if cursor.rowcount != -1 else len(values)
            conn.commit()
            conn.close()

            logger.info(f"Групповая вставка платежей: добавлено {inserted} записей")
            return inserted

        except Exception as e:
            logger.error(f"Ошибка групповой вставки платежей: {e}")
            return 0

    def get_payments(self, user_display_name: str = None, spreadsheet_id: str = None,
                    sheet_name: str = None) -> List[Dict]:
        """
        Получает платежи пользователя или все платежи
        Если параметры не указаны, возвращает все платежи
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if user_display_name and spreadsheet_id and sheet_name:
                # Получаем платежи конкретного пользователя
                cursor.execute('''
                    SELECT id, user_display_name, spreadsheet_id, sheet_name,
                           amount, date_from, date_to, comment, created_at
                    FROM payments
                    WHERE user_display_name = ? AND spreadsheet_id = ? AND sheet_name = ?
                    ORDER BY created_at DESC
                ''', (user_display_name, spreadsheet_id, sheet_name))
            else:
                # Получаем все платежи
                cursor.execute('''
                    SELECT id, user_display_name, spreadsheet_id, sheet_name,
                           amount, date_from, date_to, comment, created_at
                    FROM payments
                    ORDER BY created_at DESC
                ''')

            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
            conn.close()
            return result

        except Exception as e:
            logger.error(f"Ошибка получения платежей: {e}")
            return []

    def get_records_by_period(self, start_date: str, end_date: str) -> List[Dict]:
        """Получает записи за указанный период"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM records 
                WHERE date >= ? AND date <= ?
                ORDER BY created_at DESC
            ''', (start_date, end_date))
            
            rows = cursor.fetchall()
            
            if rows:
                columns = [desc[0] for desc in cursor.description]
                records = [dict(zip(columns, row)) for row in rows]
            else:
                records = []
            
            conn.close()
            return records

        except Exception as e:
            logger.error(f"Ошибка получения записей за период: {e}")
            return []

    def remove_duplicate_records(self) -> int:
        """Удаляет дублированные записи, оставляя самые новые по updated_at"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Находим дублированные записи по id
            cursor.execute('''
                SELECT id, COUNT(*) as count 
                FROM records 
                GROUP BY id 
                HAVING COUNT(*) > 1
            ''')
            
            duplicates = cursor.fetchall()
            logger.info(f"Найдено {len(duplicates)} дублированных ID")
            
            removed_count = 0
            
            for record_id, count in duplicates:
                # Получаем все записи с этим ID, сортируем по updated_at
                cursor.execute('''
                    SELECT rowid, updated_at 
                    FROM records 
                    WHERE id = ? 
                    ORDER BY updated_at DESC
                ''', (record_id,))
                
                rows = cursor.fetchall()
                
                # Оставляем только первую (самую новую), удаляем остальные
                if len(rows) > 1:
                    rows_to_delete = [row[0] for row in rows[1:]]  # Все кроме первой
                    
                    for rowid in rows_to_delete:
                        cursor.execute('DELETE FROM records WHERE rowid = ?', (rowid,))
                        removed_count += 1
                        logger.info(f"Удален дубликат записи {record_id}, rowid={rowid}")
            
            conn.commit()
            conn.close()
            
            logger.info(f"Удалено {removed_count} дублированных записей")
            return removed_count

        except Exception as e:
            logger.error(f"Ошибка удаления дублированных записей: {e}")
            return 0

# Создаем глобальный экземпляр менеджера базы данных
db_manager = DatabaseManager()

# Экспортируем функции для обратной совместимости
def init_db():
    return db_manager.init_db()

def add_record_to_db(record: Dict) -> bool:
    return db_manager.add_record(record)

def update_record_in_db(record_id: str, field: str, new_value) -> bool:
    return db_manager.update_record(record_id, field, new_value)

def delete_record_from_db(record_id: str) -> bool:
    return db_manager.delete_record(record_id)

def get_record_from_db(record_id: str) -> Optional[Dict]:
    return db_manager.get_record(record_id)

def get_all_records(limit: Optional[int] = None) -> List[Dict]:
    return db_manager.get_all_records(limit)

def search_records(query: str) -> List[Dict]:
    return db_manager.search_records(query)

def get_db_stats() -> Optional[Dict]:
    return db_manager.get_db_stats()

def backup_db_to_dict() -> Optional[Dict]:
    return db_manager.backup_to_dict()

def get_user_id_by_record_id(record_id: str) -> Optional[int]:
    return db_manager.get_user_id_by_record_id(record_id)

def add_payment(user_display_name: str, spreadsheet_id: str = None,
               sheet_name: str = None, amount: float = 0,
               date_from: str = None, date_to: str = None,
               comment: str = None) -> int:
    """
    Добавляет платеж в БД и синхронизирует с Google Sheets

    Returns:
        ID добавленного платежа или 0 в случае ошибки
    """
    # Добавляем в БД
    payment_id = db_manager.add_payment(
        user_display_name, spreadsheet_id, sheet_name,
        amount, date_from, date_to, comment
    )

    if payment_id > 0:
        # Синхронизируем с Google Sheets
        try:
            from ..google_integration.payments_sync_manager import PaymentsSyncManager
            from ..utils.config_utils import get_user_role

            # Определяем роль пользователя по display_name
            # TODO: улучшить определение роли
            role = get_user_role(0)  # Временное решение
            if not role:
                from ..config.settings import UserRole
                role = UserRole.WORKER  # По умолчанию

            sync_manager = PaymentsSyncManager()
            sync_manager.sync_payment_to_sheets(
                payment_id=payment_id,
                user_display_name=user_display_name,
                amount=amount,
                role=role,
                date_from=date_from,
                date_to=date_to,
                comment=comment,
                target_spreadsheet_id=spreadsheet_id,
                target_sheet_name=sheet_name
            )
        except Exception as e:
            logger.error(f"Ошибка синхронизации платежа #{payment_id} с Google Sheets: {e}")

    return payment_id

def get_payments(user_display_name: str = None, spreadsheet_id: str = None,
                sheet_name: str = None) -> List[Dict]:
    """Получает платежи пользователя или все платежи"""
    return db_manager.get_payments(user_display_name, spreadsheet_id, sheet_name)

def get_records_by_period(start_date: str, end_date: str) -> List[Dict]:
    """Получает записи за указанный период"""
    return db_manager.get_records_by_period(start_date, end_date)

def remove_duplicate_records() -> int:
    """Удаляет дублированные записи из базы данных"""
    return db_manager.remove_duplicate_records()
