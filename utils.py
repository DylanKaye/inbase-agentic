"""
Utility functions for the optimization system
"""
import os
import sys
import io
import ctypes
import tempfile
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

def get_date_range():
    """
    Get the date range for the optimization period.
    Currently hardcoded to March 2025, but could be made configurable.
    
    Returns:
        tuple: (start_date, end_date) as strings in YYYY-MM-DD format
    """
    return "2025-03-01", "2025-03-31"

@contextmanager
def capture_c_stdout(output_file=None, tee=True):
    """
    Capture stdout from C/C++ libraries (like CBC solver) that write directly to 
    the file descriptors rather than using Python's print function.
    
    Args:
        output_file: File object to write captured output to
        tee: If True, also write to original stdout
        
    Yields:
        None
    """
    # Create a temporary file to capture output
    temp_fd, temp_path = tempfile.mkstemp()
    
    # Save original stdout file descriptor
    original_stdout_fd = os.dup(sys.stdout.fileno())
    
    # Redirect stdout to our temporary file
    os.dup2(temp_fd, sys.stdout.fileno())
    
    try:
        # Yield control back to the caller
        yield
    finally:
        # Restore original stdout
        os.dup2(original_stdout_fd, sys.stdout.fileno())
        os.close(original_stdout_fd)
        os.close(temp_fd)
        
        # Read the captured output
        with open(temp_path, 'r') as f:
            captured_output = f.read()
        
        # Write to the output file if provided
        if output_file:
            output_file.write(captured_output)
            output_file.flush()
        
        # Also write to original stdout if tee is True
        if tee:
            sys.__stdout__.write(captured_output)
            sys.__stdout__.flush()
        
        # Clean up the temporary file
        os.unlink(temp_path)

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