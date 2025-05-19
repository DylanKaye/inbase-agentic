from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Literal
from pydantic import BaseModel, Field
from openai import OpenAI
import subprocess
import os
from datetime import datetime
import asyncio
import json
from utils import get_date_range

class ProgramStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"

class ProgramType(str, Enum):
    RUN = "RUN"
    ANALYZE = "ANALYZE"
    STATUS = "STATUS"
    UPLOAD = "UPLOAD"

class ProgramResult(BaseModel):
    command: str = Field(..., description="The command that was executed")
    status: ProgramStatus = Field(..., description="The execution status")
    output: str = Field(..., description="Program output")
    error: Optional[str] = Field(None, description="Error message if any")
    runtime: float = Field(..., description="Execution time in seconds")
    exit_code: int = Field(..., description="Program exit code")

@dataclass
class RunnerDeps:
    working_dir: str
    env_vars: Dict[str, str] = None
    timeout: int = 30
    
    def __post_init__(self):
        if self.env_vars is None:
            self.env_vars = {}

def execute_program(command: str, working_dir: str = ".", timeout: int = 30) -> ProgramResult:
    """
    Executes a program and returns the result.
    """
    start_time = datetime.now()
    
    try:
        # Create environment with custom vars
        env = os.environ.copy()
        
        # Run the program
        process = subprocess.Popen(
            command.split(),
            cwd=working_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True
        )
        
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            status = ProgramStatus.SUCCESS if process.returncode == 0 else ProgramStatus.ERROR
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            status = ProgramStatus.TIMEOUT
        
        runtime = (datetime.now() - start_time).total_seconds()
        
        return ProgramResult(
            command=command,
            status=status,
            output=stdout or "",
            error=stderr if stderr else None,
            runtime=runtime,
            exit_code=process.returncode
        )
        
    except Exception as e:
        runtime = (datetime.now() - start_time).total_seconds()
        return ProgramResult(
            command=command,
            status=ProgramStatus.ERROR,
            output="",
            error=str(e),
            runtime=runtime,
            exit_code=-1
        )

class IntentResult(BaseModel):
    intent: ProgramType = Field(..., description="The user's intended action")
    base_arg: Optional[str] = Field(None, description="Base argument if provided")
    seat_arg: Optional[str] = Field(None, description="Seat argument if provided")

client = OpenAI()

async def get_intent(user_input: str) -> IntentResult:
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": """
    Extract the command type and arguments. The command type must be exactly one of: RUN, ANALYZE, STATUS, or UPLOAD.
    Only extract base and seat if they exactly match these values:
    Valid bases: BUR, DAL, HPN, LAS, SCF, OPF, OAK, SNA
    Valid seats: CA, FO, FA
    Do not extract any other values as base or seat.
    Never extract partial matches or substrings.
    If a word is not an exact match (ignoring case) to these values, do not extract it.
    The word "all" should only be extracted as a base for RUN and STATUS commands.
    
    Example: "check status BUR FA" → STATUS, base=BUR, seat=FA
    Example: "check status xyz FA" → STATUS, base=None, seat=FA
    Example: "run optimization BUR xy" → RUN, base=BUR, seat=None
    Example: "upload all FA to noc" → UPLOAD, base=None, seat=FA
    Example: "upload noc FA" → UPLOAD, base=None, seat=FA
    Example: "Hey man. Upload BUR FA for me" → UPLOAD, base=BUR, seat=FA
    
    Return JSON with these fields:
    - intent: The command type (RUN/ANALYZE/STATUS/UPLOAD)
    - base_arg: The base argument if valid, or null
    - seat_arg: The seat argument if valid, or null
    """},
                {"role": "user", "content": f"Extract from: {user_input}"}
            ],
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return IntentResult(**result)
    except:
        return None

async def determine_intent(user_input: str) -> tuple[ProgramType, Optional[str], Optional[str]]:
    """
    Uses the intent agent to determine intent and extract arguments.
    Returns (intent, base_arg, seat_arg)
    """
    # Pre-process common command patterns
    input_lower = user_input.lower()  # For command detection
    if input_lower in ['command', 'commands']:
        return None, None, None
    
    # Define valid bases and seats
    VALID_BASES = ['bur', 'dal', 'las', 'scf', 'opf', 'oak', 'sna']
    VALID_SEATS = ['ca', 'fo', 'fa']
    
    # Handle special "all" commands first
    if input_lower.startswith('check all'):
        # Extract seat from "check all {seat}"
        parts = input_lower.split()
        if len(parts) >= 3:
            return ProgramType.STATUS, "all", parts[2].upper()
    elif input_lower.startswith('run all'):
        # Extract seat from "run all {seat}"
        parts = input_lower.split()
        if len(parts) >= 3:
            return ProgramType.RUN, "all", parts[2].upper()

    # Handle simple "run base seat" format
    words = input_lower.split()
    if len(words) == 3 and words[0] == 'run':
        base = words[1]
        seat = words[2]
        if base in VALID_BASES and seat in VALID_SEATS:
            return ProgramType.RUN, base.upper(), seat.upper()

    # Convert potential base/seat values to uppercase while preserving the rest
    words = user_input.split()
    processed_words = []
    for word in words:
        word_lower = word.lower()
        if word_lower in VALID_BASES:
            processed_words.append(word.upper())
        elif word_lower in VALID_SEATS:
            processed_words.append(word.upper())
        else:
            processed_words.append(word)
    processed_input = ' '.join(processed_words)

    result = await get_intent(processed_input)
    if result is None:
        return "UNRECOGNIZED", None, None
    
    print(f"Intent: {result.intent}")
    
    if result.base_arg or result.seat_arg:
        print(f"Found arguments - Base: {result.base_arg}, Seat: {result.seat_arg}")

    return result.intent, result.base_arg, result.seat_arg

async def run_optimization_program(program_type: ProgramType, base_arg: str, seat_arg: str, working_dir: str = ".", timeout: int = 30) -> None:
    """
    Runs either optrunner.py or optanalyzer.py with Base and Seat arguments.
    """
    if program_type == ProgramType.RUN:
        script = "optrunner.py"
        action = "Running optimization"
    else:
        script = "optanalyzer.py"
        action = "Analyzing optimization results"
    
    # Try to find Python in either virtual environment
    venv_names = ['new_env', 'myenv']
    venv_python = None
    tried_paths = []
    
    for venv in venv_names:
        possible_paths = [
            os.path.expanduser(f"{venv}/bin/python"),
            f"./{venv}/bin/python",
            f"../{venv}/bin/python",
            os.path.expanduser(f"~/{venv}/bin/python"),
            os.path.join(os.getcwd(), f"{venv}/bin/python")
        ]
        tried_paths.extend(possible_paths)
        
        for path in possible_paths:
            if os.path.exists(path):
                venv_python = path
                break
        if venv_python:
            break
    
    if not venv_python:
        raise FileNotFoundError(f"Could not find Python in virtual environments. Tried paths: {tried_paths}")
            
    command = f"{venv_python} {script} {base_arg} {seat_arg}"
    print(f"{action} with command: {command}")
    print(f"Using Python from: {venv_python}")
    
    try:
        # Get absolute path to the script
        script_path = os.path.abspath(script)
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Script not found: {script_path}")
            
        # Get the current working directory for debugging
        current_dir = os.getcwd()
        script_dir = os.path.dirname(script_path)
        print(f"Current directory: {current_dir}")
        print(f"Script directory: {script_dir}")
        print(f"Script path: {script_path}")
            
        # Create task for program execution
        process = await asyncio.create_subprocess_exec(
            venv_python,
            script_path,
            base_arg,
            seat_arg,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=current_dir  # Use current directory to maintain relative path relationships
        )
        
        print(f"Started process with PID: {process.pid}")
        
        # Capture any immediate errors
        stdout_data, stderr_data = await process.communicate()
        if stdout_data:
            print(f"Process stdout: {stdout_data.decode()}")
        if stderr_data:
            print(f"Process stderr: {stderr_data.decode()}")
            
        return process
        
    except Exception as e:
        print(f"Error running optimization: {str(e)}")
        raise

if __name__ == "__main__":
    async def main():
        print("\nWhat would you like to do? (e.g., 'run optimization with base 123 and seat abc' or 'analyze results')")
        user_input = input("> ")
        
        program_type, extracted_base, extracted_seat = await determine_intent(user_input)
        action = "run an optimization" if program_type == ProgramType.RUN else "analyze optimization results"
        print(f"\nI'll help you {action}.")
        
        base_arg = extracted_base if extracted_base else input("Enter Base argument: ")
        seat_arg = extracted_seat if extracted_seat else input("Enter Seat argument: ")
        working_dir = input("Enter working directory (or press Enter for current): ").strip() or "."
        timeout = int(input("Enter timeout in seconds (or press Enter for 30): ").strip() or "30")
        
        await run_optimization_program(program_type, base_arg, seat_arg, working_dir, timeout)
    
    asyncio.run(main()) 