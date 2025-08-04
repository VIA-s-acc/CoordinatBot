"""
Модуль для работы с периодическими задачами
"""
import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from telegram import Bot
from telegram.constants import ChatAction
from telegram.ext import Application
from ..config.settings import (
    AUTO_SEND_DATA_INTERVAL_HOURS, 
    AUTO_SEND_DATA_ADMIN_ID, 
    DATA_DIR, 
    TOKEN
)

logger = logging.getLogger(__name__)

class PeriodicTasks:
    """Менеджер периодических задач"""
    
    def __init__(self, application: Application):
        self.application = application
        self.bot = application.bot
        self.thread = None
        self.running = False
    
    async def send_data_files_to_admin(self):
        """Отправить файлы данных администратору"""
        try:
            admin_id = AUTO_SEND_DATA_ADMIN_ID
            
            # Проверяем существование папки data
            if not os.path.exists(DATA_DIR):
                logger.warning(f"Data directory {DATA_DIR} does not exist")
                return
            
            # Получаем список файлов
            files = [f for f in os.listdir(DATA_DIR) if os.path.isfile(os.path.join(DATA_DIR, f))]
            if not files:
                logger.info("No files to send in data directory")
                return
            
            # Отправляем уведомление о начале отправки
            await self.bot.send_message(
                chat_id=admin_id,
                text=f"🤖 Автоматическая отправка данных\n📤 Отправляю {len(files)} файлов из папки data..."
            )
            
            # Отправляем каждый файл
            for fname in files:
                fpath = os.path.join(DATA_DIR, fname)
                try:
                    await self.bot.send_chat_action(chat_id=admin_id, action=ChatAction.UPLOAD_DOCUMENT)
                    with open(fpath, 'rb') as f:
                        await self.bot.send_document(
                            chat_id=admin_id, 
                            document=f, 
                            filename=fname,
                            caption=f"📋 Файл данных: {fname}"
                        )
                    logger.info(f"Successfully sent file {fname} to admin {admin_id}")
                except Exception as e:
                    logger.error(f"Failed to send file {fname}: {e}")
                    await self.bot.send_message(
                        chat_id=admin_id,
                        text=f"❌ Не удалось отправить {fname}: {e}"
                    )
            
            # Отправляем уведомление о завершении
            await self.bot.send_message(
                chat_id=admin_id,
                text="✅ Автоматическая отправка файлов данных завершена."
            )
            
            logger.info(f"Periodic data files sent to admin {admin_id}")
            
        except Exception as e:
            logger.error(f"Error in periodic send_data_files_to_admin: {e}")
            try:
                await self.bot.send_message(
                    chat_id=AUTO_SEND_DATA_ADMIN_ID,
                    text=f"❌ Ошибка при автоматической отправке данных: {e}"
                )
            except:
                pass  # Игнорируем ошибки при отправке сообщения об ошибке
    
    def sync_send_data_files(self):
        """Синхронная обертка для отправки файлов"""
        try:
            # Создаем новый event loop для этого потока
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Запускаем асинхронную функцию
            loop.run_until_complete(self.send_data_files_to_admin())
            
        except Exception as e:
            logger.error(f"Error in sync_send_data_files: {e}")
        finally:
            if loop:
                loop.close()
    
    def periodic_worker(self):
        """Рабочий поток для периодических задач"""
        logger.info(f"Starting periodic worker thread (interval: {AUTO_SEND_DATA_INTERVAL_HOURS} hours)")
        
        # Отправляем данные сразу при запуске (без задержки)
        if self.running:
            logger.info("Sending initial data files on startup")
            self.sync_send_data_files()
        
        while self.running:
            try:
                # Ждем указанный интервал (в секундах)
                interval_seconds = int(AUTO_SEND_DATA_INTERVAL_HOURS * 3600)
                
                # Ждем с проверкой каждую минуту, чтобы можно было быстро остановить
                for _ in range(interval_seconds // 60):
                    if not self.running:
                        break
                    time.sleep(60)
                
                if self.running:  # Проверяем, что задача не была остановлена
                    self.sync_send_data_files()
                    
            except Exception as e:
                logger.error(f"Error in periodic worker: {e}")
                # Продолжаем работу даже при ошибках
                time.sleep(60)  # Небольшая пауза перед повтором
        
        logger.info("Periodic worker thread stopped")
    
    def start_periodic_tasks(self):
        """Запустить периодические задачи"""
        if self.running:
            logger.warning("Periodic tasks already running")
            return
            
        self.running = True
        
        # Создаем и запускаем поток для периодических задач
        self.thread = threading.Thread(target=self.periodic_worker, daemon=True)
        self.thread.start()
        
        logger.info("Periodic tasks started")
    
    def stop_periodic_tasks(self):
        """Остановить периодические задачи"""
        if not self.running:
            return
            
        self.running = False
        
        # Ждем завершения потока
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)  # Ждем до 5 секунд
        
        logger.info("Periodic tasks stopped")

# Глобальный экземпляр менеджера задач
periodic_tasks_manager = None

def start_periodic_tasks(application: Application):
    """Запустить периодические задачи"""
    global periodic_tasks_manager
    periodic_tasks_manager = PeriodicTasks(application)
    periodic_tasks_manager.start_periodic_tasks()

def stop_periodic_tasks():
    """Остановить периодические задачи"""
    global periodic_tasks_manager
    if periodic_tasks_manager:
        periodic_tasks_manager.stop_periodic_tasks()

def get_task_manager():
    """Получить экземпляр менеджера задач"""
    global periodic_tasks_manager
    return periodic_tasks_manager
