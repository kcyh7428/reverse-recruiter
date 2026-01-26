import os
from pyairtable import Api
import json

# Load env vars
AIRTABLE_API_KEY = os.getenv("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "app8KvRTUVMWeloR8")
AIRTABLE_TABLE_NAME = os.getenv("AIRTABLE_TABLE_NAME", "JobSeekers")

def inspect_schema():
    api = Api(AIRTABLE_API_KEY)
    
    # Method 1: Fetch a record to see active fields
    print("--- Fetching a sample record ---")
    try:
        table = api.table(AIRTABLE_BASE_ID, AIRTABLE_TABLE_NAME)
        records = table.all(max_records=1)
        if records:
            print("Successfully fetched a record.")
            print("Fields present:", list(records[0]['fields'].keys()))
            if 'Status' in records[0]['fields']:
                print(f"Current Status value: {records[0]['fields']['Status']}")
        else:
            print("No records found in table.")
    except Exception as e:
        print(f"Error fetching records: {e}")

    # Method 2: Attempting to infer Status options?
    # PyAirtable doesn't give schema definition (options) easily without metadata API.
    # We will try to update a test record with the target status to see if it fails.
    
    # We won't actually create a junk record to avoid pollution, 
    # but we can try to look for the user's mentioned status in existing records if any.
    
    print("\n--- Verifying Status '✅ Ready to Launch' ---")
    print("This script cannot authoritatively see 'Single Select' options via standard API without Metadata capabilities.")
    print("However, if the field is 'Single Select', Airtable API will accept new values if 'Typecast' is enabled or sometimes by default depending on permissions.")
    print("In our airtable_client.py, we are using standard .update().")
    
if __name__ == "__main__":
    inspect_schema()
