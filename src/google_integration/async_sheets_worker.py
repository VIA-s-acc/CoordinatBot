"""
Асинхронный воркер для работы с Google Sheets
"""
import asyncio
import logging
from queue import Queue
from threading import Thread, current_thread
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import time

from .sheets_manager import sheets_manager

logger = logging.getLogger(__name__)


class TaskType(Enum):
    ADD_RECORD = "add_record"
    UPDATE_RECORD = "update_record"
    DELETE_RECORD = "delete_record"


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
        logger.info(f"Запуск {self.max_workers} воркеров для Google Sheets")
        
        for i in range(self.max_workers):
            worker = Thread(target=self._worker_loop, name=f"SheetsWorker-{i}", daemon=True)
            worker.start()
            self.workers.append(worker)
    
    def stop(self):
        """Останавливает воркеры"""
        self.running = False
        logger.info("Остановка воркеров Google Sheets")
    
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
        logger.debug(f"Добавлена задача {task.task_type.value} для {task.record_id}")
    
    def _worker_loop(self):
        """Основной цикл воркера"""
        worker_name = current_thread().name
        logger.info(f"Воркер {worker_name} запущен")
        
        while self.running:
            try:
                # Получаем задачу с таймаутом
                task = self.task_queue.get(timeout=1.0)
                logger.debug(f"Воркер {worker_name} получил задачу {task.task_type.value}")
                self._process_task(task)
                self.task_queue.task_done()
            except Exception as e:
                # Проверяем тип исключения
                import queue
                if isinstance(e, queue.Empty):
                    # Таймаут ожидания задачи - это нормально
                    continue
                elif self.running:  # Игнорируем ошибки при остановке
                    logger.error(f"Ошибка в воркере {worker_name}: {e}", exc_info=True)
                time.sleep(0.1)
        
        logger.info(f"Воркер {worker_name} остановлен")
    
    def _process_task(self, task: SheetsTask):
        """Обрабатывает одну задачу"""
        try:
            logger.debug(f"Обработка задачи {task.task_type.value} для {task.record_id}")
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
            else:
                logger.error(f"Неизвестный тип задачи: {task.task_type}")
                return
            
            if success:
                logger.info(f"Успешно выполнена задача {task.task_type.value} для {task.record_id}")
                if task.callback:
                    try:
                        task.callback(True, None)
                    except Exception as e:
                        logger.error(f"Ошибка в callback: {e}", exc_info=True)
            else:
                logger.warning(f"Неудачное выполнение задачи {task.task_type.value} для {task.record_id}")
                self._handle_task_failure(task)
                
        except Exception as e:
            logger.error(f"Ошибка обработки задачи {task.task_type.value} для {task.record_id}: {e}", exc_info=True)
            self._handle_task_failure(task, str(e))
    
    def _handle_task_failure(self, task: SheetsTask, error: str = None):
        """Обрабатывает неудачное выполнение задачи"""
        task.retry_count += 1
        
        if task.retry_count <= task.max_retries:
            logger.warning(f"Повтор задачи {task.task_type.value} для {task.record_id} "
                          f"(попытка {task.retry_count}/{task.max_retries})")
            # Добавляем задержку перед повтором
            time.sleep(min(2 ** task.retry_count, 10))  # Экспоненциальная задержка
            self.task_queue.put(task)
        else:
            logger.error(f"Задача {task.task_type.value} для {task.record_id} не выполнена "
                        f"после {task.max_retries} попыток")
            if task.callback:
                try:
                    task.callback(False, error or "Превышено количество попыток")
                except Exception as e:
                    logger.error(f"Ошибка в callback при неудаче: {e}")


# Глобальный экземпляр воркера
from ..config.settings import GOOGLE_SHEET_WORKERS
sheets_worker = AsyncSheetsWorker(GOOGLE_SHEET_WORKERS)


def add_record_async(spreadsheet_id: str, sheet_name: str, record: Dict, 
                    callback: Optional[callable] = None):
    """Асинхронно добавляет запись в Google Sheets"""
    # Валидация входных данных
    if not spreadsheet_id or not sheet_name or not record:
        logger.error(f"Неверные параметры для add_record_async: "
                    f"spreadsheet_id={spreadsheet_id}, sheet_name={sheet_name}, "
                    f"record={record}")
        return
    
    if not record.get('id'):
        logger.error(f"Запись без ID: {record}")
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
        logger.error(f"Неверные параметры для update_record_async: "
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
        logger.error(f"Неверные параметры для delete_record_async: "
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
