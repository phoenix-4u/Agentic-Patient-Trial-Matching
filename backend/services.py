import asyncio
import os
import json
import random
from textwrap import dedent
from typing import List, Union, Dict, Any
from typing import List, Optional
from pydantic import BaseModel, Field

# --- OpenAI Library Import for direct client use ---
from openai import AsyncAzureOpenAI as SdkAsyncAzureOpenAI # Renamed to avoid confusion
# from openai.types.chat import ChatCompletionMessageParam # For explicit message typing if desired

# --- Agno Imports ---
from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.azure import AzureOpenAI as AgnoAzureOpenAI # Agno's model wrapper
# Messages, SystemMessage, UserMessage are not needed if analyze_trial_match uses SDK directly
# from agno.types.message import Messages, SystemMessage, UserMessage

# --- Local Imports ---
from models import TrialMatch
from logger import setup_logger

# --- Configuration & Initialization ---
load_dotenv()

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_TYPE = os.getenv("AZURE_OPENAI_API_TYPE", "azure")
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION") # Used by openai SDK
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME") # For agent's model
LLM_MODEL_FOR_ANALYSIS_TOOL = os.getenv("LLM_MODEL", AZURE_OPENAI_DEPLOYMENT_NAME) # Deployment for the analysis tool's direct LLM call

# Set environment variables if SDK or Agno model relies on them implicitly
# (though explicit passing to constructors is generally better)
if AZURE_OPENAI_API_KEY: os.environ["AZURE_OPENAI_API_KEY"] = AZURE_OPENAI_API_KEY
if AZURE_OPENAI_ENDPOINT: os.environ["AZURE_OPENAI_ENDPOINT"] = AZURE_OPENAI_ENDPOINT
if AZURE_OPENAI_API_TYPE: os.environ["OPENAI_API_TYPE"] = AZURE_OPENAI_API_TYPE # Agno uses OPENAI_API_TYPE
if OPENAI_API_VERSION: os.environ["OPENAI_API_VERSION"] = OPENAI_API_VERSION

logger = setup_logger("trial_matcher.services", log_level=os.getenv("LOG_LEVEL", "INFO"), log_file="logs/services.log")

# Main LLM instance for the Agno agent
agent_llm_config = AgnoAzureOpenAI(id=AZURE_OPENAI_DEPLOYMENT_NAME)

# --- Mock Data (remains the same) ---
MOCK_PATIENT_DB = {
    "PATIENT_001": {"patientId": "PATIENT_001", "condition": "Lung Cancer", "stage": "III", "age": 65, "priorTherapies": ["Chemo X"], "biomarkers": ["EGFR+"], "notes": "ECOG 1"},
    "PATIENT_002": {"patientId": "PATIENT_002", "condition": "Breast Cancer", "stage": "II", "age": 52, "priorTherapies": [], "biomarkers": ["HER2+"], "notes": "No major comorbidities"},
    "PATIENT_003": {"patientId": "PATIENT_003", "condition": "Diabetes Type 2", "age": 70, "priorTherapies": ["Metformin"], "biomarkers": [], "notes": "HbA1c 8.1%, Mild CKD Stage 2"},
    "PATIENT_NO_MATCH": {"patientId": "PATIENT_NO_MATCH", "condition": "Rare Condition Y", "age": 40, "priorTherapies": [], "biomarkers": [], "notes": ""},
    "PATIENT_ERROR": {"patientId": "PATIENT_ERROR", "condition": "Error Condition", "age": 1, "priorTherapies": [], "biomarkers": [], "notes": ""},
}

MOCK_TRIALS_DB = [
    {"id": "NCT001", "title": "Lung Cancer Trial A (EGFR+)", "condition": "Non-Small Cell Lung Cancer", "phase": "3", "status": "Recruiting", "min_age": 50, "max_age": 75, "required_markers": ["EGFR+"], "exclusions": ["Prior immunotherapy", "Brain metastases"], "inclusions": ["Stage III or IV", "ECOG 0-1"], "eligibility_text": "Must have documented EGFR mutation. No prior treatment with EGFR TKIs. Adequate organ function required.", "url": "http://example.com/nct001"},
    {"id": "NCT002", "title": "Lung Cancer Trial B (General)", "condition": "Non-Small Cell Lung Cancer", "phase": "2", "status": "Recruiting", "min_age": 18, "max_age": None, "required_markers": [], "exclusions": ["Active autoimmune disease"], "inclusions": ["Advanced or metastatic NSCLC", "At least one prior line of therapy"], "eligibility_text": "Patients with measurable disease per RECIST v1.1.", "url": "http://example.com/nct002"},
    {"id": "NCT003", "title": "Breast Cancer Trial C (HER2+)", "condition": "Breast Cancer", "phase": "3", "status": "Recruiting", "min_age": 40, "max_age": 70, "required_markers": ["HER2+"], "exclusions": ["Significant cardiovascular disease"], "inclusions": ["Metastatic HER2+ Breast Cancer", "Prior taxane therapy"], "eligibility_text": "Confirmation of HER2 status by central lab required.", "url": "http://example.com/nct003"},
    {"id": "NCT004", "title": "Diabetes Study D", "condition": "Diabetes Type 2", "phase": "4", "status": "Recruiting", "min_age": 60, "max_age": 80, "required_markers": [], "exclusions": ["eGFR < 45 ml/min", "Recent cardiovascular event"], "inclusions": ["Diagnosed Type 2 Diabetes > 5 years", "HbA1c between 7.5% and 9.5%"], "eligibility_text": "Stable dose of metformin allowed.", "url": "http://example.com/nct004"},
    {"id": "NCT005", "title": "Old Lung Cancer Trial", "condition": "Non-Small Cell Lung Cancer", "phase": "3", "status": "Completed", "min_age": 50, "max_age": 75, "required_markers": ["EGFR+"], "exclusions": [], "inclusions": [], "eligibility_text": "", "url": "http://example.com/nct005"},
]

class LLMAnalysisResult(BaseModel):
    """
    Represents the structured output from the LLM after analyzing a patient against a trial.
    """
    decision: str = Field(
        ...,
        description="The LLM's decision on whether the trial is a match (e.g., 'Potential Match', 'Likely Not a Match')."
    )
    reasoning_steps: List[str] = Field(
        default_factory=list,
        description="A step-by-step breakdown of the LLM's reasoning process."
    )
    match_rationale: List[str] = Field(
        default_factory=list,
        description="Specific points supporting why the trial might be a match."
    )
    flags: List[str] = Field(
        default_factory=list,
        description="Specific points against a match or aspects needing further review/clarification."
    )


# --- Define Agno Tools (Functions) ---

async def fetch_patient_profile(agent: Agent, patient_id: str) -> Dict[str, Any]:
    """Fetches the patient's profile using their ID. Returns patient data or error status."""
    logger.debug(f"Executing fetch_patient_profile for {patient_id}")
    if agent.session_state:
        agent.session_state["fetch_attempts"] = agent.session_state.get("fetch_attempts", 0) + 1
        logger.debug(f"Patient profile fetch attempt count: {agent.session_state['fetch_attempts']}")
    await asyncio.sleep(random.uniform(0.1, 0.3))
    if patient_id == "PATIENT_ERROR":
        logger.error("Simulated database error fetching patient profile.")
        return {"error": "Simulated database connection error"}
    profile_data = MOCK_PATIENT_DB.get(patient_id)
    if profile_data:
        return {"status": "success", "profile": profile_data}
    else:
        return {"status": "not_found", "message": f"Patient ID {patient_id} not found."}

async def discover_trials(agent: Agent, patient_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Finds potentially relevant *recruiting* clinical trials based on the patient's primary condition."""
    patient_condition = patient_profile.get("condition", "").lower()
    logger.debug(f"Executing discover_trials for condition '{patient_condition}'")
    if not patient_condition:
        return {"error": "Patient profile missing condition."}
    await asyncio.sleep(random.uniform(0.2, 0.5))
    relevant_trials = [
        trial for trial in MOCK_TRIALS_DB
        if patient_condition in trial["condition"].lower() and trial["status"] == "Recruiting"
    ]
    return {"status": "success", "trials": relevant_trials}

_ANALYSIS_PROMPT_TEMPLATE = dedent("""
    You are an expert AI assistant specialized in clinical trial matching.
    Analyze the patient against the trial criteria **meticulously**.
    **Think step-by-step** (Chain-of-Thought) comparing patient details (Age: {patient_age}, Condition: {patient_condition}, Stage: {patient_stage}, Biomarkers: {patient_biomarkers}, Notes: {patient_notes})
    against trial criteria (Min Age: {trial_min_age}, Max Age: {trial_max_age}, Condition: {trial_condition}, Biomarkers: {trial_required_markers}, Key Inclusions: {trial_inclusions}, Key Exclusions: {trial_exclusions}).
    **Decision:** Conclude if this is a 'Potential Match', 'Likely Not a Match', or 'Uncertain'.
    **Rationale:** List specific points supporting a match.
    **Flags:** List specific points against a match or needing review.
    **Output ONLY a JSON object** with keys: "decision", "reasoning_steps", "match_rationale", "flags".

    Patient Profile Snippet: {patient_profile_str}
    Trial Details Snippet: {trial_details_str}

    Perform the analysis and provide the JSON output:
""")

# Instantiate the Azure SDK client for direct use in analyze_trial_match
# This client is configured once and can be reused.
azure_sdk_client = SdkAsyncAzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=OPENAI_API_VERSION,
)

async def analyze_trial_match(agent: Agent, patient_profile: Dict[str, Any], trial: Dict[str, Any]) -> Dict[str, Any]:
    """Analyzes a specific trial against a patient profile using detailed LLM reasoning (CoT) to determine if it's a potential match. Returns match details or non-match indication."""
    # agent parameter is kept for consistency and if other agent properties (like session_state) were needed.
    trial_id = trial.get("id", "N/A")
    patient_id = patient_profile.get("patientId", "N/A")
    logger.debug(f"Executing analyze_trial_match for Patient {patient_id} and Trial {trial_id} using direct SDK call.")

    patient_profile_str = json.dumps({k: patient_profile.get(k) for k in ['age', 'condition', 'stage', 'biomarkers', 'notes']})
    trial_details_str = json.dumps({k: trial.get(k) for k in ['min_age', 'max_age', 'condition', 'required_markers', 'inclusions', 'exclusions']})

    prompt_content = _ANALYSIS_PROMPT_TEMPLATE.format(
        patient_age=patient_profile.get("age"),
        patient_condition=patient_profile.get("condition"),
        patient_stage=patient_profile.get("stage", "N/A"),
        patient_biomarkers=", ".join(patient_profile.get("biomarkers", [])),
        patient_notes=patient_profile.get("notes", "N/A"),
        trial_min_age=trial.get("min_age", "N/A"),
        trial_max_age=trial.get("max_age", "N/A"),
        trial_condition=trial.get("condition"),
        trial_required_markers=", ".join(trial.get("required_markers", [])),
        trial_inclusions=", ".join(trial.get("inclusions", [])),
        trial_exclusions=", ".join(trial.get("exclusions", [])),
        patient_profile_str=patient_profile_str,
        trial_details_str=trial_details_str
    )
    
    # Messages in OpenAI JSON-compatible format (list of dicts)
    messages_for_sdk: list[dict[str, str]] = [ # Or use List[ChatCompletionMessageParam] for stricter typing
        {"role": "system", "content": "You output ONLY valid JSON."},
        {"role": "user", "content": prompt_content}
    ]
    
    raw_llm_response_content = None
    try:
        chat_completion = await azure_sdk_client.chat.completions.create(
            model=LLM_MODEL_FOR_ANALYSIS_TOOL, # Specify the deployment name for this call
            messages=messages_for_sdk,
            temperature=0.2,
            response_format={"type": "json_object"} # For OpenAI SDK v1.x+ if model supports JSON mode
        )
        
        if chat_completion.choices and chat_completion.choices[0].message:
            raw_llm_response_content = chat_completion.choices[0].message.content
        
        if not raw_llm_response_content:
            logger.error(f"LLM returned empty content for trial {trial_id} via SDK.")
            return {"status": "error", "message": "LLM returned empty content."}

        analysis_result = json.loads(raw_llm_response_content)
        logger.debug(f"LLM analysis result for {trial_id} (SDK): {analysis_result}")

        if analysis_result.get("decision") == "Potential Match":
            match_data = TrialMatch(
                trialId=trial_id, title=trial.get("title", "Unknown Title"), status=trial.get("status", "Unknown"),
                phase=trial.get("phase", "N/A"), condition=trial.get("condition", "Unknown"),
                locations=["Location Pending API"], matchRationale=analysis_result.get("match_rationale", []),
                flags=analysis_result.get("flags", []), detailsUrl=trial.get("url"),
                contactInfo="Contact Pending API", rank_score=1.0 - (len(analysis_result.get("flags", [])) * 0.1)
            ).dict()
            return {"status": "success", "match_data": match_data}
        else:
            return {"status": "no_match", "reason": analysis_result.get("decision", "N/A"), "details": analysis_result}

    except json.JSONDecodeError as json_e:
         logger.error(f"SDK: Failed to parse LLM JSON output for trial {trial_id}: {json_e}. Raw: {raw_llm_response_content}", exc_info=True)
         return {"status": "error", "message": "LLM output parsing failed (SDK)." }
    except Exception as e: # Catch specific OpenAI API errors if possible
        logger.error(f"SDK: Error during LLM analysis for trial {trial_id}: {e}", exc_info=True)
        return {"status": "error", "message": f"LLM API call failed (SDK): {str(e)}"}

# --- Define Agno Planning Agent ---
PLANNER_SYSTEM_PROMPT = dedent("""
    You are a highly organized AI assistant responsible for managing the clinical trial matching process for a given patient ID.
    Your goal is to find suitable, recruiting clinical trials for the patient.
    You have access to the following tools:
    1.  `fetch_patient_profile`: Input `patient_id` (string). Output: patient profile data (dict) or not_found/error status.
    2.  `discover_trials`: Input `patient_profile` (dict). Output: list of potential trial dicts or error.
    3.  `analyze_trial_match`: Input `patient_profile` (dict) and `trial` (dict). Output: match details (dict) if a potential match, or no_match/error status.

    Your task is to create and execute a step-by-step plan using these tools:
    1.  **Plan Step 1:** Get the patient's profile using `fetch_patient_profile`. If the patient is not found or an error occurs, report 'PATIENT_NOT_FOUND' or 'ERROR_FETCHING_PATIENT' respectively and stop.
    2.  **Plan Step 2:** If the profile is found, use `discover_trials` with the profile to find relevant trials. If no trials are found, return an empty list [] and stop. If an error occurs, report 'ERROR_DISCOVERING_TRIALS' and stop.
    3.  **Plan Step 3:** If trials are found, iterate through *each* trial. For each one, use `analyze_trial_match` with the patient profile and the trial data.
    4.  **Plan Step 4:** Collect all the successful 'Potential Match' results (specifically the 'match_data' dictionary) from `analyze_trial_match`.
    5.  **Final Output:** Return a final JSON string representing a list containing only the detailed 'match_data' dictionaries from the successful analyses. If no matches are found at any stage (e.g. step 2 or no potential matches from step 4), return a JSON string of an empty list ('[]'). If a critical error occurred as outlined above (e.g. patient not found), return that specific error message as a plain string.

    Think step-by-step (Chain-of-Thought) to generate your plan before you start executing skills. Then, execute the skills according to your plan.
    Ensure your final output is either a JSON string representing the list of matches (or empty list), or a plain text error message string.
    Current session state related to this workflow: {session_state}
""")

# --- Agno Agent Setup ---
trial_matching_agent = Agent(
    name="TrialMatchingPlannerAgent",
    description="Orchestrates the clinical trial matching process using available skills.",
    system_message=PLANNER_SYSTEM_PROMPT,
    model=agent_llm_config,
    tools=[fetch_patient_profile, discover_trials, analyze_trial_match],
    session_state={"workflow_runs": 0, "fetch_attempts": 0, "last_error": None},
    add_state_in_messages=True,
    # response_model=LLMAnalysisResult,
    # use_json_mode=True, <-- Sometimes instead of json, it is providing the pydantic class directly. Hence handling it with prompt.
)

# --- Function for FastAPI to Call ---
async def run_agno_matching_workflow(patient_id: str) -> Union[List[Dict[str, Any]], str]:
    logger.info(f"Initiating Agno Trial Matching workflow for patient: {patient_id}")
    if trial_matching_agent.session_state is not None:
        trial_matching_agent.session_state["workflow_runs"] = trial_matching_agent.session_state.get("workflow_runs", 0) + 1
        trial_matching_agent.session_state["fetch_attempts"] = 0
    try:
        agent_task_query = f"""IMPORTANT: Your entire response MUST be ONLY a valid JSON string (no markdown, no explanations, 
        no preamble, no code blocks, no commentary). If you include anything else, the system will fail. You are a strict API. 
        You must output ONLY a valid JSON string as your entire response. Find clinical trial matches for patient ID: {patient_id}."""

        example_response1 = {'decision': 'Potential Match', 'reasoning_steps': ["Step 1: Patient age is 65, which falls within the trial's age range of 50 to 75.", 'Step 2: Patient condition is Lung Cancer. The trial specifies Non-Small Cell Lung Cancer, which is a subtype of Lung Cancer. Assuming the patient has NSCLC, this criterion is met.', "Step 3: Patient stage is III, which matches the trial's inclusion criteria of Stage III or IV.", "Step 4: Patient biomarker is EGFR+, which matches the trial's required biomarker EGFR+.", "Step 5: Patient ECOG performance status is 1, which is within the trial's inclusion criteria of ECOG 0-1.", 'Step 6: No information provided about prior immunotherapy or brain metastases, which are trial exclusion criteria. These need further review.'], 'match_rationale': ['Age is within the eligible range.', 'Condition likely matches (assuming NSCLC).', 'Stage III is explicitly included.', 'Biomarker EGFR+ is required and present.', 'ECOG performance status of 1 is acceptable.'], 'flags': ['Uncertainty about whether the patient has NSCLC specifically.', 'No information provided about prior immunotherapy history.', 'No information provided about presence or absence of brain metastases.']}
        example_response2 = {'decision': 'Likely Not a Match', 'reasoning_steps': ["Step 1: Age criteria - Patient is 65 years old, which meets the trial's minimum age requirement of 18. No maximum age is specified, so this criterion is satisfied.", "Step 2: Condition criteria - Patient has Lung Cancer, but the trial specifies Non-Small Cell Lung Cancer (NSCLC). The patient's specific subtype is not explicitly stated, so this requires clarification.", "Step 3: Stage criteria - Patient is Stage III, which is considered advanced but not metastatic. The trial requires 'Advanced or metastatic NSCLC,' so this partially meets the inclusion criteria.", "Step 4: Biomarkers - The trial does not specify required biomarkers, so the patient's EGFR+ status does not affect eligibility.", 'Step 5: Prior therapy - The trial requires at least one prior line of therapy. This information is not provided in the patient profile, so eligibility cannot be confirmed.', 'Step 6: Exclusions - The patient has an ECOG score of 1, which is acceptable. No mention of active autoimmune disease is present, so exclusions are not triggered.'], 'match_rationale': ['Age meets the trial criteria.', 'Stage III lung cancer is considered advanced, which partially aligns with the inclusion criteria.', 'No exclusions are triggered based on the provided patient details.'], 'flags': ["The patient's specific subtype of lung cancer (NSCLC or otherwise) needs clarification.", 'Information about prior lines of therapy is missing and critical for determining eligibility.']}



        response = await trial_matching_agent.arun(agent_task_query)
        if not response or not hasattr(response, 'content') or not response.content:
            error_msg = "PIPELINE_ERROR_AGNO_NO_CONTENT"
            if trial_matching_agent.session_state: trial_matching_agent.session_state["last_error"] = error_msg
            return error_msg
        raw_output = response.content
        try:
            final_result = json.loads(raw_output)
            if isinstance(final_result, list):
                if trial_matching_agent.session_state: trial_matching_agent.session_state["last_error"] = None
                return final_result
            else:
                error_msg = f"AGNO_AGENT_UNEXPECTED_JSON_TYPE: {final_result}"
                if isinstance(final_result, str): error_msg = f"AGNO_AGENT_UNEXPECTED_JSON_STRING: {final_result}"
                if trial_matching_agent.session_state: trial_matching_agent.session_state["last_error"] = error_msg
                return error_msg
        except json.JSONDecodeError:
            if trial_matching_agent.session_state: trial_matching_agent.session_state["last_error"] = raw_output
            return raw_output
    except Exception as e:
        error_str = f"PIPELINE_ERROR_UNHANDLED_EXCEPTION: {str(e)}"
        if trial_matching_agent.session_state: trial_matching_agent.session_state["last_error"] = error_str
        logger.error(f"Error running Agno workflow for {patient_id}: {e}", exc_info=True)
        return error_str