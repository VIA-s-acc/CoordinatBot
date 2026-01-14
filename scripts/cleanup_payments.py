"""
Скрипт для удаления неправильных записей из таблицы payments в Google Sheets
Удаляет все записи, ID которых не начинается с 'cb-'
"""
import sys
import os

# Добавляем корневую директорию проекта в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.google_integration.payments_sheets_manager import PaymentsSheetsManager
from src.config.settings import UserRole
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def cleanup_payments_sheets():
    """Удаляет из Google Sheets платежи с неправильными ID (не начинающиеся с cb-)"""
    manager = PaymentsSheetsManager()

    if not manager.spreadsheet_id:
        logger.error("PAYMENTS_SPREADSHEET_ID не установлен")
        return

    spreadsheet = manager.sheets_manager.open_sheet_by_id(manager.spreadsheet_id)
    if not spreadsheet:
        logger.error("Не удалось открыть таблицу платежей")
        return

    total_deleted = 0

    for role, sheet_name in manager.SHEET_NAMES.items():
        try:
            worksheet = spreadsheet.worksheet(sheet_name)

            # Получаем все ID из первой колонки
            id_column = worksheet.col_values(1)

            # Находим строки для удаления (с конца, чтобы не сбивать индексы)
            rows_to_delete = []
            for i, cell_value in enumerate(id_column):
                # Пропускаем заголовок (первая строка)
                if i == 0:
                    continue
                # Если ID не начинается с 'cb-', помечаем для удаления
                if cell_value and not str(cell_value).startswith('cb-'):
                    # Проверяем, является ли ID числом (неправильный формат для records)
                    try:
                        int(str(cell_value))
                        rows_to_delete.append(i + 1)  # +1 т.к. индексация в Sheets с 1
                    except ValueError:
                        pass  # Это не числовой ID, возможно нормальная запись

            if rows_to_delete:
                logger.info(f"Лист '{sheet_name}': найдено {len(rows_to_delete)} записей для удаления")

                # Удаляем строки с конца (чтобы не сбивать индексы)
                for row_index in sorted(rows_to_delete, reverse=True):
                    try:
                        worksheet.delete_rows(row_index)
                        total_deleted += 1
                        logger.info(f"  Удалена строка {row_index}")
                    except Exception as e:
                        logger.error(f"  Ошибка при удалении строки {row_index}: {e}")
            else:
                logger.info(f"Лист '{sheet_name}': нет записей для удаления")

        except Exception as e:
            logger.error(f"Ошибка при обработке листа {sheet_name}: {e}")

    logger.info(f"\n✅ Очистка завершена. Всего удалено: {total_deleted} записей")


if __name__ == '__main__':
    print("=" * 60)
    print("Очистка таблицы платежей от записей с неправильными ID")
    print("(будут удалены записи с числовыми ID, которые не начинаются с 'cb-')")
    print("=" * 60)

    response = input("\nПродолжить? (y/n): ")
    if response.lower() == 'y':
        cleanup_payments_sheets()
    else:
        print("Отменено")
