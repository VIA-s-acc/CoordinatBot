import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# Путь к базе данных
DB_PATH = 'expenses.db'

def init_db():
    """Инициализация базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Добавлено: spreadsheet_id и sheet_name
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_display_name TEXT NOT NULL,
                spreadsheet_id TEXT,
                amount REAL NOT NULL,
                date_from TEXT,
                date_to TEXT,
                comment TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()
        logger.info("База данных инициализирована успешно")
        return True

    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        return False


def add_record_to_db(record: Dict) -> bool:
    """Добавляет запись в базу данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO records (
                id, date, supplier, direction, description, amount,
                spreadsheet_id, sheet_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            record.get('id'),
            record.get('date'),
            record.get('supplier'),
            record.get('direction'),
            record.get('description'),
            record.get('amount', 0),
            record.get('spreadsheet_id'),
            record.get('sheet_name')
        ))

        conn.commit()
        conn.close()
        logger.info(f"Запись {record.get('id')} добавлена в БД")
        return True

    except Exception as e:
        logger.error(f"Ошибка добавления записи в БД: {e}")
        return False


def update_record_in_db(record_id: str, field: str, new_value) -> bool:
    """Обновляет запись в базе данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем допустимые поля
        allowed_fields = ['date', 'supplier', 'direction', 'description', 'amount']
        if field not in allowed_fields:
            logger.error(f"Недопустимое поле для обновления: {field}")
            return False
        
        # Обновляем запись
        query = f"UPDATE records SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        cursor.execute(query, (new_value, record_id))
        
        if cursor.rowcount == 0:
            logger.warning(f"Запись с ID {record_id} не найдена в БД")
            conn.close()
            return False
        
        conn.commit()
        conn.close()
        logger.info(f"Запись {record_id} обновлена в БД: {field} = {new_value}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка обновления записи в БД: {e}")
        return False

def delete_record_from_db(record_id: str) -> bool:
    """Удаляет запись из базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
        
        if cursor.rowcount == 0:
            logger.warning(f"Запись с ID {record_id} не найдена в БД для удаления")
            conn.close()
            return False
        
        conn.commit()
        conn.close()
        logger.info(f"Запись {record_id} удалена из БД")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка удаления записи из БД: {e}")
        return False

def get_record_from_db(record_id: str) -> Optional[Dict]:
    """Получает запись из базы данных по ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, date, supplier, direction, description, amount,
                   spreadsheet_id, sheet_name, created_at, updated_at
            FROM records WHERE id = ?
        ''', (record_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'id': row[0],
                'date': row[1],
                'supplier': row[2],
                'direction': row[3],
                'description': row[4],
                'amount': row[5],
                'spreadsheet_id': row[6],
                'sheet_name': row[7],
                'created_at': row[8],
                'updated_at': row[9]
            }

        return None

    except Exception as e:
        logger.error(f"Ошибка получения записи из БД: {e}")
        return None


def get_db_stats() -> Optional[Dict]:
    """Получает статистику базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Общее количество записей
        cursor.execute("SELECT COUNT(*) FROM records")
        total_records = cursor.fetchone()[0]
        
        # Общая сумма
        cursor.execute("SELECT SUM(amount) FROM records")
        total_amount = cursor.fetchone()[0] or 0
        
        # Записи за последние 30 дней
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        cursor.execute("SELECT COUNT(*) FROM records WHERE date >= ?", (thirty_days_ago,))
        recent_records = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_records': total_records,
            'total_amount': total_amount,
            'recent_records': recent_records
        }
        
    except Exception as e:
        logger.error(f"Ошибка получения статистики БД: {e}")
        return None

def get_all_records(limit: int = 1000000) -> List[Dict]:
    """Получает все записи из базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, date, supplier, direction, description, amount, created_at, updated_at, spreadsheet_id, sheet_name
            FROM records 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        records = []
        for row in rows:
            
            records.append({
                'id': row[0],
                'date': row[1],
                'supplier': row[2],
                'direction': row[3],
                'description': row[4],
                'amount': row[5],
                'created_at': row[6],
                'updated_at': row[7],
                'spreadsheet_id': row[8],
                'sheet_name': row[9]
            })
        
        return records
        
    except Exception as e:
        logger.error(f"Ошибка получения записей из БД: {e}")
        return []

def search_records(query: str, limit: int = 50) -> List[Dict]:
    """
    Поиск записей по тексту (supplier, direction, description)
    с сортировкой по полю 'date' (в порядке убывания)
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if query.isdigit():
            search_query = float(query)
        else:
            search_query = f"%{query}%"

        cursor.execute('''
            SELECT id, date, supplier, direction, description, amount, created_at, updated_at, spreadsheet_id, sheet_name
            FROM records 
            WHERE supplier LIKE ? OR direction LIKE ? OR description LIKE ? OR amount LIKE ?
            ORDER BY
                CAST('20' || substr(date, -2) AS INTEGER) DESC,  -- год
                CAST(substr(date, instr(date, '.') + 1, 2) AS INTEGER) DESC,  -- месяц
                CAST(substr(date, 1, instr(date, '.') - 1) AS INTEGER) DESC  -- день
            LIMIT ?
        ''', (search_query, search_query, search_query, search_query, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        records = []
        for row in rows:
            records.append({
                'id': row[0],
                'date': row[1],
                'supplier': row[2],
                'direction': row[3],
                'description': row[4],
                'amount': row[5],
                'created_at': row[6],
                'updated_at': row[7],
                'spreadsheet_id': row[8],
                'sheet_name': row[9]
            })
        
        return records

    except Exception as e:
        logger.error(f"Ошибка поиска записей в БД: {e}")
        return []


def backup_db_to_dict() -> Optional[Dict]:
    """Создает резервную копию базы данных в виде словаря"""
    try:
        records = get_all_records(limit=100000)  # Получаем все записи
        stats = get_db_stats()
        
        return {
            'backup_date': datetime.now().isoformat(),
            'stats': stats,
            'records': records
        }
        
    except Exception as e:
        logger.error(f"Ошибка создания резервной копии БД: {e}")
        return None

def add_payment(user_display_name, spreadsheet_id, sheet_name, amount, date_from, date_to, comment):
    """Добавляет выплату в базу данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO payments (user_display_name, spreadsheet_id, sheet_name, amount, date_from, date_to, comment)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_display_name, spreadsheet_id, None, amount, date_from, date_to, comment))
        conn.commit()
        conn.close()
        logger.info(f"Выплата добавлена: {user_display_name}, {spreadsheet_id}, {sheet_name}, {amount}")
        return True
    except Exception as e:
        logger.error(f"Ошибка добавления выплаты: {e}")
        return False

def get_payments(user_display_name, spreadsheet_id=None, sheet_name=None):
    """Получает все выплаты пользователя (по желанию по таблице и листу)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        query = '''
            SELECT amount, date_from, date_to, comment, created_at
            FROM payments WHERE user_display_name = ?
        '''
        params = [user_display_name]
        if spreadsheet_id:
            query += " AND spreadsheet_id = ?"
            params.append(spreadsheet_id)

        query += " ORDER BY created_at"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        if len(rows) == 0:
            return [(0, None, None, "Нет выплат", None)]
        return rows
    except Exception as e:
        logger.error(f"Ошибка получения выплат: {e}")
        return []