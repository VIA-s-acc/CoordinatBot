"""
Утилита для управления переводами через bot
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ConversationHandler

from ...config.settings import ADMIN_IDS, LOCALIZATION_FILE, logger
from ...utils.config_utils import load_json_file, save_json_file
from ...utils.localization import _
from ..states.conversation_states import ADD_TRANSLATION_KEY, ADD_TRANSLATION_TEXT, ADD_TRANSLATION_LANG


async def translation_management(update: Update, context: CallbackContext):
    """Меню управления переводами"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("translation.access_denied", user_id))
        return
    
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(_("translation.add_translation", user_id), callback_data="add_translation")],
        [InlineKeyboardButton(_("translation.add_language", user_id), callback_data="add_language")],
        [InlineKeyboardButton(_("translation.list_translations", user_id), callback_data="list_translations")],
        [InlineKeyboardButton(_("translation.reload_translations", user_id), callback_data="reload_translations")],
        [InlineKeyboardButton(_("menu.back", user_id), callback_data="settings_menu")]
    ]
    
    await query.edit_message_text(
        f"🌐 <b>{_('translation.main_menu', user_id)}</b>\n\n"
        f"{_('translation.menu_description', user_id)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_add_translation(update: Update, context: CallbackContext):
    """Начинает процесс добавления перевода"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("translation.access_denied", user_id))
        return ConversationHandler.END
    
    await query.answer()
    
    await query.edit_message_text(
        f"➕ <b>{_('translation.start_add_title', user_id)}</b>\n\n"
        f"{_('translation.enter_key', user_id)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(_("buttons.cancel", user_id), callback_data="translation_management")]
        ])
    )
    
    return ADD_TRANSLATION_KEY

async def get_translation_key(update: Update, context: CallbackContext):
    """Получает ключ перевода"""
    key = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not key:
        await update.message.reply_text(_("translation.key_empty", user_id))
        return ADD_TRANSLATION_KEY
    
    context.user_data['translation_key'] = key
    
    # Показываем доступные языки
    localization_data = load_json_file(LOCALIZATION_FILE)
    available_languages = list(localization_data.keys())
    
    keyboard = []
    for lang in available_languages:
        # Используем статические названия языков
        lang_names = {
            'ru': _("translation.language_russian", user_id),
            'hy': _("translation.language_armenian", user_id), 
            'en': _("translation.language_english", user_id)
        }
        lang_name = lang_names.get(lang, lang)
        keyboard.append([InlineKeyboardButton(lang_name, callback_data=f"trans_lang_{lang}")])
    
    keyboard.append([InlineKeyboardButton(_("buttons.cancel", user_id), callback_data="translation_management")])
    
    await update.message.reply_text(
        f"{_('translation.key_label', user_id)} <code>{key}</code>\n\n"
        f"{_('translation.select_language', user_id)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    return ADD_TRANSLATION_LANG

async def get_translation_language(update: Update, context: CallbackContext):
    """Получает язык перевода"""
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()
    
    language = query.data.replace("trans_lang_", "")
    context.user_data['translation_language'] = language
    
    key = context.user_data['translation_key']
    
    # Получаем название языка
    lang_names = {
        'ru': _("translation.language_russian", user_id),
        'hy': _("translation.language_armenian", user_id), 
        'en': _("translation.language_english", user_id)
    }
    lang_name = lang_names.get(language, language)
    
    await query.edit_message_text(
        f"{_('translation.key_label', user_id)} <code>{key}</code>\n"
        f"{_('translation.language_label', user_id)} {lang_name}\n\n"
        f"{_('translation.enter_text', user_id)}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(_("buttons.cancel", user_id), callback_data="translation_management")]
        ])
    )
    
    return ADD_TRANSLATION_TEXT

async def save_translation(update: Update, context: CallbackContext):
    """Сохраняет перевод"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if not text:
        await update.message.reply_text(_("translation.text_empty", user_id))
        return ADD_TRANSLATION_TEXT
    
    key = context.user_data['translation_key']
    language = context.user_data['translation_language']
    
    try:
        # Загружаем локализацию
        localization_data = load_json_file(LOCALIZATION_FILE)
        
        # Разбираем ключ (например, "menu.new_button" -> ["menu", "new_button"])
        key_parts = key.split('.')
        
        # Создаем вложенную структуру если нужно
        current_level = localization_data[language]
        for part in key_parts[:-1]:
            if part not in current_level:
                current_level[part] = {}
            current_level = current_level[part]
        
        # Устанавливаем значение
        current_level[key_parts[-1]] = text
        
        # Сохраняем файл
        save_json_file(LOCALIZATION_FILE, localization_data)
        
        # Получаем название языка
        lang_names = {
            'ru': _("translation.language_russian", user_id),
            'hy': _("translation.language_armenian", user_id), 
            'en': _("translation.language_english", user_id)
        }
        lang_name = lang_names.get(language, language)
        
        await update.message.reply_text(
            f"✅ <b>{_('translation.save_success', user_id)}</b>\n\n"
            f"{_('translation.key_label', user_id)} <code>{key}</code>\n"
            f"{_('translation.language_label', user_id)} {lang_name}\n"
            f"{_('translation.text_label', user_id)} {text}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_("menu.back", user_id), callback_data="translation_management")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error saving translation: {e}")
        await update.message.reply_text(
            f"{_('translation.save_error', user_id)} {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_("menu.back", user_id), callback_data="translation_management")]
            ])
        )
    
    # Очищаем данные пользователя
    context.user_data.clear()
    return ConversationHandler.END

async def list_translations(update: Update, context: CallbackContext):
    """Показывает список переводов"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("translation.access_denied", user_id))
        return
    
    await query.answer()
    
    try:
        localization_data = load_json_file(LOCALIZATION_FILE)
        
        # Получаем все ключи из русской версии
        def get_all_keys(data, prefix=""):
            keys = []
            for key, value in data.items():
                full_key = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    keys.extend(get_all_keys(value, full_key))
                else:
                    keys.append(full_key)
            return keys
        
        ru_keys = get_all_keys(localization_data.get('ru', {}))
        
        # Показываем первые 20 ключей
        keys_text = "\n".join(f"• <code>{key}</code>" for key in ru_keys[:20])
        
        if len(ru_keys) > 20:
            keys_text += f"\n... и еще {len(ru_keys) - 20} ключей"
        
        await query.edit_message_text(
            f"📋 <b>{_('translation.list_title', user_id)}</b>\n\n"
            f"{_('translation.total_keys', user_id)} {len(ru_keys)}\n\n"
            f"{keys_text}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_("menu.back", user_id), callback_data="translation_management")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error getting translations list: {e}")
        await query.edit_message_text(
            f"{_('translation.list_error', user_id)} {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_("menu.back", user_id), callback_data="translation_management")]
            ])
        )

async def reload_translations(update: Update, context: CallbackContext):
    """Перезагружает переводы"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await query.answer(_("translation.access_denied", user_id))
        return
    
    await query.answer()
    
    try:
        # Очищаем кэш локализации если он есть
        from ...utils.localization import localization_manager
        if hasattr(localization_manager, 'clear_cache'):
            localization_manager.clear_cache()
        
        await query.edit_message_text(
            f"🔄 <b>{_('translation.reload_success', user_id)}</b>\n\n"
            f"{_('translation.reload_description', user_id)}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_("menu.back", user_id), callback_data="translation_management")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error reloading translations: {e}")
        await query.edit_message_text(
            f"{_('translation.reload_error', user_id)} {e}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(_("menu.back", user_id), callback_data="translation_management")]
            ])
        )

async def cancel_translation(update: Update, context: CallbackContext):
    """Отменяет добавление перевода"""
    user_id = update.effective_user.id
    context.user_data.clear()
    await update.message.reply_text(
        _("translation.cancelled", user_id),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(_("menu.back", user_id), callback_data="translation_management")]
        ])
    )
    return ConversationHandler.END
