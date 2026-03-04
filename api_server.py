from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional
import asyncio
import os
import uvicorn

from pair_analyzer import read_pairings
from pairing_query_engine import PairingsQueryEngine

def _load_api_key():
    key_file = os.path.join(os.path.dirname(__file__), "anthropic_key.txt")
    if os.path.exists(key_file):
        with open(key_file) as f:
            return f.read().strip()
    return os.environ.get("ANTHROPIC_API_KEY", "")

ANTHROPIC_API_KEY = _load_api_key()

app = FastAPI(title="Pairing Analyzer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
engine: Optional[PairingsQueryEngine] = None
data_status = {
    "loaded": False,
    "loading": False,
    "start_date": None,
    "end_date": None,
    "num_pairings": 0,
    "num_duties": 0,
    "num_legs": 0,
    "bases": [],
    "date_range": "",
    "error": None,
}


class FetchRequest(BaseModel):
    start_date: str
    end_date: Optional[str] = None
    days: int = 30


class AskRequest(BaseModel):
    question: str
    debug: bool = False


@app.get("/status")
async def get_status():
    return data_status


@app.post("/fetch-data")
async def fetch_data(req: FetchRequest):
    global engine, data_status

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500,
                            detail="ANTHROPIC_API_KEY environment variable not set")

    if data_status["loading"]:
        return {"message": "Data fetch already in progress, please wait..."}

    data_status["loading"] = True
    data_status["error"] = None

    start_date = req.start_date
    if req.end_date:
        end_date = req.end_date
    else:
        end_date = (datetime.strptime(start_date, "%Y-%m-%d")
                    + timedelta(days=req.days)).strftime("%Y-%m-%d")

    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        data_status["loading"] = False
        raise HTTPException(status_code=400, detail="Dates must be YYYY-MM-DD format")

    loop = asyncio.get_event_loop()
    try:
        pairings_df, duties_df, legs_df = await loop.run_in_executor(
            None, read_pairings, start_date, end_date
        )
    except Exception as e:
        data_status["loading"] = False
        data_status["error"] = str(e)
        raise HTTPException(status_code=500, detail=f"Failed to fetch pairings: {e}")

    if pairings_df is None:
        data_status["loading"] = False
        data_status["error"] = "API returned no data"
        raise HTTPException(status_code=500, detail="Failed to retrieve data from API")

    if pairings_df.empty:
        data_status.update({
            "loaded": True, "loading": False,
            "start_date": start_date, "end_date": end_date,
            "num_pairings": 0, "num_duties": 0, "num_legs": 0,
            "bases": [], "date_range": f"{start_date} to {end_date}",
            "error": None,
        })
        engine = None
        return {"message": "No pairings found for this date range.", "status": data_status}

    try:
        engine = PairingsQueryEngine.from_dataframes(
            pairings_df, duties_df, legs_df,
            api_key=ANTHROPIC_API_KEY,
        )
    except Exception as e:
        data_status["loading"] = False
        data_status["error"] = str(e)
        raise HTTPException(status_code=500, detail=f"Failed to initialize query engine: {e}")

    bases = sorted(duties_df["base"].unique().tolist()) if not duties_df.empty else []
    duty_date_range = ""
    if not duties_df.empty:
        duty_date_range = f"{duties_df['duty_date'].min()} to {duties_df['duty_date'].max()}"

    data_status.update({
        "loaded": True,
        "loading": False,
        "start_date": start_date,
        "end_date": end_date,
        "num_pairings": len(pairings_df),
        "num_duties": len(duties_df),
        "num_legs": len(legs_df),
        "bases": bases,
        "date_range": duty_date_range,
        "error": None,
    })

    return {
        "message": (
            f"Loaded {len(pairings_df)} pairings, {len(duties_df)} duties, "
            f"{len(legs_df)} legs. Bases: {', '.join(bases)}. "
            f"Date range: {duty_date_range}."
        ),
        "status": data_status,
    }


@app.post("/ask")
async def ask_question(req: AskRequest):
    if not data_status["loaded"] or engine is None:
        raise HTTPException(
            status_code=400,
            detail="No data loaded. Please fetch pairing data first."
        )

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, lambda: engine.ask(req.question, return_debug=req.debug)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

    return result


app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
