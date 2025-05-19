import time
import sys
import os
import traceback
from datetime import datetime
from sys import argv
from fca import fca
import pandas as pd
from analyze_run import analyze_run
from utils import get_date_range, OutputCapture

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)
os.makedirs("testing", exist_ok=True)

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

try:
    # Use the OutputCapture context manager to capture all output
    with OutputCapture(log_file, error_file, tee=True) as output:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Starting optimization run for {base} {seat} at {current_time}")
        
        if seat in ['CA','FO','FA'] and base in ['DAL','BUR','LAS','HPN','SNA','OPF','SCF','OAK']: 
            if base == 'DAL':
                ttr = 300
            elif base in ['BUR','LAS','HPN']:
                ttr = 300
            else:
                ttr = 300

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
    # Update status file
    with open(f"testing/{base}-{seat}.txt", "w") as f:
        f.write("finished")
        f.flush()
    
    print(f"Logs saved to {log_file} and {error_file}")