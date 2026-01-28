import os
from flask import Flask, jsonify, request
from airtable_client import get_pending_jobseekers, update_jobseeker_status
from agent_orchestrator import run_automation_for_jobseeker, test_connectivity, test_clay_access, test_clay_auth

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
    Triggered by Cloud Scheduler or manual POST.
    Fetches pending records and runs the agent loop for each.
    """
    # Optional: Basic auth or header check here if needed
    
    jobseekers = get_pending_jobseekers()
    
    if not jobseekers:
        return jsonify({"message": "No pending job seekers found."}), 200
    
    results = []
    for js in jobseekers:
        js_id = js["id"]
        try:
            # Removed "Processing" update to avoid Airtable schema errors
            run_automation_for_jobseeker(js)
            update_jobseeker_status(js_id, "✅ Ready to Launch")
            results.append({"id": js_id, "status": "success"})
        except Exception as e:
            # Just log the error, don't try to update Status to "Error" (doesn't exist)
            print(f"Error processing {js_id}: {e}")
            results.append({"id": js_id, "status": "error", "error": str(e)})
            
    return jsonify({"processed": len(results), "details": results}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
