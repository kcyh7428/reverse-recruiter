import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv() # Load .env BEFORE other imports

import logging
import json
import tarfile
import io
from flask import Flask, jsonify, request, send_file
from airtable_client import get_pending_jobseekers, update_jobseeker_status
from agent_orchestrator import run_automation_for_jobseeker, test_connectivity, test_clay_access, test_clay_auth
import debug_state

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
    # Prevent concurrent runs
    status = debug_state.get_status()
    if status["status"] == "running":
        return jsonify({"error": "Automation already running", "status": status}), 409

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
            # Capture result dict instead of boolean
            result = run_automation_for_jobseeker(js)

            # Extract profile count and timestamp
            profiles_triggered = result.get("profiles_triggered", 0) if isinstance(result, dict) else 0
            completed_at = datetime.now().isoformat()

            # Update Airtable with status + profiles + timestamp
            update_jobseeker_status(
                js_id,
                "✅ Ready to Launch",
                profiles_sent=profiles_triggered,
                completed_at=completed_at
            )

            results.append({
                "id": js_id,
                "status": "success",
                "profiles": profiles_triggered,
                "completed_at": completed_at
            })

            logger.info(f"[SUCCESS] {js_id} | Profiles triggered: {profiles_triggered}")

        except Exception as e:
            logger.error(f"Error processing {js_id}: {e}")
            update_jobseeker_status(js_id, "Error - Automation Failed", error_message=str(e))
            results.append({"id": js_id, "status": "error", "error": str(e)})
            
    return jsonify({"processed": len(results), "details": results}), 200

# --- Debug Dashboard Endpoints ---

@app.route("/debug/status", methods=["GET"])
def debug_status():
    """Current run status, turn number, last action, last error."""
    return jsonify(debug_state.get_status()), 200

@app.route("/debug/screenshot", methods=["GET"])
def debug_screenshot_latest():
    """Serve the latest screenshot (most recent turn)."""
    status = debug_state.get_status()
    current_turn = status["current_turn"]
    if current_turn == 0:
        return jsonify({"error": "No run in progress"}), 404
    # Walk backward to find the most recent screenshot
    for t in range(current_turn, 0, -1):
        path = debug_state.screenshot_path(t)
        if os.path.exists(path):
            return send_file(path, mimetype="image/png")
    return jsonify({"error": "No screenshots available"}), 404

@app.route("/debug/screenshot/<int:turn>", methods=["GET"])
def debug_screenshot_turn(turn):
    """Serve screenshot for a specific turn."""
    path = debug_state.screenshot_path(turn)
    if os.path.exists(path):
        return send_file(path, mimetype="image/png")
    return jsonify({"error": f"No screenshot for turn {turn}"}), 404

@app.route("/debug/screenshot/<path:name>", methods=["GET"])
def debug_screenshot_named(name):
    """Serve screenshot by descriptive name (e.g., filter_01_seniority)."""
    path = debug_state.named_screenshot_path(name)
    if os.path.exists(path):
        return send_file(path, mimetype="image/png")
    # Try with .png extension stripped
    if name.endswith('.png'):
        path2 = debug_state.named_screenshot_path(name[:-4])
        if os.path.exists(path2):
            return send_file(path2, mimetype="image/png")
    return jsonify({"error": f"No screenshot named '{name}'"}), 404

@app.route("/debug/screenshots", methods=["GET"])
def debug_screenshot_list():
    """List all available screenshots."""
    screenshots = debug_state.list_screenshots()
    return jsonify({"screenshots": screenshots, "count": len(screenshots)}), 200

@app.route("/debug/history", methods=["GET"])
def debug_history():
    """Full turn-by-turn history with actions, results, errors, and screenshot URLs."""
    history = debug_state.get_history()
    status = debug_state.get_status()
    return jsonify({"run": status, "turns": history}), 200

@app.route("/debug/download", methods=["GET"])
def debug_download():
    """Download a tar.gz bundle of all screenshots + JSON log."""
    history = debug_state.get_history()
    status = debug_state.get_status()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Add JSON log
        log_data = json.dumps({"run": status, "turns": history}, indent=2).encode("utf-8")
        log_info = tarfile.TarInfo(name="debug_log.json")
        log_info.size = len(log_data)
        tar.addfile(log_info, io.BytesIO(log_data))

        # Add ALL screenshots from the debug directory (turns + named filter screenshots)
        added = set()
        for f in debug_state.list_screenshots():
            fpath = os.path.join(debug_state.SCREENSHOT_DIR, f)
            if os.path.exists(fpath) and f not in added:
                tar.add(fpath, arcname=f"screenshots/{f}")
                added.add(f)

    buf.seek(0)
    record_id = status.get("record_id", "unknown")
    ts = (status.get("started_at") or "unknown").replace(":", "-")
    filename = f"debug_{record_id}_{ts}.tar.gz"
    return send_file(buf, mimetype="application/gzip", as_attachment=True, download_name=filename)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
