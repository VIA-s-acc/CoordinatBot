"""
Асинхронный воркер для работы с Google Sheets
"""
import asyncio

from queue import Queue
from threading import Thread, current_thread
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import time

from .sheets_manager import sheets_manager
from ..config.settings import logger


class TaskType(Enum):
    ADD_RECORD = "add_record"
    UPDATE_RECORD = "update_record"
    DELETE_RECORD = "delete_record"
    ADD_PAYMENT = "add_payment"
    UPDATE_PAYMENT = "update_payment"
    DELETE_PAYMENT = "delete_payment"


@dataclass
class SheetsTask:
    """Задача для обработки в Google Sheets"""
    task_type: TaskType
    spreadsheet_id: str
    sheet_name: str
    record_id: str
    data: Dict[str, Any]
    callback: Optional[callable] = None
    retry_count: int = 0
    max_retries: int = 3


class AsyncSheetsWorker:
    """Асинхронный воркер для обработки операций с Google Sheets"""
    
    def __init__(self, max_workers: int = 4):
        self.task_queue = Queue()
        self.max_workers = max_workers
        self.workers = []
        self.running = False
        
    def start(self):
        """Запускает воркеры"""
        if self.running:
            return
            
        self.running = True
        logger.info(f"Starting {self.max_workers} workers for Google Sheets")
        
        for i in range(self.max_workers):
            worker = Thread(target=self._worker_loop, name=f"SheetsWorker-{i}", daemon=True)
            worker.start()
            self.workers.append(worker)
    
    def stop(self):
        """Останавливает воркеры"""
        self.running = False
        logger.info("Stopping Google Sheets workers")
    
    def add_task(self, task: SheetsTask):
        """Добавляет задачу в очередь"""
        # Check if the task queue is running, if not start it
        # Check if the thread is running, if not start it
        if not self.running:
            self.start()
        # Add the task to the queue
        # Add the task to the queue
        # Log the task that was added
        # Log the task that was added
        
        self.task_queue.put(task)
        logger.debug(f"Task {task.task_type.value} added for {task.record_id}")
    
    def _worker_loop(self):
        """Основной цикл воркера"""
        worker_name = current_thread().name
        logger.info(f"Worker {worker_name} started")
        
        while self.running:
            try:
                # Получаем задачу с таймаутом
                task = self.task_queue.get(timeout=1.0)
                logger.debug(f"Worker {worker_name} received task {task.task_type.value}")
                self._process_task(task)
                self.task_queue.task_done()
            except Exception as e:
                # Проверяем тип исключения
                import queue
                if isinstance(e, queue.Empty):
                    # Таймаут ожидания задачи - это нормально
                    continue
                elif self.running:  # Игнорируем ошибки при остановке
                    logger.error(f"Error in worker {worker_name}: {e}", exc_info=True)
                time.sleep(0.1)
        
        logger.info(f"Worker {worker_name} stopped")
    
    def _process_task(self, task: SheetsTask):
        """Обрабатывает одну задачу"""
        try:
            logger.debug(f"Processing task {task.task_type.value} for {task.record_id}")
            success = False

            if task.task_type == TaskType.ADD_RECORD:
                success = sheets_manager.add_record_to_sheet(
                    task.spreadsheet_id, task.sheet_name, task.data
                )
            elif task.task_type == TaskType.UPDATE_RECORD:
                success = sheets_manager.update_record_in_sheet(
                    task.spreadsheet_id, task.sheet_name,
                    task.record_id, task.data['field'], task.data['value']
                )
            elif task.task_type == TaskType.DELETE_RECORD:
                success = sheets_manager.delete_record_from_sheet(
                    task.spreadsheet_id, task.sheet_name, task.record_id
                )
            elif task.task_type == TaskType.ADD_PAYMENT:
                # Обработка добавления платежа
                from .payments_sheets_manager import PaymentsSheetsManager
                payments_manager = PaymentsSheetsManager()
                success = payments_manager.add_payment_to_sheet(
                    payment_id=task.data['payment_id'],
                    user_display_name=task.data['user_display_name'],
                    amount=task.data['amount'],
                    date_from=task.data.get('date_from'),
                    date_to=task.data.get('date_to'),
                    comment=task.data.get('comment'),
                    role=task.data['role'],
                    target_spreadsheet_id=task.data.get('target_spreadsheet_id'),
                    target_sheet_name=task.data.get('target_sheet_name')
                )
            elif task.task_type == TaskType.UPDATE_PAYMENT:
                # Обработка обновления платежа
                from .payments_sheets_manager import PaymentsSheetsManager
                payments_manager = PaymentsSheetsManager()
                success = payments_manager.update_payment_in_sheet(
                    payment_id=int(task.record_id),
                    role=task.data['role'],
                    updated_data=task.data.get('updated_data', {})
                )
            elif task.task_type == TaskType.DELETE_PAYMENT:
                # Обработка удаления платежа
                from .payments_sheets_manager import PaymentsSheetsManager
                payments_manager = PaymentsSheetsManager()
                success = payments_manager.delete_payment_from_sheet(
                    payment_id=int(task.record_id),
                    role=task.data['role']
                )
            else:
                logger.error(f"Unknown task type: {task.task_type}")
                return
            
            if success:
                logger.info(f"Task {task.task_type.value} completed successfully for {task.record_id}")
                if task.callback:
                    try:
                        task.callback(True, None)
                    except Exception as e:
                        logger.error(f"Error in callback: {e}", exc_info=True)
            else:
                logger.warning(f"Failed to execute task {task.task_type.value} for {task.record_id}")
                self._handle_task_failure(task)
                
        except Exception as e:
            logger.error(f"Error processing task {task.task_type.value} for {task.record_id}: {e}", exc_info=True)
            self._handle_task_failure(task, str(e))
    
    def _handle_task_failure(self, task: SheetsTask, error: str = None):
        """Обрабатывает неудачное выполнение задачи"""
        task.retry_count += 1
        
        if task.retry_count <= task.max_retries:
            logger.warning(f"Retrying task {task.task_type.value} for {task.record_id} "
                           f"(attempt {task.retry_count}/{task.max_retries})")
            # Добавляем задержку перед повтором
            time.sleep(min(2 ** task.retry_count, 10))  # Экспоненциальная задержка
            self.task_queue.put(task)
        else:
            logger.error(f"Task {task.task_type.value} for {task.record_id} not completed "
                         f"after {task.max_retries} attempts")
            if task.callback:
                try:
                    task.callback(False, error or "Maximum attempts exceeded")
                except Exception as e:
                    logger.error(f"Error in failure callback: {e}")


# Глобальный экземпляр воркера
from ..config.settings import GOOGLE_SHEET_WORKERS
sheets_worker = AsyncSheetsWorker(GOOGLE_SHEET_WORKERS)


def add_record_async(spreadsheet_id: str, sheet_name: str, record: Dict, 
                    callback: Optional[callable] = None):
    """Асинхронно добавляет запись в Google Sheets"""
    # Валидация входных данных
    if not spreadsheet_id or not sheet_name or not record:
        logger.error(f"Invalid parameters for add_record_async: "
                     f"spreadsheet_id={spreadsheet_id}, sheet_name={sheet_name}, "
                     f"record={record}")
        return
    
    if not record.get('id'):
        logger.error(f"Record without ID: {record}")
        return
    
    task = SheetsTask(
        task_type=TaskType.ADD_RECORD,
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        record_id=record.get('id', ''),
        data=record,
        callback=callback
    )
    sheets_worker.add_task(task)


def update_record_async(spreadsheet_id: str, sheet_name: str, record_id: str, 
                       field: str, value: Any, callback: Optional[callable] = None):
    """Асинхронно обновляет запись в Google Sheets"""
    # Валидация входных данных
    if not spreadsheet_id or not sheet_name or not record_id or not field:
        logger.error(f"Invalid parameters for update_record_async: "
                     f"spreadsheet_id={spreadsheet_id}, sheet_name={sheet_name}, "
                     f"record_id={record_id}, field={field}")
        return
    
    task = SheetsTask(
        task_type=TaskType.UPDATE_RECORD,
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        record_id=record_id,
        data={'field': field, 'value': value},
        callback=callback
    )
    sheets_worker.add_task(task)


def delete_record_async(spreadsheet_id: str, sheet_name: str, record_id: str,
                       callback: Optional[callable] = None):
    """Асинхронно удаляет запись из Google Sheets"""
    # Валидация входных данных
    if not spreadsheet_id or not sheet_name or not record_id:
        logger.error(f"Invalid parameters for delete_record_async: "
                     f"spreadsheet_id={spreadsheet_id}, sheet_name={sheet_name}, "
                     f"record_id={record_id}")
        return
    
    task = SheetsTask(
        task_type=TaskType.DELETE_RECORD,
        spreadsheet_id=spreadsheet_id,
        sheet_name=sheet_name,
        record_id=record_id,
        data={},
        callback=callback
    )
    sheets_worker.add_task(task)


def start_worker():
    """Запускает воркер (вызывается при старте бота)"""
    sheets_worker.start()


def stop_worker():
    """Останавливает воркер (вызывается при остановке бота)"""
    sheets_worker.stop()


def add_payment_async(payment_id: int, user_display_name: str, amount: float,
                     role: str, date_from: str = None, date_to: str = None,
                     comment: str = None, target_spreadsheet_id: str = None,
                     target_sheet_name: str = None, callback: Optional[callable] = None):
    """
    Асинхронно добавляет платеж в Google Sheets

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
        callback: Callback функция
    """
    from ..config.settings import PAYMENTS_SPREADSHEET_ID

    if not PAYMENTS_SPREADSHEET_ID:
        logger.error("PAYMENTS_SPREADSHEET_ID not set")
        if callback:
            callback(False, "PAYMENTS_SPREADSHEET_ID not set")
        return

    task = SheetsTask(
        task_type=TaskType.ADD_PAYMENT,
        spreadsheet_id=PAYMENTS_SPREADSHEET_ID,
        sheet_name='',  # Название листа определится по роли
        record_id=str(payment_id),
        data={
            'payment_id': payment_id,
            'user_display_name': user_display_name,
            'amount': amount,
            'role': role,
            'date_from': date_from,
            'date_to': date_to,
            'comment': comment,
            'target_spreadsheet_id': target_spreadsheet_id,
            'target_sheet_name': target_sheet_name
        },
        callback=callback
    )
    sheets_worker.add_task(task)
    logger.info(f"Task to add payment #{payment_id} added to queue")


def delete_payment_async(payment_id: int, role: str, callback: Optional[callable] = None):
    """
    Асинхронно удаляет платеж из Google Sheets

    Args:
        payment_id: ID платежа
        role: Роль пользователя (определяет лист)
        callback: Callback функция
    """
    from ..config.settings import PAYMENTS_SPREADSHEET_ID

    if not PAYMENTS_SPREADSHEET_ID:
        logger.error("PAYMENTS_SPREADSHEET_ID not set")
        if callback:
            callback(False, "PAYMENTS_SPREADSHEET_ID not set")
        return

    task = SheetsTask(
        task_type=TaskType.DELETE_PAYMENT,
        spreadsheet_id=PAYMENTS_SPREADSHEET_ID,
        sheet_name='',
        record_id=str(payment_id),
        data={'role': role},
        callback=callback
    )
    sheets_worker.add_task(task)
    logger.info(f"Task to delete payment #{payment_id} added to queue")


def update_payment_async(payment_id: int, role: str, updated_data: Dict,
                        callback: Optional[callable] = None):
    """
    Асинхронно обновляет платеж в Google Sheets

    Args:
        payment_id: ID платежа
        role: Роль пользователя (определяет лист)
        updated_data: Словарь с обновленными данными (amount, date_from, date_to, comment)
        callback: Callback функция
    """
    from ..config.settings import PAYMENTS_SPREADSHEET_ID

    if not PAYMENTS_SPREADSHEET_ID:
        logger.error("PAYMENTS_SPREADSHEET_ID not set")
        if callback:
            callback(False, "PAYMENTS_SPREADSHEET_ID not set")
        return

    task = SheetsTask(
        task_type=TaskType.UPDATE_PAYMENT,
        spreadsheet_id=PAYMENTS_SPREADSHEET_ID,
        sheet_name='',
        record_id=str(payment_id),
        data={
            'role': role,
            'updated_data': updated_data
        },
        callback=callback
    )
    sheets_worker.add_task(task)
    logger.info(f"Task to update payment #{payment_id} added to queue")
