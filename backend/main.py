import os
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv() # Load environment variables early

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Assuming models are compatible
from models import (NoMatchesResponse, TrialMatch, TrialSearchRequest,
                    TrialSearchResponse)
# Import the new Agno workflow function
from services import run_agno_matching_workflow 
from logger import setup_logger

# Setup logger
logger = setup_logger(
    "trial_matcher.api",
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_file="logs/api.log"
)

app = FastAPI(
    title="AI Clinical Trial Matching Service (Agno-Powered)", # Updated title
    description="Uses Agno agents to find clinical trials.",
    version="0.2.0", # Updated version
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
    # Response model might need adjustment if Agno returns slightly different structure
    # For now, assume it returns data compatible with TrialSearchResponse
    response_model=TrialSearchResponse,
    summary="Find potential clinical trials for a patient using Agno",
    description="Initiates an Agno agent workflow to match a patient against clinical trials using dynamic planning.",
    responses={
        200: {"description": "Successful match or no matches found", "model": TrialSearchResponse | NoMatchesResponse},
        404: {"description": "Patient ID not found (as determined by Agno workflow)"},
        500: {"description": "Internal server error during Agno workflow"},
    }
)
async def find_trials(request: TrialSearchRequest):
    logger.info(f"Received Agno trial matching request for patientId: {request.patientId}")
    start_time = datetime.now(timezone.utc)

    try:
        # ---> Call the new Agno workflow function <---
        logger.debug(f"Starting Agno workflow for patientId: {request.patientId}")
        workflow_result = await run_agno_matching_workflow(request.patientId)
        logger.debug(f"Agno workflow completed for patientId: {request.patientId}")

        end_time = datetime.now(timezone.utc)
        timestamp_str = end_time.isoformat()
        duration = (end_time - start_time).total_seconds()

        # Handle results from the Agno workflow
        if isinstance(workflow_result, str):
            # Map error strings from Agno workflow to HTTP errors
            if workflow_result == "PATIENT_NOT_FOUND":
                logger.warning(f"Patient not found via Agno: {request.patientId}")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Patient with ID '{request.patientId}' not found."
                )
            elif workflow_result.startswith("PIPELINE_ERROR"):
                 logger.error(f"Agno Pipeline error for patientId {request.patientId}: {workflow_result}")
                 raise HTTPException(
                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                     detail="An internal error occurred during the trial matching process."
                 )
            else: # Handle any other unexpected string results
                 logger.error(f"Unknown error string from Agno workflow for {request.patientId}: {workflow_result}")
                 raise HTTPException(
                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                     detail="An unexpected internal error occurred."
                 )

        elif isinstance(workflow_result, list):
            # Success case: we have a list of match dictionaries
            if not workflow_result:
                logger.info(f"No matches found via Agno for patientId: {request.patientId}")
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    # Use NoMatchesResponse structure
                    content=NoMatchesResponse(searchTimestamp=timestamp_str).dict()
                )
            else:
                logger.info(f"Found {len(workflow_result)} matches via Agno for patientId: {request.patientId}")
                logger.debug(f"Agno Processing time: {duration:.2f} seconds")
                # The list should contain dicts ready for TrialSearchResponse
                # We assume the Analyze skill returned dicts compatible with TrialMatch
                return JSONResponse(
                     status_code=status.HTTP_200_OK,
                     content=TrialSearchResponse(matches=workflow_result, searchTimestamp=timestamp_str).dict()
                )
        else:
            # Handle unexpected result types from Agno workflow
            logger.error(f"Unexpected result type from Agno workflow for patientId {request.patientId}: {type(workflow_result)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected internal error occurred (Agno result format)."
            )
    except Exception as e:
        logger.error(f"Unhandled error in API endpoint for Agno request {request.patientId}: {str(e)}", exc_info=True)
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