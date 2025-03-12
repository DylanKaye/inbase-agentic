#!/usr/bin/env python3
"""
Utility script to view logs for a specific base/seat combination
"""
import os
import sys
import argparse
import time
from datetime import datetime

def follow_file(file_path, sleep_sec=0.5):
    """
    Generator function that yields new lines in a file as they are added
    Similar to 'tail -f' Unix command
    """
    with open(file_path, 'r') as f:
        # Go to the end of the file
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(sleep_sec)  # Sleep briefly
                continue
            yield line

def view_logs(base, seat, error_only=False, tail=None, follow=False):
    """
    View logs for a specific base/seat combination
    
    Args:
        base: Base code (e.g., DAL, BUR)
        seat: Seat code (e.g., CA, FO, FA)
        error_only: If True, only show error logs
        tail: If provided, only show the last N lines
        follow: If True, continuously show new log entries (like 'tail -f')
    """
    base = base.upper()
    seat = seat.upper()
    
    log_file = f"logs/{base}_{seat}.log"
    error_file = f"logs/{base}_{seat}_error.log"
    
    files_to_check = [error_file] if error_only else [log_file, error_file]
    
    if follow:
        # Check if at least one file exists
        if not any(os.path.exists(f) for f in files_to_check):
            print(f"No log files found for {base} {seat}")
            return
        
        # Print header
        print(f"\n{'='*80}")
        print(f"Following logs for {base} {seat}...")
        print(f"Press Ctrl+C to stop")
        print(f"{'='*80}\n")
        
        try:
            # Keep track of the last position in each file
            file_positions = {}
            
            while True:
                for file_path in files_to_check:
                    if not os.path.exists(file_path):
                        continue
                    
                    # Get file size
                    file_size = os.path.getsize(file_path)
                    
                    # If this is a new file or it has been truncated, start from the beginning
                    if file_path not in file_positions or file_positions[file_path] > file_size:
                        file_positions[file_path] = 0
                    
                    # If the file has grown, read the new data
                    if file_size > file_positions[file_path]:
                        with open(file_path, 'r') as f:
                            f.seek(file_positions[file_path])
                            new_data = f.read()
                            if new_data:
                                file_label = "ERROR" if file_path.endswith("_error.log") else "LOG"
                                print(f"[{file_label}] {new_data}", end="")
                            file_positions[file_path] = file_size
                
                time.sleep(0.5)  # Sleep briefly to avoid high CPU usage
                
        except KeyboardInterrupt:
            print("\nStopped following logs")
    else:
        for file_path in files_to_check:
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                print(f"\n{'='*80}")
                print(f"File: {file_path}")
                print(f"Size: {file_size} bytes")
                print(f"Last modified: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"{'='*80}\n")
                
                try:
                    with open(file_path, 'r') as f:
                        lines = f.readlines()
                        
                        if tail:
                            lines = lines[-tail:]
                            print(f"Showing last {tail} lines:\n")
                        
                        for line in lines:
                            print(line.rstrip())
                except Exception as e:
                    print(f"Error reading file: {e}")
            else:
                print(f"\nFile {file_path} does not exist.")

def main():
    parser = argparse.ArgumentParser(description="View logs for a specific base/seat combination")
    parser.add_argument("base", help="Base code (e.g., DAL, BUR)")
    parser.add_argument("seat", help="Seat code (e.g., CA, FO, FA)")
    parser.add_argument("--error", "-e", action="store_true", help="Only show error logs")
    parser.add_argument("--tail", "-t", type=int, help="Only show the last N lines")
    parser.add_argument("--follow", "-f", action="store_true", help="Follow the log file (like 'tail -f')")
    
    args = parser.parse_args()
    
    view_logs(args.base, args.seat, args.error, args.tail, args.follow)

if __name__ == "__main__":
    main() 