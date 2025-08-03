"""
Тест функций безопасного парсинга дат
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from src.utils.date_utils import safe_parse_date, safe_parse_date_or_none

def test_date_parsing():
    """Тестирует функции парсинга дат"""
    print("🧪 Тестирование функций безопасного парсинга дат...")
    
    # Тестовые данные с различными форматами
    test_dates = [
        "10.10.24",      # Обычный формат
        "10.10.2024",    # С полным годом
        "2024-10-10",    # ISO формат
        "10-10-2024",    # С дефисами
        "10/10/24",      # С слэшами
        "10․10․24",      # Армянские точки
        "invalid_date",  # Некорректная дата
        "",              # Пустая строка
        "10.10.25",      # Дата, которая вызывала ошибку
    ]
    
    print("\n📊 Результаты тестирования:")
    for date_str in test_dates:
        try:
            result = safe_parse_date(date_str)
            print(f"✅ '{date_str}' → {result}")
        except Exception as e:
            print(f"❌ '{date_str}' → Ошибка: {e}")
            
        # Тест с функцией, которая возвращает None
        result_none = safe_parse_date_or_none(date_str)
        print(f"   safe_parse_date_or_none: {result_none}")
        print()

if __name__ == "__main__":
    test_date_parsing()
