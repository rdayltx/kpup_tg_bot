#!/bin/bash
# Enhanced script to rebuild the container from scratch with proper cleanup

echo "==============================================="
echo "KEEPA TELEGRAM BOT - CLEAN REBUILD"
echo "==============================================="

echo "1. Stopping containers..."
docker-compose down

echo "2. Killing any running Chrome processes..."
pkill -f chrome || echo "No Chrome processes found"

echo "3. Cleaning up Chrome data directory..."
sudo rm -rf ./chrome-data/*

echo "4. Removing Docker images..."
docker rmi -f $(docker images | grep keepa | awk '{print $3}') 2>/dev/null || echo "No images to remove"

echo "5. Cleaning Docker cache..."
docker builder prune -f

echo "6. Fixing permissions on project directories..."
sudo chown -R $USER:$USER .
sudo chmod -R 755 .

echo "7. Ensuring data directories exist with proper permissions..."
mkdir -p ./data ./logs ./backups ./chrome-data
chmod 777 ./chrome-data

echo "8. Rebuilding container..."
docker-compose up -d --build

echo "9. Showing logs..."
docker-compose logs -f