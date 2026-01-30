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

def update_jobseeker_status(record_id: str, status: str, error_message: Optional[str] = None):
    """
    Updates the status of a specific record.
    If error_message is provided, it is logged to stdout.
    Falls back to logging-only if the status value is not a valid Airtable select option.
    """
    try:
        table = get_airtable_table()
        fields = {"Status": status}
        if error_message:
            logger.error(f"Error for {record_id}: {error_message}")

        table.update(record_id, fields)
        logger.info(f"Updated record {record_id} to status: {status}")
    except Exception as e:
        error_str = str(e)
        if "INVALID_MULTIPLE_CHOICE_OPTIONS" in error_str:
            logger.warning(f"Status '{status}' is not a valid Airtable option for {record_id}. Skipping status update. Error: {error_message}")
        else:
            logger.error(f"Failed to update record {record_id}: {e}")
