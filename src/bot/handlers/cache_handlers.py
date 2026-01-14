"""
Обработчики для управления кешем листов
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from ...utils.sheets_cache import get_cache_statistics, clear_all_cache, invalidate_spreadsheets_cache
from ...utils.localization import _
from ..keyboards.inline_keyboards import create_back_to_menu_keyboard
from ...config.settings import ADMIN_IDS, logger


async def cache_management_menu(update: Update, context: CallbackContext):
    """Показывает меню управления кешем"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Проверяем права админа
    if user_id not in ADMIN_IDS:
        await query.edit_message_text(
            "❌ Доступ запрещен",
            reply_markup=create_back_to_menu_keyboard()
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("📊 Статистика кеша", callback_data="cache_stats")],
        [InlineKeyboardButton("🔄 Обновить кеш таблиц", callback_data="refresh_spreadsheets_cache")],
        [InlineKeyboardButton("🗑 Очистить весь кеш", callback_data="clear_all_cache")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="settings_menu")]
    ]
    
    await query.edit_message_text(
        "🗂 Управление кешем листов\n\n"
        "Кеш позволяет быстро загружать списки листов без обращения к API Google Sheets.\n"
        "Обновляется автоматически каждые 30 минут.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_cache_stats(update: Update, context: CallbackContext):
    """Показывает статистику кеша"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Проверяем права админа
    if user_id not in ADMIN_IDS:
        await query.edit_message_text(
            "❌ Доступ запрещен",
            reply_markup=create_back_to_menu_keyboard()
        )
        return
    
    try:
        stats = get_cache_statistics()
        
        text = "📊 Статистика кеша листов\n\n"
        text += f"🔄 Период кеширования: {stats['cache_duration_minutes']} минут\n"
        text += f"📊 Кешированных таблиц: {stats['spreadsheets_cached']}\n"
        text += f"📋 Кешированных листов: {stats['sheets_cached']}\n\n"
        
        if stats.get('spreadsheets_last_updated'):
            text += f"📅 Таблицы обновлены: {stats['spreadsheets_last_updated']}\n\n"
        
        if stats['sheets_info']:
            text += "📋 Детали по листам:\n"
            for sheet_info in stats['sheets_info'][:5]:  # Показываем первые 5
                text += f"  • {sheet_info['title'][:25]}...\n"
                text += f"    Листов: {sheet_info['sheets_count']}\n"
                text += f"    Обновлено: {sheet_info['last_updated']}\n"
            
            if len(stats['sheets_info']) > 5:
                text += f"  ... и еще {len(stats['sheets_info']) - 5} таблиц\n"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data="cache_stats")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="cache_management")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка при получении статистики кеша: {e}")
        await query.edit_message_text(
            f"❌ Ошибка при получении статистики: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="cache_management")]])
        )

async def refresh_spreadsheets_cache(update: Update, context: CallbackContext):
    """Обновляет кеш таблиц"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Проверяем права админа
    if user_id not in ADMIN_IDS:
        await query.edit_message_text(
            "❌ Доступ запрещен",
            reply_markup=create_back_to_menu_keyboard()
        )
        return
    
    try:
        # Инвалидируем кеш таблиц
        invalidate_spreadsheets_cache()
        
        # Принудительно обновляем кеш
        from ...utils.sheets_cache import get_cached_spreadsheets
        spreadsheets = get_cached_spreadsheets(force_refresh=True)
        
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="cache_stats")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="cache_management")]
        ]
        
        await query.edit_message_text(
            f"✅ Кеш таблиц обновлен!\n\n"
            f"Загружено {len(spreadsheets)} таблиц.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении кеша: {e}")
        await query.edit_message_text(
            f"❌ Ошибка при обновлении кеша: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="cache_management")]])
        )

async def clear_cache(update: Update, context: CallbackContext):
    """Очищает весь кеш"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    # Проверяем права админа
    if user_id not in ADMIN_IDS:
        await query.edit_message_text(
            "❌ Доступ запрещен",
            reply_markup=create_back_to_menu_keyboard()
        )
        return
    
    try:
        # Очищаем кеш
        clear_all_cache()
        
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="cache_stats")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="cache_management")]
        ]
        
        await query.edit_message_text(
            "✅ Весь кеш очищен!\n\n"
            "При следующем обращении данные будут загружены заново.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка при очистке кеша: {e}")
        await query.edit_message_text(
            f"❌ Ошибка при очистке кеша: {e}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Назад", callback_data="cache_management")]])
        )
