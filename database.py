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
        
        # Создаем таблицу записей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                supplier TEXT NOT NULL,
                direction TEXT NOT NULL,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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
            INSERT INTO records (id, date, supplier, direction, description, amount)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            record.get('id'),
            record.get('date'),
            record.get('supplier'),
            record.get('direction'),
            record.get('description'),
            record.get('amount', 0)
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
            SELECT id, date, supplier, direction, description, amount, created_at, updated_at
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
                'created_at': row[6],
                'updated_at': row[7]
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

def get_all_records(limit: int = 100) -> List[Dict]:
    """Получает все записи из базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, date, supplier, direction, description, amount, created_at, updated_at
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
                'updated_at': row[7]
            })
        
        return records
        
    except Exception as e:
        logger.error(f"Ошибка получения записей из БД: {e}")
        return []

def search_records(query: str, limit: int = 50) -> List[Dict]:
    """Поиск записей по тексту"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        search_query = f"%{query}%"
        cursor.execute('''
            SELECT id, date, supplier, direction, description, amount, created_at, updated_at
            FROM records 
            WHERE supplier LIKE ? OR direction LIKE ? OR description LIKE ?
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (search_query, search_query, search_query, limit))
        
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
                'updated_at': row[7]
            })
        
        return records
        
    except Exception as e:
        logger.error(f"Ошибка поиска записей в БД: {e}")
        return []

def backup_db_to_dict() -> Optional[Dict]:
    """Создает резервную копию базы данных в виде словаря"""
    try:
        records = get_all_records(limit=10000)  # Получаем все записи
        stats = get_db_stats()
        
        return {
            'backup_date': datetime.now().isoformat(),
            'stats': stats,
            'records': records
        }
        
    except Exception as e:
        logger.error(f"Ошибка создания резервной копии БД: {e}")
        return None