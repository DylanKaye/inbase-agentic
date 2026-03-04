"""
Pairings AI Query Engine
========================

Core logic for answering natural-language crew planning questions
using Claude + pandas over the pairings/duties/legs CSVs.

Architecture:
  1. Load CSVs into memory once
  2. On each question: build a prompt with the data dictionary + data summary,
     ask Claude to write pandas code
  3. Execute the code in a restricted namespace
  4. Send the raw output back to Claude for a natural-language answer

Usage:
    from pairings_query_engine import PairingsQueryEngine

    engine = PairingsQueryEngine(
        pairings_csv="pairings.csv",
        duties_csv="duties.csv",
        legs_csv="legs.csv",
        api_key="sk-ant-..."
    )
    answer = engine.ask("How many duties are in each base?")
    print(answer)

Or as a standalone API endpoint — see the FastAPI wrapper at the bottom.
"""

import pandas as pd
import numpy as np
import json
import traceback
import re
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from anthropic import Anthropic


# ---------------------------------------------------------------------------
# Data dictionary (same as in the extractor, kept here so the engine is
# self-contained and doesn't need the extractor module)
# ---------------------------------------------------------------------------
DATA_DICTIONARY = """
OVERVIEW
--------
You have three pandas DataFrames loaded in memory:

  pairings_df  →  one row per trip/pairing
  duties_df    →  one row per duty (work day within a pairing)
  legs_df      →  one row per flight leg or activity within a duty

They join on (pairing_uid), or (pairing_uid + duty_num) for legs<->duties.

A "pairing" is a multi-day (or single-day) trip starting/ending at a base.
A "duty" is one work day within that pairing (check-in to check-out).
A "leg" is a single flight or ground activity (DH, meal break, etc.) within a duty.

TERMINOLOGY
-----------
  DH (Deadhead)      A positioning flight where the crew rides as passengers.
                     ActivityCode == "DH" exactly.
  Live leg           A revenue/operated flight (not DH)
  HTL                Hotel / overnight layover between duties
  TAFB               Time Away From Base (first check-in to last check-out)
  Block hours        Flight time from departure to arrival
  MB                 Meal break (a REFERENCEACTIVITY within a duty)
  Charter            A charter pairing — identified by pairing name starting with "C"
  ER3                Embraer ERJ-135/140/145 equipment type
  XE + number        JSX flight number (e.g. XE173 = JSX flight 173)
  Base               Home airport for crew (e.g. DAL, BUR, OAK, SCF, OPF, LAS)


TABLE: pairings_df
-------------------
pairing_name         str   Pairing designator (e.g. "C5", "DE3655")
pairing_uid          str   Unique numeric ID
base                 str   Home base airport code
is_charter           bool  True if pairing name starts with "C"
qualification        str   Required qualification / equipment type
equipment_type       str   Aircraft type required
complement           str   Crew complement code
required_complement  str   Required positions pipe-separated (e.g. "CA|FO|FA")
credit               str   Credit value
is_historical        str   Whether record is historical
pairing_class        str   Classification if any
num_duties           int   Number of duty days
start_date           str   First duty date (YYYY-MM-DD)
end_date             str   Last duty date (YYYY-MM-DD)
total_block_hrs      float Sum of block hours (non-DH legs)
total_duty_hrs       float Sum of duty lengths
tafb_hrs             float Time Away From Base in hours
total_flight_legs    int   Total flight legs (live + DH)
total_dh_legs        int   Total deadhead legs
total_live_legs      int   Total live legs
stations_visited     str   Pipe-separated unique airports
num_layovers         int   Overnight layovers (= num_duties - 1)
crew_names           str   Pipe-separated assigned crew names
crew_numbers         str   Pipe-separated crew employee numbers
crew_assigned_ranks  str   Pipe-separated assigned ranks
crew_seniorities     str   Pipe-separated seniority numbers


TABLE: duties_df
-----------------
pairing_name         str   Pairing designator
pairing_uid          str   Unique pairing ID
base                 str   Home base airport code
is_charter           bool  True if charter
pairing_days         int   Total duties in parent pairing
duty_num             int   Duty day number (1, 2, 3...)
duty_date            str   Local date (YYYY-MM-DD)
day_of_week          str   Day name (Monday, Tuesday, etc.)
checkin_time         str   Local check-in (HH:MM)
checkout_time        str   Local check-out (HH:MM)
duty_start_utc       str   UTC duty start (ISO)
duty_end_utc         str   UTC duty end (ISO)
duty_length_hrs      float Duty period in hours
block_hours          float Block time for live legs only
num_legs             int   FLIGHT legs only (excludes MB etc.)
num_dh_legs          int   Deadhead legs (ActivityCode == "DH")
num_live_legs        int   Live flight legs
is_all_dh            bool  True if entire duty is deadhead
dep_station          str   First departure airport
arr_station          str   Last arrival airport
route                str   Full route (e.g. OAK-BUR-OAK-BUR-OAK)
overnight_station    str   Where crew overnights after duty (empty if last day)
is_overnight         bool  True if followed by overnight
rest_hours_after     float Rest hours after this duty (nullable)
equipment_type       str   Aircraft type
activity_codes       str   ALL codes pipe-separated (e.g. XE173|XE170|MB|XE175|XE174)
flight_codes         str   Flight-only codes pipe-separated
non_flight_codes     str   Non-flight codes pipe-separated (e.g. MB)
crew_names           str   Pipe-separated crew names
crew_numbers         str   Pipe-separated crew employee numbers
crew_assigned_ranks  str   Pipe-separated assigned ranks


TABLE: legs_df
---------------
pairing_name         str   Pairing designator
pairing_uid          str   Unique pairing ID
base                 str   Home base airport code
is_charter           bool  True if charter
duty_num             int   Duty number within pairing
leg_num              int   Leg number within duty (1, 2, 3...)
duty_date            str   Local date of parent duty
day_of_week          str   Day name
activity_type        str   "FLIGHT" or "REFERENCEACTIVITY"
activity_subtype     str   Subtype (e.g. "Shift" for meal breaks)
activity_code        str   Code (e.g. "XE173", "MB", "DH")
dep_station          str   Departure airport
arr_station          str   Arrival airport
dep_time_utc         str   Departure UTC (ISO)
arr_time_utc         str   Arrival UTC (ISO)
dep_time_local       str   Departure local (HH:MM)
arr_time_local       str   Arrival local (HH:MM)
block_hours          float Block time in hours
is_deadhead          bool  True if ActivityCode == "DH"
is_flight            bool  True if ActivityType == "FLIGHT"
equipment_type       str   Aircraft type (empty for ground activities)
"""


# ---------------------------------------------------------------------------
# System prompt for the code-generation step
# ---------------------------------------------------------------------------
CODE_SYSTEM_PROMPT = """You are a data analyst for a regional airline (JSX). You answer crew planning questions by writing pandas code.

You have three DataFrames already loaded:
  - pairings_df  (one row per pairing/trip)
  - duties_df    (one row per duty/work-day)
  - legs_df      (one row per flight leg or activity)

{data_dictionary}

RULES:
1. Write ONLY Python/pandas code. No explanation, no markdown, no backticks.
2. Your code must produce output via print() statements.
3. Use the DataFrames directly — they are already loaded. Do NOT read CSVs.
4. Keep output concise and tabular when appropriate. Use .to_string() for DataFrames.
5. For counts, averages, and aggregations: round floats to 2 decimal places.
6. If the question is ambiguous, make reasonable assumptions and note them in a print() comment.
7. Always print clear labels so the output is self-explanatory.
8. When filtering by station/base, use case-insensitive matching (e.g. .str.upper()).
9. If a question mentions a station but doesn't specify whether it's a base or a duty station,
   check BOTH the 'base' column AND station columns (dep_station, arr_station) as appropriate.
10. For "check-in times" questions, the relevant column is checkin_time in duties_df.
11. For "how many duties" questions, count rows in duties_df (each row = one duty).
12. For "how many overnights" questions, filter duties_df where is_overnight == True.

IMPORTANT: Produce ONLY executable Python code. No prose, no markdown fences, no comments
outside of print statements."""


# ---------------------------------------------------------------------------
# System prompt for the answer-formatting step
# ---------------------------------------------------------------------------
ANSWER_SYSTEM_PROMPT = """You are a helpful crew planning assistant for JSX airline. 
A crew planner asked a question and you ran some analysis on the pairings data.

Format the raw output into a clear, conversational answer. Be concise and direct.
If the data shows something noteworthy or unusual, mention it briefly.
Use simple tables or bullet points only if they genuinely help readability.
Don't repeat the question back. Don't explain what pandas is or how you got the answer.
Just give the answer as if you're a coworker responding in Slack."""


# ---------------------------------------------------------------------------
# Engine class
# ---------------------------------------------------------------------------
class PairingsQueryEngine:
    """
    Answers natural-language questions about airline pairings data
    using Claude to generate pandas code, executing it, and formatting results.
    """

    def __init__(self, pairings_csv: str, duties_csv: str, legs_csv: str,
                 api_key: str, model: str = "claude-sonnet-4-5-20250929"):
        """
        Args:
            pairings_csv: Path to pairings.csv
            duties_csv:   Path to duties.csv
            legs_csv:     Path to legs.csv
            api_key:      Anthropic API key
            model:        Claude model to use
        """
        self.client = Anthropic(api_key=api_key)
        self.model = model

        # Load data
        self.pairings_df = pd.read_csv(pairings_csv)
        self.duties_df = pd.read_csv(duties_csv)
        self.legs_df = pd.read_csv(legs_csv)

        # Build a compact data summary for context
        self._data_summary = self._build_data_summary()

    @classmethod
    def from_dataframes(cls, pairings_df: pd.DataFrame, duties_df: pd.DataFrame,
                        legs_df: pd.DataFrame, api_key: str,
                        model: str = "claude-sonnet-4-5-20250929"):
        """Create an engine directly from DataFrames (no CSV files needed)."""
        instance = cls.__new__(cls)
        instance.client = Anthropic(api_key=api_key)
        instance.model = model
        instance.pairings_df = pairings_df
        instance.duties_df = duties_df
        instance.legs_df = legs_df
        instance._data_summary = instance._build_data_summary()
        return instance

    def _build_data_summary(self) -> str:
        """Create a concise summary of the loaded data for the prompt."""
        p = self.pairings_df
        d = self.duties_df
        l = self.legs_df

        lines = [
            "DATA SUMMARY (current loaded data):",
            f"  Pairings: {len(p)} rows",
            f"  Duties:   {len(d)} rows",
            f"  Legs:     {len(l)} rows",
        ]

        if not d.empty:
            lines.append(f"  Date range: {d['duty_date'].min()} to {d['duty_date'].max()}")
            lines.append(f"  Bases: {sorted(d['base'].unique().tolist())}")
            lines.append(f"  Stations seen: {sorted(set(d['dep_station'].unique().tolist() + d['arr_station'].unique().tolist()))}")

        # Show first few rows of each df so Claude understands the shape
        lines.append("\nSAMPLE DATA (first 3 rows of each):")
        lines.append("\npairings_df.head(3):")
        lines.append(p.head(3).to_string())
        lines.append("\nduties_df.head(3):")
        lines.append(d.head(3).to_string())
        lines.append("\nlegs_df.head(3):")
        lines.append(l.head(3).to_string())

        # Column dtypes for reference
        lines.append("\nduties_df.dtypes:")
        lines.append(d.dtypes.to_string())

        return "\n".join(lines)

    def _generate_code(self, question: str) -> str:
        """Ask Claude to write pandas code to answer the question."""
        system = CODE_SYSTEM_PROMPT.format(data_dictionary=DATA_DICTIONARY)

        user_msg = f"""{self._data_summary}

QUESTION: {question}

Write pandas code to answer this. Use pairings_df, duties_df, legs_df directly.
Output via print() only. No markdown, no backticks, no explanation."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": user_msg}]
        )

        code = response.content[0].text.strip()

        # Strip markdown fences if Claude included them anyway
        code = re.sub(r'^```(?:python)?\s*\n?', '', code)
        code = re.sub(r'\n?```\s*$', '', code)

        return code

    def _execute_code(self, code: str) -> tuple[str, str, bool]:
        """
        Execute the pandas code in a sandboxed namespace.
        Returns (stdout, stderr, success).
        """
        # Create a restricted namespace with only the essentials
        namespace = {
            'pd': pd,
            'np': np,
            'pairings_df': self.pairings_df.copy(),
            'duties_df': self.duties_df.copy(),
            'legs_df': self.legs_df.copy(),
        }

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exec(code, namespace)
            return stdout_capture.getvalue(), stderr_capture.getvalue(), True
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            return stdout_capture.getvalue(), error_msg, False

    def _format_answer(self, question: str, code_output: str, code: str) -> str:
        """Ask Claude to format the raw code output into a nice answer."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=ANSWER_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": (
                f"Question: {question}\n\n"
                f"Raw analysis output:\n{code_output}\n\n"
                f"Format this into a clear, concise answer for a crew planner."
            )}]
        )
        return response.content[0].text.strip()

    def ask(self, question: str, max_retries: int = 2,
            return_debug: bool = False) -> dict:
        """
        Answer a natural-language question about pairings data.

        Args:
            question:     The crew planner's question
            max_retries:  How many times to retry if code execution fails
            return_debug: If True, include generated code and raw output in response

        Returns:
            dict with keys:
                answer:     str - the formatted natural language answer
                success:    bool - whether it worked
                code:       str - (if return_debug) the generated pandas code
                raw_output: str - (if return_debug) raw stdout from execution
                error:      str - (if failed) error message
        """
        last_error = ""

        for attempt in range(max_retries + 1):
            # Generate code (on retry, include the error so Claude can fix it)
            if attempt == 0:
                code = self._generate_code(question)
            else:
                code = self._generate_code(
                    f"{question}\n\n"
                    f"PREVIOUS ATTEMPT FAILED with this error:\n{last_error}\n\n"
                    f"Previous code was:\n{last_code}\n\n"
                    f"Fix the error and try again."
                )

            last_code = code

            # Execute
            stdout, stderr, success = self._execute_code(code)

            if success and stdout.strip():
                # Format the answer
                answer = self._format_answer(question, stdout, code)

                result = {"answer": answer, "success": True}
                if return_debug:
                    result["code"] = code
                    result["raw_output"] = stdout
                return result

            elif success and not stdout.strip():
                last_error = "Code executed but produced no output. Make sure to use print()."
            else:
                last_error = stderr

        # All retries failed
        result = {
            "answer": (
                "I wasn't able to generate a working analysis for that question. "
                "Could you try rephrasing it? Here's what went wrong: "
                f"{last_error[:500]}"
            ),
            "success": False,
            "error": last_error,
        }
        if return_debug:
            result["code"] = last_code
            result["raw_output"] = stdout
        return result

    def reload_data(self, pairings_csv: str = None, duties_csv: str = None,
                    legs_csv: str = None, pairings_df: pd.DataFrame = None,
                    duties_df: pd.DataFrame = None, legs_df: pd.DataFrame = None):
        """Reload from CSVs or DataFrames."""
        if pairings_df is not None:
            self.pairings_df = pairings_df
            self.duties_df = duties_df
            self.legs_df = legs_df
        else:
            self.pairings_df = pd.read_csv(pairings_csv)
            self.duties_df = pd.read_csv(duties_csv)
            self.legs_df = pd.read_csv(legs_csv)
        self._data_summary = self._build_data_summary()


# ---------------------------------------------------------------------------
# FastAPI wrapper (optional — if you want a REST endpoint)
# ---------------------------------------------------------------------------
def create_api(pairings_csv: str, duties_csv: str, legs_csv: str,
               api_key: str):
    """
    Create a FastAPI app that exposes the query engine as a REST endpoint.

    POST /ask
    Body: {"question": "How many duties in each base?"}
    Response: {"answer": "...", "success": true}
    """
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    app = FastAPI(title="Pairings AI Query Engine")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = PairingsQueryEngine(
        pairings_csv=pairings_csv,
        duties_csv=duties_csv,
        legs_csv=legs_csv,
        api_key=api_key,
    )

    class QuestionRequest(BaseModel):
        question: str
        debug: bool = False

    class AnswerResponse(BaseModel):
        answer: str
        success: bool
        code: str = ""
        raw_output: str = ""
        error: str = ""

    @app.post("/ask", response_model=AnswerResponse)
    async def ask_question(req: QuestionRequest):
        result = engine.ask(req.question, return_debug=req.debug)
        return AnswerResponse(**result)

    @app.post("/refresh")
    async def refresh_data():
        """Reload CSVs from disk (call after re-running the extractor)."""
        engine.reload_data(pairings_csv, duties_csv, legs_csv)
        return {"status": "reloaded", "duties": len(engine.duties_df)}

    return app


# ---------------------------------------------------------------------------
# CLI for quick testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Pairings AI Query Engine")
    parser.add_argument("--pairings", default="pairings.csv")
    parser.add_argument("--duties", default="duties.csv")
    parser.add_argument("--legs", default="legs.csv")
    parser.add_argument("--api-key", required=True, help="Anthropic API key")
    parser.add_argument("--model", default="claude-sonnet-4-5-20250929")
    parser.add_argument("--serve", action="store_true",
                        help="Run as FastAPI server on port 8000")
    parser.add_argument("--question", "-q", type=str,
                        help="Ask a single question and exit")

    args = parser.parse_args()

    if args.serve:
        import uvicorn
        app = create_api(args.pairings, args.duties, args.legs, args.api_key)
        uvicorn.run(app, host="0.0.0.0", port=8000)

    elif args.question:
        engine = PairingsQueryEngine(
            args.pairings, args.duties, args.legs,
            args.api_key, args.model
        )
        result = engine.ask(args.question, return_debug=True)
        print(f"\n{'='*60}")
        print(f"QUESTION: {args.question}")
        print(f"{'='*60}")
        print(f"\nGENERATED CODE:\n{result.get('code', 'N/A')}")
        print(f"\nRAW OUTPUT:\n{result.get('raw_output', 'N/A')}")
        print(f"\nANSWER:\n{result['answer']}")
        print(f"\nSUCCESS: {result['success']}")

    else:
        # Interactive mode
        engine = PairingsQueryEngine(
            args.pairings, args.duties, args.legs,
            args.api_key, args.model
        )
        print("Pairings AI Query Engine — type 'quit' to exit")
        print(f"Loaded: {len(engine.pairings_df)} pairings, "
              f"{len(engine.duties_df)} duties, {len(engine.legs_df)} legs\n")

        while True:
            question = input("Question: ").strip()
            if question.lower() in ('quit', 'exit', 'q'):
                break
            if not question:
                continue

            result = engine.ask(question, return_debug=True)
            print(f"\n{result['answer']}\n")
            if not result['success']:
                print(f"[Debug] Code:\n{result.get('code', '')}\n")