import sys
import os
import subprocess
from dotenv import load_dotenv

# Ensure we can import from the current directory if run from 'execution'
# OR from 'execution' subdirectory if run from root.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

# Add execution dir to path so imports work
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Load env vars from project root .env if it exists, or execution/.env
load_dotenv(os.path.join(project_root, ".env"))
load_dotenv(os.path.join(current_dir, ".env"))

try:
    from airtable_client import get_airtable_table
    from agent_orchestrator import run_automation_for_jobseeker
except ImportError as e:
    print(f"Import Error: {e}")
    print(f"sys.path: {sys.path}")
    sys.exit(1)

def main():
    # 1. Clean up existing browser sessions
    print("Closing any existing agent-browser sessions...")
    subprocess.run(["agent-browser", "close"], check=False)

    # 2. Configure Headed Mode for visibility
    os.environ["AGENT_BROWSER_HEADED"] = "true"
    print("Enabled HEADED mode. A browser window should appear.")

    # 3. Fetch the specific JobSeeker
    target_id = "recfV7X8d6XccguoL"
    print(f"Fetching JobSeeker record: {target_id}...")
    
    try:
        table = get_airtable_table()
        record = table.get(target_id)
        fields = record["fields"]
        
        jobseeker = {
            "id": record["id"],
            "name": fields.get("Name", "Unknown"),
            "targetTitles": fields.get("TargetTitles", ""),
            "targetGeos": fields.get("TargetGeos", ""),
            "seniority": fields.get("Seniority", ""),
            "excludeKeywords": fields.get("ExcludeKeywords", ""),
            "targetIndustries": fields.get("TargetIndustries", ""),
            "includeKeywords": fields.get("IncludeKeywords", ""),
            "notesForCoach": fields.get("NotesForCoach", "")
        }
        
        print(f"Successfully loaded data for: {jobseeker['name']}")
        
    except Exception as e:
        print(f"Failed to fetch record from Airtable: {e}")
        print("Please check your AIRTABLE_API_KEY and Base ID in .env")
        return

    # 4. Run Automation
    print("\nStarting Automation Loop...")
    print("---------------------------------------------------")
    try:
        result = run_automation_for_jobseeker(jobseeker)
        print("\n---------------------------------------------------")
        print("✅ Automation completed successfully!")

        # Display enrichment results
        if isinstance(result, dict):
            profiles = result.get("profiles_triggered", 0)
            enrichment_started = result.get("enrichment_started", False)
            print(f"\n📊 Enrichment Results:")
            print(f"   - Profiles triggered: {profiles}")
            print(f"   - Enrichment started: {'✅ Yes' if enrichment_started else '❌ No'}")
        else:
            print("\n⚠️  Legacy return type (boolean) - enrichment data not available")

    except Exception as e:
        print("\n---------------------------------------------------")
        print(f"❌ Automation failed: {e}")

if __name__ == "__main__":
    main()
