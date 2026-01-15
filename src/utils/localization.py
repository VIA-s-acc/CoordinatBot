"""
Утилиты для работы с локализацией
"""
import json
import os

from typing import Dict, Any
from ..config.settings import logger

class LocalizationManager:
    """Менеджер локализации"""
    
    def __init__(self):
        self.translations: Dict[str, Dict[str, Any]] = {}
        self.default_language = "hy"  # Армянский по умолчанию
        self.supported_languages = {
            "hy": "🇦🇲 Հայերեն",
            "ru": "🇷🇺 Русский", 
            "en": "🇺🇸 English"
        }
        self.load_translations()
    
    def load_translations(self):
        """Загружает переводы из файла"""
        try:
            # Получаем путь к файлу локализации в папке config
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(os.path.dirname(current_dir), "config")
            localization_file = os.path.join(config_dir, "localization.json")
            
            if os.path.exists(localization_file):
                with open(localization_file, 'r', encoding='utf-8') as f:
                    self.translations = json.load(f)
                logger.info(f"Translations loaded for languages: {list(self.translations.keys())}")
            else:
                logger.warning(f"Localization file not found: {localization_file}")
                self.translations = {}
        except Exception as e:
            logger.error(f"Error loading translations: {e}")
            self.translations = {}
    
    def save_translations(self):
        """Сохраняет переводы в файл"""
        try:
            # Получаем путь к файлу локализации в папке config
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(os.path.dirname(current_dir), "config")
            localization_file = os.path.join(config_dir, "localization.json")
            
            with open(localization_file, 'w', encoding='utf-8') as f:
                json.dump(self.translations, f, ensure_ascii=False, indent=2)
            logger.info("Translations saved")
        except Exception as e:
            logger.error(f"Error saving translations: {e}")
    
    def get_text(self, key: str, language: str = None, **kwargs) -> str:
        """
        Получает текст по ключу для указанного языка
        
        Args:
            key: Ключ в формате 'section.subsection.key'
            language: Код языка (если None - используется default_language)
            **kwargs: Параметры для форматирования строки
        
        Returns:
            Локализованный текст
        """
        if language is None:
            language = self.default_language
        
        if language not in self.translations:
            language = self.default_language
        
        # Разбиваем ключ на части
        keys = key.split('.')
        current = self.translations.get(language, {})
        
        # Проходим по вложенной структуре
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                # Если ключ не найден, пробуем в дефолтном языке
                if language != self.default_language:
                    return self.get_text(key, self.default_language, **kwargs)
                # Если и в дефолтном не найден, возвращаем сам ключ
                return key
        
        # Форматируем строку если нужно
        if isinstance(current, str) and kwargs:
            try:
                return current.format(**kwargs)
            except (KeyError, ValueError):
                return current
        
        return str(current)
    
    def get_supported_languages(self) -> Dict[str, str]:
        """Возвращает поддерживаемые языки"""
        return self.supported_languages.copy()
    
    def add_language(self, language_code: str, language_name: str, translations: Dict[str, Any]):
        """Добавляет новый язык"""
        self.supported_languages[language_code] = language_name
        self.translations[language_code] = translations
        self.save_translations()
        logger.info(f"Language added: {language_code} ({language_name})")
    
    def add_translation_key(self, key: str, translations: Dict[str, str]):
        """
        Добавляет новый ключ перевода для всех языков
        
        Args:
            key: Ключ в формате 'section.subsection.key'
            translations: Словарь переводов {language_code: translation}
        """
        keys = key.split('.')
        
        for language, translation in translations.items():
            if language not in self.translations:
                self.translations[language] = {}
            
            current = self.translations[language]
            
            # Создаем вложенную структуру
            for k in keys[:-1]:
                if k not in current:
                    current[k] = {}
                current = current[k]
            
            # Устанавливаем перевод
            current[keys[-1]] = translation
        
        self.save_translations()
        logger.info(f"Translation key added: {key}")

# Глобальный экземпляр менеджера локализации
localization_manager = LocalizationManager()

def get_user_language(user_id: int) -> str:
    """Получает язык пользователя из настроек"""
    try:
        from .config_utils import get_user_settings
        settings = get_user_settings(user_id)
        return settings.get('language', localization_manager.default_language)
    except Exception as e:
        logger.error(f"Error getting user language {user_id}: {e}")
        return localization_manager.default_language

def set_user_language(user_id: int, language: str):
    """Устанавливает язык пользователя"""
    try:
        from .config_utils import update_user_settings
        update_user_settings(user_id, {'language': language})
        logger.info(f"Language {language} set for user {user_id}")
    except Exception as e:
        logger.error(f"Error setting language for user {user_id}: {e}")

def _(key: str, user_id: int = None, **kwargs) -> str:
    """
    Сокращенная функция для получения переводов
    
    Args:
        key: Ключ перевода
        user_id: ID пользователя (для определения языка)
        **kwargs: Параметры для форматирования
    
    Returns:
        Локализованный текст
    """
    language = get_user_language(user_id) if user_id else localization_manager.default_language
    return localization_manager.get_text(key, language, **kwargs)

def get_available_languages() -> Dict[str, str]:
    """Возвращает доступные языки"""
    return localization_manager.get_supported_languages()

def add_custom_translation(key: str, translations: Dict[str, str]):
    """Добавляет пользовательский перевод"""
    localization_manager.add_translation_key(key, translations)
