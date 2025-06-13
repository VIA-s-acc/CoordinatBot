import sqlite3
import logging
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# Путь к базе данных
DB_PATH = 'expenses.db'

def init_db():
    """Инициализирует базу данных и создает таблицы"""
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована успешно")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        return False

def add_record_to_db(record: dict):
    """Добавляет запись в базу данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO records (id, date, supplier, direction, description, amount)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            record.get('id', ''),
            record.get('date', ''),
            record.get('supplier', ''),
            record.get('direction', ''),
            record.get('description', ''),
            record.get('amount', 0)
        ))
        
        conn.commit()
        conn.close()
        logger.info(f"Запись {record.get('id')} добавлена в базу данных")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка добавления записи в БД: {e}")
        return False

def update_record_in_db(record_id: str, field: str, new_value):
    """Обновляет поле записи в базе данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, что поле существует
        valid_fields = ['date', 'supplier', 'direction', 'description', 'amount']
        if field not in valid_fields:
            logger.error(f"Недопустимое поле для обновления: {field}")
            return False
        
        # Обновляем запись
        query = f"UPDATE records SET {field} = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?"
        cursor.execute(query, (new_value, record_id))
        
        if cursor.rowcount == 0:
            logger.warning(f"Запись {record_id} не найдена в БД для обновления")
            conn.close()
            return False
        
        conn.commit()
        conn.close()
        logger.info(f"Обновлено поле {field} записи {record_id} в БД")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка обновления записи в БД: {e}")
        return False

def delete_record_from_db(record_id: str):
    """Удаляет запись из базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM records WHERE id = ?", (record_id,))
        
        if cursor.rowcount == 0:
            logger.warning(f"Запись {record_id} не найдена в БД для удаления")
            conn.close()
            return False
        
        conn.commit()
        conn.close()
        logger.info(f"Запись {record_id} удалена из БД")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка удаления записи из БД: {e}")
        return False

def get_record_from_db(record_id: str):
    """Получает запись из базы данных по ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM records WHERE id = ?", (record_id,))
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            # Преобразуем результат в словарь
            record = {
                'id': row[0],
                'date': row[1],
                'supplier': row[2],
                'direction': row[3],
                'description': row[4],
                'amount': row[5],
                'created_at': row[6],
                'updated_at': row[7]
            }
            return record
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка получения записи {record_id} из БД: {e}")
        return None

def get_all_records_from_db():
    """Получает все записи из базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM records ORDER BY created_at DESC")
        rows = cursor.fetchall()
        
        conn.close()
        
        records = []
        for row in rows:
            record = {
                'id': row[0],
                'date': row[1],
                'supplier': row[2],
                'direction': row[3],
                'description': row[4],
                'amount': row[5],
                'created_at': row[6],
                'updated_at': row[7]
            }
            records.append(record)
        
        return records
        
    except Exception as e:
        logger.error(f"Ошибка получения всех записей из БД: {e}")
        return []

def backup_db_to_file(backup_path: str = None):
    """Создает резервную копию базы данных"""
    try:
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"backup_expenses_{timestamp}.db"
        
        # Копируем файл базы данных
        import shutil
        shutil.copy2(DB_PATH, backup_path)
        
        logger.info(f"Резервная копия БД создана: {backup_path}")
        return backup_path
        
    except Exception as e:
        logger.error(f"Ошибка создания резервной копии БД: {e}")
        return None

def get_db_stats():
    """Получает статистику базы данных"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Общее количество записей
        cursor.execute("SELECT COUNT(*) FROM records")
        total_records = cursor.fetchone()[0]
        
        # Сумма всех расходов
        cursor.execute("SELECT SUM(amount) FROM records")
        total_amount = cursor.fetchone()[0] or 0
        
        # Количество записей за последние 30 дней
        cursor.execute("""
            SELECT COUNT(*) FROM records 
            WHERE date >= date('now', '-30 days')
        """)
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