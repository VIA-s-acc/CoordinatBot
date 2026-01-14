"""
Скрипт для удаления записей с числовыми ID из SQLite БД (таблица records)
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config.settings import DATABASE_PATH

def is_numeric_id(value):
    """Проверяет, является ли ID числовым"""
    try:
        int(str(value))
        return True
    except (ValueError, TypeError):
        return False


def cleanup_database():
    """Удаляет записи с числовыми ID из таблицы records"""
    if not os.path.exists(DATABASE_PATH):
        print(f"База данных не найдена: {DATABASE_PATH}")
        return

    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Показываем превью
    cursor.execute("SELECT id FROM records")
    all_ids = cursor.fetchall()

    numeric_ids = [str(record_id) for (record_id,) in all_ids if is_numeric_id(record_id)]

    print(f"\nНайдено {len(numeric_ids)} записей с числовыми ID в таблице records")

    if numeric_ids:
        print(f"ID для удаления: {numeric_ids[:20]}{'...' if len(numeric_ids) > 20 else ''}")

        response = input("\nУдалить? (y/n): ")
        if response.lower() == 'y':
            placeholders = ','.join(['?' for _ in numeric_ids])
            cursor.execute(f"DELETE FROM records WHERE id IN ({placeholders})", numeric_ids)
            deleted_count = cursor.rowcount
            conn.commit()
            print(f"\n✅ Удалено {deleted_count} записей из таблицы records")
        else:
            print("Отменено")
    else:
        print("Нет записей для удаления")

    conn.close()


if __name__ == '__main__':
    print("=" * 50)
    print("Очистка таблицы records от числовых ID")
    print("=" * 50)
    cleanup_database()
