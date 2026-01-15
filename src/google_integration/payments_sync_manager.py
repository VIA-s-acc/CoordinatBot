"""
Менеджер синхронизации платежей между БД и Google Sheets
"""
from typing import List, Dict, Set
from .payments_sheets_manager import PaymentsSheetsManager
from ..database.database_manager import DatabaseManager
from ..utils.config_utils import get_user_role
from ..config.settings import UserRole, logger



class PaymentsSyncManager:
    """Менеджер для синхронизации платежей между БД и Google Sheets"""

    def __init__(self):
        self.payments_sheets = PaymentsSheetsManager()
        self.db = DatabaseManager()

    def sync_payments_from_sheets_to_db(self) -> Dict[str, int]:
        """
        Синхронизирует платежи из Google Sheets в БД
        Загружает платежи, которые есть в Sheets, но нет в БД

        Returns:
            Словарь со статистикой: {'added': count, 'skipped': count, 'errors': count}
        """
        stats = {'added': 0, 'skipped': 0, 'errors': 0}

        try:
            logger.info("Starting payments synchronization from Google Sheets to DB")

            # Получаем все платежи из БД
            db_payments = self.db.get_payments()
            db_payment_ids = {payment['id'] for payment in db_payments}

            logger.info(f"Found {len(db_payment_ids)} payments in DB")

            # Загружаем платежи из всех листов Google Sheets
            sheets_payments = self.payments_sheets.get_all_payments_from_sheets()

            logger.info(f"Found {len(sheets_payments)} payments in Google Sheets")

            # Синхронизируем платежи: собираем новые платежи и выполняем batch-вставку в БД
            new_payments = []
            for sheet_payment in sheets_payments:
                payment_id = sheet_payment.get('id')

                if not payment_id:
                    logger.warning("Skipping payment without ID")
                    stats['skipped'] += 1
                    continue

                # Если платеж уже есть в БД, пропускаем
                if payment_id in db_payment_ids:
                    stats['skipped'] += 1
                    continue

                new_payments.append({
                    'user_display_name': sheet_payment.get('user_display_name'),
                    'spreadsheet_id': sheet_payment.get('spreadsheet_id') or None,
                    'sheet_name': sheet_payment.get('sheet_name') or None,
                    'amount': sheet_payment.get('amount') or 0,
                    'date_from': sheet_payment.get('date_from') or None,
                    'date_to': sheet_payment.get('date_to') or None,
                    'comment': sheet_payment.get('comment') or None
                })

            if new_payments:
                try:
                    inserted = self.db.add_payments_batch(new_payments)
                    stats['added'] += inserted
                    logger.info(f"Batch payment insertion completed: {inserted} added")
                except Exception as e:
                    logger.error(f"Error in batch payment insertion to DB: {e}", exc_info=True)
                    stats['errors'] += len(new_payments)

            logger.info(
                f"Synchronization completed. "
                f"Added: {stats['added']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}"
            )

            return stats

        except Exception as e:
            logger.error(f"Critical error during payments synchronization: {e}", exc_info=True)
            stats['errors'] += 1
            return stats

    def sync_payment_to_sheets(
        self,
        payment_id: int,
        user_display_name: str,
        amount: float,
        role: str,
        date_from: str = None,
        date_to: str = None,
        comment: str = None,
        target_spreadsheet_id: str = None,
        target_sheet_name: str = None
    ) -> bool:
        """
        Синхронизирует один платеж из БД в Google Sheets

        Args:
            payment_id: ID платежа в БД
            user_display_name: Имя получателя
            amount: Сумма
            role: Роль пользователя (определяет лист)
            date_from: Начало периода
            date_to: Конец периода
            comment: Комментарий
            target_spreadsheet_id: ID таблицы для двойной записи
            target_sheet_name: Имя листа для двойной записи

        Returns:
            True если успешно
        """
        try:
            return self.payments_sheets.add_payment_to_sheet(
                payment_id=payment_id,
                user_display_name=user_display_name,
                amount=amount,
                date_from=date_from,
                date_to=date_to,
                comment=comment,
                role=role,
                target_spreadsheet_id=target_spreadsheet_id,
                target_sheet_name=target_sheet_name
            )
        except Exception as e:
            logger.error(f"Error synchronizing payment #{payment_id} to Sheets: {e}")
            return False

    def sync_payments_from_db_to_sheets(self) -> Dict[str, int]:
        """
        Синхронизирует платежи из БД в Google Sheets (с пакетными вставками)
        Загружает платежи, которые есть в БД, но нет в Sheets

        Returns:
            Словарь со статистикой: {'added': count, 'skipped': count, 'errors': count}
        """
        stats = {'added': 0, 'skipped': 0, 'errors': 0}

        try:
            logger.info("Starting payments synchronization from DB to Google Sheets")

            # Получаем все платежи из БД
            db_payments = self.db.get_payments()
            logger.info(f"Found {len(db_payments)} payments in DB")

            # Получаем все платежи из Google Sheets
            sheets_payments = self.payments_sheets.get_all_payments_from_sheets()
            sheets_payment_ids = {payment['id'] for payment in sheets_payments}

            logger.info(f"Found {len(sheets_payment_ids)} payments in Google Sheets")

            # Группируем новые платежи по ролям для пакетной вставки
            from ..config.settings import UserRole
            payments_by_role = {
                UserRole.ADMIN: [],
                UserRole.WORKER: [],
                UserRole.SECONDARY: [],
                UserRole.CLIENT: []
            }

            for db_payment in db_payments:
                payment_id = db_payment.get('id')

                if not payment_id:
                    logger.warning("Skipping payment without ID")
                    stats['skipped'] += 1
                    continue

                # Если платеж уже есть в Sheets, пропускаем
                if payment_id in sheets_payment_ids:
                    stats['skipped'] += 1
                    continue

                # Определяем роль получателя платежа
                # TODO: улучшить определение роли по user_display_name
                role = UserRole.WORKER  # По умолчанию

                # Добавляем платеж в группу для пакетной вставки
                payments_by_role[role].append({
                    'payment_id': payment_id,
                    'user_display_name': db_payment['user_display_name'],
                    'amount': db_payment['amount'],
                    'date_from': db_payment.get('date_from'),
                    'date_to': db_payment.get('date_to'),
                    'comment': db_payment.get('comment'),
                    'target_spreadsheet_id': db_payment.get('spreadsheet_id'),
                    'target_sheet_name': db_payment.get('sheet_name')
                })

            # Выполняем пакетные вставки для каждой роли
            for role, payments in payments_by_role.items():
                if payments:
                    try:
                        logger.info(f"Batch inserting {len(payments)} payments for role {role}")
                        success = self.payments_sheets.add_payments_batch(payments, role)
                        if success:
                            stats['added'] += len(payments)
                            logger.info(f"Batch added {len(payments)} payments for role {role}")
                        else:
                            stats['errors'] += len(payments)
                            logger.error(f"Error in batch insertion for role {role}")
                    except Exception as e:
                        logger.error(f"Error during batch insertion for role {role}: {e}", exc_info=True)
                        stats['errors'] += len(payments)

            logger.info(
                f"DB → Sheets synchronization completed. "
                f"Added: {stats['added']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}"
            )

            return stats

        except Exception as e:
            logger.error(f"Critical error during DB → Sheets synchronization: {e}", exc_info=True)
            stats['errors'] += 1
            return stats

    def full_sync_payments(self) -> Dict[str, int]:
        """
        Полная двусторонняя синхронизация платежей:
        1. Загружает платежи из Google Sheets в БД (если их там нет)
        2. Загружает платежи из БД в Google Sheets (если их там нет)
        3. Проверяет целостность данных

        Returns:
            Общая статистика синхронизации
        """
        logger.info("Starting full bidirectional payments synchronization")

        # 1. Синхронизируем из Sheets в БД
        logger.info("Sheets → DB...")
        stats_sheets_to_db = self.sync_payments_from_sheets_to_db()

        # 2. Синхронизируем из БД в Sheets
        logger.info("DB → Sheets...")
        stats_db_to_sheets = self.sync_payments_from_db_to_sheets()

        # Объединяем статистику
        total_stats = {
            'sheets_to_db': stats_sheets_to_db,
            'db_to_sheets': stats_db_to_sheets,
            'total_added': stats_sheets_to_db['added'] + stats_db_to_sheets['added'],
            'total_errors': stats_sheets_to_db['errors'] + stats_db_to_sheets['errors']
        }

        logger.info(
            f"Full synchronization completed.\n"
            f"  Sheets → DB: added {stats_sheets_to_db['added']}, "
            f"skipped {stats_sheets_to_db['skipped']}, errors {stats_sheets_to_db['errors']}\n"
            f"  DB → Sheets: added {stats_db_to_sheets['added']}, "
            f"skipped {stats_db_to_sheets['skipped']}, errors {stats_db_to_sheets['errors']}\n"
            f"  Total added: {total_stats['total_added']}, errors: {total_stats['total_errors']}"
        )

        return total_stats

    def get_sync_status(self) -> Dict:
        """
        Возвращает статус синхронизации:
        - Количество платежей в БД
        - Количество платежей в Google Sheets
        - Несинхронизированные платежи

        Returns:
            Словарь со статусом синхронизации
        """
        try:
            # Платежи в БД
            db_payments = self.db.get_payments()
            db_count = len(db_payments)
            db_ids = {p['id'] for p in db_payments}

            # Платежи в Sheets
            sheets_payments = self.payments_sheets.get_all_payments_from_sheets()
            sheets_count = len(sheets_payments)
            sheets_ids = {p['id'] for p in sheets_payments}

            # Несинхронизированные
            in_db_not_in_sheets = db_ids - sheets_ids
            in_sheets_not_in_db = sheets_ids - db_ids

            status = {
                'db_count': db_count,
                'sheets_count': sheets_count,
                'in_db_not_in_sheets': len(in_db_not_in_sheets),
                'in_sheets_not_in_db': len(in_sheets_not_in_db),
                'synced': db_count - len(in_db_not_in_sheets),
                'missing_in_sheets_ids': list(in_db_not_in_sheets),
                'missing_in_db_ids': list(in_sheets_not_in_db)
            }

            logger.info(
                f"Synchronization status: "
                f"DB: {db_count}, Sheets: {sheets_count}, "
                f"Synced: {status['synced']}, "
                f"Not in Sheets: {status['in_db_not_in_sheets']}, "
                f"Not in DB: {status['in_sheets_not_in_db']}"
            )

            return status

        except Exception as e:
            logger.error(f"Error getting synchronization status: {e}", exc_info=True)
            return {
                'error': str(e),
                'db_count': 0,
                'sheets_count': 0,
                'synced': 0
            }

    def validate_sync(self) -> bool:
        """
        Проверяет, синхронизированы ли платежи между БД и Sheets

        Returns:
            True если все синхронизировано, False если есть расхождения
        """
        status = self.get_sync_status()

        if status.get('error'):
            logger.error("Error during synchronization check")
            return False

        is_synced = (
            status['in_db_not_in_sheets'] == 0 and
            status['in_sheets_not_in_db'] == 0
        )

        if is_synced:
            logger.info("Payments are synchronized")
        else:
            logger.warning(
                f"Unsynchronized payments detected: "
                f"{status['in_db_not_in_sheets']} not in Sheets, "
                f"{status['in_sheets_not_in_db']} not in DB"
            )

        return is_synced
