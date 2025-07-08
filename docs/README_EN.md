# 🤖 CoordinatBot - Financial Accounting System

## 📋 Description

CoordinatBot is a powerful Telegram bot for managing financial records and integrating with Google Sheets. The bot is designed for expense tracking, report generation, and employee payment management.

## ✨ Key Features

### 📝 Record Management
- ➕ Add expense records through interactive menu
- ✏️ Edit and delete records
- 🔍 Search and filter records
- 📊 Detailed information for each record

### 🔄 Google Sheets Integration
- 📈 Automatic synchronization with Google Sheets
- 📋 Support for multiple spreadsheets and sheets
- 🔁 Bidirectional data synchronization
- ⚡ Real-time updates

### 📊 Reports and Analytics
- 📄 Generate reports in Excel format
- 💰 Track payments and debts
- 📈 Statistical analysis
- 🏢 Individual reports for employees

### 👥 Multi-user Support
- 🔐 Secure user management
- 🛡️ Access permission system
- 👑 Special capabilities for administrators
- 📱 User settings

## 🚀 Installation and Setup

### Requirements
```bash
Python 3.8+
pip
Git
```

### 1. Get the Project
```bash
git clone https://github.com/your-username/CoordinatBot.git
cd CoordinatBot
```

### 2. Create Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Setup
Create a `.env` file and add the necessary credentials:

```env
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Administrator IDs (comma-separated)
ADMIN_IDS=123456789,987654321

# Logging level
LOG_LEVEL=INFO
```

### 5. Google Sheets Setup
1. Create a Google Cloud Console project
2. Enable Google Sheets API
3. Create a Service Account
4. Download credentials JSON file
5. Place it in `credentials/` folder

### 6. Database Preparation
```bash
python -c "from src.database.database_manager import DatabaseManager; DatabaseManager().init_db()"
```

### 7. Run the Bot
```bash
python main_new.py
```

## 📁 Project Structure

```
CoordinatBot/
├── 📁 src/                          # Main source code
│   ├── 📁 config/                   # Project configuration
│   │   └── settings.py              # Global settings
│   ├── 📁 bot/                      # Telegram bot logic
│   │   ├── 📁 handlers/             # Command and event handlers
│   │   │   ├── basic_commands.py    # Basic commands (/start, /help)
│   │   │   ├── admin_commands.py    # Administrative commands
│   │   │   ├── record_handlers.py   # Record addition handlers
│   │   │   ├── edit_handlers.py     # Record editing handlers
│   │   │   └── callback_handlers.py # Button handlers
│   │   ├── 📁 keyboards/            # Interactive keyboards
│   │   │   └── inline_keyboards.py  # Inline keyboards
│   │   └── 📁 states/               # ConversationHandler states
│   │       └── conversation_states.py
│   ├── 📁 database/                 # Database handling
│   │   └── database_manager.py      # DB manager
│   ├── 📁 google_integration/       # Google Sheets integration
│   │   ├── sheets_manager.py        # Main operations
│   │   └── sync_manager.py          # Synchronization
│   └── 📁 utils/                    # Utility tools
│       ├── config_utils.py          # Configuration handling
│       ├── date_utils.py            # Date utilities
│       ├── formatting.py            # Message formatting
│       └── report_manager.py        # Report generation
├── 📁 data/                         # Data files
│   ├── users.json                   # User data
│   ├── allowed_users.json           # Allowed users
│   ├── bot_config.json              # Bot configuration
│   └── expenses.db                  # SQLite database
├── 📁 credentials/                  # Credentials
│   └── google-credentials.json      # Google API credentials
├── main_new.py                      # Main execution file
├── requirements.txt                 # Python dependencies
├── .env                            # Environment variables
└── README.md                       # This file
```

## 🎮 Usage Guide

### Basic Commands

#### User Commands:
- `/start` - Start bot and show main menu
- `/menu` - Show main menu
- `/help` - Command help
- `/search [text]` - Search records
- `/recent [N]` - Show last N records
- `/info [ID]` - Detailed record information

#### Administrative Commands:
- `/allow_user [ID]` - Add user
- `/disallow_user [ID]` - Remove user
- `/allowed_users` - List allowed users
- `/set_user_name [ID] [name]` - Set user name
- `/set_log` - Set log chat
- `/set_report [ID] [name]` - Configure reports
- `/export` - Export data in JSON format
- `/sync_sheets` - Synchronize with Google Sheets
- `/my_report [name]` - Generate individual report

### Adding Records

1. Click "➕ Add Expense" button
2. Choose supplier type:
   - 👤 Your name
   - 🏢 Company name
   - ✏️ Manual entry
3. Enter direction
4. Enter expense description
5. Enter amount
6. Confirm the record

### Editing Records

1. Find record using `/recent` or `/search` command
2. Click "✏️ Edit" button
3. Select field to edit
4. Enter new value
5. Confirm changes

## 🔧 Technical Details

### Technologies Used

- **Python 3.8+** - Main programming language
- **python-telegram-bot** - Telegram Bot API wrapper
- **SQLite** - Database
- **pandas** - Data analysis
- **openpyxl** - Excel file handling
- **gspread** - Google Sheets API
- **python-dotenv** - Environment management

### Architecture

The project is built on modular architecture with clear separation of concerns:

#### Layers:
1. **Presentation Layer** (`bot/handlers/`) - Telegram API interaction
2. **Business Logic Layer** (`utils/`) - Business rules and logic
3. **Data Layer** (`database/`) - Data storage and retrieval
4. **Integration Layer** (`google_integration/`) - External API integrations

### Data Model

#### Records
- `id` - Unique identifier
- `date` - Date
- `supplier` - Supplier
- `direction` - Direction
- `description` - Description
- `amount` - Amount
- `spreadsheet_id` - Google Sheets ID
- `sheet_name` - Sheet name
- `user_id` - User ID

#### Payments
- `id` - Unique identifier
- `user_display_name` - User name
- `amount` - Amount
- `date_from` - Payment start date
- `date_to` - Payment end date
- `comment` - Comment

## 🛡️ Security

### Access Control
- Only allowed users can access the bot
- Administrative functions are restricted to specific users
- Users can only edit their own records

### Data Protection
- Important data stored in environment variables
- Regular database backups
- Logging of all operations

## 📈 Monitoring and Logging

The bot has a comprehensive logging system:

- ℹ️ **INFO** - Main operations
- ⚠️ **WARNING** - Warnings and unusual situations
- ❌ **ERROR** - Errors and exceptions

Logging level can be configured in the `.env` file.

## 🔄 Data Export and Import

### Automatic Data Export
The bot creates automatic backup in JSON format using the `/export` command.

### Manual Backup
```bash
# Database backup
cp data/expenses.db backup/expenses_$(date +%Y%m%d_%H%M%S).db

# Configuration backup
cp data/*.json backup/
```

## 🚀 Production Environment

### Using Docker
```bash
# Build Docker image
docker build -t coordinatbot .

# Run
docker run -d --name coordinatbot \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/credentials:/app/credentials \
  coordinatbot
```

### Creating Systemd Service (Linux)
```bash
sudo nano /etc/systemd/system/coordinatbot.service
```

```ini
[Unit]
Description=CoordinatBot Telegram Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/path/to/CoordinatBot
ExecStart=/path/to/CoordinatBot/venv/bin/python main_new.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable coordinatbot
sudo systemctl start coordinatbot
```

## 🤝 Contributing to the Project

### Adding New Features

1. Create a new branch
```bash
git checkout -b feature/new-feature
```

2. Add your changes
3. Create a Pull Request
4. Pass code review

### Code Standards

- Follow PEP 8 standard
- Write docstrings for all functions
- Add unit tests for new features
- Maintain modular architecture

### Testing

```bash
# Run unit tests
python -m pytest tests/

# Code quality check
flake8 src/
black src/
```

## ❓ Frequently Asked Questions (FAQ)

### How to update Telegram bot token?
1. Edit `.env` file
2. Update `TELEGRAM_BOT_TOKEN` value
3. Restart the bot

### How to add a new administrator?
1. Get the user's Telegram ID
2. Add it to `ADMIN_IDS` list in `.env` file
3. Restart the bot

### How to check Google Sheets connection?
Use the `/sync_sheets` command or check the logs.

## 📞 Support

For questions or issues, please contact:

- 📧 Email: support@coordinatbot.com
- 💬 Telegram: @coordinatbot_support
- 🐛 Issues: GitHub Issues section

## 📄 License

This project is published under the MIT license. See the `LICENSE` file for details.

## 🔄 Change History

### v2.0.0 (Modular Restructure)
- ✨ Complete architectural restructure
- 📁 Implementation of modular structure
- 🔧 Improved configuration
- 📊 Extended reporting system
- 🔄 Improved Google Sheets synchronization

### v1.0.0 (First Release)
- 🚀 Basic functionality
- 💰 Expense accounting
- 📈 Google Sheets integration
- 👥 Multi-user support

## 🙏 Acknowledgments

Special thanks to:

- Telegram Bot API team
- Google Sheets API developers
- Open source community
- All supporters and contributors

---

**CoordinatBot** - Your reliable partner in financial management! 💼✨

This project is built with ❤️ to simplify your financial accounting.
