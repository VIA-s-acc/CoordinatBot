# 🛡️ Backup System

## 📝 Overview

CoordinatBot includes a comprehensive backup system that allows creating, viewing, restoring, and managing data backups.

## 🔧 Features

### ✅ Creating Backups

- **Automatic creation** of complete data backups
- **Timestamps** for each backup
- **Data compression** in ZIP archives to save space
- **Metadata** with size and content information

### 📂 What's Included in Backup

- **Database** (`data/expenses.db`)
- **Users** (`data/users.json`)
- **Allowed users** (`data/allowed_users.json`)
- **Bot configuration** (`data/bot_config.json`)
- **Localization** (`src/config/localization.json`)
- **Credentials** (`credentials/` folder)

### 📋 Viewing Backups

- **List of all backups** with creation dates
- **Size of each backup**
- **Description** and metadata
- **Validity status** of backups

### 🔄 Restoring from Backup

- **Safe restoration** with current state backup creation
- **Integrity checks** before restoration
- **Operation confirmation** to prevent accidental data loss

### 🗑️ Backup Management

- **Delete old backups** (older than 30 days)
- **Clean corrupted** files
- **Automatic validation** on startup

## 🚀 Usage

### Through Bot Interface

1. **Main Menu** → "🛡️ Backups"
2. Choose the desired action:
   - **💾 Create Backup** - creates a new backup
   - **📁 Backup List** - shows all available backups
   - **🔄 Restore Backup** - restores data
   - **🗑️ Clean Old Backups** - removes outdated backups

### Programmatic Interface

```python
from src.utils.backup_manager import BackupManager

# Create manager
backup_manager = BackupManager()

# Create backup
backup_info = backup_manager.create_backup("Backup description")

# List backups
backups = backup_manager.list_backups()

# Restore
backup_manager.restore_backup("backup_20240101_120000.zip")

# Clean old backups
cleanup_result = backup_manager.cleanup_old_backups()
```

## 📁 Backup Structure

```
backups/
├── backup_20240101_120000.zip
├── backup_20240102_093000.zip
└── backup_20240103_150000.zip
```

### Filename Format

`backup_YYYYMMDD_HHMMSS.zip`

- **YYYY** - year
- **MM** - month  
- **DD** - day
- **HH** - hour
- **MM** - minute
- **SS** - second

### Archive Contents

```
backup_20240101_120000.zip
├── metadata.json          # Backup metadata
├── data/
│   ├── expenses.db        # Database
│   ├── users.json         # Users
│   ├── allowed_users.json # Allowed users
│   └── bot_config.json    # Configuration
├── config/
│   └── localization.json  # Localization file
└── credentials/           # Credentials (if exists)
    └── *.json
```

## ⚙️ Configuration

### Environment Variables

```bash
# Backup directory path (default: backups)
BACKUP_DIR=backups

# Maximum backup age in days (default: 30)
BACKUP_MAX_AGE_DAYS=30

# Maximum number of backups (default: 50)
BACKUP_MAX_COUNT=50
```

### Automatic Cleanup

The system automatically removes:

- Backups older than 30 days
- Corrupted files
- Excess backups (more than 50)

## 🔒 Security

### Integrity Checks

- **ZIP archive validation** during creation and restoration
- **Metadata verification** for compatibility
- **Current state backup** before restoration

### Access Rights

- Backup operations are available **only to administrators**
- All actions are **logged** for audit
- **Confirmation of critical operations** (restore, delete)

## 📊 Monitoring

### Logging

All backup operations are logged:

```
2024-01-01 12:00:00 - INFO - Backup created: backup_20240101_120000.zip
2024-01-01 12:05:00 - INFO - Restored from backup: backup_20240101_120000.zip
2024-01-01 12:10:00 - INFO - Old backups cleanup: 3 files removed
```

### Statistics

- **Total number** of backups
- **Total size** of all backups
- **Last backup** date
- **Last operation** status

## ❗ Important Notes

1. **Before restoration**, a backup of the current state is always created
2. **Restoration operations** require bot restart
3. **Large databases** may take time to backup
4. **Credentials** are included only if files exist
5. **Automatic cleanup** runs on every bot startup

## 🆘 Troubleshooting

### Issue: Cannot create backup

**Solution:**
- Check access rights to `backups/` folder
- Ensure sufficient disk space
- Check if files are not locked by other processes

### Issue: Restoration error

**Solution:**
- Check ZIP archive integrity
- Ensure file is not corrupted
- Verify version compatibility in metadata

### Issue: Too many backups

**Solution:**
- Run old backups cleanup manually
- Change `BACKUP_MAX_COUNT` and `BACKUP_MAX_AGE_DAYS` settings
- Remove unnecessary backups through file system

## 🔄 Disaster Recovery

In case of complete data loss:

1. **Stop the bot**
2. **Choose appropriate backup**
3. **Restore through interface** or programmatically:

   ```python
   backup_manager.restore_backup("backup_filename.zip")
   ```

4. **Restart the bot**
5. **Verify functionality**

---

*For more information, refer to the [main documentation](../README.md)*
