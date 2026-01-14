"""
Скрипт для удаления записей с числовыми ID (1, 2, 3...) из:
1. Google Sheets таблицы records (ACTIVE_SPREADSHEET_ID)
2. SQLite базы данных (таблица records)

Эти записи - платежи, которые попали не туда.
Правильные записи должны иметь ID формата cb-XXXXXX
"""
import sys
import os
import sqlite3

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.google_integration.sheets_manager import GoogleSheetsManager
from src.config.settings import ACTIVE_SPREADSHEET_ID, DATABASE_PATH, logger



def is_numeric_id(value):
    """Проверяет, является ли ID числовым (неправильным для records)"""
    try:
        int(str(value))
        return True
    except (ValueError, TypeError):
        return False


def cleanup_google_sheets():
    """Удаляет записи с числовыми ID из Google Sheets"""
    if not ACTIVE_SPREADSHEET_ID:
        logger.error("ACTIVE_SPREADSHEET_ID не установлен")
        return 0

    manager = GoogleSheetsManager()
    spreadsheet = manager.open_sheet_by_id(ACTIVE_SPREADSHEET_ID)

    if not spreadsheet:
        logger.error(f"Не удалось открыть таблицу: {ACTIVE_SPREADSHEET_ID}")
        return 0

    total_deleted = 0

    # Получаем все листы
    worksheets = spreadsheet.worksheets()

    for worksheet in worksheets:
        sheet_name = worksheet.title
        logger.info(f"\nОбработка листа: {sheet_name}")

        try:
            # Получаем все значения первой колонки (ID)
            id_column = worksheet.col_values(1)

            # Находим строки с числовыми ID (с конца)
            rows_to_delete = []
            for i, cell_value in enumerate(id_column):
                if i == 0:  # Пропускаем заголовок
                    continue
                if cell_value and is_numeric_id(cell_value):
                    rows_to_delete.append((i + 1, cell_value))  # (row_index, id_value)

            if rows_to_delete:
                logger.info(f"  Найдено {len(rows_to_delete)} записей с числовыми ID для удаления")

                # Удаляем с конца
                for row_index, id_value in sorted(rows_to_delete, reverse=True):
                    try:
                        worksheet.delete_rows(row_index)
                        total_deleted += 1
                        logger.info(f"    Удалена строка {row_index} (ID: {id_value})")
                    except Exception as e:
                        logger.error(f"    Ошибка при удалении строки {row_index}: {e}")
            else:
                logger.info(f"  Нет записей с числовыми ID")

        except Exception as e:
            logger.error(f"  Ошибка при обработке листа {sheet_name}: {e}")

    return total_deleted


def cleanup_database():
    """Удаляет записи с числовыми ID из SQLite БД (таблица records)"""
    if not os.path.exists(DATABASE_PATH):
        logger.error(f"База данных не найдена: {DATABASE_PATH}")
        return 0

    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        # Находим записи с числовыми ID в таблице records
        cursor.execute("SELECT id FROM records")
        all_ids = cursor.fetchall()

        numeric_ids = []
        for (record_id,) in all_ids:
            if is_numeric_id(record_id):
                numeric_ids.append(record_id)

        if numeric_ids:
            logger.info(f"\nНайдено {len(numeric_ids)} записей с числовыми ID в БД")

            # Удаляем записи
            placeholders = ','.join(['?' for _ in numeric_ids])
            cursor.execute(f"DELETE FROM records WHERE id IN ({placeholders})", numeric_ids)
            deleted_count = cursor.rowcount
            conn.commit()

            logger.info(f"Удалено {deleted_count} записей из БД")
            conn.close()
            return deleted_count
        else:
            logger.info("\nНет записей с числовыми ID в БД")
            conn.close()
            return 0

    except Exception as e:
        logger.error(f"Ошибка при работе с БД: {e}")
        return 0


def show_preview():
    """Показывает превью того, что будет удалено"""
    print("\n" + "=" * 60)
    print("ПРЕВЬЮ: записи, которые будут удалены")
    print("=" * 60)

    # Превью Google Sheets
    if ACTIVE_SPREADSHEET_ID:
        print(f"\n📊 Google Sheets ({ACTIVE_SPREADSHEET_ID}):")
        manager = GoogleSheetsManager()
        spreadsheet = manager.open_sheet_by_id(ACTIVE_SPREADSHEET_ID)

        if spreadsheet:
            for worksheet in spreadsheet.worksheets():
                id_column = worksheet.col_values(1)
                numeric_count = sum(1 for i, v in enumerate(id_column) if i > 0 and v and is_numeric_id(v))
                if numeric_count > 0:
                    print(f"   Лист '{worksheet.title}': {numeric_count} записей с числовыми ID")

    # Превью БД
    if os.path.exists(DATABASE_PATH):
        print(f"\n💾 SQLite БД ({DATABASE_PATH}):")
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM records")
        all_ids = cursor.fetchall()
        numeric_count = sum(1 for (record_id,) in all_ids if is_numeric_id(record_id))
        print(f"   Таблица 'records': {numeric_count} записей с числовыми ID")
        conn.close()

    print("\n" + "=" * 60)


if __name__ == '__main__':
    print("=" * 60)
    print("Очистка записей с числовыми ID (1, 2, 3...)")
    print("Правильные записи должны иметь ID формата cb-XXXXXX")
    print("=" * 60)

    show_preview()

    response = input("\nПродолжить удаление? (y/n): ")
    if response.lower() == 'y':
        print("\n🔄 Очистка Google Sheets...")
        sheets_deleted = cleanup_google_sheets()

        print("\n🔄 Очистка SQLite БД...")
        db_deleted = cleanup_database()

        print("\n" + "=" * 60)
        print(f"✅ Готово!")
        print(f"   Удалено из Google Sheets: {sheets_deleted}")
        print(f"   Удалено из БД: {db_deleted}")
        print("=" * 60)
    else:
        print("Отменено")
