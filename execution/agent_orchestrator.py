import os
import subprocess
import json
import logging
import time
from typing import Dict, Any

# Vertex AI imports
import vertexai
from vertexai.generative_models import GenerativeModel, Part

# Valid LOG LEVELS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REGION = os.getenv("GCP_REGION", "us-central1")
MAX_TURNS = 15  # Limit safety against infinite loops

try:
    vertexai.init(project=PROJECT_ID, location=REGION)
except Exception:
    logger.warning("Vertex AI init failed. Ensure GCP credentials are correct (Workload Identity).")

# Ensure all agent-browser calls share the same session context for cookie persistence
os.environ["AGENT_BROWSER_SESSION"] = "clay_automation_session"

# Phase 3: Stealth Mode - Hide automation fingerprints
# --disable-blink-features=AutomationControlled hides navigator.webdriver
os.environ["AGENT_BROWSER_ARGS"] = "--no-sandbox,--disable-blink-features=AutomationControlled,--disable-infobars"
os.environ["AGENT_BROWSER_USER_AGENT"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"

def load_directive(file_path: str, context: Dict[str, Any]) -> str:
    """Reads the directive markdown and substitutes placeholders."""
    try:
        with open(file_path, "r") as f:
            template = f.read()
        
        # Simple substitution
        text = template.replace("{{targetTitles}}", str(context.get("targetTitles", "")))
        text = text.replace("{{targetGeos}}", str(context.get("targetGeos", "")))
        text = text.replace("{{seniority}}", str(context.get("seniority", "")))
        text = text.replace("{{excludeKeywords}}", str(context.get("excludeKeywords", "")))
        return text
    except FileNotFoundError:
        logger.error(f"Directive file not found: {file_path}")
        return "ERROR: Directive Missing"

def run_agent_browser_command(args: list) -> str:
    """Runs a subcommand of the agent-browser CLI."""
    try:
        # Full command: agent-browser <args>
        cmd = ["agent-browser"] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            logger.error(f"Command failed: {cmd}\nStderr: {result.stderr}\nStdout: {result.stdout}")
            return f"Error: {result.stderr} | {result.stdout}"
        return result.stdout
    except Exception as e:
        logger.error(f"Command exception: {e}")
        return str(e)

def test_connectivity() -> Dict[str, Any]:
    """Isolates network/rendering issues by visiting a tiny site."""
    logger.info("Starting connectivity test to example.com...")
    
    # 1. Open example.com
    open_res = run_agent_browser_command(["open", "http://example.com"])
    
    # 2. Take a snapshot to see if it renders
    snapshot_res = run_agent_browser_command(["snapshot"])
    
    # 3. Check for specific text
    if "Example Domain" in snapshot_res:
        return {
            "status": "success",
            "message": "Internet connection verified. Browser reached example.com successfully.",
            "snapshot_length": len(snapshot_res)
        }
    else:
        return {
            "status": "error",
            "message": "Connected but snapshot was empty or incorrect.",
            "raw_output": snapshot_res[:500]
        }

def test_clay_access() -> Dict[str, Any]:
    """Tests if we can reach Clay's login page and gathers diagnostics."""
    logger.info("Starting Clay access test with diagnostics...")
    
    # 1. Open the login page
    run_agent_browser_command(["open", "https://app.clay.com/login"])
    time.sleep(15)  # Give it significantly more time to render (heavy React app)
    
    # 2. Check for bot detection via navigator.webdriver
    # agent-browser eval returns the result of the JS execution
    webdriver_res = run_agent_browser_command(["eval", "navigator.webdriver"])
    is_automated = "true" in webdriver_res.lower()
    
    # 3. Take a snapshot
    snapshot_res = run_agent_browser_command(["snapshot"])
    
    # 4. Take a screenshot (agent-browser saves it to a file or returns buffer info)
    # We'll try to trigger a screenshot. If the CLI saves to a default path, we'll look for it.
    screenshot_res = run_agent_browser_command(["screenshot", "diagnostics/clay_diag.png"])
    
    return {
        "status": "success" if ("Clay" in snapshot_res or "Sign in" in snapshot_res) else "error",
        "bot_detected": is_automated,
        "webdriver_val": webdriver_res.strip(),
        "snapshot_preview": snapshot_res[:200],
        "screenshot_info": screenshot_res.strip()
    }

def test_clay_auth() -> Dict[str, Any]:
    """Tests if cookies correctly grant access to the workbook, and falls back to login if needed."""
    logger.info("Starting Clay auth test with auto-login fallback...")
    target_url = "https://app.clay.com/workspaces/579795/w/find-people?destinationTableId=t_0t6pb5u5rFNYudNfngq&workbookId=wb_0t6pb5rpbgD8nRCHvYh"
    
    # 1. Close any existing daemon to ensure stealth args apply
    run_agent_browser_command(["close"])
    time.sleep(2)
    
    # 2. Open login page
    logger.info("Opening login page...")
    run_agent_browser_command(["open", "https://app.clay.com/login"])
    time.sleep(15)
    
    # 3. Inject cookies after opening page (to have domain context)
    inject_cookies("session_cookies.json")
    
    # 4. Try to open target URL (might already be logged in if cookies worked)
    logger.info("Opening target URL...")
    run_agent_browser_command(["open", target_url])
    time.sleep(15) 
    
    snapshot_res = run_agent_browser_command(["snapshot"])
    current_url = run_agent_browser_command(["get", "url"]).strip()
    
    # Check if we are on the login page or session expired
    if "Welcome back" in snapshot_res or "expired=true" in current_url:
        logger.info("Session expired or not found. Attempting Auto-Login...")
        
        email = os.getenv("CLAY_EMAIL")
        password = os.getenv("CLAY_PASSWORD")
        
        if not email or not password:
            return {"status": "error", "message": "Credentials missing in ENV", "url": current_url}

        # Step 1: Email
        # Find ref for email textbox
        email_ref = None
        for line in snapshot_res.split('\n'):
            if 'textbox "email address"' in line:
                # Format: - textbox "email address" [ref=e2]
                parts = line.split('[ref=')
                if len(parts) > 1:
                    email_ref = parts[1].split(']')[0]
                    break
        
        if email_ref:
            logger.info(f"Filling email: {email} into {email_ref}")
            run_agent_browser_command(["fill", f"@{email_ref}", email])
            # Find ref for Continue button
            cont_ref = None
            for line in snapshot_res.split('\n'):
                if 'button "Continue"' in line:
                    parts = line.split('[ref=')
                    if len(parts) > 1:
                        cont_ref = parts[1].split(']')[0]
                        break
            if cont_ref:
                run_agent_browser_command(["click", f"@{cont_ref}"])
            else:
                run_agent_browser_command(["press", "Enter"])
        else:
            return {"status": "error", "message": "Could not find email field", "snapshot": snapshot_res[:500]}
            
        time.sleep(8)
        
        # Step 2: Password
        login_snap = run_agent_browser_command(["snapshot"])
        pass_ref = None
        for line in login_snap.split('\n'):
            if 'textbox "password"' in line:
                parts = line.split('[ref=')
                if len(parts) > 1:
                    pass_ref = parts[1].split(']')[0]
                    break
        
        if pass_ref:
            logger.info(f"Filling password into {pass_ref}...")
            run_agent_browser_command(["fill", f"@{pass_ref}", password])
            # Click Continue again
            cont_ref_2 = None
            for line in login_snap.split('\n'):
                if 'button "Continue"' in line:
                    parts = line.split('[ref=')
                    if len(parts) > 1:
                        cont_ref_2 = parts[1].split(']')[0]
                        break
            if cont_ref_2:
                run_agent_browser_command(["click", f"@{cont_ref_2}"])
            else:
                run_agent_browser_command(["press", "Enter"])
        else:
            return {"status": "error", "message": "Could not find password field", "snapshot": login_snap[:500]}

        time.sleep(25) # Wait for heavy redirect/security check
        
        # Step 3: Verification
        final_snap = run_agent_browser_command(["snapshot"])
        current_url = run_agent_browser_command(["get", "url"]).strip()
        
        if "Verify your email" in final_snap or "verify-your-email" in current_url:
            logger.info("SECURITY CHECK: 'Verify your email' page detected.")
            run_agent_browser_command(["screenshot", "diagnostics/clay_verify_page.png"])
            
            # Find Resend ref
            resend_ref = None
            for line in final_snap.split('\n'):
                if 'Resend verification link' in line:
                    parts = line.split('[ref=')
                    if len(parts) > 1:
                        resend_ref = parts[1].split(']')[0]
                        break
            
            if resend_ref:
                logger.info(f"Clicking 'Resend verification link' (@{resend_ref}) to trigger email...")
                run_agent_browser_command(["click", f"@{resend_ref}"])
            
            logger.info("Email triggered. Waiting 60s for user to verify via email...")
            time.sleep(60)

    # 4. Final Verification
    final_snap = run_agent_browser_command(["snapshot"])
    run_agent_browser_command(["screenshot", "diagnostics/clay_final_auth.png"])
    
    is_logged_in = "Welcome" not in final_snap and ("Search" in final_snap or "Find" in final_snap)
    
    return {
        "status": "success" if is_logged_in else "error",
        "logged_in": is_logged_in,
        "url": run_agent_browser_command(["get", "url"]).strip(),
        "snapshot_preview": final_snap[:500]
    }

def inject_cookies(file_path: str):
    """Loads cookies from JSON and injects them into agent-browser."""
    try:
        if not os.path.exists(file_path):
            logger.warning(f"Cookie file not found at {file_path}, skipping injection.")
            return

        with open(file_path, "r") as f:
            cookies = json.load(f)
        
        logger.info("Clearing existing cookies...")
        run_agent_browser_command(["cookies", "clear"])
        
        logger.info(f"Injecting {len(cookies)} cookies...")
        for c in cookies:
            name = c.get("name")
            value = c.get("value")
            if name and value:
                # Command: agent-browser cookies set <name> <value>
                run_agent_browser_command(["cookies", "set", name, value])
        logger.info("Cookie injection complete.")
    except Exception as e:
        logger.error(f"Failed to inject cookies: {e}")

def run_automation_for_jobseeker(jobseeker: Dict[str, Any]):
    """
    Main agent loop for a single job seeker.
    """
    logger.info(f"Starting automation for JobSeeker: {jobseeker.get('id')}")
    
    # 1. Initialize Browser & Session
    CLAY_URL = "https://app.clay.com/workspaces/579795/w/find-people?destinationTableId=t_0t6pb5u5rFNYudNfngq&workbookId=wb_0t6pb5rpbgD8nRCHvYh"
    
    # Sequence: 
    # 1. Open target URL (establishes domain app.clay.com)
    # 2. Inject cookies
    # 3. Open target URL again (now authenticated)
    
    logger.info("Opening target URL to establish domain context...")
    run_agent_browser_command(["open", CLAY_URL])
    
    inject_cookies("session_cookies.json")
    
    # DEBUG: Check if cookies are set
    cookies_check = run_agent_browser_command(["cookies"])
    logger.info(f"Current Browser Cookies: {cookies_check}")
    
    logger.info("Re-opening target URL with cookies...")
    run_agent_browser_command(["open", CLAY_URL])
    
    # 2. Load Directive
    directive_text = load_directive("clay_directive.md", jobseeker)
    
    # 3. Initialize Model
    model = GenerativeModel("gemini-2.5-flash") # Upgraded to 2.5 Flash as requested (Verified)
    chat = model.start_chat()
    
    # 4. Loop
    turn = 0
    while turn < MAX_TURNS:
        turn += 1
        logger.info(f"Turn {turn}: Snapshotting...")
        
        # Observe
        snapshot_json = run_agent_browser_command(["snapshot", "--json"])
        
        # Check for hard failure in snapshot to avoid infinite loop
        if snapshot_json.startswith("Error:"):
             logger.error(f"Snapshot failed: {snapshot_json}")
             raise Exception(f"Browser Snapshot Failed: {snapshot_json}")
        
        # Think
        prompt = f"""
{directive_text}

---
CURRENT PAGE STATE (JSON Snapshot):
{snapshot_json}

INSTRUCTIONS:
Decide the next action based on the Directive and current state.
Return ONLY a JSON object with one of these structures:
{{"type": "click", "element_id": "@eX", "reason": "why"}}
{{"type": "fill", "element_id": "@eX", "value": "text", "reason": "why"}}
{{"type": "done", "reason": "why"}}
{{"type": "fail", "reason": "why"}}
"""
        response = chat.send_message(prompt)
        raw_text = response.text.strip()
        
        # Clean up markdown code blocks if present
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:-3].strip()
        elif raw_text.startswith("```"):
            raw_text = raw_text[3:-3].strip()
            
        logger.info(f"Agent Decision: {raw_text}")
        
        try:
            action = json.loads(raw_text)
        except json.JSONDecodeError:
            logger.error("Failed to parse agent JSON. Retrying...")
            continue
            
        # Act
        action_type = action.get("type")
        if action_type == "snapshot":
             logger.info("Agent requested explicit snapshot.")
             continue # Loop will take a new snapshot at start of next turn

        elif action_type == "done":
            logger.info("Agent signaled completion.")
            return True
        elif action_type == "fail":
            logger.error(f"Agent reported failure: {action.get('reason')}")
            raise Exception(f"Agent Failure: {action.get('reason')}")
            
        elif action_type == "click":
            eid = action.get("element_id")
            run_agent_browser_command(["click", eid])
            time.sleep(2) # Wait for UI reaction
            
        elif action_type == "fill":
            eid = action.get("element_id")
            val = action.get("value")
            # Clear first? 'fill' usually replaces in agent-browser, but we can be safe
            run_agent_browser_command(["fill", eid, val])
            # Often need to press enter for pills
            run_agent_browser_command(["press", "Enter"]) 
            time.sleep(1)
            
        else:
            logger.warning(f"Unknown action type: {action_type}")
            
    logger.warning("Max turns reached without completion.")
    raise Exception("Timeout: Max turns reached")
