from program_runner import determine_intent, run_optimization_program, ProgramType
from program_runner import execute_program, ProgramResult
from pydantic_ai import Agent, RunContext
import asyncio
import os
from datetime import datetime
from typing import Dict
import warnings
from utils import get_date_range
warnings.filterwarnings("ignore")
# Track running optimizations
running_optimizations: Dict[str, asyncio.subprocess.Process] = {}

BASES = ["bur", "dal", "las", "scf", "opf", "oak", "sna"]

async def run_optimization_async(program_type: ProgramType, base_arg: str, seat_arg: str):
    """Run optimization asynchronously and update status"""
    try:
        print(f"\nStarting optimization process for base={base_arg}, seat={seat_arg}")
        process = await run_optimization_program(program_type, base_arg, seat_arg)
        
        # Store process for status checking
        key = f"{base_arg}-{seat_arg}"
        running_optimizations[key] = process
        
        # Monitor the process
        try:
            stdout_data, stderr_data = await process.communicate()
            if stdout_data:
                print(f"Process stdout: {stdout_data.decode()}")
            if stderr_data:
                print(f"Process stderr: {stderr_data.decode()}")
                
            if process.returncode != 0:
                print(f"Process failed with return code: {process.returncode}")
                if stderr_data:
                    print(f"Error output: {stderr_data.decode()}")
                    
        except Exception as e:
            print(f"Error monitoring process: {str(e)}")
            
        print(f"Optimization process completed for base={base_arg}, seat={seat_arg}")
        return process
        
    except Exception as e:
        print(f"\nFailed to start optimization for base={base_arg}, seat={seat_arg}: {str(e)}")
        key = f"{base_arg}-{seat_arg}"
        if key in running_optimizations:
            del running_optimizations[key]
        raise

def check_status(base_arg: str, seat_arg: str):
    """Check the current status of optimization for given base and seat"""
    print(f"\n=== Checking Status for Base: {base_arg}, Seat: {seat_arg} ===")
    
    # Check if optimization is currently running
    key = f"{base_arg}-{seat_arg}"
    if key in running_optimizations:
        process = running_optimizations[key]
        if process.returncode is None:
            print("\nStatus: Optimization is currently running")
        else:
            print(f"\nStatus: Optimization completed with return code {process.returncode}")
            # Cleanup completed process
            del running_optimizations[key]
    
    # Check for status file regardless of running status
    status_file = f"testing/{base_arg}-{seat_arg}.txt"
    
    if os.path.exists(status_file):
        with open(status_file, "r") as f:
            status = f.read()
        print("\nFile Status:")
        print(status)
        
        timestamp = os.path.getmtime(status_file)
        modified_time = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        print(f"\nLast Updated: {modified_time}")
    else:
        print(f"\nNo status file found: {status_file}")

async def upload_to_noc(base_arg: str, seat_arg: str):
    """Upload results to NOC"""
    try:
        process = await asyncio.create_subprocess_exec(
            "python",
            "upload_noc.py",
            base_arg,
            seat_arg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            print(f"\nSuccessfully uploaded results for base={base_arg}, seat={seat_arg}")
            if stdout:
                print("Output:", stdout.decode())
        else:
            print(f"\nFailed to upload results for base={base_arg}, seat={seat_arg}")
            if stderr:
                print("Error:", stderr.decode())
    except Exception as e:
        print(f"\nError during upload: {str(e)}")

async def process_all_bases(program_type: ProgramType, seat_arg: str):
    """Process command for all bases with given seat"""
    for base in BASES:
        if program_type == ProgramType.RUN:
            key = f"{base}-{seat_arg}"
            if key in running_optimizations and not running_optimizations[key].returncode is None:
                print(f"Optimization already running for base={base}, seat={seat_arg}")
                continue
            
            task = asyncio.create_task(run_optimization_async(program_type, base, seat_arg))
            running_optimizations[key] = task
            print(f"Started optimization for base={base}, seat={seat_arg}")
        
        elif program_type == ProgramType.STATUS:
            check_status(base, seat_arg)
        
        elif program_type == ProgramType.UPLOAD:
            await upload_to_noc(base, seat_arg)
            
        elif program_type == ProgramType.ANALYZE:
            print(f"\nAnalyzing for base={base}, seat={seat_arg}")
            await view_results(base, seat_arg)
        
        # Add small delay between operations
        await asyncio.sleep(0.5)

async def chat_interface():
    print("Welcome to the Optimization Chat Tool!")
    print("You can:")
    print("1. Run optimization (e.g., 'run optimization with base bur seat fa' or 'run all with seat fa')")
    print("2. Analyze results (e.g., 'analyze results for base bur seat fa')")
    print("3. Check status (e.g., 'check status bur fa' or 'check all fa')")
    print("4. Upload to NOC (e.g., 'upload bur fa to noc' or 'upload all fa to noc')")
    print("\nNote: Optimizations run in background. Use status to check progress.")
    
    while True:
        user_input = input("\nEnter your command: ")
        program_type, base_arg, seat_arg = await determine_intent(user_input)
        
        if not seat_arg:
            print("Could not extract Seat value from your command.")
            continue
            
        if base_arg == "all":
            await process_all_bases(program_type, seat_arg)
            continue
        
        if not base_arg:
            print("Could not extract Base value from your command.")
            continue
            
        if program_type == ProgramType.RUN:
            key = f"{base_arg}-{seat_arg}"
            if key in running_optimizations and not running_optimizations[key].returncode is None:
                print(f"Optimization already running for base={base_arg}, seat={seat_arg}")
                continue
                
            # Start optimization asynchronously
            task = asyncio.create_task(run_optimization_async(program_type, base_arg, seat_arg))
            running_optimizations[key] = task
            print("Use 'check status' command to monitor progress")
        
        elif program_type == ProgramType.ANALYZE:
            print("Analyzing optimization results...")
            await view_results(base_arg, seat_arg)
        
        elif program_type == ProgramType.STATUS:
            check_status(base_arg, seat_arg)
        
        elif program_type == ProgramType.UPLOAD:
            await upload_to_noc(base_arg, seat_arg)
        
        else:
            print(f"Unexpected program type: {program_type}")
        
        if user_input.lower() == 'exit':
            # Wait for running optimizations to complete
            if running_optimizations:
                print("\nWaiting for running optimizations to complete...")
                await asyncio.gather(*running_optimizations.values())
            print("Goodbye!")
            break

async def view_results(base_arg: str, seat_arg: str) -> str:
    """
    Reads the analysis file and returns the result as a string.
    """
    try:
        result_file = f"testing/{base_arg}-{seat_arg}-opt.txt"
        if os.path.exists(result_file):
            with open(result_file, "r") as f:
                analyze_result = f.read()
            output = (
                f"=== Optimization Results ===\n"
                f"Results for {base_arg}-{seat_arg}:\n"
                f"{analyze_result}"
            )
        else:
            output = f"No results found at {result_file}. Please ensure the optimization has completed."
    except Exception as e:
        output = f"Error reading results: {str(e)}"
    return output

if __name__ == "__main__":
    asyncio.run(chat_interface()) 