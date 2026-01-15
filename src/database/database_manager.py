"""
Модуль для работы с базой данных
"""
import sqlite3
from datetime import datetime
from typing import Dict, Optional, List, Tuple
from ..config.settings import DATABASE_PATH, logger


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
                logger.info("Migration: added user_id column to records table")

            conn.commit()
            conn.close()
            logger.info("Database initialized and migration completed successfully")
            return True

        except Exception as e:
            logger.error(f"Error initializing/migrating database: {e}")
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
            logger.info(f"Record {record.get('id')} added to DB")
            return True

        except Exception as e:
            logger.error(f"Error adding record to DB: {e}")
            return False

    def update_record(self, record_id: str, field: str, new_value) -> bool:
        """Обновляет запись в базе данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            allowed_fields = ['date', 'supplier', 'direction', 'description', 'amount']
            if field not in allowed_fields:
                logger.error(f"Invalid field for update: {field}")
                return False
            
            cursor.execute(f'''
                UPDATE records 
                SET {field} = ?, updated_at = CURRENT_TIMESTAMP 
                WHERE id = ?
            ''', (new_value, record_id))
            
            conn.commit()
            conn.close()
            logger.info(f"Record {record_id} updated: {field} = {new_value}")
            return True

        except Exception as e:
            logger.error(f"Error updating record in DB: {e}")
            return False

    def delete_record(self, record_id: str) -> bool:
        """Удаляет запись из базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM records WHERE id = ?', (record_id,))
            
            conn.commit()
            conn.close()
            logger.info(f"Record {record_id} deleted from DB")
            return True

        except Exception as e:
            logger.error(f"Error deleting record from DB: {e}")
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
            logger.error(f"Error getting record from DB: {e}")
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
            logger.error(f"Error getting records from DB: {e}")
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
            logger.error(f"Error searching records in DB: {e}")
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
            logger.error(f"Error getting DB statistics: {e}")
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
            logger.error(f"Error creating backup: {e}")
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
            logger.error(f"Error getting user_id for record {record_id}: {e}")
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
            logger.info(f"Payment #{payment_id} added: {amount} for {user_display_name}")
            return payment_id

        except Exception as e:
            logger.error(f"Error adding payment: {e}")
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

            logger.info(f"Batch payment insertion: {inserted} records added")
            return inserted

        except Exception as e:
            logger.error(f"Error in batch payment insertion: {e}")
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

            # Формируем WHERE условия динамически
            conditions = []
            params = []

            if user_display_name:
                conditions.append("user_display_name = ?")
                params.append(user_display_name)

            if spreadsheet_id:
                conditions.append("spreadsheet_id = ?")
                params.append(spreadsheet_id)

            if sheet_name:
                conditions.append("sheet_name = ?")
                params.append(sheet_name)

            query = '''
                SELECT id, user_display_name, spreadsheet_id, sheet_name,
                       amount, date_from, date_to, comment, created_at
                FROM payments
            '''

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY created_at DESC"

            cursor.execute(query, params)

            rows = cursor.fetchall()
            result = [dict(row) for row in rows]
            conn.close()
            return result

        except Exception as e:
            logger.error(f"Error getting payments: {e}")
            return []

    def delete_payment(self, payment_id: int) -> bool:
        """
        Удаляет платеж из БД

        Args:
            payment_id: ID платежа для удаления

        Returns:
            True если успешно, False если ошибка
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute('DELETE FROM payments WHERE id = ?', (payment_id,))
            deleted = cursor.rowcount > 0

            conn.commit()
            conn.close()

            if deleted:
                logger.info(f"Payment #{payment_id} deleted from DB")
            else:
                logger.warning(f"Payment #{payment_id} not found in DB")

            return deleted

        except Exception as e:
            logger.error(f"Error deleting payment #{payment_id}: {e}")
            return False

    def update_payment(self, payment_id: int, amount: float = None,
                      date_from: str = None, date_to: str = None,
                      comment: str = None) -> bool:
        """
        Обновляет платеж в БД

        Args:
            payment_id: ID платежа для обновления
            amount: Новая сумма (опционально)
            date_from: Новая дата начала (опционально)
            date_to: Новая дата окончания (опционально)
            comment: Новый комментарий (опционально)

        Returns:
            True если успешно, False если ошибка
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Формируем запрос только для изменяемых полей
            updates = []
            params = []

            if amount is not None:
                updates.append("amount = ?")
                params.append(amount)
            if date_from is not None:
                updates.append("date_from = ?")
                params.append(date_from)
            if date_to is not None:
                updates.append("date_to = ?")
                params.append(date_to)
            if comment is not None:
                updates.append("comment = ?")
                params.append(comment)

            if not updates:
                logger.warning(f"Nothing to update for payment #{payment_id}")
                conn.close()
                return False

            params.append(payment_id)
            query = f"UPDATE payments SET {', '.join(updates)} WHERE id = ?"

            cursor.execute(query, params)
            updated = cursor.rowcount > 0

            conn.commit()
            conn.close()

            if updated:
                logger.info(f"Payment #{payment_id} updated in DB")
            else:
                logger.warning(f"Payment #{payment_id} not found in DB")

            return updated

        except Exception as e:
            logger.error(f"Error updating payment #{payment_id}: {e}")
            return False

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
            logger.error(f"Error getting records for period: {e}")
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
            logger.info(f"Found {len(duplicates)} duplicated IDs")
            
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
                        logger.info(f"Deleted duplicate record {record_id}, rowid={rowid}")
            
            conn.commit()
            conn.close()
            
            logger.info(f"Deleted {removed_count} duplicate records")
            return removed_count

        except Exception as e:
            logger.error(f"Error deleting duplicate records: {e}")
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
        # Синхронизируем с Google Sheets через async worker
        try:
            from ..google_integration.async_sheets_worker import add_payment_async

            # Определяем роль пользователя по display_name
            role = get_role_by_display_name(user_display_name)

            # Добавляем задачу в очередь async worker
            add_payment_async(
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
            logger.info(f"Payment #{payment_id} added to queue for synchronization with Google Sheets (role: {role})")
        except Exception as e:
            logger.error(f"Error queuing payment synchronization task #{payment_id}: {e}")

    return payment_id

def get_payments(user_display_name: str = None, spreadsheet_id: str = None,
                sheet_name: str = None) -> List[Dict]:
    """Получает платежи пользователя или все платежи"""
    return db_manager.get_payments(user_display_name, spreadsheet_id, sheet_name)

def get_role_by_display_name(display_name: str) -> str:
    """
    Определяет роль пользователя по display_name

    Args:
        display_name: Отображаемое имя пользователя

    Returns:
        Роль пользователя или UserRole.WORKER по умолчанию
    """
    from ..utils.config_utils import load_users
    from ..config.settings import UserRole

    users = load_users()
    for user_id_str, user_data in users.items():
        if user_data.get('display_name') == display_name:
            return user_data.get('role', UserRole.WORKER)
    return UserRole.WORKER


def delete_payment(payment_id: int) -> bool:
    """
    Удаляет платеж из БД и из Google Sheets

    Args:
        payment_id: ID платежа для удаления

    Returns:
        True если успешно удален из БД
    """
    # Сначала получаем информацию о платеже для удаления из Sheets
    try:
        from ..google_integration.async_sheets_worker import delete_payment_async

        # Получаем информацию о платеже перед удалением
        all_payments = db_manager.get_payments()
        payment = next((p for p in all_payments if p['id'] == payment_id), None)

        # Определяем роль по display_name
        role = get_role_by_display_name(payment['user_display_name']) if payment else None

        # Удаляем из БД
        success = db_manager.delete_payment(payment_id)

        if success and role:
            # Добавляем задачу на удаление из Google Sheets
            delete_payment_async(payment_id=payment_id, role=role)
            logger.info(f"Payment #{payment_id} added to queue for deletion from Google Sheets (role: {role})")

        return success

    except Exception as e:
        logger.error(f"Error deleting payment #{payment_id}: {e}")
        return False

def update_payment(payment_id: int, amount: float = None,
                  date_from: str = None, date_to: str = None,
                  comment: str = None) -> bool:
    """
    Обновляет платеж в БД и синхронизирует с Google Sheets через async worker

    Args:
        payment_id: ID платежа
        amount: Новая сумма
        date_from: Новая дата начала
        date_to: Новая дата окончания
        comment: Новый комментарий

    Returns:
        True если успешно
    """
    from ..google_integration.async_sheets_worker import update_payment_async

    try:
        # Получаем информацию о платеже для определения роли
        all_payments = db_manager.get_payments()
        payment = next((p for p in all_payments if p['id'] == payment_id), None)

        if not payment:
            logger.error(f"Payment #{payment_id} not found")
            return False

        # Определяем роль по display_name
        role = get_role_by_display_name(payment['user_display_name'])

        # Обновляем в БД
        success = db_manager.update_payment(payment_id, amount, date_from, date_to, comment)

        if success and role:
            # Формируем словарь с обновленными данными
            updated_data = {}
            if amount is not None:
                updated_data['amount'] = amount
            if date_from is not None:
                updated_data['date_from'] = date_from
            if date_to is not None:
                updated_data['date_to'] = date_to
            if comment is not None:
                updated_data['comment'] = comment

            # Добавляем задачу на обновление в Google Sheets
            update_payment_async(payment_id=payment_id, role=role, updated_data=updated_data)
            logger.info(f"Payment #{payment_id} updated and added to queue for synchronization with Google Sheets (role: {role})")

        return success

    except Exception as e:
        logger.error(f"Error updating payment #{payment_id}: {e}")
        return False

def get_records_by_period(start_date: str, end_date: str) -> List[Dict]:
    """Получает записи за указанный период"""
    return db_manager.get_records_by_period(start_date, end_date)

def remove_duplicate_records() -> int:
    """Удаляет дублированные записи из базы данных"""
    return db_manager.remove_duplicate_records()
