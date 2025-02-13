from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Literal
from pydantic import BaseModel, Field
from pydantic_ai.agent import Agent, RunContext
import subprocess
import os
from datetime import datetime
import asyncio

class ProgramStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"

class ProgramType(str, Enum):
    RUN = "run"
    ANALYZE = "analyze"
    STATUS = "status"
    UPLOAD = "upload"

class IntentResult(BaseModel):
    intent: ProgramType = Field(..., description="The user's intended action")
    base_arg: Optional[str] = Field(None, description="Base argument if provided")
    seat_arg: Optional[str] = Field(None, description="Seat argument if provided")
    confidence: float = Field(..., description="Confidence in the intent classification", ge=0, le=1)
    explanation: str = Field(..., description="Brief explanation of why this intent was chosen")

intent_agent = Agent(
    'gpt-3.5-turbo',
    result_type=IntentResult,
    system_prompt="""
    Classify as RUN/ANALYZE/STATUS/UPLOAD. 
    Only extract base and seat if they exactly match these values:
    Valid bases: bur, dal, las, scf, opf, oak, sna
    Valid seats: ca, fo, fa
    Do not extract any other values as base or seat.

    Format: intent, base=X, seat=Y
    Example: "check status bur fa" → STATUS, base=bur, seat=fa
    Example: "check status xyz fa" → STATUS, base=None, seat=fa
    Example: "run optimization bur xy" → RUN, base=bur, seat=None
    Note: The command "commands" should be handled separately before intent detection.
    """
)

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

async def determine_intent(user_input: str) -> tuple[ProgramType, Optional[str], Optional[str]]:
    """
    Uses the intent agent to determine intent and extract arguments.
    Returns (intent, base_arg, seat_arg)
    """
    # Pre-process common command patterns
    input_lower = user_input.lower()
    if input_lower in ['command', 'commands']:
        return None, None, None
    if input_lower.startswith('check all'):
        # Extract seat from "check all {seat}"
        parts = input_lower.split()
        if len(parts) >= 3:
            return ProgramType.STATUS, "all", parts[2]

    result = await intent_agent.run(f"Extract from: {user_input}")
    print(f"Intent: {result.data.intent} ({result.data.confidence:.2f})")
    if result.data.base_arg or result.data.seat_arg:
        print(f"Found arguments - Base: {result.data.base_arg}, Seat: {result.data.seat_arg}")
   
    # If confidence is not 100%, return special values to indicate clarification needed
    if result.data.confidence < 1.0:
        explanation = (
            f"I'm not completely sure what you want to do (confidence: {result.data.confidence:.2f}). "
            f"I think you want to {result.data.intent.lower()}"
        )
        if result.data.base_arg:
            explanation += f" for base {result.data.base_arg}"
        if result.data.seat_arg:
            explanation += f" with seat {result.data.seat_arg}"
        explanation += ". Please confirm or rephrase your command."
        
        # Return special values that api_server will recognize
        return "CLARIFY", explanation, None

    return result.data.intent, result.data.base_arg, result.data.seat_arg

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
    
    command = f"python {script} {base_arg} {seat_arg}"
    print(f"{action} with command: {command}")
    
    # Create task for program execution
    process = await asyncio.create_subprocess_exec(
        "python",
        script,
        base_arg,
        seat_arg,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Don't wait for completion
    return process

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