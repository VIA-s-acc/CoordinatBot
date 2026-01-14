"""
Система резервного копирования для CoordinatBot
"""
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import os
import shutil
from ..config.settings import logger

class BackupManager:
    """Менеджер резервного копирования"""
    
    def __init__(self, backup_dir: str = "backups"):
        """
        Инициализация менеджера резервного копирования
        
        Args:
            backup_dir: Директория для хранения резервных копий
        """
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        
        # Определяем пути к файлам в зависимости от режима
        if os.environ.get('DEPLOY_MODE') == 'true':
            data_dir = '/app_data'
        else:
            data_dir = 'data'
        
        # Пути к важным файлам
        self.database_path = Path(f"{data_dir}/expenses.db")
        self.users_path = Path(f"{data_dir}/users.json")
        self.allowed_users_path = Path(f"{data_dir}/allowed_users.json")
        self.config_path = Path(f"{data_dir}/bot_config.json")
        self.localization_path = Path("src/config/localization.json")
        self.credentials_dir = Path("credentials")
        
    def create_backup(self, description: str = "") -> Dict[str, any]:
        """
        Создает резервную копию всех важных данных
        
        Args:
            description: Описание резервной копии
            
        Returns:
            Информация о созданной резервной копии
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{timestamp}"
            backup_path = self.backup_dir / f"{backup_name}.zip"
            
            logger.info(f"Создание резервной копии: {backup_name}")
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Добавляем базу данных
                if self.database_path.exists():
                    zip_file.write(self.database_path, "data/expenses.db")
                    logger.info("База данных добавлена в резервную копию")
                
                # Добавляем файлы пользователей
                for user_file in [self.users_path, self.allowed_users_path]:
                    if user_file.exists():
                        zip_file.write(user_file, f"data/{user_file.name}")
                        logger.info(f"Файл {user_file.name} добавлен в резервную копию")
                
                # Добавляем конфигурацию
                if self.config_path.exists():
                    zip_file.write(self.config_path, "data/bot_config.json")
                    logger.info("Конфигурация бота добавлена в резервную копию")
                
                # Добавляем локализацию
                if self.localization_path.exists():
                    zip_file.write(self.localization_path, "src/config/localization.json")
                    logger.info("Файл локализации добавлен в резервную копию")
                
                # Добавляем учетные данные (если есть)
                if self.credentials_dir.exists():
                    for cred_file in self.credentials_dir.glob("*.json"):
                        zip_file.write(cred_file, f"credentials/{cred_file.name}")
                        logger.info(f"Файл учетных данных {cred_file.name} добавлен")
                
                # Создаем манифест резервной копии
                manifest = {
                    "backup_name": backup_name,
                    "created_at": datetime.now().isoformat(),
                    "description": description,
                    "version": "2.0.0",
                    "files": []
                }
                
                # Список файлов в архиве
                for info in zip_file.infolist():
                    manifest["files"].append({
                        "filename": info.filename,
                        "size": info.file_size,
                        "compressed_size": info.compress_size
                    })
                
                # Добавляем манифест в архив
                zip_file.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            
            backup_info = {
                "name": backup_name,
                "path": str(backup_path),
                "size": backup_path.stat().st_size,
                "created_at": datetime.now().isoformat(),
                "description": description,
                "files_count": len(manifest["files"])
            }
            
            logger.info(f"Резервная копия успешно создана: {backup_name}")
            return backup_info
            
        except Exception as e:
            logger.error(f"Ошибка создания резервной копии: {e}")
            raise
    
    def list_backups(self) -> List[Dict[str, any]]:
        """
        Возвращает список всех резервных копий
        
        Returns:
            Список резервных копий с информацией
        """
        backups = []
        
        try:
            for backup_file in self.backup_dir.glob("backup_*.zip"):
                try:
                    stats = backup_file.stat()
                    
                    # Пытаемся прочитать манифест из архива
                    backup_info = {
                        "name": backup_file.stem,
                        "filename": backup_file.name,
                        "path": str(backup_file),
                        "size": stats.st_size,
                        "created_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                        "description": "",
                        "files_count": 0
                    }
                    
                    # Читаем манифест если есть
                    try:
                        with zipfile.ZipFile(backup_file, 'r') as zip_file:
                            if "manifest.json" in zip_file.namelist():
                                manifest_data = zip_file.read("manifest.json")
                                manifest = json.loads(manifest_data.decode('utf-8'))
                                backup_info.update({
                                    "description": manifest.get("description", ""),
                                    "files_count": len(manifest.get("files", [])),
                                    "version": manifest.get("version", "unknown")
                                })
                    except:
                        pass  # Игнорируем ошибки чтения манифеста
                    
                    backups.append(backup_info)
                    
                except Exception as e:
                    logger.warning(f"Ошибка чтения информации о резервной копии {backup_file}: {e}")
                    
            # Сортируем по дате создания (новые первыми)
            backups.sort(key=lambda x: x["created_at"], reverse=True)
            
        except Exception as e:
            logger.error(f"Ошибка получения списка резервных копий: {e}")
            
        return backups
    
    def restore_backup(self, backup_name: str) -> Dict[str, any]:
        """
        Восстанавливает данные из резервной копии
        
        Args:
            backup_name: Имя резервной копии для восстановления
            
        Returns:
            Информация о процессе восстановления
        """
        try:
            backup_path = self.backup_dir / f"{backup_name}.zip"
            
            if not backup_path.exists():
                raise FileNotFoundError(f"Резервная копия {backup_name} не найдена")
            
            logger.info(f"Начало восстановления из резервной копии: {backup_name}")
            
            # Создаем резервную копию текущего состояния перед восстановлением
            current_backup = self.create_backup("Автоматический бэкап перед восстановлением")
            
            restored_files = []
            
            with zipfile.ZipFile(backup_path, 'r') as zip_file:
                # Определяем путь для восстановления базы данных
                if os.environ.get('DEPLOY_MODE') == 'true':
                    db_restore_dir = '/app_data'
                else:
                    db_restore_dir = 'data'
                
                # Восстанавливаем базу данных
                if "data/expenses.db" in zip_file.namelist():
                    # Создаем директорию если не существует
                    os.makedirs(db_restore_dir, exist_ok=True)
                    
                    # Извлекаем базу данных
                    extracted_path = zip_file.extract("data/expenses.db", ".")
                    # Перемещаем в правильную директорию
                    final_db_path = os.path.join(db_restore_dir, "expenses.db")
                    shutil.move(extracted_path, final_db_path)
                    restored_files.append(final_db_path)
                    logger.info(f"База данных восстановлена в {final_db_path}")
                
                # Определяем путь для восстановления файлов
                if os.environ.get('DEPLOY_MODE') == 'true':
                    restore_dir = '/app_data'
                else:
                    restore_dir = 'data'
                
                # Восстанавливаем файлы пользователей
                user_files = ["users.json", "allowed_users.json", "bot_config.json"]
                for user_file in user_files:
                    file_in_archive = f"data/{user_file}"
                    if file_in_archive in zip_file.namelist():
                        # Извлекаем файл
                        extracted_path = zip_file.extract(file_in_archive, ".")
                        # Перемещаем в правильную директорию
                        final_path = os.path.join(restore_dir, user_file)
                        os.makedirs(restore_dir, exist_ok=True)
                        shutil.move(extracted_path, final_path)
                        restored_files.append(final_path)
                        logger.info(f"Файл {final_path} восстановлен")
                
                # Восстанавливаем локализацию
                if "src/config/localization.json" in zip_file.namelist():
                    # Создаем директорию если не существует
                    self.localization_path.parent.mkdir(parents=True, exist_ok=True)
                    zip_file.extract("src/config/localization.json", ".")
                    restored_files.append("src/config/localization.json")
                    logger.info("Файл локализации восстановлен")
                
                # Восстанавливаем учетные данные
                for file_info in zip_file.infolist():
                    if file_info.filename.startswith("credentials/"):
                        # Создаем директорию если не существует
                        self.credentials_dir.mkdir(exist_ok=True)
                        zip_file.extract(file_info, ".")
                        restored_files.append(file_info.filename)
                        logger.info(f"Файл учетных данных {file_info.filename} восстановлен")
            
            restore_info = {
                "backup_name": backup_name,
                "restored_at": datetime.now().isoformat(),
                "restored_files": restored_files,
                "files_count": len(restored_files),
                "current_backup": current_backup["name"]
            }
            
            logger.info(f"Восстановление успешно завершено: {len(restored_files)} файлов")
            return restore_info
            
        except Exception as e:
            logger.error(f"Ошибка восстановления резервной копии: {e}")
            raise
    
    def delete_backup(self, backup_name: str) -> bool:
        """
        Удаляет резервную копию
        
        Args:
            backup_name: Имя резервной копии для удаления
            
        Returns:
            True если удаление успешно
        """
        try:
            backup_path = self.backup_dir / f"{backup_name}.zip"
            
            if backup_path.exists():
                backup_path.unlink()
                logger.info(f"Резервная копия {backup_name} удалена")
                return True
            else:
                logger.warning(f"Резервная копия {backup_name} не найдена")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка удаления резервной копии {backup_name}: {e}")
            return False
    
    def cleanup_old_backups(self, keep_count: int = 10) -> Dict[str, any]:
        """
        Удаляет старые резервные копии, оставляя только последние
        
        Args:
            keep_count: Количество последних резервных копий для сохранения
            
        Returns:
            Информация об очистке
        """
        try:
            backups = self.list_backups()
            
            if len(backups) <= keep_count:
                return {
                    "deleted_count": 0,
                    "kept_count": len(backups),
                    "freed_space": 0,
                    "message": f"Нет резервных копий для удаления. Всего: {len(backups)}"
                }
            
            # Удаляем старые резервные копии
            backups_to_delete = backups[keep_count:]
            deleted_count = 0
            freed_space = 0
            
            for backup in backups_to_delete:
                if self.delete_backup(backup["name"]):
                    deleted_count += 1
                    freed_space += backup["size"]
            
            cleanup_info = {
                "deleted_count": deleted_count,
                "kept_count": len(backups) - deleted_count,
                "freed_space": freed_space,
                "message": f"Удалено {deleted_count} старых резервных копий"
            }
            
            logger.info(f"Очистка завершена: удалено {deleted_count} резервных копий")
            return cleanup_info
            
        except Exception as e:
            logger.error(f"Ошибка очистки резервных копий: {e}")
            raise
    
    def cleanup_old_backups_by_age(self, max_age_days: int = 30) -> Dict[str, any]:
        """
        Удаляет резервные копии старше указанного количества дней
        
        Args:
            max_age_days: Максимальный возраст резервных копий в днях
            
        Returns:
            Информация об очистке
        """
        try:
            from datetime import datetime, timedelta
            
            backups = self.list_backups()
            cutoff_date = datetime.now() - timedelta(days=max_age_days)
            
            old_backups = []
            for backup in backups:
                backup_date = datetime.fromisoformat(backup['created_at'])
                if backup_date < cutoff_date:
                    old_backups.append(backup)
            
            if not old_backups:
                return {
                    "deleted_count": 0,
                    "kept_count": len(backups),
                    "freed_space": 0,
                    "message": f"Нет резервных копий старше {max_age_days} дней"
                }
            
            # Удаляем старые резервные копии
            deleted_count = 0
            freed_space = 0
            
            for backup in old_backups:
                if self.delete_backup(backup["name"]):
                    deleted_count += 1
                    freed_space += backup["size"]
            
            cleanup_info = {
                "deleted_count": deleted_count,
                "kept_count": len(backups) - deleted_count,
                "freed_space": freed_space,
                "cutoff_date": cutoff_date.isoformat(),
                "message": f"Удалено {deleted_count} резервных копий старше {max_age_days} дней"
            }
            
            logger.info(f"Очистка по возрасту завершена: удалено {deleted_count} копий старше {max_age_days} дней")
            return cleanup_info
            
        except Exception as e:
            logger.error(f"Ошибка очистки резервных копий по возрасту: {e}")
            raise

    def get_backup_statistics(self) -> Dict[str, any]:
        """
        Возвращает статистику по резервным копиям
        
        Returns:
            Статистика резервных копий
        """
        try:
            backups = self.list_backups()
            
            if not backups:
                return {
                    "total_count": 0,
                    "total_size": 0,
                    "oldest_backup": None,
                    "newest_backup": None,
                    "average_size": 0
                }
            
            total_size = sum(backup['size'] for backup in backups)
            oldest_backup = min(backups, key=lambda x: x['created_at'])
            newest_backup = max(backups, key=lambda x: x['created_at'])
            average_size = total_size / len(backups)
            
            return {
                "total_count": len(backups),
                "total_size": total_size,
                "oldest_backup": oldest_backup,
                "newest_backup": newest_backup,
                "average_size": average_size,
                "total_size_mb": total_size / (1024 * 1024),
                "average_size_mb": average_size / (1024 * 1024)
            }
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики резервных копий: {e}")
            return {
                "total_count": 0,
                "total_size": 0,
                "oldest_backup": None,
                "newest_backup": None,
                "average_size": 0
            }
    
    def get_backup_info(self, backup_name: str) -> Optional[Dict[str, any]]:
        """
        Возвращает подробную информацию о резервной копии
        
        Args:
            backup_name: Имя резервной копии
            
        Returns:
            Подробная информация о резервной копии
        """
        try:
            backup_path = self.backup_dir / f"{backup_name}.zip"
            
            if not backup_path.exists():
                return None
            
            stats = backup_path.stat()
            
            backup_info = {
                "name": backup_name,
                "filename": backup_path.name,
                "path": str(backup_path),
                "size": stats.st_size,
                "created_at": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                "files": []
            }
            
            # Читаем содержимое архива
            with zipfile.ZipFile(backup_path, 'r') as zip_file:
                for file_info in zip_file.infolist():
                    backup_info["files"].append({
                        "filename": file_info.filename,
                        "size": file_info.file_size,
                        "compressed_size": file_info.compress_size,
                        "compression_ratio": (
                            1 - file_info.compress_size / file_info.file_size
                        ) if file_info.file_size > 0 else 0
                    })
                
                # Читаем манифест если есть
                if "manifest.json" in zip_file.namelist():
                    manifest_data = zip_file.read("manifest.json")
                    manifest = json.loads(manifest_data.decode('utf-8'))
                    backup_info.update({
                        "description": manifest.get("description", ""),
                        "version": manifest.get("version", "unknown"),
                        "manifest": manifest
                    })
            
            return backup_info
            
        except Exception as e:
            logger.error(f"Ошибка получения информации о резервной копии {backup_name}: {e}")
            return None
    
    def verify_backup(self, backup_name: str) -> Dict[str, any]:
        """
        Проверяет целостность резервной копии
        
        Args:
            backup_name: Имя резервной копии для проверки
            
        Returns:
            Результат проверки
        """
        try:
            backup_path = self.backup_dir / f"{backup_name}.zip"
            
            if not backup_path.exists():
                return {
                    "valid": False,
                    "error": f"Резервная копия {backup_name} не найдена"
                }
            
            # Проверяем ZIP архив
            with zipfile.ZipFile(backup_path, 'r') as zip_file:
                # Тестируем целостность архива
                bad_files = zip_file.testzip()
                
                if bad_files:
                    return {
                        "valid": False,
                        "error": f"Поврежденные файлы в архиве: {bad_files}"
                    }
                
                files = zip_file.namelist()
                
                # Проверяем наличие важных файлов
                required_files = ["data/expenses.db"]
                missing_files = [f for f in required_files if f not in files]
                
                return {
                    "valid": True,
                    "files_count": len(files),
                    "missing_files": missing_files,
                    "has_manifest": "manifest.json" in files
                }
                
        except Exception as e:
            return {
                "valid": False,
                "error": f"Ошибка проверки резервной копии: {e}"
            }

# Глобальный экземпляр менеджера резервного копирования
backup_manager = BackupManager()

