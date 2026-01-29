import os
import subprocess
import json
import logging
import time
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from google.api_core.exceptions import ResourceExhausted

# Vertex AI imports
import vertexai
from vertexai.generative_models import GenerativeModel, Part

# Valid LOG LEVELS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
REGION = os.getenv("GCP_REGION", "us-central1")
MAX_TURNS = 30  # Increased limit for complex filter flows

@retry(
    retry=retry_if_exception_type(ResourceExhausted),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=5, max=60)
)
def call_with_retry(func, *args, **kwargs):
    return func(*args, **kwargs)

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
        
        # Original field substitutions
        text = template.replace("{{targetTitles}}", str(context.get("targetTitles", "")))
        text = text.replace("{{targetGeos}}", str(context.get("targetGeos", "")))
        text = text.replace("{{seniority}}", str(context.get("seniority", "")))
        text = text.replace("{{excludeKeywords}}", str(context.get("excludeKeywords", "")))
        
        # AI-interpreted criteria substitutions (Phase 3)
        text = text.replace("{{ai_titles}}", json.dumps(context.get("ai_titles", [])))
        text = text.replace("{{ai_locations}}", json.dumps(context.get("ai_locations", [])))
        text = text.replace("{{ai_seniority}}", json.dumps(context.get("ai_seniority", [])))
        text = text.replace("{{ai_industries}}", json.dumps(context.get("ai_industries", [])))
        text = text.replace("{{ai_excludeKeywords}}", json.dumps(context.get("ai_excludeKeywords", [])))
        text = text.replace("{{ai_confidence}}", str(context.get("ai_confidence", "unknown")))
        text = text.replace("{{ai_reasoning}}", str(context.get("ai_reasoning", "")))
        
        text = text.replace("{{ai_reasoning}}", str(context.get("ai_reasoning", "")))
        
        # Credentials (Phase 3 fallback)
        text = text.replace("{{clay_email}}", str(context.get("clay_email", "")))
        text = text.replace("{{clay_password}}", str(context.get("clay_password", "")))
        
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

def parse_ref(snapshot: str, element_label: str) -> str:
    """Parse snapshot text to find ref (e.g., 'e5') for a given element label."""
    if not snapshot:
        return None
    for line in snapshot.split('\n'):
        if element_label.lower() in line.lower():
            # Format: - textbox "email address" [ref=e2]
            parts = line.split('[ref=')
            if len(parts) > 1:
                return parts[1].split(']')[0]
    return None

def perform_login() -> bool:
    """
    Deterministic login flow using the proven test_clay_auth pattern.
    Returns True on success, raises Exception on failure.
    """
    email = os.getenv("CLAY_EMAIL")
    password = os.getenv("CLAY_PASSWORD")
    
    if not email or not password:
        logger.error("CLAY_EMAIL or CLAY_PASSWORD not set in environment")
        raise ValueError("CLAY_EMAIL or CLAY_PASSWORD not set in environment")
    
    # STEP 1: Open login page + LONG WAIT (React app render)
    logger.info("Login Step 1: Opening login page...")
    run_agent_browser_command(["open", "https://app.clay.com/login"])
    time.sleep(15)
    
    # STEP 2: Snapshot + Fill Email
    logger.info("Login Step 2: Filling email...")
    snapshot = run_agent_browser_command(["snapshot"])
    email_ref = parse_ref(snapshot, 'textbox "email address"')
    
    if not email_ref:
        logger.error(f"Could not find email field. Snapshot preview: {snapshot[:500]}")
        raise Exception("Could not find email field")
    
    run_agent_browser_command(["fill", f"@{email_ref}", email])
    
    # STEP 3: Click Continue (NOT press Enter)
    cont_ref = parse_ref(snapshot, 'button "Continue"')
    if cont_ref:
        logger.info(f"Clicking Continue (@{cont_ref})...")
        run_agent_browser_command(["click", f"@{cont_ref}"])
    else:
        logger.info("No Continue button found in snapshot, pressing Enter...")
        run_agent_browser_command(["press", "Enter"])
    
    time.sleep(10)  # Wait for password screen
    
    # STEP 4: Snapshot + Fill Password
    logger.info("Login Step 4: Filling password...")
    pass_snapshot = run_agent_browser_command(["snapshot"])
    pass_ref = parse_ref(pass_snapshot, 'textbox "password"')
    
    if not pass_ref:
        # Retry once after 5s
        logger.info("Password field not found, waiting 5s for retry...")
        time.sleep(5)
        pass_snapshot = run_agent_browser_command(["snapshot"])
        pass_ref = parse_ref(pass_snapshot, 'textbox "password"')
    
    if not pass_ref:
        logger.error(f"Could not find password field after retry. Snapshot preview: {pass_snapshot[:500]}")
        raise Exception("Could not find password field after retry")
    
    run_agent_browser_command(["fill", f"@{pass_ref}", password])
    
    # STEP 5: Click Continue
    cont_ref_2 = parse_ref(pass_snapshot, 'button "Continue"')
    if cont_ref_2:
        logger.info(f"Clicking Continue (@{cont_ref_2})...")
        run_agent_browser_command(["click", f"@{cont_ref_2}"])
    else:
        logger.info("No Continue button found for password, pressing Enter...")
        run_agent_browser_command(["press", "Enter"])
    
    time.sleep(25)  # Wait for heavy redirect/security check
    
    # STEP 6: Verify success
    logger.info("Login Step 6: Verifying login success...")
    final_snapshot = run_agent_browser_command(["snapshot"])
    current_url = run_agent_browser_command(["get", "url"]).strip()
    
    if "login" in current_url.lower() or "Welcome back" in final_snapshot:
        logger.error(f"Login failed - still on login page. URL: {current_url}")
        raise Exception("Login failed - still on login page")
    
    logger.info(f"Login successful! Current URL: {current_url}")
    return True

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
    logger.info("Starting Clay auth test with deterministic login fallback...")
    target_url = "https://app.clay.com/workspaces/579795/w/find-people?destinationTableId=t_0t6pb5u5rFNYudNfngq&workbookId=wb_0t6pb5rpbgD8nRCHvYh"
    
    # 1. Prepare session
    run_agent_browser_command(["close"])
    time.sleep(2)
    
    # 2. Inject cookies (initial attempt)
    run_agent_browser_command(["open", "https://app.clay.com/login"])
    time.sleep(5)
    inject_cookies("session_cookies.json")
    
    # 3. Try target URL
    logger.info("Opening target URL...")
    run_agent_browser_command(["open", target_url])
    time.sleep(15) 
    
    snapshot = run_agent_browser_command(["snapshot"])
    current_url = run_agent_browser_command(["get", "url"]).strip()
    
    # 4. Fallback to deterministic login if needed
    if "login" in current_url.lower() or "Welcome back" in snapshot:
        logger.info("Session invalid. Launching deterministic login...")
        try:
            perform_login()
            # Re-open target after success
            logger.info("Re-opening target workbook URL after login...")
            run_agent_browser_command(["open", target_url])
            time.sleep(15)
            snapshot = run_agent_browser_command(["snapshot"])
            current_url = run_agent_browser_command(["get", "url"]).strip()
        except Exception as e:
            return {"status": "error", "message": f"Deterministic login failed: {e}", "url": current_url}

    # 5. Final validation
    if "workbook" in current_url.lower() or "find-people" in current_url.lower():
        return {"status": "success", "message": "Authenticated successfully", "url": current_url}
    else:
        return {"status": "error", "message": "Failed to reach target workbook", "url": current_url, "snapshot_preview": snapshot[:500]}

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

def interpret_search_criteria(jobseeker: Dict[str, Any]) -> Dict[str, Any]:
    """
    Uses Gemini to intelligently interpret raw Airtable JobSeeker data
    and generate optimized Clay search criteria.
    
    The AI considers:
    - TargetTitles: selects 3-5 most relevant
    - TargetGeos: simplifies if too many locations
    - Seniority: maps to Clay dropdown values
    - Industries: selects top 3-5
    - ExcludeKeywords: used directly
    
    Returns a dict with optimized search parameters.
    """
    logger.info(f"Interpreting search criteria for JobSeeker: {jobseeker.get('id')}")
    
    model = GenerativeModel("gemini-2.5-flash")
    
    # Build the prompt with all available JobSeeker data
    prompt = f"""You are a recruiting specialist. Analyze this JobSeeker profile and generate 
optimized search criteria for Clay.com's People Search.

JOB SEEKER DATA:
- Name: {jobseeker.get('name', 'Unknown')}
- Target Titles: {jobseeker.get('targetTitles', '')}
- Target Geos: {jobseeker.get('targetGeos', '')}
- Seniority: {jobseeker.get('seniority', '')}
- Industries: {jobseeker.get('targetIndustries', '')}
- Include Keywords: {jobseeker.get('includeKeywords', '')}
- Exclude Keywords: {jobseeker.get('excludeKeywords', '')}
- Notes: {jobseeker.get('notesForCoach', '')}

RULES:
1. Select 3-5 most relevant job titles (avoid over-filtering)
2. For geography: if >5 locations, consolidate to 2-3 primary metro areas or "United States"
3. Map seniority to Clay values: C-suite, VP, Director, Manager, Senior, Lead/Principal, Mid-Level, Entry-Level
4. Select top 3 industries if many are listed
5. Keep excludeKeywords as-is (use for job titles to exclude)
6. CRITICAL GUARDRAILS:
   - Country must match original intent (if US, don't suggest India)
   - Seniority range should be +/- 1 level from stated preference
   - Domain/industry must be relevant to stated preferences

Return ONLY valid JSON (no markdown, no explanation):
{{
  "titles": ["title1", "title2", "title3"],
  "locations": ["city1", "city2"],
  "seniority": ["VP", "Director"],
  "industries": ["Technology", "Financial Services"],
  "excludeKeywords": ["keyword1", "keyword2"],
  "confidence": "high",
  "reasoning": "Brief explanation of choices"
}}
"""
    
    try:
        response = call_with_retry(model.generate_content, prompt)
        raw_text = response.text.strip()
        
        # Clean up markdown code blocks if present
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()
        
        criteria = json.loads(raw_text)
        logger.info(f"AI interpreted criteria: {json.dumps(criteria, indent=2)}")
        
        # Validate guardrails
        if not criteria.get("titles"):
            raise ValueError("No titles generated")
        if not criteria.get("locations"):
            raise ValueError("No locations generated")
        
        return criteria
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse AI response as JSON: {e}")
        logger.error(f"Raw response: {raw_text[:500]}")
        # Fallback: use raw Airtable data directly
        return {
            "titles": jobseeker.get("targetTitles", "").split("\n")[:5],
            "locations": jobseeker.get("targetGeos", "").split("\n")[:3],
            "seniority": [jobseeker.get("seniority", "Manager")],
            "industries": jobseeker.get("targetIndustries", "").split("\n")[:3],
            "excludeKeywords": jobseeker.get("excludeKeywords", "").split("\n"),
            "confidence": "fallback",
            "reasoning": "AI parsing failed, using raw Airtable data"
        }
    except Exception as e:
        logger.error(f"Error interpreting criteria: {e}")
        raise

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
    time.sleep(10) # Wait for initial redirect check
    
    # Check if login is needed (cookies might have failed/expired)
    snapshot = run_agent_browser_command(["snapshot"])
    current_url = run_agent_browser_command(["get", "url"]).strip()
    
    if "login" in current_url.lower() or "Welcome back" in snapshot:
        logger.info("Login required or cookies expired. Launching deterministic login...")
        perform_login()
        # After login, re-open the target URL to ensure we are on the workbook
        logger.info("Re-opening target workbook URL after login...")
        run_agent_browser_command(["open", CLAY_URL])
        time.sleep(10)
    
    # 2. AI Interpretation of Search Criteria (Phase 3 addition)
    logger.info("Interpreting search criteria via Gemini AI...")
    search_criteria = interpret_search_criteria(jobseeker)
    logger.info(f"AI-interpreted search criteria: {json.dumps(search_criteria, indent=2)}")
    
    # Merge AI criteria with jobseeker context for directive
    jobseeker_with_criteria = {
        **jobseeker,
        "ai_titles": search_criteria.get("titles", []),
        "ai_locations": search_criteria.get("locations", []),
        "ai_seniority": search_criteria.get("seniority", []),
        "ai_industries": search_criteria.get("industries", []),
        "ai_excludeKeywords": search_criteria.get("excludeKeywords", []),
        "ai_confidence": search_criteria.get("confidence", "unknown"),
        "ai_reasoning": search_criteria.get("reasoning", ""),
        # Credentials for fallback login
        "clay_email": os.getenv("CLAY_EMAIL", ""),
        "clay_password": os.getenv("CLAY_PASSWORD", "")
    }

    
    # 3. Load Directive with AI-enhanced context
    # Fixed path: assume running from project root or ensure path exists
    directive_path = "directives/clay_directive.md"
    if not os.path.exists(directive_path):
        directive_path = "execution/clay_directive.md" # Fallback checks
    
    directive_text = load_directive(directive_path, jobseeker_with_criteria)
    
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
{{"type": "press", "key": "Enter", "reason": "Use for Enter, Escape, or other keys"}}
{{"type": "done", "reason": "why"}}
{{"type": "fail", "reason": "why"}}
"""
        try:
            response = call_with_retry(chat.send_message, prompt)
        except Exception as e:
            logger.error(f"AI decision failed after retries: {e}")
            raise
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
            run_agent_browser_command(["press", "Enter"]) 
            time.sleep(1)
            
        elif action_type == "press":
            key = action.get("key", "Enter")
            run_agent_browser_command(["press", key])
            time.sleep(1)
            
        else:
            logger.warning(f"Unknown action type: {action_type}")
            
    logger.warning("Max turns reached without completion.")
    raise Exception("Timeout: Max turns reached")
