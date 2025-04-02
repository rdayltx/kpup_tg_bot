#!/bin/bash
# Script to clean up zombie Chrome processes

echo "Checking for running Chrome processes..."
chrome_count=$(ps aux | grep -i chrome | grep -v grep | wc -l)

if [ $chrome_count -gt 0 ]; then
    echo "Found $chrome_count Chrome processes. Cleaning up..."
    
    # Kill all Chrome processes
    pkill -f chrome
    
    # Verify
    sleep 2
    remaining=$(ps aux | grep -i chrome | grep -v grep | wc -l)
    
    if [ $remaining -gt 0 ]; then
        echo "Force killing remaining Chrome processes..."
        pkill -9 -f chrome
    fi
    
    echo "Chrome processes cleaned up successfully."
else
    echo "No Chrome processes found. Nothing to clean up."
fi

echo "Cleaning up any leftover Chrome data directories..."
# Only remove temporary Chrome data directories, not the main one
find /tmp -maxdepth 1 -name "chrome-data-*" -type d -mmin +60 -exec rm -rf {} \;

echo "Cleanup completed!"