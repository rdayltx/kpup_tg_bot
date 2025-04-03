#!/bin/bash
# Healthcheck script to monitor and clean up Chrome processes
# Add to crontab to run every 15 minutes:
# */15 * * * * /path/to/healthcheck.sh >> /path/to/logs/healthcheck.log 2>&1

echo "===== $(date) ====="
echo "Checking bot container status..."

# Check if container is running
if ! docker ps | grep -q keepa_telegram_bot; then
  echo "Container is not running! Attempting to restart..."
  docker-compose up -d
  echo "Restart initiated. Exiting."
  exit 1
fi

# Check container memory usage
echo "Memory usage:"
docker stats keepa_telegram_bot --no-stream --format "{{.MemUsage}}"

# Check for zombie Chrome processes in container
echo "Checking for zombie Chrome processes in container..."
zombie_count=$(docker exec keepa_telegram_bot ps aux | grep -i chrome | grep -v grep | wc -l)
echo "Found $zombie_count Chrome processes"

if [ "$zombie_count" -gt 3 ]; then
  echo "Too many Chrome processes detected! Cleaning up..."
  docker exec keepa_telegram_bot pkill -f chrome
  echo "Chrome processes cleaned."
fi

# Check disk space
echo "Checking disk space..."
df -h | grep "/dev/sda1"

echo "Healthcheck completed successfully."