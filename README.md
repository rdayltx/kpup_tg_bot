# Keepa Telegram Bot (Dockerized)

This is a Telegram bot that monitors messages for Amazon product links (ASINs), tracks the prices, and updates Keepa price watches based on comments.

## Features

- Monitor Telegram chats for Amazon product links
- Extract ASINs from messages
- Process comments with price information
- Update Keepa price watch alerts
- Support for multiple Keepa accounts
- Automated backups with bot commands

## Docker Setup

### Prerequisites

- Docker and Docker Compose installed
- A Telegram Bot token (from [@BotFather](https://t.me/botfather))
- Keepa account credentials

### Setup Instructions

1. **Clone this repository**

```bash
git clone <repository-url>
cd keepa-telegram-bot
```

2. **Create an .env file**

Create a `.env` file in the project root with the following variables:

```
# Telegram settings
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
SOURCE_CHAT_ID=your_source_chat_id
DESTINATION_CHAT_ID=your_destination_chat_id
ADMIN_ID=your_admin_user_id

# Keepa settings (add as many accounts as needed)
KEEPA_PREMIUM_USERNAME=your_keepa_username
KEEPA_PREMIUM_PASSWORD=your_keepa_password
KEEPA_MERAXES_USERNAME=another_keepa_username
KEEPA_MERAXES_PASSWORD=another_keepa_password
# ... add more accounts if needed

# Default account
DEFAULT_KEEPA_ACCOUNT=Premium

# Other settings
UPDATE_EXISTING_TRACKING=true
DATA_FILE=post_info.json
```

3. **Build and run the Docker container**

```bash
docker-compose up -d
```

This will:

- Build the Docker image with all dependencies
- Start the container in detached mode
- Create persistent volumes for data, logs, and backups

4. **View logs**

```bash
docker-compose logs -f
```

## Bot Commands

- `/start` - Start the bot
- `/status` - Show current bot configuration and status
- `/accounts` - List all configured Keepa accounts
- `/start_keepa [ACCOUNT]` - Start a Keepa session for the specified account
- `/test_account ACCOUNT` - Test login for a specific Keepa account
- `/update ASIN PRICE [ACCOUNT]` - Manually update price for a product
- `/clear` - Clear cache of tracked posts
- `/close_sessions` - Close all browser sessions

### Backup Commands

- `/backup` - Create a backup of the bot data and logs
- `/list_backups` - List all available backups
- `/download_backup FILENAME` - Download a specific backup file
- `/delete_backup FILENAME` - Delete a specific backup file

## Volume Management

The Docker setup creates the following persistent volumes:

- `./data:/app/data` - Application data, including tracked posts
- `./logs:/app/logs` - Application logs
- `./backups:/app/backups` - Backup files
- `./chrome-data:/app/chrome-data` - Chrome browser data

These volumes are mounted from your host system to the container, ensuring data persistence across container restarts.

## Manual Backup (Host System)

If you need to create a backup outside of the bot commands, you can simply archive the mounted volumes:

```bash
tar -czvf keepa_bot_manual_backup.tar.gz ./data ./logs
```

## Maintenance

### Updating the Bot

1. Pull the latest code:

```bash
git pull
```

2. Rebuild and restart the container:

```bash
docker-compose down
docker-compose up --build -d
```

### Restarting the Bot

```bash
docker-compose restart
```

### Stopping the Bot

```bash
docker-compose down
```

## Troubleshooting

### Browser Issues

If you encounter browser-related issues:

1. Clear the Chrome data:

```bash
rm -rf ./chrome-data/*
```

2. Restart the container:
