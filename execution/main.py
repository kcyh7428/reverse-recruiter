import os
from dotenv import load_dotenv
load_dotenv() # Load .env BEFORE other imports

import logging
from flask import Flask, jsonify, request
from airtable_client import get_pending_jobseekers, update_jobseeker_status
from agent_orchestrator import run_automation_for_jobseeker, test_connectivity, test_clay_access, test_clay_auth

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route("/test-connectivity", methods=["GET"])
def connectivity_test():
    """Verify if the browser can reach a simple external site."""
    result = test_connectivity()
    return jsonify(result), 200

@app.route("/test-clay-access", methods=["GET"])
def clay_access_test():
    """Verify if the browser can reach clay.com without cookies."""
    result = test_clay_access()
    return jsonify(result), 200

@app.route("/test-clay-auth", methods=["GET"])
def clay_auth_test():
    """Verify if the browser can see the workspace using cookies."""
    result = test_clay_auth()
    return jsonify(result), 200

@app.route("/", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "clay-browser-automation"}), 200

@app.route("/run-automation", methods=["POST"])
def trigger_automation():
    """
    Triggered by manual POST or scheduled task.
    Fetches pending records or a specific record_id and runs the agent loop.
    """
    record_id = request.args.get("record_id")
    
    if record_id:
        logger.info(f"Targeted automation triggered for record: {record_id}")
        # Fetch single record from Airtable
        from airtable_client import get_airtable_table
        try:
            table = get_airtable_table()
            r = table.get(record_id)
            fields = r.get("fields", {})
            jobseekers = [{
                "id": r["id"],
                "name": fields.get("Name", "Unknown"),
                "targetTitles": fields.get("TargetTitles", ""),
                "targetGeos": fields.get("TargetGeos", ""),
                "seniority": fields.get("Seniority", ""),
                "excludeKeywords": fields.get("ExcludeKeywords", ""),
                "targetIndustries": fields.get("TargetIndustries", ""),
                "includeKeywords": fields.get("IncludeKeywords", ""),
                "notesForCoach": fields.get("NotesForCoach", "")
            }]
        except Exception as e:
            logger.error(f"Failed to fetch record {record_id}: {e}")
            return jsonify({"error": f"Record {record_id} not found"}), 404
    else:
        logger.info("Batch automation triggered for all pending records.")
        jobseekers = get_pending_jobseekers()
    
    if not jobseekers:
        return jsonify({"message": "No job seekers found to process."}), 200
    
    results = []
    for js in jobseekers:
        js_id = js["id"]
        try:
            run_automation_for_jobseeker(js)
            update_jobseeker_status(js_id, "✅ Ready to Launch")
            results.append({"id": js_id, "status": "success"})
        except Exception as e:
            logger.error(f"Error processing {js_id}: {e}")
            update_jobseeker_status(js_id, "Error - Automation Failed", error_message=str(e))
            results.append({"id": js_id, "status": "error", "error": str(e)})
            
    return jsonify({"processed": len(results), "details": results}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
