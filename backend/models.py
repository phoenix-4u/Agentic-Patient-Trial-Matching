from pydantic import BaseModel, Field
from typing import List, Optional

# --- Request Models ---

class TrialSearchRequestContext(BaseModel):
    requestingClinicianId: Optional[str] = None
    searchRadiusKm: Optional[int] = None

class TrialSearchRequest(BaseModel):
    patientId: str = Field(..., description="Unique identifier for the patient")
    context: Optional[TrialSearchRequestContext] = None

# --- Data Models (used internally and in responses) ---

class PatientProfile(BaseModel):
    patientId: str
    condition: str
    stage: Optional[str] = None
    age: int
    priorTherapies: List[str] = []
    biomarkers: List[str] = []

class TrialMatch(BaseModel):
    trialId: str = Field(..., example="NCT12345678")
    title: str = Field(..., example="Trial for Advanced Widgetitis")
    status: str = Field(..., example="Recruiting")
    phase: str = Field(..., example="Phase 3")
    condition: str = Field(..., example="Widgetitis")
    locations: List[str] = Field(default_factory=list, example=["City Hospital", "Regional Clinic"])
    matchRationale: List[str] = Field(default_factory=list, example=["Matches diagnosis: Widgetitis Stage IV", "Meets age criteria (55)"])
    flags: List[str] = Field(default_factory=list, example=["Requires confirmation of eGFR > 60"])
    detailsUrl: Optional[str] = Field(None, example="https://clinicaltrials.gov/ct2/show/NCT12345678")
    contactInfo: Optional[str] = Field(None, example="Dr. Smith, 555-1234")
    rank_score: Optional[float] = Field(None, description="Internal score for ranking") # Usually not sent to frontend

# --- Response Models ---

class TrialSearchResponse(BaseModel):
    status: str = "success"
    matches: List[TrialMatch]
    searchTimestamp: str # ISO format string

class NoMatchesResponse(BaseModel):
    status: str = "no_matches_found"
    matches: List = []
    message: str = "No suitable recruiting trials found based on current criteria."
    searchTimestamp: str # ISO format string

# You might add a specific ErrorResponse model too