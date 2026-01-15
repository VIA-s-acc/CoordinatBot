"""
Миграция пользователей: присвоение ролей существующим пользователям
"""
from ..config.settings import ADMIN_IDS, SUPER_ADMIN_ID, UserRole, logger
from .config_utils import load_users, save_users, is_user_allowed



def migrate_existing_users_to_roles() -> dict:
    """
    Присваивает роли существующим пользователям, у которых их нет

    Логика:
    - Если user_id == SUPER_ADMIN_ID → SUPER_ADMIN
    - Если user_id in ADMIN_IDS → ADMIN
    - Если user_id в allowed_users.json → WORKER
    - Остальные → не изменяются

    Returns:
        Словарь со статистикой миграции
    """
    stats = {
        'total': 0,
        'migrated': 0,
        'skipped': 0,
        'errors': 0,
        'details': []
    }

    try:
        logger.info("🔄 Starting user migration...")

        users = load_users()
        stats['total'] = len(users)

        if not users:
            logger.info("📋 No users to migrate")
            return stats

        for user_id_str, user_data in users.items():
            try:
                user_id = int(user_id_str)

                # Если роль уже есть, пропускаем
                if user_data.get('role'):
                    logger.info(f"User {user_id} already has a role: {user_data['role']}")
                    stats['skipped'] += 1
                    continue

                # Определяем роль
                assigned_role = None

                # Проверяем супер-админа
                if SUPER_ADMIN_ID and user_id == SUPER_ADMIN_ID:
                    assigned_role = UserRole.SUPER_ADMIN
                    logger.info(f"✨ User {user_id} assigned SUPER_ADMIN")

                # Проверяем админа
                elif user_id in ADMIN_IDS:
                    assigned_role = UserRole.ADMIN
                    logger.info(f"👨‍💼 User {user_id} assigned ADMIN")

                # Проверяем разрешенных пользователей (работники)
                elif is_user_allowed(user_id):
                    assigned_role = UserRole.WORKER
                    logger.info(f"👷 User {user_id} assigned WORKER")

                else:
                    logger.warning(f"⚠️ User {user_id} not in allowed_users - role not assigned")
                    stats['skipped'] += 1
                    continue

                # Присваиваем роль
                if assigned_role:
                    user_data['role'] = assigned_role
                    stats['migrated'] += 1

                    display_name = user_data.get('display_name', 'Unknown')
                    stats['details'].append({
                        'user_id': user_id,
                        'display_name': display_name,
                        'assigned_role': assigned_role
                    })

            except Exception as e:
                logger.error(f"❌ Error migrating user {user_id_str}: {e}")
                stats['errors'] += 1

        # Сохраняем изменения
        if stats['migrated'] > 0:
            if save_users(users):
                logger.info(f"✅ Migration completed. Changes saved: {stats['migrated']}")
            else:
                logger.error("❌ Error saving user data")
                stats['errors'] += 1
        else:
            logger.info("📋 No users to migrate")

        # Log final statistics
        logger.info(
            f"\n📊 Migration statistics:\n"
            f"  Total users: {stats['total']}\n"
            f"  Migrated: {stats['migrated']}\n"
            f"  Skipped: {stats['skipped']}\n"
            f"  Errors: {stats['errors']}"
        )

        # Выводим детали миграции
        if stats['details']:
            logger.info("\n👥 Migrated users:")
            for detail in stats['details']:
                from .config_utils import get_role_display_name
                role_display = get_role_display_name(detail['assigned_role'])
                logger.info(
                    f"  • {detail['display_name']} (ID: {detail['user_id']}) → {role_display}"
                )

        return stats

    except Exception as e:
        logger.error(f"❌ Critical migration error: {e}", exc_info=True)
        stats['errors'] += 1
        return stats


def check_migration_needed() -> bool:
    """
    Проверяет, нужна ли миграция

    Returns:
        True если есть пользователи без ролей
    """
    try:
        users = load_users()

        if not users:
            return False

        # Проверяем, есть ли пользователи без роли
        users_without_roles = [
            user_id for user_id, data in users.items()
            if not data.get('role')
        ]

        if users_without_roles:
            logger.info(
                f"⚠️ Found {len(users_without_roles)} users without roles. "
                f"Migration required."
            )
            return True

        logger.info("✅ All users have roles")
        return False

    except Exception as e:
        logger.error(f"Error checking migration necessity: {e}")
        return False


def auto_migrate_if_needed():
    """
    Автоматически выполняет миграцию, если она необходима
    Вызывается при старте бота
    """
    try:
        if check_migration_needed():
            logger.info("🔄 Starting automatic user migration...")
            stats = migrate_existing_users_to_roles()

            if stats['errors'] > 0:
                logger.warning(
                    f"⚠️ Migration completed with errors. "
                    f"Migrated: {stats['migrated']}, Errors: {stats['errors']}"
                )
            else:
                logger.info(f"✅ Automatic migration completed successfully. Migrated: {stats['migrated']}")

            return stats
        else:
            logger.info("✅ Migration not required")
            return None

    except Exception as e:
        logger.error(f"❌ Automatic migration error: {e}", exc_info=True)
        return None


# Функция для ручного запуска миграции
if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    print("=" * 60)
    print("МИГРАЦИЯ ПОЛЬЗОВАТЕЛЕЙ К СИСТЕМЕ РОЛЕЙ")
    print("=" * 60)
    print()

    if check_migration_needed():
        response = input("Выполнить миграцию? (yes/no): ").strip().lower()

        if response in ['yes', 'y', 'да', 'д']:
            stats = migrate_existing_users_to_roles()

            print("\n" + "=" * 60)
            print("РЕЗУЛЬТАТЫ МИГРАЦИИ")
            print("=" * 60)
            print(f"Всего пользователей: {stats['total']}")
            print(f"Мигрировано: {stats['migrated']}")
            print(f"Пропущено: {stats['skipped']}")
            print(f"Ошибок: {stats['errors']}")
            print("=" * 60)

            if stats['details']:
                print("\nМигрированные пользователи:")
                from config_utils import get_role_display_name
                for detail in stats['details']:
                    role_display = get_role_display_name(detail['assigned_role'])
                    print(f"  • {detail['display_name']} (ID: {detail['user_id']}) → {role_display}")
        else:
            print("Миграция отменена")
    else:
        print("✅ Миграция не требуется. Все пользователи имеют роли.")
