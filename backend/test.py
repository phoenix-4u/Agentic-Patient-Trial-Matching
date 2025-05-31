#I could not run this even after extensive debugging, the workflow and team setup goes on in a loop. 
#nKeeping the original code for reference

import asyncio
import os
import json
import random
from textwrap import dedent
from typing import List, Union, Dict, Any, Optional, Iterator

# --- OpenAI Library Import for direct client use ---
from openai import AsyncAzureOpenAI as SdkAsyncAzureOpenAI

# --- Pydantic Model for LLM Analysis Output ---
from pydantic import BaseModel, Field

# --- Agno Imports ---
from dotenv import load_dotenv
from agno.agent import Agent
from agno.models.azure import AzureOpenAI as AgnoAzureOpenAI
from agno.team.team import Team 
from agno.workflow import Workflow, RunEvent, RunResponse
# from agno.storage.sqlite import SqliteStorage # Example if persistent storage is needed

# --- Local Imports ---
from models import TrialMatch # Assuming models.py contains TrialMatch
from logger import setup_logger # Assuming logger.py contains setup_logger

# --- Configuration & Initialization ---
load_dotenv()

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_TYPE = os.getenv("AZURE_OPENAI_API_TYPE", "azure")
OPENAI_API_VERSION = os.getenv("OPENAI_API_VERSION")
AZURE_OPENAI_DEPLOYMENT_NAME_AGENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME") 
AZURE_OPENAI_DEPLOYMENT_NAME_TOOL = os.getenv("LLM_MODEL", AZURE_OPENAI_DEPLOYMENT_NAME_AGENT)
AZURE_OPENAI_DEPLOYMENT_NAME_TEAM = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME_TEAM", AZURE_OPENAI_DEPLOYMENT_NAME_AGENT)


if AZURE_OPENAI_API_KEY: os.environ["AZURE_OPENAI_API_KEY"] = AZURE_OPENAI_API_KEY
if AZURE_OPENAI_ENDPOINT: os.environ["AZURE_OPENAI_ENDPOINT"] = AZURE_OPENAI_ENDPOINT
if AZURE_OPENAI_API_TYPE: os.environ["OPENAI_API_TYPE"] = AZURE_OPENAI_API_TYPE
if OPENAI_API_VERSION: os.environ["OPENAI_API_VERSION"] = OPENAI_API_VERSION

logger = setup_logger("trial_matcher.services", log_level=os.getenv("LOG_LEVEL", "INFO"), log_file="logs/services.log")

# LLM instance for Agno Agents and Team
common_llm_config = AgnoAzureOpenAI(id=AZURE_OPENAI_DEPLOYMENT_NAME_AGENT)
team_llm_config = AgnoAzureOpenAI(id=AZURE_OPENAI_DEPLOYMENT_NAME_TEAM)


# SDK client for direct use in analyze_trial_match tool - initialized globally
azure_sdk_client_for_tool = SdkAsyncAzureOpenAI(
    api_key=AZURE_OPENAI_API_KEY,
    azure_endpoint=AZURE_OPENAI_ENDPOINT,
    api_version=OPENAI_API_VERSION,
)

# --- Pydantic Model for LLM Analysis Result ---
class LLMAnalysisResult(BaseModel):
    decision: str = Field(..., description="LLM's decision (e.g., 'Potential Match').")
    reasoning_steps: List[str] = Field(default_factory=list, description="LLM's reasoning steps.")
    match_rationale: List[str] = Field(default_factory=list, description="Points supporting a match.")
    flags: List[str] = Field(default_factory=list, description="Points against a match or needing review.")

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

# --- Tool Functions (largely unchanged, ensure agent.session_state is handled if needed by tools) ---
async def fetch_patient_profile(patient_id: str) -> Dict[str, Any]:
    """Fetch a patient's profile from the database.

    Args:
        patient_id: The ID of the patient to fetch.

    Returns:
        Dict containing the patient's profile data or error information.
    """
    logger.debug(f"Executing fetch_patient_profile for {patient_id}")
    # Team-level context is managed by the Team orchestrator.
    await asyncio.sleep(random.uniform(0.1, 0.3))
    if patient_id == "PATIENT_ERROR":
        return {"error": "Simulated database connection error", "status": "error"}
    profile_data = MOCK_PATIENT_DB.get(patient_id)
    if profile_data:
        return {"status": "success", "profile": profile_data}
    else:
        return {"status": "not_found", "message": f"Patient ID {patient_id} not found."}

async def discover_trials(patient_profile: Dict[str, Any]) -> Dict[str, Any]:
    """Discover trials matching a patient's profile.

    Args:
        patient_profile: Dictionary containing patient profile data.

    Returns:
        Dict containing matching trials or error information.
    """
    logger.debug("Executing discover_trials")
    patient_condition = patient_profile.get("condition", "").lower()
    if not patient_condition: 
        return {"status": "error", "error": "Patient profile missing condition."}
    await asyncio.sleep(random.uniform(0.2, 0.5))
    relevant_trials = [
        t for t in MOCK_TRIALS_DB if patient_condition in t["condition"].lower() and t["status"] == "Recruiting"
    ]
    return {"status": "success", "trials": relevant_trials}

_ANALYSIS_PROMPT_TEMPLATE_FOR_TOOL = dedent("""
    You are an expert AI assistant specialized in clinical trial matching.
    Analyze the patient against the trial criteria **meticulously**.
    Patient Profile Snippet: {patient_profile_str}
    Trial Details Snippet: {trial_details_str}
    **Think step-by-step** comparing patient details against trial criteria.
    **Decision:** Conclude 'Potential Match', 'Likely Not a Match', or 'Uncertain'.
    **Rationale:** List specific points supporting a match.
    **Flags:** List specific points against a match or needing review.
    **Output ONLY a JSON object** with keys: "decision", "reasoning_steps", "match_rationale", "flags".
""")

async def analyze_trial_match(patient_profile: Dict[str, Any], trial: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze if a trial matches a patient's profile.

    Args:
        patient_profile: Dictionary containing patient profile data.
        trial: Dictionary containing trial data to analyze.

    Returns:
        Dict containing analysis results.
    """
    logger.debug(f"Executing analyze_trial_match for trial {trial.get('id', 'N/A')}")
    patient_profile_str = json.dumps({k: patient_profile.get(k) for k in ['age', 'condition', 'stage', 'biomarkers', 'notes']})
    trial_details_str = json.dumps({k: trial.get(k) for k in ['min_age', 'max_age', 'condition', 'required_markers', 'inclusions', 'exclusions']})
    
    prompt_content = _ANALYSIS_PROMPT_TEMPLATE_FOR_TOOL.format(
        patient_profile_str=patient_profile_str, trial_details_str=trial_details_str
    )
    messages_for_sdk: list[dict[str, str]] = [
        {"role": "system", "content": "You output ONLY valid JSON."},
        {"role": "user", "content": prompt_content}
    ]
    raw_llm_response_content = None
    try:
        chat_completion = await azure_sdk_client_for_tool.chat.completions.create(
            model=AZURE_OPENAI_DEPLOYMENT_NAME_TOOL, messages=messages_for_sdk, temperature=0.2,
            response_format={"type": "json_object"}
        )
        if chat_completion.choices and chat_completion.choices[0].message:
            raw_llm_response_content = chat_completion.choices[0].message.content
        if not raw_llm_response_content:
            return {"status": "error", "message": "LLM returned empty content (SDK)."}
        
        parsed_llm_data = LLMAnalysisResult(**json.loads(raw_llm_response_content))
        logger.debug(f"LLM analysis (SDK) for trial {trial.get('id', 'N/A')}: {parsed_llm_data.decision}")

        if parsed_llm_data.decision == "Potential Match":
            phase_value = f"Phase {trial.get('phase')}" if trial.get('phase') not in [None, "N/A"] else "N/A"
            match_data = TrialMatch(
                trialId=trial.get("id", "N/A"), title=trial.get("title", "Unknown Title"),
                status=trial.get("status", "Unknown"), phase=phase_value,
                condition=trial.get("condition", "Unknown"), locations=["Location Pending API"],
                matchRationale=parsed_llm_data.match_rationale, flags=parsed_llm_data.flags,
                detailsUrl=trial.get("url"), contactInfo="Contact Pending API",
                rank_score=1.0 - (len(parsed_llm_data.flags) * 0.1) 
            ).model_dump()
            return {"status": "success", "match_data": match_data, "llm_analysis": parsed_llm_data.model_dump()}
        else:
            return {"status": "no_match", "reason": parsed_llm_data.decision, "details": parsed_llm_data.model_dump()}
    except json.JSONDecodeError as e:
        logger.error(f"SDK JSON Parsing Error: {e}. Raw: {raw_llm_response_content}", exc_info=True)
        return {"status": "error", "message": "LLM output parsing failed (SDK)."}
    except Exception as e:
        logger.error(f"SDK LLM Call Error: {e}", exc_info=True)
        return {"status": "error", "message": f"LLM API call failed (SDK): {str(e)}"}


# --- Team Instructions (Adapted from original) ---
TEAM_INSTRUCTIONS = dedent("""
    You are the 'ClinicalTrialMatchingTeam' orchestrator. Your goal is to find suitable clinical trials for a given patient ID.
    The patient_id will be provided in the initial message.
    Your entire response (final output of the team's collaboration) MUST be ONLY a valid JSON string (no markdown, no explanations, no preamble, no code blocks, no commentary).
    If you include anything else, the downstream system parsing your output will fail. You are a strict API.

    **TOOL CALL RETRY POLICY:**
    - For each critical tool call (fetch_patient_profile, discover_trials, analyze_trial_match), you are allowed a **maximum of TWO (2) attempts in total** for that specific invocation.
    - The first attempt is the initial call. If it fails (e.g., due to argument errors, API errors from the tool, or any other reason the tool returns a non-success status), you may make ONE (1) additional retry.
    - To manage retries for a specific tool call, use the `team_context` to store an attempt counter. For example, before the first call to `fetch_patient_profile`, you might ensure `team_context['fetch_patient_profile_attempts']` is 0 or 1. If it fails, increment this counter.
    - If a tool call fails and its attempt counter has reached 2, you MUST NOT try that specific tool invocation again.
    - Instead, your process for that patient_id must terminate for that step, and you should return a specific JSON error object:
      `{{"error_type": "TOOL_CALL_FAILED_MAX_RETRIES", "tool_name": "name_of_failed_tool", "attempts_made": 2, "message": "Specific error from the last tool attempt or 'Failed after 2 attempts.'"}}`
    - If a tool call succeeds, you can reset or remove its specific retry counter from `team_context` or simply ignore it as you move to the next task.

    CRITICAL SEQUENCE OF STEPS AND CONTEXT MANAGEMENT:

    1.  **Get Patient Profile**:
        - Initialize or check `team_context['retries_for_fetch_patient_profile']`. Set to 0 if not present.
        - If `team_context.get('retries_for_fetch_patient_profile', 0) >= 2`:
            - Return JSON: `{{"error_type": "TOOL_CALL_FAILED_MAX_RETRIES", "tool_name": "fetch_patient_profile", "attempts_made": 2, "message": "Failed to fetch patient profile after 2 attempts."}}`
        - Increment `team_context['retries_for_fetch_patient_profile'] = team_context.get('retries_for_fetch_patient_profile', 0) + 1`.
        - Use PatientProfilerAgent with `fetch_patient_profile` tool.
        - **CRITICAL TOOL CALL FORMAT:** The `fetch_patient_profile` tool requires one argument named `patient_id`.
          You MUST call it as: `fetch_patient_profile(patient_id=THE_PATIENT_ID_FROM_INITIAL_MESSAGE)`
          For example, if the initial message says "patient ID: PATIENT_001", the call is `fetch_patient_profile(patient_id="PATIENT_001")`.
        - Let the result be `tool_result`.
        - If `tool_result['status'] == 'success'`:
            - Store result in `team_context['patient_profile'] = tool_result['profile']`.
            - Reset `team_context['retries_for_fetch_patient_profile'] = 0`.
            - Proceed to step 2.
        - Else if `tool_result['status'] == 'not_found'`:
            - Return JSON string: `{{"error_type": "PATIENT_NOT_FOUND", "message": tool_result['message']}}`
        - Else (`tool_result['status'] == 'error'` or other failure):
            - Log the failure details.
            - If `team_context['retries_for_fetch_patient_profile'] < 2`:
                - Re-attempt this step 1, ensuring retry counter logic is respected.
            - Else (this was the second failed attempt):
                - Return JSON: `{{"error_type": "TOOL_CALL_FAILED_MAX_RETRIES", "tool_name": "fetch_patient_profile", "attempts_made": 2, "message": tool_result.get('error', 'Failed after 2 attempts.')}}`
        - VERIFY `team_context['patient_profile']` exists before proceeding if successful.

    2.  **Discover Trials**:
        - VERIFY `team_context['patient_profile']` (a dictionary) exists. If not, return `{"error_type": "MISSING_PATIENT_PROFILE", "message": "Cannot discover trials without patient profile."}`.
        - Initialize or check `team_context['retries_for_discover_trials']`. Set to 0 if not present.
        - If `team_context.get('retries_for_discover_trials', 0) >= 2`:
            - Return JSON: `{{"error_type": "TOOL_CALL_FAILED_MAX_RETRIES", "tool_name": "discover_trials", "attempts_made": 2, "message": "Failed to discover trials after 2 attempts."}}`
        - Increment `team_context['retries_for_discover_trials'] = team_context.get('retries_for_discover_trials', 0) + 1`.
        - Use TrialDiscovererAgent with `discover_trials` tool.
        - **CRITICAL TOOL CALL FORMAT:** The `discover_trials` tool requires one argument named `patient_profile`.
          The value for this `patient_profile` argument MUST be the entire dictionary object stored in `team_context['patient_profile']`.
          You MUST call it as: `discover_trials(patient_profile=team_context['patient_profile'])`
          (Here, `team_context['patient_profile']` refers to the actual dictionary data, not the string 'team_context['patient_profile']').
        - Let the result be `tool_result`.
        - If `tool_result['status'] == 'success'`:
            - Store result in `team_context['trials'] = tool_result['trials']`.
            - Reset `team_context['retries_for_discover_trials'] = 0`.
            - If `team_context['trials']` is empty: return JSON string: '[]'.
            - Proceed to step 3.
        - Else (`tool_result['status'] == 'error'` or other failure):
            - Log the failure details.
            - If `team_context['retries_for_discover_trials'] < 2`:
                - Re-attempt this step 2, respecting retry logic.
            - Else (second failed attempt):
                - Return JSON: `{{"error_type": "TOOL_CALL_FAILED_MAX_RETRIES", "tool_name": "discover_trials", "attempts_made": 2, "message": tool_result.get('error', 'Failed after 2 attempts.')}}`
        - VERIFY `team_context['trials']` exists and is not empty before proceeding if successful and trials found.

    3.  **Analyze Each Trial**:
        - VERIFY both `team_context['patient_profile']` (a dictionary) and non-empty `team_context['trials']` (a list of dictionaries) exist.
        - Initialize `team_context['analysis_results'] = []` if it doesn't exist.
        - For each `current_trial` (which is a dictionary) in `team_context['trials']`:
            - Let `trial_id_for_retry_key = "retries_for_analyze_trial_" + current_trial.get("id", "unknown_trial")`.
            - Initialize or check `team_context[trial_id_for_retry_key]`. Set to 0 if not present.
            - If `team_context.get(trial_id_for_retry_key, 0) >= 2`:
                - Append to `team_context['analysis_results']`: `{{"trial_id": current_trial.get("id"), "status": "error_max_retries", "message": "analyze_trial_match for this trial failed after 2 attempts."}}`
                - Continue to the next trial.
            - Increment `team_context[trial_id_for_retry_key] = team_context.get(trial_id_for_retry_key, 0) + 1`.
            - Use TrialAnalyzerAgent with `analyze_trial_match` tool.
            - **CRITICAL TOOL CALL FORMAT:** The `analyze_trial_match` tool requires two arguments: `patient_profile` and `trial`.
              The value for `patient_profile` MUST be the dictionary from `team_context['patient_profile']`.
              The value for `trial` MUST be the `current_trial` dictionary from the loop.
              You MUST call it as: `analyze_trial_match(patient_profile=team_context['patient_profile'], trial=current_trial)`
            - Let the result be `tool_call_output`.
            - If `tool_call_output['status'] == 'success'` or `tool_call_output['status'] == 'no_match'`:
                - Append `tool_call_output` to `team_context['analysis_results']`.
                - Reset `team_context[trial_id_for_retry_key] = 0`.
            - Else (`tool_call_output['status'] == 'error'`):
                - Log failure for this trial.
                - If `team_context[trial_id_for_retry_key] < 2`:
                    - Retry analyzing this specific `current_trial` (re-execute this iteration for `current_trial`, respecting retry logic).
                - Else (second failed attempt for this trial):
                    - Append to `team_context['analysis_results']`: `{{"trial_id": current_trial.get("id"), "status": "error_max_retries", "message": f"analyze_trial_match for this trial failed after 2 attempts: {tool_call_output.get('message')}"}}`
                    - Continue to the next trial.

    4.  **Compile Final Results & Return JSON String**:
        - VERIFY `team_context['analysis_results']` exists and is a list.
        - Create an empty list: `final_matches_list = []`.
        - Iterate through each `item` in `team_context['analysis_results']`.
        - For each `item`:
            - Check if `item` is a dictionary AND `item.get('status') == 'success'` AND `item.get('match_data')` exists and is a dictionary.
            - **If all these conditions are true, then the dictionary at `item['match_data']` is a valid match. Add this `item['match_data']` dictionary DIRECTLY to `final_matches_list`.**
            - **IMPORTANT: The `item['match_data']` dictionary is ALREADY in the correct format. DO NOT modify it. DO NOT wrap it in other keys like 'match_criteria'.**
        - After iterating, if `final_matches_list` is empty, return the JSON string `'[]'`.
        - Otherwise, return `final_matches_list` as a JSON STRING.
        - **Each dictionary in the `final_matches_list` MUST EXACTLY match this schema:**
          ```json
          {
              "trialId": "string",
              "title": "string",
              "status": "string (e.g., Recruiting)",
              "phase": "string (e.g., Phase 3)",
              "condition": "string",
              "locations": ["list of strings"],
              "matchRationale": ["list of strings"],
              "flags": ["list of strings"],
              "detailsUrl": "string or null",
              "contactInfo": "string or null",
              "rank_score": "number or null"
          }
          ```
        - **Example of a SINGLE item in the `final_matches_list` (before converting the whole list to a JSON string):**
          ```json
          {
              "trialId": "NCT001",
              "title": "Lung Cancer Trial A (EGFR+)",
              "status": "Recruiting",
              "phase": "Phase 3",
              "condition": "Non-Small Cell Lung Cancer",
              "locations": ["Location Pending API"],
              "matchRationale": ["Patient has EGFR+", "Age is within range"],
              "flags": ["Requires ECOG 0-1, patient is ECOG 1"],
              "detailsUrl": "http://example.com/nct001",
              "contactInfo": "Contact Pending API",
              "rank_score": 0.9
          }
          ```
        - **Example of the final JSON string if there's one match:**
          `'[{"trialId": "NCT001", "title": "Lung Cancer Trial A (EGFR+)", "status": "Recruiting", "phase": "Phase 3", "condition": "Non-Small Cell Lung Cancer", "locations": ["Location Pending API"], "matchRationale": ["Patient has EGFR+", "Age is within range"], "flags": ["Requires ECOG 0-1, patient is ECOG 1"], "detailsUrl": "http://example.com/nct001", "contactInfo": "Contact Pending API", "rank_score": 0.9}]'`

    CONTEXT VERIFICATION CHECKLIST (mental check before dispatching agent tasks):
    ✓ fetch_patient_profile: patient_id available. Tool call format `fetch_patient_profile(patient_id=...)`. `team_context['retries_for_fetch_patient_profile']` managed.
    ✓ discover_trials: `team_context['patient_profile']` (dict) available. Tool call format `discover_trials(patient_profile=...)`. `team_context['retries_for_discover_trials']` managed.
    ✓ analyze_trial_match: `team_context['patient_profile']` (dict) AND a `current_trial` (dict) available. Tool call format `analyze_trial_match(patient_profile=..., trial=...)`. `team_context['retries_for_analyze_trial_TRIALID']` managed per trial.

    REMEMBER: Your final output from the team's entire run must be a single, valid JSON string.
    The `team_context` (also known as session_state for the team) is your primary way to manage state between steps, including retry counts.
""")


# --- Define Clinical Trial Matching Workflow using a Team ---
class ClinicalTrialMatchingWorkflow(Workflow):
    description: str = "Orchestrates a team of agents to find clinical trial matches for a patient."

    # Define agents as class attributes or initialize in __init__
    patient_profiler_agent: Agent
    trial_discoverer_agent: Agent
    trial_analyzer_agent: Agent
    clinical_trial_matching_team: Team

    def __init__(self, **kwargs):
        super().__init__(**kwargs) # Pass workflow-specific args like session_id, storage, debug_mode
        
        self.patient_profiler_agent = Agent(
            name="PatientProfilerAgent",
            role="Responsible for fetching and validating a patient's medical profile using their ID.",
            model=common_llm_config,
            tools=[fetch_patient_profile],
            # session_state for agent can be used if tool needs it, team manages broader context
            add_name_to_instructions=True, 
            instructions="Use the patient_id provided in the task to fetch the patient's profile.",
        )

        self.trial_discoverer_agent = Agent(
            name="TrialDiscovererAgent",
            role="Discovers potentially relevant clinical trials based on a patient's primary condition.",
            model=common_llm_config,
            tools=[discover_trials],
            add_name_to_instructions=True,
            instructions="Given a patient profile (especially the 'condition'), find suitable recruiting clinical trials.",
        )

        self.trial_analyzer_agent = Agent(
            name="TrialAnalyzerAgent",
            role="Performs in-depth analysis of a specific clinical trial against a patient's detailed profile.",
            model=common_llm_config, 
            tools=[analyze_trial_match],
            add_name_to_instructions=True,
            instructions="Given a patient profile and a single clinical trial's details, analyze them meticulously for a match.",
        )

        self.clinical_trial_matching_team = Team(
            name="ClinicalTrialMatchingTeamOrchestrator",
            mode="collaborate", 
            model=team_llm_config, # Team's own LLM for orchestration
            members=[
                self.patient_profiler_agent,
                self.trial_discoverer_agent,
                self.trial_analyzer_agent,
            ],
            instructions=TEAM_INSTRUCTIONS,
            success_criteria="A valid JSON string representing matches, no matches, or a specific error type is produced.",            # Team-level session_state for context shared among members, managed by team LLM
            # This state is reset or managed per team run.
            # Workflow's session_state is for caching results of team.run() or other workflow steps.
            session_state={ 
                "patient_profile": None,
                "trials": None,
                "analysis_results": [],
                "patient_id": None,  # Added for context sharing
                "state": {}  # Required for set_shared_context
            },
            show_tool_calls=True, 
            show_members_responses=True, 
            add_datetime_to_instructions=True, # Can be useful for logging/tracing
            enable_agentic_context=True, # Crucial for team_context management by the orchestrator
            share_member_interactions=True,
            markdown=False, # Ensure outputs are clean JSON strings as per instructions
            debug_mode=self.debug_mode # Inherit from workflow debug_mode
        )

    def _get_cached_final_result(self, patient_id: str) -> Optional[Any]:
        key = f"final_team_result_for_{patient_id}"
        data = self.session_state.get(key)
        if data:
            logger.debug(f"Workflow cache hit for key: {key}")
            return data
        logger.debug(f"Workflow cache miss for key: {key}")
        return None

    def _add_cached_final_result(self, patient_id: str, data: Any):
        key = f"final_team_result_for_{patient_id}"
        logger.debug(f"Workflow caching final team result for key: {key}")
        self.session_state[key] = data    # Synchronous run method, as per TeamWorkflow example
    def run(
        self,
        patient_id: str,
        use_overall_cache: bool = True
    ) -> Iterator[RunResponse]:
        logger.info(f"Workflow.run starting for patient_id: {patient_id}")
        
        # Since we can't do async operations in a sync method,
        # we need to wrap the async call in an event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._arun(patient_id, use_overall_cache))
            yield result
        finally:
            loop.close()

    async def _arun(
        self,
        patient_id: str,
        use_overall_cache: bool = True
    ) -> RunResponse:
        if use_overall_cache:
            cached_result = self._get_cached_final_result(patient_id)
            if cached_result is not None:
                logger.info(f"Returning cached final result from workflow for patient {patient_id}")
                # The cached result is already the final string or list we expect
                return RunResponse(content=cached_result, event="success", run_id=self.run_id)
          # Reset relevant parts of team's session_state before a run if necessary,
        # or ensure team instructions handle starting fresh for a new patient_id.
        # For this setup, the TEAM_INSTRUCTIONS imply a fresh start based on patient_id.
        self.clinical_trial_matching_team.session_state.update({
            "patient_profile": None,
            "trials": None,
            "analysis_results": [],
            "patient_id": patient_id,  # Set current patient_id for context
            "state": {}  # Reset shared state
        })

        team_initial_message = f"Find clinical trial matches for patient ID: {patient_id}. Adhere strictly to outputting only a valid JSON string as your entire response."
        
        logger.debug(f"Calling team.arun() with message: \"{team_initial_message}\"")
        
        # Team.arun() is asynchronous. It orchestrates its async members/tools internally.
        # It should return a RunResponse object where .content is the final string.
        team_response_object: Optional[RunResponse] = await self.clinical_trial_matching_team.arun(team_initial_message)

        final_content_for_client: Union[List[Dict[str,Any]], str] = "WORKFLOW_ERROR_TEAM_NO_VALID_RESPONSE"
        response_event = "failure"

        if team_response_object and team_response_object.content:
            raw_team_output = team_response_object.content
            logger.info(f"Raw output from team.arun() for {patient_id}: {raw_team_output}")
            try:
                # Team is instructed to return a JSON string
                parsed_json_output = json.loads(raw_team_output)
                # This could be a list of matches or a dict representing an error from the team
                final_content_for_client = parsed_json_output 
                response_event = "success"
                logger.info(f"Successfully parsed team output as JSON for {patient_id}.")
            except json.JSONDecodeError:
                # If it's not JSON, it might be a direct error string (though instructions say JSON string)
                # Or it's malformed.
                final_content_for_client = f"TEAM_OUTPUT_NOT_JSON: {raw_team_output}"
                logger.warning(f"Team output for {patient_id} was not valid JSON, treating as error string.")
                # Keep as failure unless specific error strings are expected to be success
        else:
            logger.error(f"Team returned no content or no response object for {patient_id}.")
            final_content_for_client = "ERROR_TEAM_NO_CONTENT"
            # response_event remains failure

        if use_overall_cache and response_event == "success":
             self._add_cached_final_result(patient_id, final_content_for_client)

        return RunResponse(content=final_content_for_client, event=response_event, run_id=self.run_id)
        

# --- Main function to run the workflow (FastAPI endpoint context) ---
async def run_trial_matching_workflow(patient_id: str) -> Union[List[Dict[str, Any]], str]:
    logger.info(f"run_trial_matching_workflow (async wrapper) for patient: {patient_id}")

    workflow_session_id = f"trial_matching_workflow_for_{patient_id}" # Unique per patient for caching
    
    # Initialize workflow (debug_mode can be passed here)
    trial_matcher_workflow = ClinicalTrialMatchingWorkflow(
        session_id=workflow_session_id,
        debug_mode=os.getenv("DEBUG_MODE", "false").lower() == "true"
    )
    
    final_output: Union[List[Dict[str, Any]], str] = "WORKFLOW_ERROR_NO_FINAL_OUTPUT_FROM_ASYNC_WRAPPER" 

    try:
        # Now we can directly await the _arun method
        final_event_response = await trial_matcher_workflow._arun(
            patient_id=patient_id, 
            use_overall_cache=True
        )
        
        if final_event_response:
            if final_event_response.event == "success":
                final_output = final_event_response.content
                logger.info(f"Workflow for {patient_id} completed.")
            else: # Failed or other
                final_output = final_event_response.content if isinstance(final_event_response.content, str) else "WORKFLOW_FAILED_UNKNOWN_FORMAT"
                logger.error(f"Workflow for {patient_id} did not complete successfully. Status: {final_event_response.event}, Content: {final_output}")
        else:
            final_output = "WORKFLOW_ERROR_NO_RESPONSE"
            logger.error(f"Workflow for {patient_id} yielded no response object.")
        
        return final_output

    except Exception as e:
        error_message = f"WORKFLOW_UNHANDLED_EXCEPTION: {str(e)}"
        logger.error(f"Unhandled error in run_trial_matching_workflow for {patient_id}: {e}", exc_info=True)
        return error_message

# --- Example Usage (if running this script directly) ---
async def main():
    test_patient_ids = ["PATIENT_001", "PATIENT_002", "PATIENT_003", "PATIENT_NO_MATCH", "PATIENT_ERROR"]
    # test_patient_ids = ["PATIENT_001"] 

    for p_id in test_patient_ids:
        print(f"\n--- Running workflow for Patient ID: {p_id} ---")
        result = await run_trial_matching_workflow(p_id)
        # Output will be a list (matches/empty) or an error string/dict.
        if isinstance(result, (list, dict)):
            print(f"Result for {p_id} (1st run): {json.dumps(result, indent=2)}")
        else:
            print(f"Result for {p_id} (1st run): {result}")


        # Second run (should use workflow-level cache if enabled and available for the final result)
        print(f"\n--- Running workflow for Patient ID: {p_id} (AGAIN to test cache) ---")
        result_cached = await run_trial_matching_workflow(p_id)
        if isinstance(result_cached, (list, dict)):
             print(f"Result for {p_id} (2nd run): {json.dumps(result_cached, indent=2)}")
        else:
            print(f"Result for {p_id} (2nd run): {result_cached}")


if __name__ == "__main__":
    # Run the main function to execute the workflow for test patients
    asyncio.run(main())