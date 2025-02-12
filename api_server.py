from fastapi import FastAPI, HTTPException
import asyncio
import os
from datetime import datetime
import uvicorn

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
   - Example: "run optimization with base bur seat fa"

2. Analyze Results:
   - Command: "analyze results for base <base> seat <seat>"
   - Example: "analyze results for base bur seat fa"

3. Check Status:
   - Command: "check status <base> <seat>" or "check all <seat>"
   - Example: "check status bur fa" or "check all fa"

4. Upload to NOC:
   - Command: "upload <base> <seat> to noc" or "upload all <seat> to noc"
   - Example: "upload bur fa to noc" or "upload all fa to noc"

Simply type "help" to receive these instructions.
"""

app = FastAPI(title="Optimization Chat Tool API")

@app.post("/command")
async def process_command(payload: dict):
    """
    POST endpoint that accepts a JSON payload with a "command" key.
    Example payload: { "command": "run optimization with base bur seat fa" }
    """
    command = payload.get("command")
    if not command:
        raise HTTPException(status_code=400, detail="Command not provided.")

    # Check if the command is for help.
    if command.strip().lower() == "help":
        return {"instructions": HELP_TEXT.strip()}

    # Use your existing AI agent to determine the intent and extract arguments.
    program_type, base_arg, seat_arg = await determine_intent(command)
    
    logs = []  # We'll accumulate messages that will be returned to the client.

    # Ensure the seat argument is present.
    if not seat_arg:
        return {"message": "Seat argument is missing in your command."}
    
    # If "all" bases are requested, process for each base.
    if base_arg == "all":
        await process_all_bases(program_type, seat_arg)
        logs.append("Processed command for all bases.")
        return {"logs": logs}
    
    # Ensure a base argument was extracted.
    if not base_arg:
        return {"message": "Base argument is missing in your command."}
    
    # Dispatch based on the detected program type.
    if program_type == ProgramType.RUN:
        key = f"{base_arg}-{seat_arg}"
        # Check if an optimization is already running.
        if key in running_optimizations and running_optimizations[key].returncode is None:
            return {"message": f"Optimization already running for base={base_arg}, seat={seat_arg}"}
        task = asyncio.create_task(run_optimization_async(program_type, base_arg, seat_arg))
        running_optimizations[key] = task
        logs.append(f"Started optimization for base={base_arg}, seat={seat_arg}.")

    elif program_type == ProgramType.STATUS:
        key = f"{base_arg}-{seat_arg}"

        # Check if an optimization process is running or has completed.
        if key in running_optimizations:
            process = running_optimizations[key]
            if process.returncode is None:
                logs.append("Optimization is currently running.")
            else:
                logs.append(f"Optimization completed with return code {process.returncode}.")
                del running_optimizations[key]
        else:
            logs.append("No running optimization found.")
        
        # Also check for a status file.
        status_file = f"testing/{base_arg}-{seat_arg}.txt"
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                file_status = f.read()
            timestamp = os.path.getmtime(status_file)
            modified_time = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
            logs.append(f"File Status: {file_status}")
            logs.append(f"Last Updated: {modified_time}")
        else:
            logs.append(f"No status file found: {status_file}.")

    elif program_type == ProgramType.UPLOAD:
        await upload_to_noc(base_arg, seat_arg)
        logs.append(f"Uploaded results for base={base_arg}, seat={seat_arg} to NOC.")

    elif program_type == ProgramType.ANALYZE:
        await view_results(base_arg, seat_arg)
        logs.append(f"Analyzed results for base={base_arg}, seat={seat_arg}.")

    else:
        logs.append(f"Unexpected program type: {program_type}.")

    return {"logs": logs}

@app.get("/help")
async def help_command():
    """
    GET endpoint that returns usage instructions.
    """
    return {"instructions": HELP_TEXT.strip()}

if __name__ == "__main__":
    # Run the API server on port 8000.
    uvicorn.run(app, host="0.0.0.0", port=8002) 