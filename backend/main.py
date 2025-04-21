import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from models import (NoMatchesResponse, TrialMatch, TrialSearchRequest,
                    TrialSearchResponse)
from services import run_trial_matching_pipeline

# Load environment variables (optional for mocks)
load_dotenv()

app = FastAPI(
    title="AI Clinical Trial Matching Service (Mock)",
    description="Provides mock endpoints for finding clinical trials.",
    version="0.1.0",
)

# Ensure the EXACT origin of your React app is listed here
origins = [
    # --- KEEP THE ONE THAT MATCHES YOUR VITE SERVER ---
    "http://localhost:5173",  # Common Vite default port
    "http://127.0.0.1:5173", # Also include the IP version
    # --- REMOVE OR UPDATE OLD ONES ---
    # "http://localhost:3000", # Old CRA port, likely remove
    # "http://127.0.0.1:3000", # Old CRA port, likely remove
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # <<< Does this list contain your frontend URL?
    allow_credentials=True,
    allow_methods=["*"],        # <<< Should include "OPTIONS", "POST", "GET" (*)
    allow_headers=["*"],        # <<< Should include "Content-Type", "Authorization" etc. (*)
)

# --- API Endpoints ---

@app.post(
    "/api/v1/trials/find",
    response_model=TrialSearchResponse, # Primarily describes success case
    summary="Find potential clinical trials for a patient",
    description="Initiates a (mock) AI workflow to match a patient against clinical trials.",
    responses={
        200: {"description": "Successful match or no matches found", "model": TrialSearchResponse | NoMatchesResponse},
        404: {"description": "Patient ID not found"},
        500: {"description": "Internal server error during matching pipeline"},
    }
)
async def find_trials(request: TrialSearchRequest):
    """
    Receives a patient ID and orchestrates the mock backend services
    to find matching clinical trials.
    """
    print(f"Received request for patientId: {request.patientId}")
    start_time = datetime.now(timezone.utc)

    # Run the mocked pipeline
    pipeline_result = await run_trial_matching_pipeline(request.patientId)

    end_time = datetime.now(timezone.utc)
    timestamp_str = end_time.isoformat()

    # Handle results from the pipeline
    if isinstance(pipeline_result, str):
        if pipeline_result == "PATIENT_NOT_FOUND":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Patient with ID '{request.patientId}' not found."
            )
        else: # Generic pipeline error
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An internal error occurred during the trial matching process."
            )
    elif isinstance(pipeline_result, list):
        if not pipeline_result:
            # No matches found scenario
            print(f"No matches found for {request.patientId}")
            # Return a 200 OK but with the NoMatchesResponse structure
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=NoMatchesResponse(searchTimestamp=timestamp_str).dict()
            )
        else:
            # Success scenario with matches
            print(f"Successfully found {len(pipeline_result)} matches for {request.patientId}")
            # Return a 200 OK with the TrialSearchResponse structure
            # We need to convert TrialMatch objects back to dicts for JSONResponse
            matches_dict = [match.dict(exclude={'rank_score'}) for match in pipeline_result] # Exclude internal score
            return JSONResponse(
                 status_code=status.HTTP_200_OK,
                 content=TrialSearchResponse(matches=matches_dict, searchTimestamp=timestamp_str).dict()
            )
    else:
        # Should not happen, but good practice
        print("ERROR: Unexpected result type from pipeline")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected internal error occurred."
        )


@app.get("/health", summary="Health Check", status_code=status.HTTP_200_OK)
async def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}

# --- Main execution (for running with uvicorn) ---
if __name__ == "__main__":
    # This block is mainly for info; run using: uvicorn main:app --reload
    print("To run the application:")
    print("uvicorn main:app --reload --port 8000")