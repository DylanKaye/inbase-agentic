#!/usr/bin/env python3
"""
Utility script to clean up log files
"""
import os
import sys
import argparse
import glob
from datetime import datetime

def clean_logs(all_logs=False, base=None, seat=None):
    """
    Clean up log files
    
    Args:
        all_logs: If True, remove all logs
        base: Base code to clean logs for (e.g., DAL, BUR)
        seat: Seat code to clean logs for (e.g., CA, FO, FA)
    """
    if not os.path.exists("logs"):
        print("Logs directory does not exist.")
        return
    
    if all_logs:
        pattern = "logs/*.log"
    elif base and seat:
        base = base.upper()
        seat = seat.upper()
        pattern = f"logs/{base}_{seat}*.log"
    elif base:
        base = base.upper()
        pattern = f"logs/{base}_*.log"
    elif seat:
        seat = seat.upper()
        pattern = f"logs/*_{seat}*.log"
    else:
        print("No criteria specified. Use --all, --base, or --seat.")
        return
    
    log_files = glob.glob(pattern)
    
    if not log_files:
        print(f"No log files found matching pattern: {pattern}")
        return
    
    print(f"Found {len(log_files)} log files to remove:")
    for file_path in log_files:
        file_size = os.path.getsize(file_path)
        file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
        print(f"- {file_path} ({file_size} bytes, last modified: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')})")
    
    confirm = input("\nAre you sure you want to remove these files? (y/n): ")
    
    if confirm.lower() == 'y':
        for file_path in log_files:
            try:
                os.remove(file_path)
                print(f"Removed: {file_path}")
            except Exception as e:
                print(f"Error removing {file_path}: {e}")
        print(f"\nRemoved {len(log_files)} log files.")
    else:
        print("Operation cancelled.")

def main():
    parser = argparse.ArgumentParser(description="Clean up log files")
    parser.add_argument("--all", "-a", action="store_true", help="Remove all log files")
    parser.add_argument("--base", "-b", help="Base code to clean logs for (e.g., DAL, BUR)")
    parser.add_argument("--seat", "-s", help="Seat code to clean logs for (e.g., CA, FO, FA)")
    
    args = parser.parse_args()
    
    clean_logs(args.all, args.base, args.seat)

if __name__ == "__main__":
    main() 