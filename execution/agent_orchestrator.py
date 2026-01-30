import os
import subprocess
import json
import logging
import time
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI

# Valid LOG LEVELS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_TURNS = 60  # Increased limit for complex filter flows

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=5, max=60))
def call_with_retry(func, *args, **kwargs):
    return func(*args, **kwargs)

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Ensure all agent-browser calls share the same session context for cookie persistence
os.environ["AGENT_BROWSER_SESSION"] = "clay_automation_session"

# Stealth Mode - Hide automation fingerprints
# --disable-blink-features=AutomationControlled hides navigator.webdriver
os.environ["AGENT_BROWSER_ARGS"] = (
    "--no-sandbox,"
    "--disable-blink-features=AutomationControlled,"
    "--disable-infobars,"
    "--disable-gpu"
)
os.environ["AGENT_BROWSER_USER_AGENT"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"

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

def log_resource_diagnostics(turn: int):
    """Log container resource metrics for debugging EAGAIN issues."""
    try:
        shm_proc = subprocess.run(
            ["df", "-h", "/dev/shm"], capture_output=True, text=True, timeout=5
        )
        fd_count = len(os.listdir("/proc/self/fd"))
        # Phase 6: Log process count to detect process limit (nproc) exhaustion
        ps_out = subprocess.run(["ps", "-e", "--no-headers"], capture_output=True, text=True)
        proc_count = len(ps_out.stdout.strip().split('\n')) if ps_out.stdout.strip() else 0
        
        logger.info(f"[DIAG] Turn {turn} | SHM: {shm_proc.stdout.strip().splitlines()[-1] if shm_proc.stdout else 'N/A'} | FDs: {fd_count} | Procs: {proc_count}")
    except Exception as e:
        logger.warning(f"[DIAG] Turn {turn} diagnostics failed: {e}")

def run_agent_browser_command(args: list) -> str:
    """Runs a subcommand of the agent-browser CLI."""
    try:
        # Full command: agent-browser <args>
        cmd = ["agent-browser"] + args
        
        # Local Debugging: Support headed mode via env var
        if os.environ.get("AGENT_BROWSER_HEADED") == "true" and "open" in args:
             if "--headed" not in cmd:
                 cmd.append("--headed")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        # Phase 4 Update: Ignore daemon-already-running warnings in stderr
        # These warnings can cause a non-zero exit code but the action may still succeed.
        has_daemon_warning = "daemon already running" in result.stderr
        
        if result.returncode != 0:
            # Phase 6: Gracefully handle 'daemon already running' warning.
            # This can cause a non-zero exit code but doesn't mean the command failed.
            if "daemon already running" in result.stderr:
                logger.info("Agent browser daemon already running. Proceeding...")
                return result.stdout or "Success: Daemon already running"
            
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

def focus_input_by_text(text: str) -> str:
    """Focus an input element by placeholder, aria-label, or partial match.
    Returns the eval result string. Check for 'Element not found' to detect failure."""
    # Escape quotes for JS
    safe_text = text.replace('"', '\\"')
    js_code = f"""
        let el = document.querySelector('input[placeholder="{safe_text}"]')
            || document.querySelector('input[aria-label="{safe_text}"]')
            || document.querySelector('[placeholder="{safe_text}"]')
            || document.querySelector('[aria-label="{safe_text}"]');
        if (!el) {{
            // Partial match fallback
            let inputs = document.querySelectorAll('input');
            for (let inp of inputs) {{
                if ((inp.placeholder && inp.placeholder.includes('{safe_text}'))
                    || (inp.getAttribute('aria-label') && inp.getAttribute('aria-label').includes('{safe_text}'))) {{
                    el = inp;
                    break;
                }}
            }}
        }}
        if (el) {{ el.focus(); el.click(); 'Focused' }}
        else {{ 'Element not found' }}
    """
    return run_agent_browser_command(["eval", js_code])

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
    
    # 2. Perform deterministic login
    try:
        perform_login()
    except Exception as e:
        return {"status": "error", "message": f"Deterministic login failed: {e}", "url": ""}

    # 3. Try target URL after login
    logger.info("Opening target workbook URL after login...")
    run_agent_browser_command(["open", target_url])
    time.sleep(15)

    snapshot = run_agent_browser_command(["snapshot"])
    current_url = run_agent_browser_command(["get", "url"]).strip()

    # 5. Final validation
    if "workbook" in current_url.lower() or "find-people" in current_url.lower():
        return {"status": "success", "message": "Authenticated successfully", "url": current_url}
    else:
        return {"status": "error", "message": "Failed to reach target workbook", "url": current_url, "snapshot_preview": snapshot[:500]}


def interpret_search_criteria(jobseeker: Dict[str, Any]) -> Dict[str, Any]:
    """
    Uses OpenAI GPT-4o to intelligently interpret raw Airtable JobSeeker data
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
        response = call_with_retry(
            openai_client.chat.completions.create,
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        raw_text = response.choices[0].message.content.strip()
        
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
    logger.info(f"Preparing workspace for {jobseeker.get('id')}...")
    # Force close any existing daemon to ensure a clean browser state
    run_agent_browser_command(["close"]) 
    time.sleep(5) # Increase wait for cleanup
    
    logger.info("Opening target URL to establish domain context...")
    run_agent_browser_command(["open", CLAY_URL])
    time.sleep(10)
    
    # Check if login is needed
    snapshot = run_agent_browser_command(["snapshot"])
    if "Log in" in snapshot or "Sign in" in snapshot or "login" in snapshot.lower():
        logger.info("Login required. Launching deterministic login...")
        perform_login()
        # After login, re-open the target URL to ensure we are on the workbook
        logger.info("Re-opening target workbook URL after login...")
        run_agent_browser_command(["open", CLAY_URL])
        time.sleep(10)
    
    # 2. AI Interpretation of Search Criteria (Phase 3 addition)
    logger.info("Interpreting search criteria via OpenAI GPT-4o...")
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
    
    # 3. Initialize chat history for OpenAI
    # Directive goes in system message (sent once). Snapshots go in user messages per turn.
    # Windowed: keep system message + last N turn pairs to prevent context overflow.
    CHAT_WINDOW_SIZE = 5  # Keep last 5 turn pairs (10 user+assistant messages)
    system_message = {"role": "system", "content": directive_text}
    chat_messages = []

    # 4. Loop
    turn = 0
    last_error = None
    last_action_key = None
    repeat_count = 0
    while turn < MAX_TURNS:
        turn += 1
        log_resource_diagnostics(turn)
        logger.info(f"Turn {turn}: Snapshotting...")

        # Browser Recycling (insurance — VPS has real /dev/shm so rarely needed)
        # Increased from 15 to 50 turns: recycling wipes all applied filters,
        # so it should only happen as a last resort for resource leaks.
        if turn % 50 == 0 and turn > 0:
            logger.info("Recycling browser daemon to free resources...")
            run_agent_browser_command(["close"])
            time.sleep(5)
            # Use deterministic login instead of cookie injection (cookies expire too quickly)
            run_agent_browser_command(["open", CLAY_URL])
            time.sleep(10)
            # Check if login is needed post-recycling
            snapshot = run_agent_browser_command(["snapshot"])
            if "Log in" in snapshot or "Sign in" in snapshot or "login" in snapshot.lower():
                logger.info("Post-recycling login required. Logging in...")
                perform_login()
                run_agent_browser_command(["open", CLAY_URL])
                time.sleep(10)
            logger.info("Browser recycled successfully.")
            # Reset chat history after recycling — the browser state is fresh,
            # so old context about previous actions is misleading.
            chat_messages = []
            logger.info("Chat history cleared after browser recycling.")

        
        # Observe
        # Use --compact to reduce token usage and prevent payload size errors
        snapshot_json = run_agent_browser_command(["snapshot", "--json", "--compact"])
        
        # Check for hard failure in snapshot to avoid infinite loop
        if snapshot_json.startswith("Error:"):
             logger.error(f"Snapshot failed: {snapshot_json}")
             raise Exception(f"Browser Snapshot Failed: {snapshot_json}")

        # Smart truncation: keep first half + last half to preserve both top nav AND bottom buttons
        MAX_SNAPSHOT_CHARS = 8000
        if len(snapshot_json) > MAX_SNAPSHOT_CHARS:
            half = MAX_SNAPSHOT_CHARS // 2
            logger.info(f"Snapshot truncated: {len(snapshot_json)} -> {MAX_SNAPSHOT_CHARS} chars (first {half} + last {half})")
            snapshot_json = snapshot_json[:half] + "\n\n... [MIDDLE TRUNCATED] ...\n\n" + snapshot_json[-half:]
        
        # Build prompt with previous error if any
        error_context = ""
        if last_error:
            error_context = f"\n⚠️ PREVIOUS ACTION FAILED with error:\n{last_error}\nPlease try a different approach (e.g., use a more specific element ID, or a different strategy).\n"

        # Loop detection: if same action repeated 3+ times, inject hint
        loop_hint = ""
        if repeat_count >= 3:
            loop_hint = f"\n🔁 LOOP DETECTED: You have repeated the same action ({last_action_key}) {repeat_count} times. You MUST choose a DIFFERENT action type. If you were using focus_placeholder, switch to type_and_enter with the value you want to type. Do NOT repeat the same action.\n"
            logger.warning(f"Loop detected: {last_action_key} repeated {repeat_count} times. Injecting hint.")

        # Think — directive is in system message, only send snapshot + instructions per turn
        prompt = f"""{error_context}{loop_hint}
CURRENT PAGE STATE (JSON Snapshot):
{snapshot_json}

INSTRUCTIONS:
Decide the next action based on the Directive (in system message) and current page state.
Return ONLY a JSON object with one of these structures:
{{"type": "click", "element_id": "@eX", "reason": "why"}}
{{"type": "fill", "element_id": "@eX", "value": "text", "reason": "why"}}
{{"type": "type_and_enter", "placeholder": "text", "value": "text", "reason": "Type text and press Enter - use for multi-select pill inputs like job titles, exclusions, cities"}}
{{"type": "press", "key": "Enter", "reason": "Use for Enter, Escape, or other keys"}}
{{"type": "click_by_text", "text": "Add to table", "reason": "Click a button by its visible text (use when element ref is not in snapshot)"}}
{{"type": "scroll", "direction": "down", "pixels": 300, "reason": "Scroll to reveal hidden sections"}}
{{"type": "done", "reason": "why"}}
{{"type": "fail", "reason": "why"}}
"""
        try:
            chat_messages.append({"role": "user", "content": prompt})

            # Chat history windowing: keep only last N turn pairs to prevent context overflow
            max_messages = CHAT_WINDOW_SIZE * 2  # Each turn = 1 user + 1 assistant message
            if len(chat_messages) > max_messages:
                chat_messages = chat_messages[-max_messages:]
                logger.info(f"Chat history trimmed to last {CHAT_WINDOW_SIZE} turns ({len(chat_messages)} messages)")

            # Prepend system message (directive) — always present, not counted in window
            messages_to_send = [system_message] + chat_messages

            response = call_with_retry(
                openai_client.chat.completions.create,
                model="gpt-4o",
                messages=messages_to_send,
                response_format={"type": "json_object"}
            )
            raw_text = response.choices[0].message.content.strip()
            chat_messages.append({"role": "assistant", "content": raw_text})
        except Exception as e:
            # Log detailed error info for OpenAI BadRequestError (likely context overflow)
            total_chars = sum(len(m.get("content", "")) for m in messages_to_send)
            logger.error(f"AI decision failed after retries: {e}")
            logger.error(f"Message stats: {len(messages_to_send)} messages, ~{total_chars} total chars, snapshot: {len(snapshot_json)} chars")
            raise
        
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
            last_error = f"Invalid JSON returned: {raw_text[:100]}"
            continue
            
        # Act
        action_type = action.get("type")
        last_error = None  # Reset error before new action

        # Loop detection: track repeated actions
        action_key = f"{action_type}:{action.get('element_id', action.get('placeholder', ''))}"
        if action_key == last_action_key:
            repeat_count += 1
        else:
            repeat_count = 1
            last_action_key = action_key

        if action_type == "snapshot":
             logger.info("Agent requested explicit snapshot.")
             continue # Loop will take a new snapshot at start of next turn

        elif action_type == "done":
            logger.info(f"Agent signaled completion. Reason: {action.get('reason')}")
            # Verify completion: check page state after filters + "Add to table" click
            verify_url = run_agent_browser_command(["get", "url"]).strip()
            logger.info(f"Completion check URL: {verify_url}")
            # Reject: still on login page
            if "login" in verify_url.lower():
                logger.warning("Completion rejected: still on login page.")
                last_error = "You are still on the login page. The task is NOT done."
                continue
            # Accept: page transitioned to table/workbook view (expected after "Add to table")
            if "workbook" in verify_url.lower() or "table" in verify_url.lower():
                if "find-people" not in verify_url.lower():
                    logger.info("Completion verified: page transitioned to table view after import.")
                    return True
            # Reject: still on find-people page with "Add to table" visible
            if "find-people" in verify_url.lower():
                verify_snapshot = run_agent_browser_command(["snapshot"])
                if "Add to table" in verify_snapshot:
                    logger.warning("Completion rejected: still on filter page.")
                    last_error = "You must click 'Add to table' before signaling done."
                    continue
                else:
                    # On find-people but Add to table is gone — may have been clicked
                    logger.info("Completion verified: on find-people but Add to table button gone.")
                    return True
            # Default accept: not on login, not on find-people — likely transitioned
            logger.info(f"Completion accepted (default): URL={verify_url}")
            return True
        elif action_type == "fail":
            logger.error(f"Agent reported failure: {action.get('reason')}")
            raise Exception(f"Agent Failure: {action.get('reason')}")
            
        elif action_type == "click":
            eid = action.get("element_id")
            res = run_agent_browser_command(["click", eid])
            if res.startswith("Error:"):
                last_error = res
                logger.warning(f"Click failed: {res}")
            else:
                time.sleep(2) # Wait for UI reaction
            
        elif action_type == "fill":
            eid = action.get("element_id")
            val = action.get("value")
            res = run_agent_browser_command(["fill", eid, val])
            if res.startswith("Error:"):
                last_error = res
                logger.warning(f"Fill failed: {res}")
            else:
                # Often need to press enter for pills, but ONLY if fill succeeded
                run_agent_browser_command(["press", "Enter"]) 
                run_agent_browser_command(["press", "Enter"]) 
                time.sleep(1)
            
        elif action_type == "press":
            key = action.get("key", "Enter")
            res = run_agent_browser_command(["press", key])
            if res.startswith("Error:"):
                last_error = res
                logger.warning(f"Press failed: {res}")
            else:
                time.sleep(1)

        elif action_type == "fill_placeholder":
            ph = action.get("placeholder")
            val = action.get("value")
            focus_res = focus_input_by_text(ph)
            if "Element not found" in focus_res:
                last_error = f"Placeholder '{ph}' not found"
                logger.warning(last_error)
            else:
                time.sleep(0.3)
                res = run_agent_browser_command(["fill", ":focus", val])
                if res.startswith("Error:"):
                    last_error = res
                    logger.warning(f"Fill-Placeholder failed: {res}")
                else:
                    run_agent_browser_command(["press", "Enter"])
                    time.sleep(1)

        elif action_type == "fill_label":
            lbl = action.get("label")
            val = action.get("value")
            focus_res = focus_input_by_text(lbl)
            if "Element not found" in focus_res:
                last_error = f"Label '{lbl}' not found"
                logger.warning(last_error)
            else:
                time.sleep(0.3)
                res = run_agent_browser_command(["fill", ":focus", val])
                if res.startswith("Error:"):
                    last_error = res
                    logger.warning(f"Fill-Label failed: {res}")
                else:
                    run_agent_browser_command(["press", "Enter"])
                    time.sleep(1)

        elif action_type == "focus_placeholder":
            # Focus an element by placeholder/aria-label without typing
            ph = action.get("placeholder")
            res = focus_input_by_text(ph)
            if "Element not found" in res:
                last_error = f"Placeholder '{ph}' not found via JS"
                logger.warning(last_error)
            else:
                logger.info(f"JS Focus result: {res}")
                time.sleep(0.5)

        elif action_type == "type_and_enter":
            # Type text into a multi-select input then press Enter to create a pill.
            # If value contains commas, split and enter each individually.
            ph = action.get("placeholder")
            val = action.get("value")

            # Split comma-separated values into individual entries
            # But preserve city names like "San Francisco, CA" — don't split if any part is ≤3 chars
            if "," in val:
                parts = [v.strip() for v in val.split(",") if v.strip()]
                if len(parts) > 1 and all(len(p) > 3 for p in parts):
                    values = parts  # All parts substantive → split (e.g., "VP of Sales, Head of Sales")
                else:
                    values = [val]  # Short part detected → keep as-is (e.g., "San Francisco, CA")
            else:
                values = [val]
            logger.info(f"type_and_enter: {len(values)} value(s) to enter for placeholder '{ph}'")

            any_error = None
            for i, single_val in enumerate(values):
                # Focus the input (first time by placeholder, subsequent by :focus fallback)
                if ph and i == 0:
                    focus_res = focus_input_by_text(ph)
                    if "Element not found" in focus_res:
                        logger.info(f"Placeholder '{ph}' not found, trying fill :focus directly")
                elif ph and i > 0:
                    # After first pill, placeholder may disappear — re-focus
                    focus_res = focus_input_by_text(ph)
                    if "Element not found" in focus_res:
                        logger.info(f"Placeholder gone after pill {i}, using :focus fallback")

                time.sleep(0.3)
                res = run_agent_browser_command(["fill", ":focus", single_val])

                if res.startswith("Error:"):
                    any_error = res
                    logger.warning(f"Type (Fill) failed for '{single_val}': {res}")
                    break
                else:
                    run_agent_browser_command(["press", "Enter"])
                    time.sleep(1)
                    run_agent_browser_command(["press", "Enter"])  # Double enter for Clay pills
                    time.sleep(0.5)
                    logger.info(f"Pill {i+1}/{len(values)} entered: '{single_val}'")

            if any_error:
                last_error = any_error
            
        elif action_type == "click_by_text":
            # Click a button/link by its visible text content using JS.
            # Useful when element ref is not visible in truncated snapshot.
            btn_text = action.get("text", "")
            safe_text = btn_text.replace('"', '\\"')
            click_js = f"""
                let btns = document.querySelectorAll('button, a, [role="button"]');
                let found = null;
                for (let b of btns) {{
                    if (b.textContent.trim().includes('{safe_text}')) {{
                        found = b;
                        break;
                    }}
                }}
                if (found) {{ found.click(); 'Clicked: ' + found.textContent.trim() }}
                else {{ 'Button not found: {safe_text}' }}
            """
            res = run_agent_browser_command(["eval", click_js])
            logger.info(f"click_by_text result: {res}")
            if "Button not found" in res:
                last_error = res
            else:
                time.sleep(2)  # Wait for UI reaction

        elif action_type == "scroll":
            direction = action.get("direction", "down")
            pixels = action.get("pixels", 500)
            sign = "" if direction == "down" else "-"
            # Try scrolling the filter panel first, fall back to window scroll
            scroll_js = f"""
                let panel = document.querySelector('[class*="sidebar"]')
                    || document.querySelector('[class*="filter"]')
                    || document.querySelector('[class*="panel"]');
                if (panel) {{ panel.scrollBy(0, {sign}{pixels}); 'Scrolled panel' }}
                else {{ window.scrollBy(0, {sign}{pixels}); 'Scrolled window' }}
            """
            res = run_agent_browser_command(["eval", scroll_js])
            logger.info(f"Scroll result: {res}")
            time.sleep(1)

        else:
            logger.warning(f"Unknown action type: {action_type}")
            last_error = f"Unknown action type: {action_type}"
            
    logger.warning("Max turns reached without completion.")
    raise Exception("Timeout: Max turns reached")
