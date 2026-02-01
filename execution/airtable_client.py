import os
import logging
from typing import List, Dict, Optional
from pyairtable import Api

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "JobSeekers")

if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID:
    logger.warning("Airtable credentials not set. Application will fail if these are required.")

def get_airtable_table():
    api = Api(AIRTABLE_API_KEY)
    return api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)

def get_pending_jobseekers() -> List[Dict]:
    """
    Fetches records where Status is '✨ Sourcing Profiles'.
    Returns a list of dicts containing the fields needed for automation.
    """
    try:
        table = get_airtable_table()
        # Filter formula: {Status} = '✨ Sourcing Profiles'
        records = table.all(formula="{Status} = '✨ Sourcing Profiles'")
        
        jobseekers = []
        for r in records:
            fields = r.get("fields", {})
            jobseekers.append({
                "id": r["id"],  # Internal Airtable Record ID
                "name": fields.get("Name", "Unknown"),
                "targetTitles": fields.get("TargetTitles", ""),
                "targetGeos": fields.get("TargetGeos", ""),
                "seniority": fields.get("Seniority", ""),
                "excludeKeywords": fields.get("ExcludeKeywords", ""),
                "targetIndustries": fields.get("TargetIndustries", ""),
                "includeKeywords": fields.get("IncludeKeywords", ""),
                "notesForCoach": fields.get("NotesForCoach", "")
            })
        
        logger.info(f"Found {len(jobseekers)} pending job seekers.")
        return jobseekers
    except Exception as e:
        logger.error(f"Failed to fetch pending job seekers: {e}")
        return []

def update_jobseeker_status(
    record_id: str,
    status: str,
    error_message: Optional[str] = None,
    profiles_sent: Optional[int] = None,
    completed_at: Optional[str] = None
):
    """
    Updates the status of a specific record, optionally writing ProfilesSent and CompletedAt.

    Args:
        record_id: Airtable Record ID
        status: Status value (e.g., "✅ Ready to Launch")
        error_message: Optional error message (logged only)
        profiles_sent: Optional profile count to write to ProfilesSent field
        completed_at: Optional ISO 8601 timestamp to write to CompletedAt field
    """
    try:
        table = get_airtable_table()

        # Build fields dict dynamically
        fields = {"Status": status}

        if profiles_sent is not None:
            fields["ProfilesSent"] = profiles_sent
            logger.info(f"Writing ProfilesSent={profiles_sent} for {record_id}")

        if completed_at is not None:
            fields["CompletedAt"] = completed_at
            logger.info(f"Writing CompletedAt={completed_at} for {record_id}")

        if error_message:
            logger.error(f"Error for {record_id}: {error_message}")
            # Note: ErrorNotes field not written yet (future enhancement)

        table.update(record_id, fields)
        logger.info(f"Updated record {record_id} to status: {status}")
    except Exception as e:
        error_str = str(e)
        if "INVALID_MULTIPLE_CHOICE_OPTIONS" in error_str:
            logger.warning(f"Status '{status}' is not a valid Airtable option for {record_id}. Skipping status update.")
        else:
            logger.error(f"Failed to update record {record_id}: {e}")
