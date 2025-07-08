"""
Константы состояний для ConversationHandler
"""

# Состояния для добавления записи
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
PAY_AMOUNT = 20
PAY_PERIOD = 21
PAY_COMMENT = 22
PAYMENT_AMOUNT = 23
PAYMENT_DESCRIPTION = 24
PAYMENT_PERIOD = 25
PAYMENT_COMMENT = 26

# Состояния для поиска и экспорта
SEARCH_QUERY = 30
EXPORT_PERIOD = 31

# Состояния для настройки пользователей
SET_USER_NAME = 40
SET_USER_DISPLAY_NAME = 41
