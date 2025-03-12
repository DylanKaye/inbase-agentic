import time
import sys
import os
import traceback
from datetime import datetime
from sys import argv
from fca import fca
import pandas as pd
from analyze_run import analyze_run
from utils import get_date_range

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Get base and seat from command line arguments
base = argv[1].upper() if len(argv) > 1 else "UNKNOWN"
seat = argv[2].upper() if len(argv) > 2 else "UNKNOWN"

# Log file paths without timestamp - will overwrite previous logs
log_file = f"logs/{base}_{seat}.log"
error_file = f"logs/{base}_{seat}_error.log"

# Create status file
with open(f"testing/{base}-{seat}.txt", "w") as f:
    f.write("running")
    f.flush()

# Custom stdout and stderr classes that flush after every write
class FlushingFileWriter:
    def __init__(self, file_path, mode='w'):
        self.file = open(file_path, mode)
        self.original_stream = None
    
    def write(self, text):
        self.file.write(text)
        self.file.flush()
        if self.original_stream:
            self.original_stream.write(text)
            self.original_stream.flush()
    
    def flush(self):
        self.file.flush()
        if self.original_stream:
            self.original_stream.flush()
    
    def close(self):
        self.file.close()

try:
    # Redirect stdout to log file
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # Open log files (overwriting previous ones)
    log_f = FlushingFileWriter(log_file)
    log_f.original_stream = original_stdout
    
    error_f = FlushingFileWriter(error_file)
    error_f.original_stream = original_stderr
    
    # Redirect stdout and stderr
    sys.stdout = log_f
    sys.stderr = error_f
    
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Starting optimization run for {base} {seat} at {current_time}")
    
    if seat in ['CA','FO','FA'] and base in ['DAL','BUR','LAS','SNA','OPF','SCF','OAK']: 
        if base == 'DAL':
            ttr = 1500
        elif base in ['BUR','LAS']:
            ttr = 1000
        else:
            ttr = 500

        print(f"Running FCA optimization with time limit: {ttr} seconds")
        start_date, end_date = get_date_range()
        fca(base, seat, start_date, end_date, ttr)
        print(f"FCA optimization completed, running analysis")
        analyze_run(base, seat)
    else:
        print(f"Invalid base/seat combination: {base}/{seat}")
        with open(f"testing/{base}-{seat}-opt.txt", "w") as f:
            f.write('not actually running yet')
            f.flush()

    print(f"Run completed successfully at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

except Exception as e:
    # Log the exception
    print(f"Error occurred: {str(e)}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    
    # Also write to status file
    with open(f"testing/{base}-{seat}-error.txt", "w") as f:
        f.write(f"Error: {str(e)}")
        f.flush()

finally:
    # Restore stdout and stderr
    if 'log_f' in locals():
        sys.stdout = original_stdout
        log_f.close()
    
    if 'error_f' in locals():
        sys.stderr = original_stderr
        error_f.close()
    
    # Update status file
    with open(f"testing/{base}-{seat}.txt", "w") as f:
        f.write("finished")
        f.flush()
    
    print(f"Logs saved to {log_file} and {error_file}")