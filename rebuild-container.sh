#!/bin/bash
# Enhanced script to rebuild the container from scratch with proper cleanup
# Guarantees preservation of post_info.json and .env files

echo "==============================================="
echo "KEEPA TELEGRAM BOT - CLEAN REBUILD"
echo "==============================================="

# Create backup folder if it doesn't exist
mkdir -p ./backups

# Timestamp for backups
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo "1. Creating backup of critical data..."
# Backup .env file
if [ -f .env ]; then
    cp .env ./backups/env_backup_${TIMESTAMP}
    echo "   ✓ .env file backed up"
fi

# Backup post_info.json (check multiple possible locations)
if [ -f post_info.json ]; then
    cp post_info.json ./backups/post_info_backup_${TIMESTAMP}.json
    echo "   ✓ post_info.json (root dir) backed up"
elif [ -f ./data/post_info.json ]; then
    cp ./data/post_info.json ./backups/post_info_backup_${TIMESTAMP}.json
    echo "   ✓ post_info.json (data dir) backed up"
elif [ -f /app/data/post_info.json ]; then
    # Try to copy from container if running
    docker cp keepa_telegram_bot:/app/data/post_info.json ./backups/post_info_backup_${TIMESTAMP}.json 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "   ✓ post_info.json (container) backed up"
    else
        echo "   ⚠ Could not find post_info.json to backup"
    fi
else
    echo "   ⚠ Could not find post_info.json to backup"
fi

echo "2. Stopping containers..."
docker-compose down

echo "3. Killing any running Chrome processes..."
pkill -f chrome || echo "No Chrome processes found"

echo "4. Cleaning up Chrome data directory..."
sudo rm -rf ./chrome-data/*

echo "5. Removing Docker images..."
docker rmi -f $(docker images | grep keepa | awk '{print $3}') 2>/dev/null || echo "No images to remove"

echo "6. Cleaning Docker cache..."
docker builder prune -f

echo "7. Fixing permissions on project directories..."
sudo chown -R $USER:$USER .
sudo chmod -R 755 .

echo "8. Ensuring data directories exist with proper permissions..."
mkdir -p ./data ./logs ./backups ./chrome-data
chmod 777 ./chrome-data

# Restore post_info.json if it's not in the data directory
if [ ! -f ./data/post_info.json ] && [ -f ./backups/post_info_backup_${TIMESTAMP}.json ]; then
    echo "9. Restoring post_info.json to data directory..."
    cp ./backups/post_info_backup_${TIMESTAMP}.json ./data/post_info.json
    echo "   ✓ post_info.json restored"
fi

echo "10. Rebuilding container..."
docker-compose up -d --build

echo "11. Showing logs..."
docker-compose logs -f