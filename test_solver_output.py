#!/usr/bin/env python3
"""
Test script to verify that CBC solver output is properly captured in the logs
"""
import os
import sys
import cvxpy as cp
import numpy as np
from utils import capture_solver_output, OutputCapture

def test_solver_output():
    """
    Run a simple optimization problem with CBC solver and verify output is captured
    """
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    
    # Log file paths
    log_file = "logs/test_solver.log"
    
    print("Testing CBC solver output capture")
    print("================================")
    
    # Create a simple optimization problem
    x = cp.Variable(2, integer=True)
    objective = cp.Minimize(cp.sum_squares(x - np.array([10, 10])))
    constraints = [x >= 0]
    prob = cp.Problem(objective, constraints)
    
    # Use the OutputCapture context manager to capture all output
    with OutputCapture(log_file, tee=True) as output:
        print("Starting optimization with CBC solver")
        
        # Define a function to run the solver
        def run_solver():
            return prob.solve(solver='CBC', verbose=True)
        
        # Use the capture_solver_output function to capture CBC solver output
        capture_solver_output(run_solver, output_file=sys.stdout)
        
        print(f"Optimization completed with status: {prob.status}")
        print(f"Optimal value: {prob.value}")
        print(f"Optimal x: {x.value}")
    
    # Check if the log file was created and contains solver output
    if os.path.exists(log_file):
        file_size = os.path.getsize(log_file)
        print(f"\nLog file created: {log_file} ({file_size} bytes)")
        
        # Read the log file and check for CBC solver output
        with open(log_file, 'r') as f:
            log_content = f.read()
            
            # Check for typical CBC solver output
            if "CBC" in log_content and "Welcome to the CBC MILP Solver" in log_content:
                print("SUCCESS: CBC solver output was captured in the log file")
            else:
                print("WARNING: CBC solver output may not have been captured correctly")
                print("Log file content:")
                print("----------------")
                print(log_content)
    else:
        print(f"\nERROR: Log file was not created: {log_file}")

if __name__ == "__main__":
    test_solver_output() 