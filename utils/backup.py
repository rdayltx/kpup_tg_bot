import os
import shutil
import tarfile
import datetime
from utils.logger import get_logger

logger = get_logger(__name__)

def create_backup(backup_dir="/app/backups", data_dir="/app/data", logs_dir="/app/logs"):
    """
    Create a backup of the application data and logs
    
    Args:
        backup_dir (str): Directory to store backups
        data_dir (str): Directory containing application data
        logs_dir (str): Directory containing application logs
        
    Returns:
        str: Backup file path or None if backup failed
    """
    try:
        # Ensure the backup directory exists
        os.makedirs(backup_dir, exist_ok=True)
        
        # Create a timestamp for the backup filename
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"keepa_bot_backup_{timestamp}.tar.gz"
        backup_path = os.path.join(backup_dir, backup_filename)
        
        logger.info(f"Creating backup: {backup_filename}")
        
        # Create a tarball with data and logs
        with tarfile.open(backup_path, "w:gz") as tar:
            # Add data directory
            if os.path.exists(data_dir):
                logger.info(f"Adding data directory to backup: {data_dir}")
                tar.add(data_dir, arcname="data")
            
            # Add logs directory
            if os.path.exists(logs_dir):
                logger.info(f"Adding logs directory to backup: {logs_dir}")
                tar.add(logs_dir, arcname="logs")
        
        logger.info(f"Backup created successfully: {backup_path}")
        return backup_path
    
    except Exception as e:
        logger.error(f"Error creating backup: {str(e)}")
        return None

def list_backups(backup_dir="/app/backups"):
    """
    List all backup files in the backup directory
    
    Args:
        backup_dir (str): Directory containing backups
        
    Returns:
        list: List of backup filenames with creation times
    """
    try:
        # Ensure the backup directory exists
        os.makedirs(backup_dir, exist_ok=True)
        
        # Get all .tar.gz files in the backup directory
        backup_files = []
        for filename in os.listdir(backup_dir):
            if filename.endswith(".tar.gz") and filename.startswith("keepa_bot_backup_"):
                file_path = os.path.join(backup_dir, filename)
                
                # Get file creation time
                creation_time = os.path.getctime(file_path)
                creation_datetime = datetime.datetime.fromtimestamp(creation_time)
                
                # Get file size
                file_size = os.path.getsize(file_path)
                file_size_mb = file_size / (1024 * 1024)  # Convert to MB
                
                backup_files.append({
                    "filename": filename,
                    "path": file_path,
                    "creation_time": creation_datetime,
                    "size_mb": round(file_size_mb, 2)
                })
        
        # Sort by creation time (newest first)
        backup_files.sort(key=lambda x: x["creation_time"], reverse=True)
        
        return backup_files
    
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        return []

def delete_backup(backup_filename, backup_dir="/app/backups"):
    """
    Delete a specific backup file
    
    Args:
        backup_filename (str): Name of the backup file to delete
        backup_dir (str): Directory containing backups
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
    try:
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # Verify the file exists and is a backup file
        if not os.path.exists(backup_path):
            logger.error(f"Backup file not found: {backup_filename}")
            return False
        
        if not backup_filename.startswith("keepa_bot_backup_") or not backup_filename.endswith(".tar.gz"):
            logger.error(f"Not a valid backup file: {backup_filename}")
            return False
        
        # Delete the file
        os.remove(backup_path)
        logger.info(f"Backup deleted successfully: {backup_filename}")
        return True
    
    except Exception as e:
        logger.error(f"Error deleting backup: {str(e)}")
        return False

def auto_cleanup_backups(backup_dir="/app/backups", max_backups=10):
    """
    Automatically clean up old backups, keeping only the most recent ones
    
    Args:
        backup_dir (str): Directory containing backups
        max_backups (int): Maximum number of backups to keep
        
    Returns:
        int: Number of backups deleted
    """
    try:
        backups = list_backups(backup_dir)
        
        # If we have more backups than the maximum, delete the oldest ones
        if len(backups) > max_backups:
            # Get the backups to delete (oldest first)
            backups_to_delete = backups[max_backups:]
            
            # Delete each backup
            deleted_count = 0
            for backup in backups_to_delete:
                if delete_backup(backup["filename"], backup_dir):
                    deleted_count += 1
            
            logger.info(f"Auto-cleanup deleted {deleted_count} old backups")
            return deleted_count
        
        return 0
    
    except Exception as e:
        logger.error(f"Error during auto-cleanup: {str(e)}")
        return 0