import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from models import (NoMatchesResponse, TrialMatch, TrialSearchRequest,
                    TrialSearchResponse)
from services import run_trial_matching_pipeline
from logger import setup_logger

# Load environment variables
load_dotenv()

# Setup logger
logger = setup_logger(
    "trial_matcher.api",
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_file="logs/api.log"
)

app = FastAPI(
    title="AI Clinical Trial Matching Service (Mock)",
    description="Provides mock endpoints for finding clinical trials.",
    version="0.1.0",
)

# CORS configuration
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post(
    "/api/v1/trials/find",
    response_model=TrialSearchResponse,
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
    logger.info(f"Received trial matching request for patientId: {request.patientId}")
    start_time = datetime.now(timezone.utc)

    try:
        # Run the mocked pipeline
        logger.debug(f"Starting trial matching pipeline for patientId: {request.patientId}")
        pipeline_result = await run_trial_matching_pipeline(request.patientId)
        logger.debug(f"Pipeline completed for patientId: {request.patientId}")

        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat()
        duration = (end_time - start_time).total_seconds()

        # Handle results from the pipeline
        if isinstance(pipeline_result, str):
            if pipeline_result == "PATIENT_NOT_FOUND":
                logger.warning(f"Patient not found: {request.patientId}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Patient with ID '{request.patientId}' not found."
                )
            else:
                logger.error(f"Pipeline error for patientId {request.patientId}: {pipeline_result}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="An internal error occurred during the trial matching process."
                )
        elif isinstance(pipeline_result, list):
            if not pipeline_result:
                logger.info(f"No matches found for patientId: {request.patientId}")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content=NoMatchesResponse(searchTimestamp=timestamp_str).dict()
                )
            else:
                logger.info(f"Found {len(pipeline_result)} matches for patientId: {request.patientId}")
                logger.debug(f"Processing time: {duration:.2f} seconds")
                matches_dict = [match.dict(exclude={'rank_score'}) for match in pipeline_result]
                return JSONResponse(
                     status_code=status.HTTP_200_OK,
                     content=TrialSearchResponse(matches=matches_dict, searchTimestamp=timestamp_str).dict()
                )
        else:
            logger.error(f"Unexpected result type from pipeline for patientId {request.patientId}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred."
            )
    except Exception as e:
        logger.error(f"Unhandled error processing request for patientId {request.patientId}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request."
        )

@app.get("/health", summary="Health Check", status_code=status.HTTP_200_OK)
async def health_check():
    """Basic health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "ok"}

# --- Main execution (for running with uvicorn) ---
if __name__ == "__main__":
    # This block is mainly for info; run using: uvicorn main:app --reload
    print("To run the application:")
    print("uvicorn main:app --reload --port 8000")