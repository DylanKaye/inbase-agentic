"""
Utility functions for the optimization system
"""
import os
import sys
import io
import ctypes
import tempfile
import subprocess
from datetime import datetime, timedelta
from contextlib import contextmanager

NUM_TO_MONTH = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec"
}

MONTH_TO_NUM = {month: num for num, month in NUM_TO_MONTH.items()}

def get_global_date():
    """
    Get the global date from global_date.txt
    
    Returns:
        dict: Dictionary with month and year
    """
    try:
        with open('../pbsoptimizer/global_date.txt', 'r') as f:
            lines = f.read().strip().split('\n')
        
        # If file has at least 4 lines, use the stored month and year
        if len(lines) >= 4:
            month = lines[2]
            year = int(lines[3])
        else:
            # Parse from the start date if month and year aren't explicitly stored
            start_date = lines[0]
            date_parts = start_date.split('-')
            month_num = int(date_parts[1])
            month = NUM_TO_MONTH.get(month_num, "None")
            year = int(date_parts[0])
        
        return {"month": month, "year": year}
    except (FileNotFoundError, IndexError, ValueError) as e:
        print(f"Error reading global date file: {e}")
        # Default to current month/year if there's an error
        now = datetime.now()
        return {"month": NUM_TO_MONTH.get(now.month, "Jan"), "year": now.year}

def get_date_range():
    """
    Get the date range for the optimization period based on the global date.
    Returns the first and last days of the month from the global date.
    
    Returns:
        tuple: (start_date, end_date) as strings in YYYY-MM-DD format
    """
    # Get the month and year from global date
    date_info = get_global_date()
    month_str = date_info["month"]
    year = date_info["year"]
    
    # Convert month name to number
    month_num = MONTH_TO_NUM.get(month_str, 1)  # Default to January if month not found
    
    # First day is always 1
    first_day = 1
    
    # Calculate last day of month
    if month_str in ["Jan", "Mar", "May", "Jul", "Aug", "Oct", "Dec"]:
        last_day = 31
    elif month_str in ["Apr", "Jun", "Sep", "Nov"]:
        last_day = 30
    else:  # February
        # Check for leap year
        if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
            last_day = 29  # Leap year
        else:
            last_day = 28  # Non-leap year
    
    # Format dates
    start_date = f"{year}-{month_num:02d}-{first_day:02d}"
    end_date = f"{year}-{month_num:02d}-{last_day:02d}"
    
    print(f"Using date range: {start_date} to {end_date}")
    return start_date, end_date

def capture_solver_output(solver_command, output_file=None, tee=True):
    """
    A simpler approach to capture solver output using string buffers
    
    Args:
        solver_command: A function that runs the solver
        output_file: File object to write captured output to
        tee: If True, also write to original stdout
    
    Returns:
        The result of the solver_command function
    """
    # Create a string buffer to capture output
    buffer = io.StringIO()
    
    # Save original stdout
    original_stdout = sys.stdout
    
    try:
        # Redirect stdout to our buffer
        sys.stdout = buffer if not tee else TeeStringIO(buffer, original_stdout)
        
        # Run the solver command
        result = solver_command()
        
        return result
    finally:
        # Restore original stdout
        sys.stdout = original_stdout
        
        # Get the captured output
        captured_output = buffer.getvalue()
        
        # Write to the output file if provided
        if output_file:
            output_file.write(captured_output)
            output_file.flush()
        
        # Close the buffer
        buffer.close()

class TeeStringIO(io.StringIO):
    """StringIO that also writes to another stream"""
    def __init__(self, buffer, original=None):
        super().__init__()
        self.buffer = buffer
        self.original = original
    
    def write(self, text):
        self.buffer.write(text)
        if self.original:
            self.original.write(text)
        return len(text)
    
    def flush(self):
        self.buffer.flush()
        if self.original:
            self.original.flush()

@contextmanager
def capture_c_stdout(output_file=None, tee=True):
    """
    Capture stdout from C/C++ libraries (like CBC solver) that write directly to 
    the file descriptors rather than using Python's print function.
    
    This version uses a temporary file approach that's more robust.
    
    Args:
        output_file: File object to write captured output to
        tee: If True, also write to original stdout
        
    Yields:
        None
    """
    # Create a temporary file to capture output
    temp_file = tempfile.NamedTemporaryFile(mode='w+', delete=False)
    temp_path = temp_file.name
    temp_file.close()
    
    # Save original stdout
    original_stdout = sys.stdout
    
    try:
        # Open the temp file for writing
        with open(temp_path, 'w') as f:
            # Redirect stdout to our temporary file
            sys.stdout = f if not tee else TeeWriter(f, original_stdout)
            
            # Yield control back to the caller
            yield
    finally:
        # Restore original stdout
        sys.stdout = original_stdout
        
        # Read the captured output
        with open(temp_path, 'r') as f:
            captured_output = f.read()
        
        # Write to the output file if provided
        if output_file:
            output_file.write(captured_output)
            output_file.flush()
        
        # Clean up the temporary file
        try:
            os.unlink(temp_path)
        except:
            pass

class TeeWriter:
    """Writer that writes to a file and optionally to another stream"""
    def __init__(self, file, original=None):
        self.file = file
        self.original = original
    
    def write(self, text):
        self.file.write(text)
        self.file.flush()
        if self.original:
            self.original.write(text)
            self.original.flush()
        return len(text)
    
    def flush(self):
        self.file.flush()
        if self.original:
            self.original.flush()

class OutputCapture:
    """
    Utility class to capture all output, including from C/C++ libraries.
    """
    def __init__(self, log_file, error_file=None, tee=True):
        """
        Initialize the output capture.
        
        Args:
            log_file: Path to the log file
            error_file: Path to the error file (if None, errors go to log_file)
            tee: If True, also write to original stdout/stderr
        """
        self.log_file_path = log_file
        self.error_file_path = error_file or log_file
        self.tee = tee
        self.log_file = None
        self.error_file = None
        self.original_stdout = None
        self.original_stderr = None
    
    def __enter__(self):
        """Start capturing output"""
        # Save original stdout and stderr
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
        # Open log files
        self.log_file = open(self.log_file_path, 'w')
        if self.error_file_path == self.log_file_path:
            self.error_file = self.log_file
        else:
            self.error_file = open(self.error_file_path, 'w')
        
        # Create custom stdout and stderr
        class TeeWriter(io.TextIOBase):
            def __init__(self, file, original=None, tee=True):
                self.file = file
                self.original = original
                self.tee = tee
            
            def write(self, text):
                self.file.write(text)
                self.file.flush()
                if self.tee and self.original:
                    self.original.write(text)
                    self.original.flush()
                return len(text)
            
            def flush(self):
                self.file.flush()
                if self.tee and self.original:
                    self.original.flush()
        
        # Redirect stdout and stderr
        sys.stdout = TeeWriter(self.log_file, self.original_stdout, self.tee)
        sys.stderr = TeeWriter(self.error_file, self.original_stderr, self.tee)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop capturing output"""
        # Restore stdout and stderr
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr
        
        # Close log files
        if self.log_file:
            self.log_file.close()
        if self.error_file and self.error_file != self.log_file:
            self.error_file.close() 