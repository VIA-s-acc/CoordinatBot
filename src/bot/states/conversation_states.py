"""
Константы состояний для ConversationHandler
"""

# Состояния для добавления записи
SHEET_SELECTION = 0  # Новое состояние для выбора листа
DATE = 1
SUPPLIER_CHOICE = 2
SUPPLIER_MANUAL = 3
DIRECTION = 4
DESCRIPTION = 5
AMOUNT = 6

# Состояния для редактирования записи
EDIT_FIELD = 7
EDIT_VALUE = 8
CONFIRM_DELETE = 9

# Состояния для настройки отчетов
SET_REPORT_SHEET = 10

# Состояния для платежей
PAYMENT_AMOUNT = 11
PAYMENT_PERIOD = 12
PAYMENT_COMMENT = 13

# Состояния для настроек
SET_USER_LIMIT = 14
SET_USER_CATEGORY = 15

# Состояния для переводов
ADD_TRANSLATION_KEY = 16
ADD_TRANSLATION_LANG = 17
ADD_TRANSLATION_TEXT = 18

# Состояния для настройки языков
SELECT_LANGUAGE = 60
ADD_LANGUAGE = 61
