"""
Менеджер для работы с Google Sheets таблицами платежей
Создает и управляет отдельными листами для каждой роли
"""

from datetime import datetime
from typing import Optional, List, Dict
from .sheets_manager import GoogleSheetsManager
from ..config.settings import PAYMENTS_SPREADSHEET_ID, UserRole, logger
from ..utils.config_utils import get_role_display_name



class PaymentsSheetsManager:
    """Менеджер для работы с таблицами платежей"""

    # Названия листов для каждой роли
    SHEET_NAMES = {
        UserRole.ADMIN: 'Վճարումներ - Ադմինիստրատոր',
        UserRole.WORKER: 'Վճարումներ - Աշխատող',
        UserRole.SECONDARY: 'Վճարումներ - Երկրորդային',
        UserRole.CLIENT: 'Վճարումներ - Կլիենտ',
    }

    # Заголовки колонок для таблиц платежей
    HEADERS = [
        'ID',
        'Անուն',  # User Display Name
        'Գումար',  # Amount
        'Սկզբնական ամսաթիվ',  # Date From
        'Վերջնական ամսաթիվ',  # Date To
        'Մեկնաբանություն',  # Comment
        'Ստեղծման ամսաթիվ',  # Created At
        'Աղյուսակի ID',  # Spreadsheet ID (для двойной записи)
        'Թերթիկի անուն'  # Sheet Name (для двойной записи)
    ]

    def __init__(self):
        self.sheets_manager = GoogleSheetsManager()
        self.spreadsheet_id = PAYMENTS_SPREADSHEET_ID

        if not self.spreadsheet_id:
            logger.warning("PAYMENTS_SPREADSHEET_ID не установлен в переменных окружения")

    def initialize_payment_sheets(self) -> bool:
        """
        Инициализирует таблицу платежей: создает листы для каждой роли
        Вызывается при старте бота
        """
        if not self.spreadsheet_id:
            logger.error("Не указан PAYMENTS_SPREADSHEET_ID")
            return False

        try:
            logger.info(f"Инициализация таблицы платежей: {self.spreadsheet_id}")

            # Получаем доступ к таблице
            spreadsheet = self.sheets_manager.open_sheet_by_id(self.spreadsheet_id)
            if not spreadsheet:
                logger.error(f"Не удалось открыть таблицу платежей: {self.spreadsheet_id}")
                return False

            # Получаем список существующих листов
            existing_sheets = [ws.title for ws in spreadsheet.worksheets()]

            # Создаем листы для каждой роли, если их нет
            sheets_to_create = []
            for role, sheet_name in self.SHEET_NAMES.items():
                if sheet_name not in existing_sheets:
                    sheets_to_create.append((role, sheet_name))

            if sheets_to_create:
                logger.info(f"Создаем {len(sheets_to_create)} новых листов...")
                for role, sheet_name in sheets_to_create:
                    logger.info(f"  - {sheet_name} (роль: {role})")
                    self._create_payment_sheet(spreadsheet, sheet_name)
            else:
                logger.info("Все необходимые листы уже существуют")

            logger.info("✅ Инициализация таблицы платежей завершена")
            return True

        except Exception as e:
            logger.error(f"Ошибка при инициализации таблицы платежей: {e}", exc_info=True)
            return False

    def _create_payment_sheet(self, spreadsheet, sheet_name: str):
        """Создает новый лист для платежей с заголовками"""
        try:
            # Создаем лист
            worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(self.HEADERS))

            # Устанавливаем заголовки
            worksheet.append_row(self.HEADERS)

            # Форматируем заголовки (жирный шрифт)
            worksheet.format('A1:I1', {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })

            # Замораживаем первую строку
            worksheet.freeze(rows=1)

            logger.info(f"✅ Создан лист: {sheet_name}")

        except Exception as e:
            logger.error(f"Ошибка при создании листа {sheet_name}: {e}", exc_info=True)
            raise

    def _ensure_headers(self, spreadsheet, sheet_name: str):
        """Проверяет наличие заголовков в листе, добавляет если нет"""
        try:
            worksheet = spreadsheet.worksheet(sheet_name)

            # Проверяем первую строку
            first_row = worksheet.row_values(1)

            if not first_row or first_row != self.HEADERS:
                logger.info(f"Обновляем заголовки в листе {sheet_name}")
                worksheet.insert_row(self.HEADERS, index=1)

                # Форматируем заголовки
                worksheet.format('A1:I1', {
                    'textFormat': {'bold': True},
                    'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
                })

        except Exception as e:
            logger.error(f"Ошибка при проверке заголовков в {sheet_name}: {e}")

    def get_sheet_name_for_role(self, role: str) -> Optional[str]:
        """Возвращает название листа для указанной роли"""
        return self.SHEET_NAMES.get(role)

    def add_payment_to_sheet(
        self,
        payment_id: int,
        user_display_name: str,
        amount: float,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        comment: Optional[str] = None,
        role: str = UserRole.WORKER,
        target_spreadsheet_id: Optional[str] = None,
        target_sheet_name: Optional[str] = None
    ) -> bool:
        """
        Добавляет платеж в соответствующий лист таблицы

        Args:
            payment_id: ID платежа в БД
            user_display_name: Имя получателя платежа
            amount: Сумма платежа
            date_from: Начало периода (опционально)
            date_to: Конец периода (опционально)
            comment: Комментарий (опционально)
            role: Роль пользователя (определяет лист)
            target_spreadsheet_id: ID таблицы для двойной записи (опционально)
            target_sheet_name: Имя листа для двойной записи (опционально)

        Returns:
            True если успешно, False если ошибка
        """
        if not self.spreadsheet_id:
            logger.error("PAYMENTS_SPREADSHEET_ID не установлен")
            return False

        try:
            # Получаем название листа для роли
            sheet_name = self.get_sheet_name_for_role(role)
            if not sheet_name:
                logger.error(f"Не найден лист для роли: {role}")
                return False

            # Открываем таблицу и лист
            spreadsheet = self.sheets_manager.open_sheet_by_id(self.spreadsheet_id)
            if not spreadsheet:
                logger.error(f"Не удалось открыть таблицу: {self.spreadsheet_id}")
                return False

            worksheet = spreadsheet.worksheet(sheet_name)

            # Проверяем, существует ли уже платеж с таким ID
            id_column = worksheet.col_values(1)  # Первая колонка - ID
            if str(payment_id) in id_column:
                logger.info(f"Платеж #{payment_id} уже существует в листе '{sheet_name}', пропускаем")
                return True  # Возвращаем True, т.к. это не ошибка

            # Подготавливаем данные для записи
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            row_data = [
                str(payment_id),
                user_display_name or '',
                amount,
                date_from or '',
                date_to or '',
                comment or '',
                created_at,
                target_spreadsheet_id or '',
                target_sheet_name or ''
            ]

            # Добавляем строку
            worksheet.append_row(row_data)

            logger.info(
                f"✅ Платеж #{payment_id} добавлен в лист '{sheet_name}' "
                f"(получатель: {user_display_name}, сумма: {amount})"
            )
            return True

        except Exception as e:
            logger.error(f"Ошибка при добавлении платежа в таблицу: {e}", exc_info=True)
            return False

    def add_payments_batch(self, payments: List[Dict], role: str) -> bool:
        """
        Пакетная вставка платежей в таблицу (более эффективно)

        Args:
            payments: Список словарей с данными платежей
                Каждый словарь должен содержать:
                - payment_id: int
                - user_display_name: str
                - amount: float
                - date_from: Optional[str]
                - date_to: Optional[str]
                - comment: Optional[str]
                - target_spreadsheet_id: Optional[str]
                - target_sheet_name: Optional[str]
            role: Роль пользователя (определяет лист)

        Returns:
            True если успешно, False если ошибка
        """
        if not self.spreadsheet_id:
            logger.error("PAYMENTS_SPREADSHEET_ID не установлен")
            return False

        if not payments:
            logger.info("Нет платежей для пакетной вставки")
            return True

        try:
            # Получаем название листа для роли
            sheet_name = self.get_sheet_name_for_role(role)
            if not sheet_name:
                logger.error(f"Не найден лист для роли: {role}")
                return False

            # Открываем таблицу и лист
            spreadsheet = self.sheets_manager.open_sheet_by_id(self.spreadsheet_id)
            if not spreadsheet:
                logger.error(f"Не удалось открыть таблицу: {self.spreadsheet_id}")
                return False

            worksheet = spreadsheet.worksheet(sheet_name)

            # Получаем существующие ID для проверки дубликатов
            existing_ids = set(worksheet.col_values(1))  # Первая колонка - ID

            # Подготавливаем данные для пакетной вставки (только новые платежи)
            rows_data = []
            skipped_count = 0
            for payment in payments:
                payment_id = str(payment.get('payment_id', ''))
                # Пропускаем, если платеж уже существует
                if payment_id in existing_ids:
                    skipped_count += 1
                    continue
                created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                row_data = [
                    str(payment.get('payment_id', '')),
                    payment.get('user_display_name', ''),
                    payment.get('amount', 0),
                    payment.get('date_from', ''),
                    payment.get('date_to', ''),
                    payment.get('comment', ''),
                    created_at,
                    payment.get('target_spreadsheet_id', ''),
                    payment.get('target_sheet_name', '')
                ]
                rows_data.append(row_data)

            # Пакетная вставка всех строк за один раз (только если есть новые)
            if rows_data:
                worksheet.append_rows(rows_data)
                logger.info(
                    f"✅ Пакетная вставка: {len(rows_data)} платежей добавлено в лист '{sheet_name}'"
                    f"{f', пропущено {skipped_count} дубликатов' if skipped_count else ''}"
                )
            else:
                logger.info(
                    f"Все {len(payments)} платежей уже существуют в листе '{sheet_name}', пропускаем"
                )
            return True

        except Exception as e:
            logger.error(f"Ошибка при пакетной вставке платежей: {e}", exc_info=True)
            return False

    def get_payments_from_sheet(self, role: str) -> List[Dict]:
        """
        Загружает все платежи из листа указанной роли

        Returns:
            Список словарей с данными платежей
        """
        if not self.spreadsheet_id:
            logger.error("PAYMENTS_SPREADSHEET_ID не установлен")
            return []

        try:
            sheet_name = self.get_sheet_name_for_role(role)
            if not sheet_name:
                logger.error(f"Не найден лист для роли: {role}")
                return []

            spreadsheet = self.sheets_manager.open_sheet_by_id(self.spreadsheet_id)
            if not spreadsheet:
                logger.error(f"Не удалось открыть таблицу: {self.spreadsheet_id}")
                return []

            worksheet = spreadsheet.worksheet(sheet_name)

            # Получаем все записи (кроме заголовка)
            records = worksheet.get_all_records()

            # Преобразуем в нужный формат
            payments = []
            for record in records:
                # Пропускаем пустые записи
                if not record.get('ID'):
                    continue

                payment = {
                    'id': int(record['ID']),
                    'user_display_name': record.get('Անուն', ''),
                    'amount': float(record.get('Գումար', 0)),
                    'date_from': record.get('Սկզբնական ամսաթիվ', ''),
                    'date_to': record.get('Վերջնական ամսաթիվ', ''),
                    'comment': record.get('Մեկնաբանություն', ''),
                    'created_at': record.get('Ստեղծման ամսաթիվ', ''),
                    'spreadsheet_id': record.get('Աղյուսակի ID', ''),
                    'sheet_name': record.get('Թերթիկի անուն', '')
                }
                payments.append(payment)

            logger.info(f"Загружено {len(payments)} платежей из листа '{sheet_name}'")
            return payments

        except Exception as e:
            logger.error(f"Ошибка при загрузке платежей из таблицы: {e}", exc_info=True)
            return []

    def get_all_payments_from_sheets(self) -> List[Dict]:
        """
        Загружает все платежи из всех листов

        Returns:
            Список всех платежей со всех листов
        """
        all_payments = []

        for role in self.SHEET_NAMES.keys():
            payments = self.get_payments_from_sheet(role)
            # Добавляем информацию о роли
            for payment in payments:
                payment['role'] = role
            all_payments.extend(payments)

        logger.info(f"Загружено всего {len(all_payments)} платежей из всех листов")
        return all_payments

    def update_payment_in_sheet(
        self,
        payment_id: int,
        role: str,
        updated_data: Dict
    ) -> bool:
        """
        Обновляет платеж в таблице

        Args:
            payment_id: ID платежа
            role: Роль (определяет лист)
            updated_data: Словарь с обновленными данными
                Может содержать: amount, date_from, date_to, comment

        Returns:
            True если успешно
        """
        if not self.spreadsheet_id:
            logger.error("PAYMENTS_SPREADSHEET_ID не установлен")
            return False

        try:
            sheet_name = self.get_sheet_name_for_role(role)
            if not sheet_name:
                logger.error(f"Не найден лист для роли: {role}")
                return False

            spreadsheet = self.sheets_manager.open_sheet_by_id(self.spreadsheet_id)
            if not spreadsheet:
                return False

            worksheet = spreadsheet.worksheet(sheet_name)

            # Находим строку с нужным ID
            id_column = worksheet.col_values(1)  # Первая колонка - ID

            try:
                row_index = id_column.index(str(payment_id)) + 1  # +1 т.к. индексация с 1
            except ValueError:
                logger.warning(f"Платеж #{payment_id} не найден в листе '{sheet_name}'")
                return False

            # Обновляем данные в соответствующих ячейках
            # Колонки: ID, Անուն, Գումար, Սկզբնական ամսաթիվ, Վերջնական ամսաթիվ, Մեկնաբանություն, ...
            updates = []

            if 'amount' in updated_data:
                # Колонка C (3) - Գումար
                updates.append({
                    'range': f'C{row_index}',
                    'values': [[updated_data['amount']]]
                })

            if 'date_from' in updated_data:
                # Колонка D (4) - Սկզբնական ամսաթիվ
                updates.append({
                    'range': f'D{row_index}',
                    'values': [[updated_data['date_from'] or '']]
                })

            if 'date_to' in updated_data:
                # Колонка E (5) - Վերջնական ամսաթիվ
                updates.append({
                    'range': f'E{row_index}',
                    'values': [[updated_data['date_to'] or '']]
                })

            if 'comment' in updated_data:
                # Колонка F (6) - Մեկնաբանություն
                updates.append({
                    'range': f'F{row_index}',
                    'values': [[updated_data['comment'] or '']]
                })

            # Выполняем пакетное обновление
            if updates:
                worksheet.batch_update(updates)
                logger.info(f"✅ Платеж #{payment_id} обновлен в листе '{sheet_name}' (обновлено полей: {len(updates)})")
            else:
                logger.warning(f"Нет данных для обновления платежа #{payment_id}")

            return True

        except Exception as e:
            logger.error(f"Ошибка при обновлении платежа в таблице: {e}", exc_info=True)
            return False

    def delete_payment_from_sheet(self, payment_id: int, role: str) -> bool:
        """
        Удаляет платеж из таблицы

        Args:
            payment_id: ID платежа
            role: Роль (определяет лист)

        Returns:
            True если успешно
        """
        if not self.spreadsheet_id:
            logger.error("PAYMENTS_SPREADSHEET_ID не установлен")
            return False

        try:
            sheet_name = self.get_sheet_name_for_role(role)
            if not sheet_name:
                logger.error(f"Не найден лист для роли: {role}")
                return False

            spreadsheet = self.sheets_manager.open_sheet_by_id(self.spreadsheet_id)
            if not spreadsheet:
                return False

            worksheet = spreadsheet.worksheet(sheet_name)

            # Находим строку с нужным ID
            id_column = worksheet.col_values(1)

            try:
                row_index = id_column.index(str(payment_id)) + 1
                worksheet.delete_rows(row_index)
                logger.info(f"✅ Платеж #{payment_id} удален из листа '{sheet_name}'")
                return True
            except ValueError:
                logger.warning(f"Платеж #{payment_id} не найден в листе '{sheet_name}'")
                return False

        except Exception as e:
            logger.error(f"Ошибка при удалении платежа из таблицы: {e}", exc_info=True)
            return False
