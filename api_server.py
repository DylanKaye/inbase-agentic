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
    running_optimizations
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
            for base in ["BUR", "DAL", "LAS", "SCF", "OPF", "OAK", "SNA"]:
                try:
                    # Check if optimization is running
                    key = f"{base}-{seat_arg}"
                    is_running = key in running_optimizations
                    
                    # Check status file
                    status_file = f"testing/{base}-{seat_arg}.txt"
                    status_info = ""
                    last_updated = ""
                    
                    if os.path.exists(status_file):
                        with open(status_file, "r") as f:
                            status_info = f.read().strip()
                        timestamp = os.path.getmtime(status_file)
                        last_updated = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
                    
                    status = {
                        "base": base,
                        "seat": seat_arg,
                        "running": is_running,
                        "status_info": status_info,
                        "last_updated": last_updated
                    }
                    all_statuses.append(status)
                except Exception as e:
                    all_statuses.append({
                        "base": base,
                        "seat": seat_arg,
                        "error": str(e)
                    })
            return {"all_statuses": all_statuses}
        elif program_type == ProgramType.RUN:
            run_statuses = []
            for base in ["BUR", "DAL", "LAS", "SCF", "OPF", "OAK", "SNA"]:
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
    """Check the current status of optimization for given base and seat"""
    logs = []
    
    # Check if optimization is currently running
    key = f"{base_arg}-{seat_arg}"
    if key in running_optimizations:
        task = running_optimizations[key]
        if not task.done():
            logs.append("Status: Optimization is currently running")
        else:
            try:
                result = task.result()
                logs.append("Status: Optimization completed successfully")
            except Exception as e:
                logs.append(f"Status: Optimization failed with error: {str(e)}")
            # Cleanup completed task
            del running_optimizations[key]
    
    # Check for status file regardless of running status
    status_file = f"testing/{base_arg}-{seat_arg}.txt"
    
    if os.path.exists(status_file):
        with open(status_file, "r") as f:
            status = f.read()
        logs.append("\nFile Status:")
        logs.append(status)
    
    return {"logs": logs}

# Then mount the static files.
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    # Run the API server on port 8000.
    uvicorn.run(app, host="0.0.0.0", port=8002) 