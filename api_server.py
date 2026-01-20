from fastapi import FastAPI, HTTPException
import asyncio
import os
from datetime import datetime
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Import functions and variables from your existing modules.
from chat_tool import (
    run_optimization_async, 
    upload_to_noc, 
    process_all_bases, 
    view_results, 
    running_optimizations,
    run_diagnose
)
from program_runner import ProgramType, determine_intent

# Help text that contains the instructions.
HELP_TEXT = """
Welcome to the Optimization Chat Tool!

You can interact with this tool by sending commands with the following formats:

1. Run Optimization:
   - Command: "run optimization with base <base> seat <seat>"
   - Example: "run optimization with base BUR seat FA"
   - You can also use "run all <seat>" to run optimizations for all bases

2. Analyze Results:
   - Command: "analyze results for base <base> seat <seat>"
   - Example: "analyze results for base BUR seat FA"

3. Check Status:
   - Command: "check status <base> <seat>"
   - Example: "check status BUR FA"
   - You can also use "check all <seat>" to check status for all bases

4. Upload to NOC:
   - Command: "upload <base> <seat> to noc"
   - Example: "upload BUR FA to noc"

5. Diagnose Failures:
   - Command: "diagnose <base> <seat>"
   - Example: "diagnose DAL FO"
   - Use this to find out why an optimization failed
   - Also works with: "why did DAL FO fail", "debug BUR CA", "troubleshoot SNA FA"

Simply type "help" to receive these instructions.
"""

app = FastAPI(title="Optimization Chat Tool API")

# Optionally, allow CORS if accessing from a different origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define API endpoints first.
@app.post("/command")
async def process_command(payload: dict):
    """
    POST endpoint that accepts a JSON payload with a "command" key.
    Example payload: { "command": "run optimization with base bur seat fa" }
    """
    command = payload.get("command")
    if not command:
        raise HTTPException(status_code=400, detail="Command not provided.")

    print(f"\nReceived command: {command}")  # Debug log

    # Use your existing AI agent to determine the intent and extract arguments.
    program_type, base_arg, seat_arg = await determine_intent(command)
    
    print(f"Parsed intent: type={program_type}, base={base_arg}, seat={seat_arg}")  # Debug log
    
    # Handle unrecognized commands
    if program_type == "UNRECOGNIZED":
        print("Command was unrecognized")  # Debug log
        return {"message": "I'm not sure what you want to do. Please try rephrasing your command or type 'commands' to see available options."}
    
    # Handle clarification requests
    if program_type == "CLARIFY":
        print("Clarification needed")  # Debug log
        return {"message": base_arg}  # base_arg contains the explanation
    
    # Handle the commands request
    if program_type is None and base_arg is None and seat_arg is None:
        print("Returning help text")  # Debug log
        return {"instructions": HELP_TEXT.strip()}
    
    logs = []  # We'll accumulate messages that will be returned to the client.

    # Ensure the seat argument is present.
    if not seat_arg:
        print("Missing seat argument")  # Debug log
        return {"message": "Seat argument is missing in your command."}
    
    # If "all" bases are requested, process for each base.
    if base_arg == "all":
        print("Processing all bases")  # Debug log
        # Only allow "all" with RUN and STATUS commands
        if program_type not in [ProgramType.RUN, ProgramType.STATUS]:
            return {"message": f"The 'all' option is only available for 'run' and 'check' commands, not for {program_type.value}"}
        
        if program_type == ProgramType.STATUS:
            all_statuses = []
            for base in ["BUR", "DAL", "HPN", "LAS", "SCF", "OPF", "OAK", "SNA"]:
                try:
                    status_result = check_status(base, seat_arg)
                    status_result["base"] = base
                    status_result["seat"] = seat_arg
                    
                    # Add last updated timestamp
                    status_file = f"testing/{base}-{seat_arg}.txt"
                    if os.path.exists(status_file):
                        timestamp = os.path.getmtime(status_file)
                        status_result["last_updated"] = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    
                    all_statuses.append(status_result)
                except Exception as e:
                    all_statuses.append({
                        "base": base,
                        "seat": seat_arg,
                        "status": "error",
                        "message": str(e)
                    })
            return {"all_statuses": all_statuses}
        elif program_type == ProgramType.RUN:
            run_statuses = []
            for base in ["BUR", "DAL", "HPN", "LAS", "SCF", "OPF", "OAK", "SNA"]:
                try:
                    key = f"{base}-{seat_arg}"
                    # Check if optimization is already running
                    if key in running_optimizations and running_optimizations[key].returncode is None:
                        run_statuses.append({
                            "base": base,
                            "seat": seat_arg,
                            "status": "Already running",
                            "error": None
                        })
                        continue
                    
                    # Start new optimization
                    task = asyncio.create_task(run_optimization_async(program_type, base, seat_arg))
                    running_optimizations[key] = task
                    run_statuses.append({
                        "base": base,
                        "seat": seat_arg,
                        "status": "Started optimization",
                        "error": None
                    })
                except Exception as e:
                    run_statuses.append({
                        "base": base,
                        "seat": seat_arg,
                        "status": "Failed to start",
                        "error": str(e)
                    })
            return {"all_statuses": run_statuses}
    
    # Ensure a base argument was extracted.
    if not base_arg:
        print("Missing base argument")  # Debug log
        return {"message": "Base argument is missing in your command."}
    
    # Dispatch based on the detected program type.
    if program_type == ProgramType.RUN:
        print(f"Starting optimization for base={base_arg}, seat={seat_arg}")  # Debug log
        key = f"{base_arg}-{seat_arg}"
        # Check if an optimization is already running.
        if key in running_optimizations and running_optimizations[key].returncode is None:
            print(f"Optimization already running for {key}")  # Debug log
            return {"message": f"Optimization already running for base={base_arg}, seat={seat_arg}"}
        try:
            task = asyncio.create_task(run_optimization_async(program_type, base_arg, seat_arg))
            running_optimizations[key] = task
            print(f"Started optimization task for {key}")  # Debug log
            logs.append(f"Started optimization for base={base_arg}, seat={seat_arg}.")
        except Exception as e:
            print(f"Error starting optimization: {str(e)}")  # Debug log
            logs.append(f"Error starting optimization: {str(e)}")

    elif program_type == ProgramType.STATUS:
        print(f"Checking status for base={base_arg}, seat={seat_arg}")  # Debug log
        return check_status(base_arg, seat_arg)

    elif program_type == ProgramType.ANALYZE:
        print(f"Analyzing results for base={base_arg}, seat={seat_arg}")  # Debug log
        # Handle single base analysis
        result_file = f"testing/{base_arg}-{seat_arg}-opt.txt"
        try:
            if os.path.exists(result_file):
                with open(result_file, "r") as f:
                    analyze_output = f.read().strip()
            else:
                analyze_output = f"No optimization results found for {base_arg}-{seat_arg}"
            return {"logs": [analyze_output]}
        except Exception as e:
            return {"logs": [f"Error analyzing results: {str(e)}"]}

    elif program_type == ProgramType.UPLOAD:
        print(f"Uploading results for base={base_arg}, seat={seat_arg}")  # Debug log
        await upload_to_noc(base_arg, seat_arg)
        logs.append(f"Uploaded results for base={base_arg}, seat={seat_arg} to NOC.")

    elif program_type == ProgramType.DIAGNOSE:
        print(f"Running diagnostics for base={base_arg}, seat={seat_arg}")  # Debug log
        diagnose_output = await run_diagnose(base_arg, seat_arg)
        return {"logs": [diagnose_output]}

    else:
        print(f"Unexpected program type: {program_type}")  # Debug log
        logs.append(f"Unexpected program type: {program_type}.")

    return {"logs": logs}

@app.get("/commands")
async def commands():
    """
    GET endpoint that returns available commands and usage instructions.
    """
    return {"instructions": HELP_TEXT.strip()}

def check_status(base_arg: str, seat_arg: str) -> dict:
    """Check the current status of optimization for given base and seat
    
    Returns status:
    - "running" - optimization is in progress
    - "complete_feasible" - optimization finished with a feasible solution
    - "complete_infeasible" - optimization finished but no feasible solution found
    - "unknown" - status could not be determined
    """
    key = f"{base_arg}-{seat_arg}"
    
    # Check the status file first (testing/{base}-{seat}.txt)
    status_file = f"testing/{base_arg}-{seat_arg}.txt"
    solver_status_file = f"{base_arg}.txt"
    
    # Determine if running from status file
    is_running = False
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                file_status = f.read().strip().lower()
            is_running = (file_status == "running")
        except Exception:
            pass
    
    # Also check task tracking
    if key in running_optimizations:
        task = running_optimizations[key]
        try:
            if not task.done():
                is_running = True
            else:
                # Cleanup completed task
                del running_optimizations[key]
        except Exception:
            pass
    
    # If running, return that status
    if is_running:
        return {
            "status": "running",
            "message": f"Optimization for {base_arg} {seat_arg} is currently running"
        }
    
    # Check solver status file for feasibility
    feasibility = "unknown"
    solver_status = None
    
    if os.path.exists(solver_status_file):
        try:
            with open(solver_status_file, "r") as f:
                content = f.read().strip()
            # Parse "Status: optimal" format
            if content.startswith("Status:"):
                solver_status = content.split(":", 1)[1].strip().lower()
            else:
                solver_status = content.lower()
            
            # Determine feasibility from solver status
            if solver_status in ["optimal", "optimal_inaccurate"]:
                feasibility = "feasible"
            elif solver_status in ["infeasible", "unbounded", "infeasible_or_unbounded"]:
                feasibility = "infeasible"
            else:
                feasibility = "unknown"
        except Exception:
            pass
    
    # Check if we have a finished status file
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                file_status = f.read().strip().lower()
            if file_status == "finished":
                if feasibility == "feasible":
                    return {
                        "status": "complete_feasible",
                        "message": f"Optimization for {base_arg} {seat_arg} completed with a feasible solution",
                        "solver_status": solver_status
                    }
                elif feasibility == "infeasible":
                    return {
                        "status": "complete_infeasible", 
                        "message": f"Optimization for {base_arg} {seat_arg} completed but no feasible solution was found",
                        "solver_status": solver_status
                    }
                else:
                    return {
                        "status": "complete_unknown",
                        "message": f"Optimization for {base_arg} {seat_arg} completed but feasibility status is unknown",
                        "solver_status": solver_status
                    }
        except Exception:
            pass
    
    # No status file found
    return {
        "status": "not_found",
        "message": f"No optimization status found for {base_arg} {seat_arg}. Has the optimization been run?"
    }

# Then mount the static files.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    # Run the API server on port 8000.
    uvicorn.run(app, host="0.0.0.0", port=8002) 