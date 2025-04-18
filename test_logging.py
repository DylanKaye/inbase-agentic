#!/usr/bin/env python3
"""
Test script to verify the logging implementation in optrunner.py
"""
import os
import sys
import subprocess
import time
from datetime import datetime

def main():
    # Create testing directory if it doesn't exist
    os.makedirs("testing", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    # Test parameters
    base = "DAL"
    seat = "CA"
    
    # Expected log files
    log_file = f"logs/{base}_{seat}.log"
    error_file = f"logs/{base}_{seat}_error.log"
    
    print(f"Testing logging for {base} {seat}")
    print(f"Starting test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Run the optrunner script
    cmd = f"python optrunner.py {base} {seat}"
    print(f"Running command: {cmd}")
    
    try:
        # Run the command
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        # Print the output
        print("\nCommand output:")
        print(stdout.decode())
        
        if stderr:
            print("\nCommand errors:")
            print(stderr.decode())
        
        # Check if log files were created
        log_files = [log_file, error_file]
        
        print(f"\nChecking log files:")
        for file_path in log_files:
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                print(f"- {os.path.basename(file_path)} exists ({file_size} bytes)")
                
                # Print the first few lines of each log file
                print(f"\nPreview of {os.path.basename(file_path)}:")
                with open(file_path, 'r') as f:
                    lines = f.readlines()
                    for i, line in enumerate(lines[:10]):
                        print(f"  {i+1}: {line.strip()}")
                    if len(lines) > 10:
                        print(f"  ... and {len(lines) - 10} more lines")
            else:
                print(f"- {os.path.basename(file_path)} does not exist!")
            
        # Check status files
        status_files = [f for f in os.listdir("testing") if f.startswith(f"{base}-{seat}")]
        if status_files:
            print(f"\nStatus files created:")
            for status_file in status_files:
                file_path = os.path.join("testing", status_file)
                file_size = os.path.getsize(file_path)
                print(f"- {status_file} ({file_size} bytes)")
                
                # Print the content of each status file
                print(f"\nContent of {status_file}:")
                with open(file_path, 'r') as f:
                    content = f.read()
                    print(content)
        else:
            print("\nNo status files were created!")
            
    except Exception as e:
        print(f"Error running test: {e}")
    
    print(f"\nTest completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main() 