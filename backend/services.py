import asyncio
import random
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Union

from models import PatientProfile, TrialMatch

# --- Mock Data ---

MOCK_PATIENT_DB = {
    "PATIENT_001": PatientProfile(patientId="PATIENT_001", condition="Lung Cancer", stage="III", age=65, priorTherapies=["Chemo X"], biomarkers=["EGFR+"]),
    "PATIENT_002": PatientProfile(patientId="PATIENT_002", condition="Breast Cancer", stage="II", age=52, priorTherapies=[], biomarkers=["HER2+"]),
    "PATIENT_003": PatientProfile(patientId="PATIENT_003", condition="Diabetes Type 2", age=70, priorTherapies=["Metformin"], biomarkers=[]),
    "PATIENT_NO_MATCH": PatientProfile(patientId="PATIENT_NO_MATCH", condition="Rare Condition Y", age=40, priorTherapies=[], biomarkers=[]),
    "PATIENT_ERROR": PatientProfile(patientId="PATIENT_ERROR", condition="Error Condition", age=1, priorTherapies=[], biomarkers=[]), # To simulate errors
}

MOCK_TRIALS_DB = [
    {"id": "NCT001", "title": "Lung Cancer Trial A (EGFR+)", "condition": "Lung Cancer", "phase": "3", "status": "Recruiting", "min_age": 50, "required_markers": ["EGFR+"], "url": "http://example.com/nct001"},
    {"id": "NCT002", "title": "Lung Cancer Trial B (General)", "condition": "Lung Cancer", "phase": "2", "status": "Recruiting", "min_age": 18, "required_markers": [], "url": "http://example.com/nct002"},
    {"id": "NCT003", "title": "Breast Cancer Trial C (HER2+)", "condition": "Breast Cancer", "phase": "3", "status": "Recruiting", "min_age": 40, "required_markers": ["HER2+"], "url": "http://example.com/nct003"},
    {"id": "NCT004", "title": "Diabetes Study D", "condition": "Diabetes Type 2", "phase": "4", "status": "Recruiting", "min_age": 60, "required_markers": [], "url": "http://example.com/nct004"},
    {"id": "NCT005", "title": "Old Lung Cancer Trial", "condition": "Lung Cancer", "phase": "3", "status": "Completed", "min_age": 50, "required_markers": ["EGFR+"], "url": "http://example.com/nct005"}, # Not recruiting
]

# --- Mock Service Functions ---

async def fetch_patient_profile(patient_id: str) -> Optional[PatientProfile]:
    """MOCK: Simulates fetching patient data from EHR."""
    print(f"MOCK [PatientDataAgent]: Fetching profile for {patient_id}")
    await asyncio.sleep(random.uniform(0.2, 0.8)) # Simulate network/DB delay
    if patient_id == "PATIENT_ERROR":
         raise ValueError("Simulated database connection error") # Simulate failure
    return MOCK_PATIENT_DB.get(patient_id)

async def discover_trials(profile: PatientProfile) -> List[dict]:
    """MOCK: Simulates querying trial databases based on condition."""
    print(f"MOCK [TrialDiscoveryAgent]: Discovering trials for condition '{profile.condition}'")
    await asyncio.sleep(random.uniform(0.5, 1.5)) # Simulate API/DB delay
    # Simple filtering based on condition (a real agent would be more complex)
    relevant_trials = [
        trial for trial in MOCK_TRIALS_DB
        if trial["condition"] == profile.condition and trial["status"] == "Recruiting"
    ]
    print(f"MOCK [TrialDiscoveryAgent]: Found {len(relevant_trials)} potentially relevant recruiting trials.")
    return relevant_trials

async def perform_matching(profile: PatientProfile, trials: List[dict]) -> List[TrialMatch]:
    """
    MOCK: Simulates the complex Langchain/LLM matching process.
    Uses simple rules instead of real AI analysis.
    """
    print(f"MOCK [MatchingAgent]: Performing matching for {profile.patientId} against {len(trials)} trials.")
    matches = []
    for trial in trials:
        await asyncio.sleep(random.uniform(0.3, 1.0)) # Simulate LLM/analysis delay per trial
        print(f"MOCK [MatchingAgent]: Analyzing trial {trial['id']}...")

        rationale = []
        flags = []
        score = 0.0

        # --- Start Simple Mock Matching Rules ---
        # Rule 1: Condition Match (already pre-filtered, but good check)
        if trial["condition"] == profile.condition:
             rationale.append(f"Matches condition: {profile.condition}")
             score += 0.5
        else:
             continue # Should not happen due to discovery filter

        # Rule 2: Age Match
        if "min_age" in trial and profile.age >= trial["min_age"]:
            rationale.append(f"Meets minimum age: {profile.age} >= {trial['min_age']}")
            score += 0.3
        elif "min_age" in trial:
            flags.append(f"Potential Age Exclusion: Patient age {profile.age} < Min age {trial['min_age']}")
            score -= 0.5 # Penalize harder for exclusion

        # Rule 3: Biomarker Match (Simplified)
        if trial.get("required_markers"):
            match = True
            for marker in trial["required_markers"]:
                if marker not in profile.biomarkers:
                    flags.append(f"Missing required biomarker: {marker}")
                    match = False
                    score -= 0.5
                    break
            if match:
                rationale.append(f"Matches required biomarkers: {trial['required_markers']}")
                score += 0.4
        # --- End Simple Mock Matching Rules ---

        # Only add if score is reasonably positive (simulates basic relevance)
        if score > 0.1:
             match_entry = TrialMatch(
                trialId=trial["id"],
                title=trial["title"],
                status=trial["status"],
                phase=trial["phase"],
                condition=trial["condition"],
                locations=["Mock Location A", "Mock Location B"], # Hardcoded mock locations
                matchRationale=rationale,
                flags=flags,
                detailsUrl=trial.get("url"),
                contactInfo="Trial Contact: 555-MOCK", # Hardcoded mock contact
                rank_score=score # Keep score for sorting
            )
             matches.append(match_entry)

    # Sort matches by score descending
    matches.sort(key=lambda m: m.rank_score if m.rank_score else 0, reverse=True)

    print(f"MOCK [MatchingAgent]: Completed matching. Found {len(matches)} potential matches.")
    return matches


# --- Orchestrator ---

async def run_trial_matching_pipeline(patient_id: str) -> Union[List[TrialMatch], str]:
    """
    MOCK: Orchestrates the simulated agent workflow.
    Returns list of matches or an error string/code.
    """
    try:
        # 1. Get Patient Profile
        profile = await fetch_patient_profile(patient_id)
        if not profile:
            return "PATIENT_NOT_FOUND" # Specific error code

        # 2. Discover Trials
        potential_trials = await discover_trials(profile)
        if not potential_trials:
            return [] # No trials found for this condition

        # 3. Perform Matching (Simulated AI)
        matched_trials = await perform_matching(profile, potential_trials)

        return matched_trials

    except Exception as e:
        print(f"ERROR in pipeline for {patient_id}: {e}")
        # In real app, log exception details securely
        return "PIPELINE_ERROR" # Generic error code