import os
import subprocess
import json
import logging
import time
import re
from typing import Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI
import debug_state

# Valid LOG LEVELS
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
MAX_TURNS = 20  # Reduced: filters applied deterministically, GPT-4o only verifies + clicks Add to table

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=5, max=60))
def call_with_retry(func, *args, **kwargs):
    return func(*args, **kwargs)

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def parse_js_json(result):
    """Parse JSON from agent-browser eval results, handling double-encoding."""
    if not isinstance(result, str):
        return result
    try:
        data = json.loads(result)
        # Handle double-encoded JSON: agent-browser may wrap string results in quotes
        if isinstance(data, str):
            data = json.loads(data)
        return data
    except (json.JSONDecodeError, TypeError):
        return result  # Return raw string if not valid JSON

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

def _find_combobox_between(snapshot, after_text, before_text):
    """Find first combobox ref between two text markers in -i snapshot.
    Used to locate pill input fields that lose their labels after pills are added."""
    lines = snapshot.split('\n')
    found_after = False
    for line in lines:
        if after_text.lower() in line.lower():
            found_after = True
            continue
        if found_after and before_text and before_text.lower() in line.lower():
            break
        if found_after and 'combobox' in line.lower() and '[ref=' in line:
            parts = line.split('[ref=')
            if len(parts) > 1:
                return parts[1].split(']')[0]
    return None


def _find_ref_exact(snapshot, element_type, label_text, exclude_text=None):
    """Find element ref by type and label, with optional exclusion."""
    for line in snapshot.split('\n'):
        line_lower = line.lower()
        if element_type.lower() not in line_lower:
            continue
        if label_text.lower() not in line_lower:
            continue
        if exclude_text and exclude_text.lower() in line_lower:
            continue
        parts = line.split('[ref=')
        if len(parts) > 1:
            return parts[1].split(']')[0]
    return None


def _is_section_expanded(snapshot, section_ref):
    """Check if a section (button with ref) is expanded in -i snapshot."""
    for line in snapshot.split('\n'):
        if f'ref={section_ref}' in line:
            return '[expanded]' in line
    return False


def _expand_section(snapshot, section_text):
    """Find and expand a section by its text label if not already expanded.
    Returns (new_snapshot, success)."""
    ref = parse_ref(snapshot, section_text)
    if not ref:
        return snapshot, False
    if not _is_section_expanded(snapshot, ref):
        run_agent_browser_command(["click", f"@{ref}"])
        time.sleep(1)
        snapshot = run_agent_browser_command(["snapshot", "-i"])
    return snapshot, True


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

# Default import limit for Clay People Search
IMPORT_LIMIT = 150

def set_import_limit(limit: int = IMPORT_LIMIT) -> bool:
    """
    Set the 'Limit results' field using snapshot -i + fill @eX.
    Uses native agent-browser scroll + fill commands instead of JS eval.
    Playwright's fill simulates real keystrokes, properly triggering React state updates.
    """
    logger.info(f"[IMPORT] Setting import limit to {limit}...")

    # Scroll sidebar down to reveal Limit section (it's near the bottom)
    run_agent_browser_command(["scroll", "down"])
    time.sleep(1)

    snap = run_agent_browser_command(["snapshot", "-i"])

    # Expand "Limit results" section if collapsed
    snap, found = _expand_section(snap, "Limit results")
    if not found:
        # Try scrolling more
        run_agent_browser_command(["scroll", "down"])
        time.sleep(1)
        snap = run_agent_browser_command(["snapshot", "-i"])
        snap, found = _expand_section(snap, "Limit results")

    # Find the Limit spinbutton (not "Limit per company")
    limit_ref = _find_ref_exact(snap, 'spinbutton', '"Limit"', exclude_text='per company')
    if not limit_ref:
        # Broader search
        limit_ref = _find_ref_exact(snap, 'spinbutton', 'Limit', exclude_text='per company')
    if not limit_ref:
        logger.warning("[IMPORT] Limit spinbutton not found in snapshot")
        logger.info(f"[IMPORT] Snapshot for debug:\n{snap[:500]}")
        return False

    # Fill the limit value using native Playwright fill (triggers React events)
    res = run_agent_browser_command(["fill", f"@{limit_ref}", str(limit)])
    if res and "Error" in res:
        logger.warning(f"[IMPORT] Failed to fill limit: {res}")
        return False

    time.sleep(1)
    logger.info(f"[IMPORT] Import limit set to {limit}")
    return True


# Known country names — route to "Countries to include" instead of "Cities to include"
COUNTRY_NAMES = {
    "united states", "usa", "us", "united kingdom", "uk", "great britain",
    "canada", "australia", "germany", "france", "india", "brazil",
    "japan", "china", "singapore", "israel", "netherlands", "sweden",
    "norway", "denmark", "finland", "ireland", "spain", "italy",
    "switzerland", "austria", "belgium", "portugal", "new zealand",
    "south korea", "mexico", "argentina", "chile", "colombia",
    "south africa", "nigeria", "kenya", "egypt", "uae",
    "united arab emirates", "saudi arabia", "qatar", "poland",
    "czech republic", "romania", "hungary", "philippines", "thailand",
    "vietnam", "indonesia", "malaysia", "taiwan", "hong kong",
}

# US state abbreviations to strip from city names (e.g., "San Francisco CA" → "San Francisco")
US_STATE_ABBREVS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

def _parse_location(location_str):
    """Classify a location as 'country' or 'city' and clean the name.
    - "United States" → ("country", "United States")
    - "San Francisco CA" → ("city", "San Francisco")
    - "New York NY" → ("city", "New York")
    - "London" → ("city", "London")
    """
    loc = location_str.strip()
    if loc.lower() in COUNTRY_NAMES:
        return ("country", loc)
    # Strip trailing US state abbreviation
    # Handles: "San Francisco CA", "San Francisco, CA", "New York, NY"
    if "," in loc:
        comma_parts = [p.strip() for p in loc.split(",")]
        if len(comma_parts) == 2 and comma_parts[1].upper() in US_STATE_ABBREVS:
            return ("city", comma_parts[0])
    parts = loc.rsplit(" ", 1)
    if len(parts) == 2 and parts[1].upper() in US_STATE_ABBREVS:
        return ("city", parts[0])
    return ("city", loc)


def _take_filter_screenshot(name, scroll_to_top=False):
    """Take a named screenshot during filter application for visual verification."""
    try:
        if scroll_to_top:
            for _ in range(5):
                run_agent_browser_command(["scroll", "up"])
            time.sleep(0.5)
        path = debug_state.named_screenshot_path(name)
        res = run_agent_browser_command(["screenshot", path])
        if res and "Error" not in res:
            logger.info(f"[SCREENSHOT] Saved: {name}")
        else:
            logger.warning(f"[SCREENSHOT] Failed: {name}: {res}")
    except Exception as e:
        logger.warning(f"[SCREENSHOT] Exception: {name}: {e}")


def apply_filters_deterministic(search_criteria):
    """
    Apply all Clay People Search filters deterministically using snapshot -i + fill @eX.
    Called BEFORE the GPT-4o verification loop.

    Key patterns proven in probe:
    - Job titles: fill combobox + Enter creates pills
    - Exclusions: fill combobox + Enter creates pills
    - Cities: fill combobox + click autocomplete option
    - Seniority: click combobox + click options
    - Limit: fill spinbutton
    - CRITICAL: refs shift after each DOM change — re-snapshot before every fill

    Returns dict with results of each filter step.
    """
    results = {"seniority": False, "titles": False, "exclusions": False,
               "locations": False, "limit": False, "failed_filters": []}

    seniority = search_criteria.get("seniority", [])
    titles = search_criteria.get("titles", [])
    exclusions = search_criteria.get("excludeKeywords", [])
    locations = search_criteria.get("locations", [])

    # Take initial interactive snapshot
    snap = run_agent_browser_command(["snapshot", "-i"])
    logger.info(f"[FILTERS] Initial snapshot ({len(snap)} chars)")

    # --- 1. EXPAND JOB TITLE SECTION ---
    snap, expanded = _expand_section(snap, "Job title")
    if not expanded:
        logger.warning("[FILTERS] Job title section not found — may already be expanded")

    # --- 2. SENIORITY (click-based multi-select dropdown) ---
    if seniority:
        logger.info(f"[FILTERS] Applying seniority: {seniority}")
        snap = run_agent_browser_command(["snapshot", "-i"])

        sen_ref = parse_ref(snap, 'combobox "Seniority"')
        if not sen_ref:
            sen_ref = parse_ref(snap, 'Seniority')

        if sen_ref:
            run_agent_browser_command(["click", f"@{sen_ref}"])
            time.sleep(1)
            snap = run_agent_browser_command(["snapshot", "-i"])

            for level in seniority:
                opt_ref = _find_ref_exact(snap, 'option', f'"{level}"')
                if not opt_ref:
                    opt_ref = parse_ref(snap, level)
                if opt_ref:
                    run_agent_browser_command(["click", f"@{opt_ref}"])
                    time.sleep(0.5)
                    snap = run_agent_browser_command(["snapshot", "-i"])
                    logger.info(f"[FILTERS] Selected seniority: {level}")
                else:
                    logger.warning(f"[FILTERS] Seniority option not found: {level}")
                    results["failed_filters"].append(f"seniority:{level}")

            run_agent_browser_command(["press", "Escape"])
            time.sleep(1)
            results["seniority"] = True
            _take_filter_screenshot("filter_01_seniority", scroll_to_top=True)
        else:
            logger.warning("[FILTERS] Seniority combobox not found")
            results["failed_filters"].append("seniority")

    # --- 3. JOB TITLES (pill input via combobox fill + Enter) ---
    # KEY FIX: Do NOT press Escape between pills — it closes the input, hiding the
    # combobox from subsequent snapshots. Only Escape after ALL pills are entered.
    # Ref: SKILL.md pattern: "Type → Enter to add pill → repeat → ESC only after done"
    if titles:
        logger.info(f"[FILTERS] Applying job titles: {titles}")
        snap = run_agent_browser_command(["snapshot", "-i"])

        titles_applied = 0
        for i, title in enumerate(titles):
            # Strategy 1: placeholder label (works for first pill)
            title_ref = parse_ref(snap, 'e.g. CEO')
            # Strategy 2: combobox between text markers
            if not title_ref:
                title_ref = _find_combobox_between(snap, "is similar to", "Job titles to exclude")
            # Strategy 3: combobox after Clear chip buttons
            if not title_ref:
                title_ref = _find_combobox_between(snap, "Clear chip", "Job titles to exclude")
            # Strategy 4: combobox after last entered title
            if not title_ref and titles_applied > 0:
                title_ref = _find_combobox_between(snap, titles[titles_applied - 1], "Job titles to exclude")
            # Strategy 5: click section area to activate hidden input, re-snapshot
            if not title_ref:
                section_ref = parse_ref(snap, "is similar to")
                if section_ref:
                    run_agent_browser_command(["click", f"@{section_ref}"])
                    time.sleep(1)
                    snap = run_agent_browser_command(["snapshot", "-i"])
                    title_ref = parse_ref(snap, 'e.g. CEO')
                    if not title_ref:
                        title_ref = _find_combobox_between(snap, "is similar to", "Job titles to exclude")
                    if not title_ref:
                        title_ref = _find_combobox_between(snap, "Clear chip", "Job titles to exclude")

            if not title_ref:
                logger.warning(f"[FILTERS] Title input not found for '{title}' (pill {i+1})")
                logger.info(f"[FILTERS] Snapshot for debug (title ref search):\n{snap[:2000]}")
                results["failed_filters"].append(f"title:{title}")
                continue  # Try remaining titles instead of breaking

            res = run_agent_browser_command(["fill", f"@{title_ref}", title])
            if res and "Error" in res:
                logger.warning(f"[FILTERS] Fill failed for title '{title}': {res}")
                results["failed_filters"].append(f"title:{title}")
                continue  # Try remaining titles

            time.sleep(1)
            run_agent_browser_command(["press", "Enter"])
            time.sleep(1)
            # NO Escape here — keep input active for next pill

            # Re-snapshot — refs shift after pill creation
            snap = run_agent_browser_command(["snapshot", "-i"])
            titles_applied += 1
            logger.info(f"[FILTERS] Added title pill {titles_applied}/{len(titles)}: {title}")
            _take_filter_screenshot(f"filter_02_title_{titles_applied}", scroll_to_top=True)

        # Escape ONCE after all titles are done
        run_agent_browser_command(["press", "Escape"])
        time.sleep(0.5)

        results["titles"] = titles_applied == len(titles)
        results["titles_applied"] = titles_applied
        results["titles_total"] = len(titles)
        if titles_applied < len(titles):
            logger.warning(f"[FILTERS] PARTIAL: Only {titles_applied}/{len(titles)} title pills created")
        _take_filter_screenshot("filter_02_titles_final", scroll_to_top=True)

    # --- 4. EXCLUSIONS (pill input via combobox fill + Enter) ---
    # Same Escape fix as titles: only Escape after all exclusions are entered
    if exclusions:
        logger.info(f"[FILTERS] Applying exclusions: {exclusions}")
        snap = run_agent_browser_command(["snapshot", "-i"])

        exclusions_applied = 0
        for i, keyword in enumerate(exclusions):
            excl_ref = parse_ref(snap, 'Job titles to exclude')
            if not excl_ref:
                excl_ref = parse_ref(snap, 'exclude')

            if not excl_ref:
                logger.warning(f"[FILTERS] Exclusion input not found for '{keyword}'")
                logger.info(f"[FILTERS] Snapshot for debug (exclusion ref search):\n{snap[:2000]}")
                results["failed_filters"].append(f"exclusion:{keyword}")
                continue  # Try remaining exclusions

            res = run_agent_browser_command(["fill", f"@{excl_ref}", keyword])
            if res and "Error" in res:
                logger.warning(f"[FILTERS] Fill failed for exclusion '{keyword}': {res}")
                results["failed_filters"].append(f"exclusion:{keyword}")
                continue  # Try remaining exclusions

            time.sleep(1)
            run_agent_browser_command(["press", "Enter"])
            time.sleep(1)
            # NO Escape between pills — keep input active

            snap = run_agent_browser_command(["snapshot", "-i"])
            exclusions_applied += 1
            logger.info(f"[FILTERS] Added exclusion pill {exclusions_applied}/{len(exclusions)}: {keyword}")

        # Escape ONCE after all exclusions are done
        run_agent_browser_command(["press", "Escape"])
        time.sleep(0.5)

        results["exclusions"] = exclusions_applied == len(exclusions)
        results["exclusions_applied"] = exclusions_applied
        results["exclusions_total"] = len(exclusions)
        if exclusions_applied < len(exclusions):
            logger.warning(f"[FILTERS] PARTIAL: Only {exclusions_applied}/{len(exclusions)} exclusion pills created")
        _take_filter_screenshot("filter_03_exclusions", scroll_to_top=True)

    # --- 5. LOCATIONS (route countries vs cities to correct sub-fields) ---
    if locations:
        logger.info(f"[FILTERS] Applying locations: {locations}")

        # Classify each location as country or city
        countries = []
        cities = []
        for loc in locations:
            loc_type, clean_name = _parse_location(loc)
            if loc_type == "country":
                countries.append(clean_name)
            else:
                cities.append(clean_name)
        logger.info(f"[FILTERS] Location routing: countries={countries}, cities={cities}")

        # Scroll down to reveal Location section
        run_agent_browser_command(["scroll", "down"])
        time.sleep(1)
        snap = run_agent_browser_command(["snapshot", "-i"])

        # Expand Location section
        snap, expanded = _expand_section(snap, "Location")
        if not expanded:
            run_agent_browser_command(["scroll", "down"])
            time.sleep(1)
            snap = run_agent_browser_command(["snapshot", "-i"])
            snap, expanded = _expand_section(snap, "Location")

        locations_applied = 0

        # --- 5a. Countries (with retry + fuzzy matching) ---
        for country in countries:
            country_applied = False
            for attempt in range(2):  # Up to 2 attempts
                snap = run_agent_browser_command(["snapshot", "-i"])
                country_ref = parse_ref(snap, 'Countries to include')

                if not country_ref:
                    logger.warning(f"[FILTERS] 'Countries to include' not found for '{country}' (attempt {attempt+1})")
                    if attempt == 0:
                        run_agent_browser_command(["scroll", "down"])
                        time.sleep(1)
                        continue
                    results["failed_filters"].append(f"location:{country}")
                    break

                # Clear any previous value on retry
                if attempt > 0:
                    run_agent_browser_command(["fill", f"@{country_ref}", ""])
                    time.sleep(0.5)

                res = run_agent_browser_command(["fill", f"@{country_ref}", country])
                if res and "Error" in res:
                    logger.warning(f"[FILTERS] Fill failed for country '{country}': {res}")
                    if attempt == 0:
                        continue
                    results["failed_filters"].append(f"location:{country}")
                    break

                time.sleep(3)  # Increased from 2s — Clay autocomplete needs time
                snap = run_agent_browser_command(["snapshot", "-i"])
                logger.info(f"[FILTERS] Country autocomplete snapshot (attempt {attempt+1}):\n{snap[:1500]}")

                # Fuzzy option matching — try multiple strategies
                opt_ref = None

                # Try 1: exact match with quotes
                opt_ref = _find_ref_exact(snap, 'option', f'"{country}"')

                # Try 2: exact match without quotes
                if not opt_ref:
                    opt_ref = _find_ref_exact(snap, 'option', country)

                # Try 3: partial match — country name contained in option text
                if not opt_ref:
                    for line in snap.split('\n'):
                        if 'option' in line.lower() and '[ref=' in line:
                            if country.lower() in line.lower():
                                parts = line.split('[ref=')
                                if len(parts) > 1:
                                    opt_ref = parts[1].split(']')[0]
                                    logger.info(f"[FILTERS] Country partial match: '{country}' in '{line.strip()[:100]}'")
                                    break

                # Try 4: select first autocomplete option (most relevant)
                if not opt_ref:
                    for line in snap.split('\n'):
                        if 'option' in line.lower() and '[ref=' in line:
                            parts = line.split('[ref=')
                            if len(parts) > 1:
                                opt_ref = parts[1].split(']')[0]
                                logger.info(f"[FILTERS] Country: selecting first autocomplete option: '{line.strip()[:100]}'")
                                break

                if opt_ref:
                    run_agent_browser_command(["click", f"@{opt_ref}"])
                    time.sleep(1)
                    country_applied = True
                    locations_applied += 1
                    logger.info(f"[FILTERS] Selected country: {country}")
                    break  # Success, exit retry loop
                elif attempt == 0:
                    logger.info(f"[FILTERS] No autocomplete options for '{country}', retrying...")
                    run_agent_browser_command(["press", "Escape"])
                    time.sleep(1)
                    continue
                else:
                    # Don't count Enter fallback as success — unreliable for countries
                    logger.warning(f"[FILTERS] Country '{country}' autocomplete failed after 2 attempts")
                    run_agent_browser_command(["press", "Escape"])
                    results["failed_filters"].append(f"country_autocomplete:{country}")

            if country_applied:
                run_agent_browser_command(["press", "Escape"])
                time.sleep(0.5)

        # --- 5b. Cities ---
        for city in cities:
            snap = run_agent_browser_command(["snapshot", "-i"])
            city_ref = parse_ref(snap, 'Cities to include')

            if not city_ref:
                logger.warning(f"[FILTERS] 'Cities to include' combobox not found for '{city}'")
                results["failed_filters"].append(f"location:{city}")
                continue

            res = run_agent_browser_command(["fill", f"@{city_ref}", city])
            if res and "Error" in res:
                logger.warning(f"[FILTERS] Fill failed for city '{city}': {res}")
                results["failed_filters"].append(f"location:{city}")
                continue

            time.sleep(3)  # Increased from 2s for autocomplete
            snap = run_agent_browser_command(["snapshot", "-i"])

            opt_ref = _find_ref_exact(snap, 'option', f'"{city}"')
            if not opt_ref:
                opt_ref = parse_ref(snap, f'option "{city}')
            if not opt_ref:
                opt_ref = parse_ref(snap, city)

            if opt_ref:
                run_agent_browser_command(["click", f"@{opt_ref}"])
                time.sleep(1)
                locations_applied += 1
                logger.info(f"[FILTERS] Selected city: {city}")
            else:
                run_agent_browser_command(["press", "Enter"])
                time.sleep(1)
                locations_applied += 1
                logger.info(f"[FILTERS] Entered city (free-text): {city}")

            run_agent_browser_command(["press", "Escape"])
            time.sleep(0.5)

        results["locations"] = locations_applied > 0
        _take_filter_screenshot("filter_04_locations")

    # --- 6. IMPORT LIMIT ---
    results["limit"] = set_import_limit(IMPORT_LIMIT)
    _take_filter_screenshot("filter_05_limit")

    # --- Scroll to top for final overview screenshot ---
    _take_filter_screenshot("filter_06_final_top", scroll_to_top=True)

    # --- Summary ---
    logger.info(f"[FILTERS] Deterministic filter results: {json.dumps(results)}")
    return results


def wait_for_add_button_enabled(max_wait=90, poll_interval=5):
    """
    Poll snapshots until the 'Add to table' button is enabled (not loading).
    Clay disables the button with a loading spinner while computing search results
    after filter changes. Must wait for loading to complete before clicking.

    Returns: (button_ref, snapshot) if found enabled, (None, snapshot) if timeout.
    """
    logger.info("[IMPORT] Waiting for 'Add to table' button to become enabled...")

    # Scroll up to ensure the button area is visible (filters may have scrolled down)
    run_agent_browser_command(["scroll", "up"])
    run_agent_browser_command(["scroll", "up"])
    time.sleep(2)

    elapsed = 0
    last_snap = ""
    while elapsed < max_wait:
        snap = run_agent_browser_command(["snapshot", "-i"])
        last_snap = snap

        # Look for "Add to table" button ref
        button_ref = None
        is_disabled = False
        for line in snap.split('\n'):
            if 'add to table' in line.lower() and '[ref=' in line:
                parts = line.split('[ref=')
                if len(parts) > 1:
                    button_ref = parts[1].split(']')[0]
                    # Check if button has [disabled] marker
                    is_disabled = '[disabled]' in line.lower()
                    break

        if button_ref and not is_disabled:
            logger.info(f"[IMPORT] 'Add to table' button is enabled: @{button_ref} (waited {elapsed}s)")
            return button_ref, snap
        elif button_ref:
            logger.info(f"[IMPORT] Button found but disabled (loading), waiting... ({elapsed}s/{max_wait}s)")
        else:
            logger.info(f"[IMPORT] Button not found in snapshot, scrolling up... ({elapsed}s/{max_wait}s)")
            run_agent_browser_command(["scroll", "up"])

        time.sleep(poll_interval)
        elapsed += poll_interval

    logger.warning(f"[IMPORT] Timeout waiting for button after {max_wait}s")
    return None, last_snap


def click_add_to_table_deterministic(record_id=None):
    """
    Deterministically wait for and click the 'Add to table' button.
    Handles: loading state wait, confirmation dialogs, page transition verification.

    Returns: dict with import/enrichment results, or None if button not found (fall back to GPT-4o).
    """
    logger.info("[IMPORT] Starting deterministic 'Add to table' flow...")

    # Step 1: Wait for button to become enabled (Clay loads results after filter changes)
    button_ref, snap = wait_for_add_button_enabled(max_wait=90, poll_interval=5)

    if not button_ref:
        logger.warning("[IMPORT] Button never became enabled — falling back to GPT-4o")
        return None

    # Step 2: Capture expected count before clicking
    expected_count = capture_search_count()
    logger.info(f"[IMPORT] Expected count before click: {expected_count}")

    # Step 3: Take debug screenshot before clicking
    try:
        _ss_path = os.path.join(debug_state.SCREENSHOT_DIR, "pre_import.png")
        debug_state._ensure_screenshot_dir()
        run_agent_browser_command(["screenshot", _ss_path])
    except Exception:
        pass

    # Step 4: Click the button
    res = run_agent_browser_command(["click", f"@{button_ref}"])
    logger.info(f"[IMPORT] Click 'Add to table' result: {res}")

    if res and "Error" in res:
        # Button ref may have shifted — re-snapshot and try once more
        logger.warning(f"[IMPORT] Click failed: {res}. Re-snapshotting...")
        snap = run_agent_browser_command(["snapshot", "-i"])
        for line in snap.split('\n'):
            if 'add to table' in line.lower() and '[ref=' in line and '[disabled]' not in line.lower():
                parts = line.split('[ref=')
                if len(parts) > 1:
                    button_ref = parts[1].split(']')[0]
                    res = run_agent_browser_command(["click", f"@{button_ref}"])
                    logger.info(f"[IMPORT] Retry click result: {res}")
                    break
    time.sleep(3)

    # Step 5: Handle confirmation dialog (if any)
    snap = run_agent_browser_command(["snapshot", "-i"])
    for keyword in ['confirm', 'import', 'yes']:
        confirm_ref = None
        for line in snap.split('\n'):
            if keyword in line.lower() and ('button' in line.lower() or '[ref=' in line):
                if 'add to table' not in line.lower():  # Don't re-click the same button
                    parts = line.split('[ref=')
                    if len(parts) > 1:
                        confirm_ref = parts[1].split(']')[0]
                        break
        if confirm_ref:
            logger.info(f"[IMPORT] Clicking confirmation button: @{confirm_ref} (matched '{keyword}')")
            run_agent_browser_command(["click", f"@{confirm_ref}"])
            time.sleep(3)
            break

    # Step 6: Wait for page transition (find-people → table view)
    logger.info("[IMPORT] Waiting for page transition after click...")
    for wait_round in range(12):  # Up to 60 seconds
        time.sleep(5)
        current_url = run_agent_browser_command(["get", "url"]).strip()
        logger.info(f"[IMPORT] Page check {wait_round+1}/12: {current_url}")

        if "find-people" not in current_url.lower():
            logger.info(f"[IMPORT] Page transitioned to: {current_url}")
            # Take post-import screenshot
            try:
                _post_ss = os.path.join(debug_state.SCREENSHOT_DIR, "post_import.png")
                run_agent_browser_command(["screenshot", _post_ss])
            except Exception:
                pass
            # Import triggered — wait for rows, update RecordID, trigger enrichment
            import_result = wait_for_import_completion(expected_count)

            # Update JobSeeker RecordID column before triggering enrichment
            if record_id:
                recordid_result = update_record_id_column(record_id)
                logger.info(f"[RECORDID] Update result: {json.dumps(recordid_result)}")

            enrichment_result = trigger_enrichment(
                expected_count=expected_count,
                import_result=import_result
            )
            return {
                "success": True,
                "profiles_triggered": enrichment_result.get("count", 0),
                "enrichment_started": enrichment_result.get("started", False),
                "import_rows": import_result.get("row_count", 0),
                "record_id_set": record_id if record_id else None,
            }

    # Page didn't transition — check if button is gone (import may have happened inline)
    logger.warning("[IMPORT] Page didn't transition after 60s. Checking page state...")
    snap = run_agent_browser_command(["snapshot", "-i"])
    if "add to table" not in snap.lower():
        logger.info("[IMPORT] 'Add to table' button gone — import may have triggered inline")
        import_result = wait_for_import_completion(expected_count)

        # Update JobSeeker RecordID column before triggering enrichment
        if record_id:
            recordid_result = update_record_id_column(record_id)
            logger.info(f"[RECORDID] Update result: {json.dumps(recordid_result)}")

        enrichment_result = trigger_enrichment(
            expected_count=expected_count,
            import_result=import_result
        )
        return {
            "success": True,
            "profiles_triggered": enrichment_result.get("count", 0),
            "enrichment_started": enrichment_result.get("started", False),
            "import_rows": import_result.get("row_count", 0),
            "record_id_set": record_id if record_id else None,
        }

    logger.warning("[IMPORT] Import may not have triggered — falling back to GPT-4o")
    return None


def capture_search_count() -> int:
    """
    Capture the expected profile count from Clay's search results page
    before clicking 'Add to table'.

    Clay UI shows:
    - Top bar: "Previewing 50 of 1,362 results. 100 will be..."
    - Left sidebar 'Limit results' section: input field with limit value (e.g. 100)
    The Limit input value = number of profiles that will actually be imported.

    Returns:
        int: Expected profile count, or None if not found.
    """
    logger.info("[IMPORT] Capturing expected profile count from search results...")

    capture_js = """
    (function() {
        // Strategy 1: Read the Limit input field value from the sidebar
        // The 'Limit results' section has an input with the import count
        let allInputs = document.querySelectorAll('input');
        for (let input of allInputs) {
            // Check if this input is near text containing 'Limit'
            let parent = input.closest('div, section, label, fieldset');
            if (parent) {
                let parentText = parent.textContent || '';
                if (parentText.includes('Limit') && !parentText.includes('Limit per company')) {
                    let val = parseInt(input.value);
                    if (val > 0 && val < 100000) {
                        return JSON.stringify({"count": val, "source": "limit_input"});
                    }
                }
            }
        }

        // Strategy 1b: Look for number inputs specifically
        let numInputs = document.querySelectorAll('input[type="number"], input[inputmode="numeric"]');
        for (let input of numInputs) {
            let val = parseInt(input.value);
            if (val > 0 && val < 100000) {
                let parent = input.closest('div, section');
                let parentText = parent ? (parent.textContent || '') : '';
                if (parentText.includes('Limit')) {
                    return JSON.stringify({"count": val, "source": "number_input"});
                }
            }
        }

        // Strategy 2: Parse top preview bar text - "X will be added"
        let bodyText = document.body.innerText;
        let willBeMatch = bodyText.match(/(\\d[\\d,]*)\\s+will\\s+be/i);
        if (willBeMatch) {
            let count = parseInt(willBeMatch[1].replace(/,/g, ''));
            if (count > 0) {
                return JSON.stringify({"count": count, "source": "will_be_text", "match": willBeMatch[0]});
            }
        }

        // Strategy 3: Parse "Previewing X of Y results" and use Y
        let previewMatch = bodyText.match(/Previewing\\s+\\d+\\s+of\\s+([\\d,]+)\\s+results/i);
        if (previewMatch) {
            let total = parseInt(previewMatch[1].replace(/,/g, ''));
            if (total > 0) {
                return JSON.stringify({"count": total, "source": "total_results", "match": previewMatch[0]});
            }
        }

        // Strategy 4: Look for text with "people" or "results" count near Add to table
        let buttons = document.querySelectorAll('button, a, [role="button"]');
        for (let btn of buttons) {
            if (btn.textContent.toLowerCase().includes('add to table')) {
                let container = btn.closest('div, section, form');
                if (container) {
                    let containerText = container.innerText;
                    let match = containerText.match(/(\\d[\\d,]*)\\s+(?:people|results?|profiles?)/i);
                    if (match) {
                        let count = parseInt(match[1].replace(/,/g, ''));
                        return JSON.stringify({"count": count, "source": "button_container", "match": match[0]});
                    }
                }
            }
        }

        return JSON.stringify({"count": null, "source": "not_found"});
    })();
    """

    result = run_agent_browser_command(["eval", capture_js])
    logger.info(f"[IMPORT] Search count capture result: {result}")

    try:
        data = parse_js_json(result)
        count = data.get("count")
        source = data.get("source", "unknown")
        if count is not None and count > 0:
            logger.info(f"[IMPORT] Expected profile count: {count} (source: {source})")
            return count
        else:
            logger.warning(f"[IMPORT] Could not capture profile count (source: {source})")
            return None
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[IMPORT] Failed to parse search count result: {result}")
        return None


def wait_for_import_completion(expected_count) -> Dict[str, Any]:
    """
    Poll the Clay table view until the imported row count matches the expected count
    or stabilizes (fallback when expected count is unknown).

    Args:
        expected_count: Expected number of profiles (int), or None for stabilization mode.

    Returns:
        dict: {"row_count": int, "matched": bool, "timed_out": bool}
    """
    MAX_WAIT_SECONDS = 360   # 6 minutes max (large imports need time)
    POLL_INTERVAL = 10       # seconds between polls
    STABILIZE_CHECKS = 3     # consecutive unchanged counts = done
    INITIAL_WAIT = 10        # initial wait for page transition

    mode = "count_match" if expected_count is not None else "stabilization"
    logger.info(f"[IMPORT] Waiting for import completion (mode={mode}, expected={expected_count})")

    # Initial wait for page transition to table view
    logger.info(f"[IMPORT] Initial wait ({INITIAL_WAIT}s) for page transition to table view...")
    time.sleep(INITIAL_WAIT)

    # Clay shows row count as "X/Y" (e.g., "49,935/49,935") in the top bar.
    # This is much more reliable than counting DOM elements (Clay uses virtual scrolling).
    count_js = """
    (function() {
        // Strategy 1: Find ALL "X/Y" patterns in the page.
        // Clay header shows "22/23" (columns) THEN "65/65" (rows).
        // We need the ROW count, which has the highest denominator.
        let bodyText = document.body.innerText;
        let allMatches = [...bodyText.matchAll(/(\\d[\\d,]*)\\/(\\d[\\d,]*)/g)];
        if (allMatches.length > 0) {
            // Pick the match with the highest denominator (row count > column count)
            let best = null;
            let bestTotal = 0;
            for (let m of allMatches) {
                let current = parseInt(m[1].replace(/,/g, ''));
                let total = parseInt(m[2].replace(/,/g, ''));
                if (total > bestTotal && current > 0 && total > 0) {
                    best = m;
                    bestTotal = total;
                }
            }
            if (best) {
                let current = parseInt(best[1].replace(/,/g, ''));
                let total = parseInt(best[2].replace(/,/g, ''));
                let allStr = allMatches.map(m => m[0]).join(', ');
                return JSON.stringify({"count": current, "total": total, "source": "row_counter_text", "match": best[0], "all_matches": allStr});
            }
        }

        // Strategy 2: Look for "X rows" text
        let rowsMatch = bodyText.match(/(\\d[\\d,]*)\\s+rows?/i);
        if (rowsMatch) {
            let count = parseInt(rowsMatch[1].replace(/,/g, ''));
            if (count > 0) {
                return JSON.stringify({"count": count, "source": "rows_text", "match": rowsMatch[0]});
            }
        }

        // Strategy 3: Fallback - count visible DOM rows
        let ariaRows = document.querySelectorAll('[role="row"]');
        let headerRows = document.querySelectorAll('[role="columnheader"]');
        let dataRowCount = ariaRows.length > headerRows.length ? ariaRows.length - headerRows.length : ariaRows.length;
        if (dataRowCount > 0) {
            return JSON.stringify({"count": dataRowCount, "source": "aria_row"});
        }

        return JSON.stringify({"count": 0, "source": "not_found"});
    })();
    """

    elapsed = 0
    last_count = -1
    stable_streak = 0

    while elapsed < MAX_WAIT_SECONDS:
        result = run_agent_browser_command(["eval", count_js])

        try:
            data = parse_js_json(result)
            current_count = data.get("count", 0)
            source = data.get("source", "unknown")
            all_matches = data.get("all_matches", "")
        except (json.JSONDecodeError, TypeError):
            current_count = 0
            source = "parse_error"
            all_matches = ""

        logger.info(
            f"[IMPORT] Poll: {current_count}/{expected_count or '?'} rows "
            f"(elapsed={elapsed}s, source={source}, all_xy=[{all_matches}])"
        )

        # Check completion: count_match mode
        if mode == "count_match" and current_count >= expected_count:
            logger.info(
                f"[IMPORT] Import complete! Row count ({current_count}) matches "
                f"expected ({expected_count}). Elapsed: {elapsed}s. "
                f"Waiting 10s for UI to settle before enrichment..."
            )
            _take_filter_screenshot("import_complete")
            time.sleep(10)  # Let Clay's UI fully settle before any clicks
            return {"row_count": current_count, "matched": True, "timed_out": False}

        # Take screenshot when count changes (track import progress visually)
        if current_count != last_count and current_count > 0:
            _take_filter_screenshot(f"import_poll_{current_count}")

        # Stabilization tracking (applies to BOTH modes)
        if current_count == last_count and current_count > 0:
            stable_streak += 1
            logger.info(f"[IMPORT] Stable streak: {stable_streak}/{STABILIZE_CHECKS}")
        else:
            stable_streak = 0

        # Stabilization check (works in both count_match and stabilization modes)
        # If count has been stable for N consecutive checks, import is likely done
        if stable_streak >= STABILIZE_CHECKS and current_count > 0:
            if mode == "count_match" and current_count < expected_count:
                # Still below expected — don't exit early, keep waiting
                logger.warning(
                    f"[IMPORT] Count stable at {current_count} but expected {expected_count}. "
                    f"Resetting streak, will keep polling up to {MAX_WAIT_SECONDS}s..."
                )
                _take_filter_screenshot(f"import_stalled_{current_count}_of_{expected_count}")
                stable_streak = 0  # Reset to keep polling
            else:
                # Either no expected count (stabilization mode), or we've met/exceeded it
                matched = (mode == "count_match" and current_count >= expected_count)
                logger.info(
                    f"[IMPORT] Import stabilized at {current_count} rows "
                    f"after {STABILIZE_CHECKS} consecutive checks. "
                    f"Elapsed: {elapsed}s, matched={matched}"
                )
                _take_filter_screenshot("import_complete")
                return {"row_count": current_count, "matched": matched, "timed_out": False}

        last_count = current_count
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    # Timeout
    logger.warning(
        f"[IMPORT] Timeout after {MAX_WAIT_SECONDS}s. "
        f"Current rows: {last_count}, expected: {expected_count or '?'}. Proceeding anyway."
    )
    _take_filter_screenshot(f"import_timeout_{last_count}")
    return {"row_count": last_count, "matched": False, "timed_out": True}


# ============================================================================
# Shared helpers for snapshot-based element finding and clicking
# ============================================================================

def _extract_refs(line_text):
    """Extract element refs from snapshot line. Handles both @eXX and [ref=eXX] formats."""
    ref_matches = re.findall(r'\[ref=(e\d+)\]', line_text)
    if ref_matches:
        return ['@' + r for r in ref_matches]
    at_matches = re.findall(r'(@e\d+)', line_text)
    return at_matches


def _find_and_click_snapshot(search_text, exclude_text=None, max_retries=3, log_prefix="[UI]"):
    """
    Use agent-browser snapshot to find element by text, then native click.
    Native clicks properly trigger React event handlers (unlike JS DOM clicks).
    Returns (success: bool, click_result: str, matched_line: str)
    """
    search_lower = search_text.lower()
    exclude_lower = exclude_text.lower() if exclude_text else None

    for attempt in range(max_retries):
        snapshot_text = run_agent_browser_command(["snapshot"])
        if not snapshot_text:
            time.sleep(2)
            continue

        lines = snapshot_text.split('\n')

        # Log snapshot diagnostics on first attempt
        if attempt == 0:
            logger.info(f"{log_prefix} Snapshot: {len(lines)} lines, {len(snapshot_text)} chars")

        # Search with case-insensitive matching
        for i, line in enumerate(lines):
            line_lower = line.lower()
            if search_lower in line_lower:
                if exclude_lower and exclude_lower in line_lower:
                    continue
                refs = _extract_refs(line)
                if refs:
                    logger.info(f"{log_prefix} Found '{search_text}' at line {i}: {line.strip()[:120]}, refs={refs}")
                    for ref in refs:
                        click_result = run_agent_browser_command(["click", ref])
                        logger.info(f"{log_prefix} Native click {ref}: {click_result}")
                        if click_result and "error" not in str(click_result).lower():
                            return True, click_result, line.strip()
                        time.sleep(1)

        # Also try matching individual words (handles split text across elements)
        if ' ' in search_text:
            words = search_text.split()
            for i, line in enumerate(lines):
                line_lower = line.lower()
                if all(w.lower() in line_lower for w in words):
                    if exclude_lower and exclude_lower in line_lower:
                        continue
                    refs = _extract_refs(line)
                    if refs:
                        logger.info(f"{log_prefix} Found '{search_text}' (word match) at line {i}: {line.strip()[:120]}, refs={refs}")
                        for ref in refs:
                            click_result = run_agent_browser_command(["click", ref])
                            logger.info(f"{log_prefix} Native click {ref}: {click_result}")
                            if click_result and "error" not in str(click_result).lower():
                                return True, click_result, line.strip()
                            time.sleep(1)

        if attempt < max_retries - 1:
            logger.info(f"{log_prefix} '{search_text}' not found in snapshot, retrying ({attempt + 1}/{max_retries})...")
            time.sleep(3)

    return False, None, None


def _find_ref_in_snapshot(search_text, exclude_text=None, log_prefix="[UI]"):
    """
    Find an element ref by text in the current snapshot WITHOUT clicking it.
    Returns the ref string (e.g., '@e5') or None.
    """
    snapshot_text = run_agent_browser_command(["snapshot"])
    if not snapshot_text:
        return None

    search_lower = search_text.lower()
    exclude_lower = exclude_text.lower() if exclude_text else None

    for line in snapshot_text.split('\n'):
        line_lower = line.lower()
        if search_lower in line_lower:
            if exclude_lower and exclude_lower in line_lower:
                continue
            refs = _extract_refs(line)
            if refs:
                logger.info(f"{log_prefix} Found ref for '{search_text}': {refs[0]} in: {line.strip()[:120]}")
                return refs[0]
    return None


def update_record_id_column(record_id: str) -> Dict[str, Any]:
    """
    Edit the 'JobSeeker RecordID' column to set the record ID for all rows.
    Must be done BEFORE triggering 'Create Profile' enrichment so the webhook
    knows which JobSeeker the profiles belong to.

    Clay UI flow:
    1. Click "JobSeeker RecordID" column header → dropdown opens
    2. Click "Edit column" from dropdown → edit panel opens on right
    3. Find text input in edit panel
    4. Clear existing value, fill with record_id
    5. Press Escape to close edit panel

    Returns:
        dict: {"success": bool, "record_id": str, "error": str (optional)}
    """
    LOG = "[RECORDID]"
    logger.info(f"{LOG} Setting JobSeeker RecordID column to '{record_id}'...")

    try:
        # Step 1: Click "JobSeeker RecordID" column header
        logger.info(f"{LOG} Step 1: Clicking 'JobSeeker RecordID' column header...")
        header_clicked, _, _ = _find_and_click_snapshot(
            'JobSeeker RecordID', exclude_text=None, max_retries=3, log_prefix=LOG
        )
        if not header_clicked:
            # Try shorter text match
            header_clicked, _, _ = _find_and_click_snapshot(
                'RecordID', exclude_text='Create', max_retries=2, log_prefix=LOG
            )
        if not header_clicked:
            logger.error(f"{LOG} Failed to find/click 'JobSeeker RecordID' column header")
            _take_filter_screenshot("recordid_01_header_FAILED")
            return {"success": False, "record_id": record_id, "error": "Column header not found"}

        time.sleep(2)  # Wait for dropdown to render
        _take_filter_screenshot("recordid_01_header_click")

        # Step 2: Click "Edit column" from the dropdown
        logger.info(f"{LOG} Step 2: Clicking 'Edit column' from dropdown...")
        edit_clicked, _, _ = _find_and_click_snapshot(
            'Edit column', max_retries=3, log_prefix=LOG
        )
        if not edit_clicked:
            logger.error(f"{LOG} 'Edit column' not found in dropdown")
            _take_filter_screenshot("recordid_02_edit_FAILED")
            return {"success": False, "record_id": record_id, "error": "Edit column option not found"}

        time.sleep(2)  # Wait for edit panel to open on right side
        _take_filter_screenshot("recordid_02_edit_panel")

        # Step 3: Find and fill the text input in the edit panel
        # Clay's edit panel has a rich text editor for the column value
        # It may appear as textbox, editor, textarea, or contenteditable
        logger.info(f"{LOG} Step 3: Finding text input in edit panel...")

        # Try both snapshot modes - interactive and regular may show elements differently
        snap_i = run_agent_browser_command(["snapshot", "-i"]) or ""
        snap_r = run_agent_browser_command(["snapshot"]) or ""

        # Log full interactive snapshot for debugging
        logger.info(f"{LOG} Edit panel snapshot-i ({len(snap_i)} chars):")
        for i, line in enumerate(snap_i.split('\n')):
            if line.strip():
                logger.info(f"{LOG} SNAP[{i}]: {line.rstrip()[:160]}")

        input_ref = None
        used_js_fallback = False
        role_keywords = ['textbox', 'input', 'combobox', 'editor']
        skip_keywords = ['search', 'data type', 'column name', 'rename']

        # Search a snapshot string with multiple strategies
        for snap_label, snap in [("snap-i", snap_i), ("snap-reg", snap_r)]:
            if input_ref:
                break
            lines = snap.split('\n')

            # Strategy 1: placeholder text + input role on same line
            for line in lines:
                ll = line.lower()
                if ('type /' in ll or 'insert column' in ll):
                    if any(kw in ll for kw in role_keywords):
                        refs = _extract_refs(line)
                        if refs:
                            input_ref = refs[0]
                            logger.info(f"{LOG} {snap_label} S1 placeholder+role: {input_ref} | {line.strip()[:120]}")
                            break
            if input_ref:
                break

            # Strategy 2: any textbox/combobox/editor (skip irrelevant)
            for line in lines:
                ll = line.lower()
                if any(kw in ll for kw in role_keywords):
                    if any(skip in ll for skip in skip_keywords):
                        continue
                    refs = _extract_refs(line)
                    if refs:
                        input_ref = refs[0]
                        logger.info(f"{LOG} {snap_label} S2 role-scan: {input_ref} | {line.strip()[:120]}")
                        break
            if input_ref:
                break

            # Strategy 3: textarea / contenteditable
            for line in lines:
                ll = line.lower()
                if 'textarea' in ll or 'contenteditable' in ll:
                    refs = _extract_refs(line)
                    if refs:
                        input_ref = refs[0]
                        logger.info(f"{LOG} {snap_label} S3 textarea: {input_ref} | {line.strip()[:120]}")
                        break
            if input_ref:
                break

            # Strategy 4: proximity - find "Type /" line, look at preceding lines for refs
            type_line_idx = None
            for i, line in enumerate(lines):
                if 'type /' in line.lower() or 'insert column' in line.lower():
                    type_line_idx = i
                    break
            if type_line_idx is not None:
                # Search 15 lines before "Type /" for the nearest ref
                for j in range(type_line_idx - 1, max(-1, type_line_idx - 16), -1):
                    refs = _extract_refs(lines[j])
                    if refs:
                        input_ref = refs[-1]  # Last ref on line = deepest element
                        logger.info(f"{LOG} {snap_label} S4 proximity: {input_ref} at line {j}: {lines[j].strip()[:120]}")
                        break
            if input_ref:
                break

            # Strategy 5: line containing existing record ID value (starts with 'rec')
            for line in lines:
                ll = line.lower()
                if re.search(r'\brec[a-z0-9]{8,}', ll):
                    refs = _extract_refs(line)
                    if refs:
                        input_ref = refs[0]
                        logger.info(f"{LOG} {snap_label} S5 existing-recID: {input_ref} | {line.strip()[:120]}")
                        break

        # Strategy 6 (JavaScript fallback): directly find and fill via DOM
        if not input_ref:
            logger.info(f"{LOG} All snapshot strategies failed. Trying JavaScript fallback...")
            js_fill = f"""(() => {{
                // Try contenteditable elements (Clay rich text editor)
                const editables = document.querySelectorAll('[contenteditable="true"]');
                for (const el of editables) {{
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 100 && rect.height > 15 && rect.right > window.innerWidth / 2) {{
                        el.focus();
                        document.execCommand('selectAll', false, null);
                        document.execCommand('insertText', false, '{record_id}');
                        return JSON.stringify({{found: true, method: 'contenteditable', tag: el.tagName}});
                    }}
                }}
                // Try textareas
                const textareas = document.querySelectorAll('textarea');
                for (const el of textareas) {{
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 100 && rect.right > window.innerWidth / 2) {{
                        el.focus();
                        el.value = '{record_id}';
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        el.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return JSON.stringify({{found: true, method: 'textarea', tag: el.tagName}});
                    }}
                }}
                // Try inputs with placeholder containing "Type"
                const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
                for (const el of inputs) {{
                    if (el.placeholder && el.placeholder.includes('Type')) {{
                        el.focus();
                        el.value = '{record_id}';
                        el.dispatchEvent(new Event('input', {{bubbles: true}}));
                        el.dispatchEvent(new Event('change', {{bubbles: true}}));
                        return JSON.stringify({{found: true, method: 'input', tag: el.tagName}});
                    }}
                }}
                return JSON.stringify({{found: false}});
            }})()"""
            js_result = run_agent_browser_command(["eval", js_fill])
            logger.info(f"{LOG} JS fallback result: {js_result}")

            if js_result and '"found": true' in js_result.replace('"found":true', '"found": true'):
                used_js_fallback = True
                time.sleep(1)
                _take_filter_screenshot("recordid_03_filled_js")
            else:
                logger.error(f"{LOG} All strategies (including JS) failed to find input")
                _take_filter_screenshot("recordid_03_input_FAILED")
                return {"success": False, "record_id": record_id, "error": "Text input not found in edit panel (all 6 strategies failed)"}

        # Step 4: Fill the record ID via Playwright (skip if JS fallback already filled)
        if not used_js_fallback:
            logger.info(f"{LOG} Step 4: Filling record ID '{record_id}' into {input_ref}...")

            # Click the input to focus it
            run_agent_browser_command(["click", input_ref])
            time.sleep(0.5)

            # Select all existing text
            run_agent_browser_command(["press", "Control+a"])
            time.sleep(0.3)

            # Fill with record_id
            fill_result = run_agent_browser_command(["fill", input_ref, record_id])
            logger.info(f"{LOG} Fill result: {fill_result}")

            # If fill fails, try typing instead
            if fill_result and "error" in str(fill_result).lower():
                logger.info(f"{LOG} Fill failed, trying type approach...")
                run_agent_browser_command(["click", input_ref])
                time.sleep(0.3)
                run_agent_browser_command(["press", "Control+a"])
                time.sleep(0.2)
                run_agent_browser_command(["press", "Backspace"])
                time.sleep(0.2)
                # Type character by character via keyboard
                for char in record_id:
                    run_agent_browser_command(["press", char])
                    time.sleep(0.05)
                logger.info(f"{LOG} Typed record_id via keyboard")

            time.sleep(1)
            _take_filter_screenshot("recordid_03_filled")

        # Step 5: Click "Save and don't run enrichments" button to apply value
        # (Pressing Escape might not save the value)
        logger.info(f"{LOG} Step 5: Clicking 'Save and don't run enrichments'...")
        time.sleep(1)

        save_clicked, _, _ = _find_and_click_snapshot(
            "Save and don't run", max_retries=2, log_prefix=LOG
        )
        if not save_clicked:
            # Fall back to just "Save" button
            save_clicked, _, _ = _find_and_click_snapshot(
                'Save', exclude_text='don', max_retries=2, log_prefix=LOG
            )
        if not save_clicked:
            # Last resort: press Escape and hope the value was auto-saved
            logger.warning(f"{LOG} Could not find Save button, pressing Escape as fallback")
            run_agent_browser_command(["press", "Escape"])
            time.sleep(1)
            run_agent_browser_command(["press", "Escape"])
            time.sleep(1)

        time.sleep(2)
        _take_filter_screenshot("recordid_04_complete")
        logger.info(f"{LOG} Successfully set JobSeeker RecordID to '{record_id}'")
        return {"success": True, "record_id": record_id}

    except Exception as e:
        logger.error(f"{LOG} Exception during RecordID update: {e}")
        _take_filter_screenshot("recordid_exception")
        return {"success": False, "record_id": record_id, "error": str(e)}


def trigger_enrichment(expected_count=None, import_result=None) -> Dict[str, Any]:
    """
    After import completes, clicks the 'Create Profile' play button to trigger
    n8n webhook enrichment.

    Args:
        expected_count: Expected profile count (from capture_search_count), or None.
        import_result: Result from wait_for_import_completion, or None.

    Returns:
        dict: {"count": int, "started": bool, "error": str (optional),
               "import_rows": int (optional)}
    """
    import_rows = import_result.get("row_count", 0) if import_result else 0
    logger.info(f"[ENRICHMENT] Starting enrichment trigger sequence... (import_rows={import_rows})")

    try:
        # ================================================================
        # Step 1: Click "Create Profile" column header to open dropdown
        # Using agent-browser native click (Playwright) for proper React event handling
        # ================================================================
        logger.info("[ENRICHMENT] Step 1: Opening 'Create Profile' column header dropdown...")

        header_clicked, header_result, header_line = _find_and_click_snapshot(
            'Create Profile', exclude_text='Click to run', max_retries=3
        )

        _take_filter_screenshot("enrichment_01_header_click")

        if not header_clicked:
            logger.error("[ENRICHMENT] Failed to find/click 'Create Profile' column header")
            _take_filter_screenshot("enrichment_01_header_FAILED")
            return {"count": 0, "started": False, "error": "Column header not found", "import_rows": import_rows}

        # ================================================================
        # Step 2: Click "Run column" from the dropdown menu
        # ================================================================
        time.sleep(2)  # Wait for dropdown to render
        logger.info("[ENRICHMENT] Step 2: Clicking 'Run column' from dropdown...")

        run_col_clicked, run_col_result, run_col_line = _find_and_click_snapshot(
            'Run column', max_retries=2
        )

        if not run_col_clicked:
            # Maybe the dropdown didn't open; try clicking header again
            logger.info("[ENRICHMENT] 'Run column' not found. Re-clicking header and retrying...")
            _find_and_click_snapshot('Create Profile', exclude_text='Click to run', max_retries=1)
            time.sleep(3)
            run_col_clicked, run_col_result, run_col_line = _find_and_click_snapshot(
                'Run column', max_retries=2
            )

        _take_filter_screenshot("enrichment_02_run_column")

        if not run_col_clicked:
            logger.error("[ENRICHMENT] Failed to find/click 'Run column' in dropdown")
            _take_filter_screenshot("enrichment_02_run_column_FAILED")
            return {"count": 0, "started": False, "error": "Run column not found in dropdown", "import_rows": import_rows}

        # ================================================================
        # Step 3: Click "Run all X rows" / "Force run all X rows" from submenu
        # ================================================================
        # Wait for submenu to fully load (it shows "Loading..." initially)
        time.sleep(3)
        logger.info("[ENRICHMENT] Step 3: Waiting for submenu to load...")
        for _wait in range(5):
            snap_text = run_agent_browser_command(["snapshot"]) or ""
            if "loading" not in snap_text.lower() or "force run" in snap_text.lower() or "run all" in snap_text.lower():
                break
            logger.info("[ENRICHMENT] Submenu still loading, waiting 2s...")
            time.sleep(2)
        time.sleep(1)  # Extra 1s for rendering

        logger.info("[ENRICHMENT] Step 3: Clicking 'Force run all' / 'Run all' from submenu...")

        # Try "Force run all" first (Clay shows this in column dropdown submenu)
        run_all_clicked, run_all_result, run_all_line = _find_and_click_snapshot(
            'Force run all', max_retries=2
        )
        if not run_all_clicked:
            # Fallback to "Run all"
            logger.info("[ENRICHMENT] 'Force run all' not found, trying 'Run all'...")
            run_all_clicked, run_all_result, run_all_line = _find_and_click_snapshot(
                'Run all', max_retries=2
            )

        # Extract count from the matched line
        count = 0
        if run_all_clicked and run_all_line:
            # Try multiple patterns to extract the row count
            count_match = _re.search(r'Run all ([\d,]+)', run_all_line)
            if count_match:
                count = int(count_match.group(1).replace(',', ''))
            else:
                # Try "X rows" pattern anywhere in the line
                rows_match = _re.search(r'([\d,]+)\s+rows?', run_all_line)
                if rows_match:
                    count = int(rows_match.group(1).replace(',', ''))

            # Fallback: use import_rows or expected_count when text has no number
            # Clay sometimes shows "Run all rows that haven't run or have errors" without a count
            if count == 0 and import_rows > 0:
                count = import_rows
                logger.info(f"[ENRICHMENT] No count in button text, using import_rows={import_rows}")
            elif count == 0 and expected_count:
                count = expected_count
                logger.info(f"[ENRICHMENT] No count in button text, using expected_count={expected_count}")

            logger.info(f"[ENRICHMENT] Successfully triggered enrichment for {count} profiles")

            if expected_count and count > 0 and count != expected_count:
                logger.warning(
                    f"[ENRICHMENT] Count mismatch: enrichment reports {count} rows, "
                    f"expected {expected_count}"
                )

            time.sleep(3)
            _take_filter_screenshot("enrichment_03_run_all")
            return {"count": count, "started": True, "import_rows": import_rows}

        # If "Run all" not found, check if there's a different text pattern
        # Try looking for just "rows that haven't run"
        logger.info("[ENRICHMENT] 'Run all' not found. Trying 'rows that haven' pattern...")
        alt_clicked, alt_result, alt_line = _find_and_click_snapshot(
            "rows that haven", max_retries=2
        )
        if alt_clicked and alt_line:
            count_match = _re.search(r'([\d,]+)\s+rows?', alt_line)
            count = int(count_match.group(1).replace(',', '')) if count_match else 0
            # Fallback to import_rows or expected_count
            if count == 0 and import_rows > 0:
                count = import_rows
                logger.info(f"[ENRICHMENT] Alt pattern: no count in text, using import_rows={import_rows}")
            elif count == 0 and expected_count:
                count = expected_count
            logger.info(f"[ENRICHMENT] Alt pattern triggered enrichment for {count} profiles")
            time.sleep(3)
            _take_filter_screenshot("enrichment_03_run_all_alt")
            return {"count": count, "started": True, "import_rows": import_rows}

        # Log diagnostic snapshot for debugging
        logger.info("[ENRICHMENT] Taking diagnostic snapshot...")
        diag_snapshot = run_agent_browser_command(["snapshot"])
        if diag_snapshot:
            for i, line in enumerate(diag_snapshot.split('\n')):
                if any(kw in line.lower() for kw in ['run', 'column', 'profile', 'menu', 'dialog']):
                    logger.info(f"[ENRICHMENT] Diag line {i}: {line.strip()[:120]}")

        logger.error("[ENRICHMENT] Failed: Could not find 'Run all' option after all attempts")
        return {"count": 0, "started": False, "error": "Run all option not found", "import_rows": import_rows}

    except Exception as e:
        logger.error(f"[ENRICHMENT] Exception during enrichment trigger: {e}")
        return {"count": 0, "started": False, "error": str(e)}

def run_automation_for_jobseeker(jobseeker: Dict[str, Any]):
    """
    Main agent loop for a single job seeker.
    """
    logger.info(f"Starting automation for JobSeeker: {jobseeker.get('id')}")
    debug_state.reset_run(
        record_id=jobseeker.get("id", "unknown"),
        jobseeker_name=jobseeker.get("name", "Unknown"),
        max_turns=MAX_TURNS
    )

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
    CHAT_WINDOW_SIZE = 6  # Keep last 6 turn pairs — GPT-4o only verifies + clicks Add to table
    system_message = {"role": "system", "content": directive_text}
    chat_messages = []

    # 3b. Apply ALL filters deterministically BEFORE the GPT-4o loop
    logger.info("[FILTERS] Applying filters deterministically before GPT-4o loop...")
    filter_results = apply_filters_deterministic(search_criteria)
    logger.info(f"[FILTERS] Results: {json.dumps(filter_results)}")
    time.sleep(2)

    # 3c. Deterministically click "Add to table" — wait for loading, then click
    # This eliminates the need for GPT-4o in the happy path.
    # Clay disables the button with a loading spinner while computing results.
    logger.info("[IMPORT] Attempting deterministic 'Add to table' click...")
    record_id = jobseeker.get("id", "unknown")
    deterministic_result = click_add_to_table_deterministic(record_id=record_id)
    if deterministic_result:
        logger.info(f"[IMPORT] Deterministic import succeeded: {json.dumps(deterministic_result)}")
        debug_state.complete_run(deterministic_result)
        return deterministic_result
    logger.warning("[IMPORT] Deterministic import failed — falling back to GPT-4o verification loop")

    # Build filter summary for GPT-4o verification prompt (fallback path only)
    ai_seniority = search_criteria.get("seniority", [])
    ai_titles = search_criteria.get("titles", [])
    ai_exclude = search_criteria.get("excludeKeywords", [])
    ai_locations = search_criteria.get("locations", [])
    filter_summary_items = []
    if filter_results.get("seniority"):
        filter_summary_items.append(f"  OK Seniority: {', '.join(ai_seniority)}")
    if filter_results.get("titles"):
        filter_summary_items.append(f"  OK Job Titles: {', '.join(ai_titles)}")
    if filter_results.get("exclusions"):
        filter_summary_items.append(f"  OK Exclusions: {', '.join(ai_exclude)}")
    if filter_results.get("locations"):
        filter_summary_items.append(f"  OK Locations: {', '.join(ai_locations)}")
    if filter_results.get("limit"):
        filter_summary_items.append(f"  OK Import Limit: {IMPORT_LIMIT}")
    for fail in filter_results.get("failed_filters", []):
        filter_summary_items.append(f"  FAILED: {fail}")
    filter_summary = "\n".join(filter_summary_items)

    filter_reminder = f"""
FILTERS WERE APPLIED PROGRAMMATICALLY. Here are the results:
{filter_summary}

YOUR JOB:
1. Look at the snapshot — verify filter pills are visible ("Clear chip" buttons, "X filters" labels)
2. If all filters look correct, click the "Add to table" button (WAIT if it shows a loading spinner — it will become enabled once results are computed)
3. Handle any confirmation dialogs
4. Signal "done" after the page transitions away from the filter view
Do NOT re-apply filters — they are already set.
If "Add to table" is disabled/loading, wait a few seconds and try again — do NOT signal fail.
If a critical filter is visibly MISSING, report with {{"type": "fail", "reason": "Missing filter: X"}}
"""
    logger.info(f"[FILTERS] GPT-4o fallback: verification prompt ready")

    # 4. GPT-4o Fallback Loop (only reached if deterministic click failed)
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
        # Use -i for interactive elements only — compact, shows all filter inputs/pills/buttons
        snapshot_json = run_agent_browser_command(["snapshot", "-i"])
        
        # Check for hard failure in snapshot to avoid infinite loop
        if snapshot_json.startswith("Error:"):
             logger.error(f"Snapshot failed: {snapshot_json}")
             raise Exception(f"Browser Snapshot Failed: {snapshot_json}")

        # Smart truncation: keep first half + last half to preserve both top nav AND bottom buttons
        # Increased to 20000 to ensure filter sections (job titles, locations) are NOT truncated
        MAX_SNAPSHOT_CHARS = 20000
        if len(snapshot_json) > MAX_SNAPSHOT_CHARS:
            half = MAX_SNAPSHOT_CHARS // 2
            logger.info(f"Snapshot truncated: {len(snapshot_json)} -> {MAX_SNAPSHOT_CHARS} chars (first {half} + last {half})")
            snapshot_json = snapshot_json[:half] + "\n\n... [MIDDLE TRUNCATED] ...\n\n" + snapshot_json[-half:]
        
        # Debug: capture screenshot for this turn
        _debug_ss_path = debug_state.screenshot_path(turn)
        _debug_ss_ok = False
        try:
            _ss_res = run_agent_browser_command(["screenshot", _debug_ss_path])
            _debug_ss_ok = "Error" not in _ss_res
        except Exception:
            pass  # Never break automation for a debug screenshot

        # PAGE-STATE GUARD: ensure we're still on the find-people page
        current_url = run_agent_browser_command(["get", "url"]).strip()
        if "find-people" not in current_url.lower():
            if "login" in current_url.lower():
                logger.warning(f"[GUARD] Redirected to login page. Re-authenticating...")
                debug_state.record_turn(turn, snapshot_json[:500], {"type": "guard-relogin"}, "relogin", None, _debug_ss_ok)
                perform_login()
                run_agent_browser_command(["open", CLAY_URL])
                time.sleep(10)
                continue
            elif any(kw in current_url.lower() for kw in ["workbook", "table"]):
                logger.info(f"[GUARD] Page transitioned to table view: {current_url}")
                import_result = wait_for_import_completion(None)
                enrichment_result = trigger_enrichment(expected_count=None, import_result=import_result)
                _result = {
                    "success": True,
                    "profiles_triggered": enrichment_result.get("count", 0),
                    "enrichment_started": enrichment_result.get("started", False),
                    "import_rows": import_result.get("row_count", 0),
                }
                debug_state.record_turn(turn, snapshot_json[:500], {"type": "guard-table-transition"}, "auto-complete", None, _debug_ss_ok)
                debug_state.complete_run(_result)
                return _result
            else:
                logger.error(f"[GUARD] Unexpected page: {current_url}")
                debug_state.record_turn(turn, snapshot_json[:500], {"type": "guard-unexpected"}, current_url, None, _debug_ss_ok)
                debug_state.fail_run(f"Unexpected page: {current_url}")
                raise Exception(f"Unexpected page: {current_url}")

        # Build prompt with previous error if any
        error_context = ""
        if last_error:
            error_context = f"\n⚠️ PREVIOUS ACTION FAILED with error:\n{last_error}\nPlease try a different approach (e.g., use a more specific element ID, or a different strategy).\n"

        # Loop detection: if same action repeated 3+ times, inject hint
        loop_hint = ""
        if repeat_count >= 3:
            loop_hint = f"\n🔁 LOOP DETECTED: You have repeated the same action ({last_action_key}) {repeat_count} times. You MUST choose a DIFFERENT action type. If you were using focus_placeholder, switch to type_and_enter with the value you want to type. Do NOT repeat the same action.\n"
            logger.warning(f"Loop detected: {last_action_key} repeated {repeat_count} times. Injecting hint.")

        # After turn 8, strongly nudge GPT-4o to click "Add to table" — filters are pre-applied
        completion_hint = ""
        if turn >= 8:
            completion_hint = f"""
⏰ URGENT: Turn {turn}/{MAX_TURNS}. Filters are already applied programmatically.
You MUST click "Add to table" NOW. Look for the button in the snapshot and click it immediately.
"""

        # Think — directive is in system message, only send snapshot + instructions per turn
        prompt = f"""{error_context}{loop_hint}{completion_hint}
{filter_reminder}

CURRENT PAGE STATE (Interactive Elements):
{snapshot_json}

INSTRUCTIONS:
Filters have been applied programmatically. Your job is to verify and click "Add to table".
Look for "Clear chip" buttons (indicate pills), "X filters" labels, and the "Add to table" button.
IMPORTANT: If "Add to table" button is disabled or shows a loading indicator, use "wait" to wait for it to become enabled. Do NOT signal fail for a loading button.
Return ONLY a JSON object with one of these structures:
{{"type": "click", "element_id": "@eX", "reason": "why"}}
{{"type": "wait", "seconds": 5, "reason": "Waiting for Add to table button to become enabled"}}
{{"type": "press", "key": "Enter", "reason": "Use for Enter, Escape, or other keys"}}
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

        # Loop detection: track repeated actions (include value to avoid false positives on different pill entries)
        action_key = f"{action_type}:{action.get('element_id', action.get('placeholder', ''))}:{action.get('value', '')}"
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
                    # Wait for import + trigger enrichment (stabilization mode)
                    import_result = wait_for_import_completion(None)
                    enrichment_result = trigger_enrichment(expected_count=None, import_result=import_result)
                    _result = {
                        "success": True,
                        "profiles_triggered": enrichment_result.get("count", 0),
                        "enrichment_started": enrichment_result.get("started", False),
                        "import_rows": import_result.get("row_count", 0),
                    }
                    debug_state.record_turn(turn, snapshot_json[:500], action, "done-table-view", None, _debug_ss_ok)
                    debug_state.complete_run(_result)
                    return _result
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
                    # Wait for import + trigger enrichment (stabilization mode)
                    import_result = wait_for_import_completion(None)
                    enrichment_result = trigger_enrichment(expected_count=None, import_result=import_result)
                    _result = {
                        "success": True,
                        "profiles_triggered": enrichment_result.get("count", 0),
                        "enrichment_started": enrichment_result.get("started", False),
                        "import_rows": import_result.get("row_count", 0),
                    }
                    debug_state.record_turn(turn, snapshot_json[:500], action, "done-button-gone", None, _debug_ss_ok)
                    debug_state.complete_run(_result)
                    return _result
            # Default accept: not on login, not on find-people — likely transitioned
            logger.info(f"Completion accepted (default): URL={verify_url}")
            # Wait for import + trigger enrichment (stabilization mode)
            import_result = wait_for_import_completion(None)
            enrichment_result = trigger_enrichment(expected_count=None, import_result=import_result)
            _result = {
                "success": True,
                "profiles_triggered": enrichment_result.get("count", 0),
                "enrichment_started": enrichment_result.get("started", False),
                "import_rows": import_result.get("row_count", 0),
            }
            debug_state.record_turn(turn, snapshot_json[:500], action, "done-default", None, _debug_ss_ok)
            debug_state.complete_run(_result)
            return _result
        elif action_type == "fail":
            logger.warning(f"Agent reported failure: {action.get('reason')}")
            # Auto-recovery: try clicking "Add to table" before accepting failure
            logger.info("Attempting auto-recovery: clicking 'Add to table' via JS...")

            # Capture search count (import limit already set early in flow)
            recovery_search_count = capture_search_count()

            add_js = """
                let btns = document.querySelectorAll('button, a, [role="button"], [class*="button"]');
                let found = null;
                for (let b of btns) {
                    if (b.textContent.trim().toLowerCase().includes('add to table')) {
                        found = b;
                        break;
                    }
                }
                if (found) { found.scrollIntoView(); found.click(); 'Clicked: ' + found.textContent.trim() }
                else { 'Button not found' }
            """
            add_res = run_agent_browser_command(["eval", add_js])
            logger.info(f"Auto-recovery result: {add_res}")
            if "Clicked" in add_res:
                logger.info("Auto-recovery succeeded: 'Add to table' clicked. Waiting for import...")
                import_result = wait_for_import_completion(recovery_search_count)
                enrichment_result = trigger_enrichment(
                    expected_count=recovery_search_count,
                    import_result=import_result
                )
                _result = {
                    "success": True,
                    "profiles_triggered": enrichment_result.get("count", 0),
                    "enrichment_started": enrichment_result.get("started", False),
                    "import_rows": import_result.get("row_count", 0),
                }
                debug_state.record_turn(turn, snapshot_json[:500], action, "fail-recovered", None, _debug_ss_ok)
                debug_state.complete_run(_result)
                return _result
            else:
                # Button not found — check if page already transitioned (button was clicked in a previous turn)
                check_url = run_agent_browser_command(["get", "url"]).strip()
                logger.info(f"Auto-recovery: button not found, checking URL: {check_url}")
                if "find-people" not in check_url.lower() and "login" not in check_url.lower():
                    logger.info("Page already transitioned — waiting for import with stabilization mode...")
                    import_result = wait_for_import_completion(None)
                    enrichment_result = trigger_enrichment(
                        expected_count=None,
                        import_result=import_result
                    )
                    _result = {
                        "success": True,
                        "profiles_triggered": enrichment_result.get("count", 0),
                        "enrichment_started": enrichment_result.get("started", False),
                        "import_rows": import_result.get("row_count", 0),
                    }
                    debug_state.record_turn(turn, snapshot_json[:500], action, "fail-page-transitioned", None, _debug_ss_ok)
                    debug_state.complete_run(_result)
                    return _result
                logger.error("Auto-recovery failed: 'Add to table' button not found and page hasn't transitioned.")
                debug_state.record_turn(turn, snapshot_json[:500], action, "fail-unrecoverable", action.get('reason'), _debug_ss_ok)
                debug_state.fail_run(f"Agent Failure: {action.get('reason')}")
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
            
        elif action_type == "wait":
            wait_secs = min(action.get("seconds", 5), 15)  # Cap at 15 seconds
            logger.info(f"Agent waiting {wait_secs}s: {action.get('reason', 'no reason')}")
            time.sleep(wait_secs)

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
            # Uses snapshot -i to find the target input ref instead of broken `fill :focus`.
            val = action.get("value")
            ph = action.get("placeholder", "")

            # Split comma-separated values if needed
            if "," in val:
                parts = [v.strip() for v in val.split(",") if v.strip()]
                if len(parts) > 1 and all(len(p) > 3 for p in parts):
                    values = parts
                else:
                    values = [val]
            else:
                values = [val]
            logger.info(f"type_and_enter: {len(values)} value(s) to enter")

            snap = run_agent_browser_command(["snapshot", "-i"])
            any_error = None
            for i, single_val in enumerate(values):
                # Find the target input via snapshot -i
                input_ref = None

                # Strategy 1: find expanded combobox (indicates active input)
                for line in snap.split('\n'):
                    if ('combobox' in line.lower() or 'textbox' in line.lower()) and '[ref=' in line:
                        if '[expanded]' in line:
                            parts = line.split('[ref=')
                            if len(parts) > 1:
                                input_ref = parts[1].split(']')[0]
                                break

                # Strategy 2: use placeholder text from action
                if not input_ref and ph:
                    input_ref = parse_ref(snap, ph)

                # Strategy 3: find unlabeled combobox not matching known sections
                if not input_ref:
                    for line in snap.split('\n'):
                        if 'combobox' in line.lower() and '[ref=' in line:
                            if not any(kw in line.lower() for kw in ['seniority', 'function', 'cities', 'countries', 'regions', 'states']):
                                parts = line.split('[ref=')
                                if len(parts) > 1:
                                    input_ref = parts[1].split(']')[0]
                                    break

                if input_ref:
                    res = run_agent_browser_command(["fill", f"@{input_ref}", single_val])
                    if res and res.startswith("Error:"):
                        any_error = res
                        logger.warning(f"Type (Fill) failed for '{single_val}': {res}")
                        break
                    time.sleep(1)
                    run_agent_browser_command(["press", "Enter"])
                    time.sleep(1)
                    run_agent_browser_command(["press", "Escape"])
                    time.sleep(0.5)
                    snap = run_agent_browser_command(["snapshot", "-i"])
                    logger.info(f"Pill {i+1}/{len(values)} entered: '{single_val}'")
                else:
                    # Fallback: JS execCommand on active element
                    safe_val = single_val.replace("'", "\\'")
                    run_agent_browser_command(["eval",
                        f"document.activeElement && document.execCommand('insertText', false, '{safe_val}')"])
                    time.sleep(0.5)
                    run_agent_browser_command(["press", "Enter"])
                    time.sleep(1)
                    snap = run_agent_browser_command(["snapshot", "-i"])
                    logger.info(f"Pill {i+1}/{len(values)} entered via JS fallback: '{single_val}'")

            if any_error:
                last_error = any_error
            
        elif action_type == "click_by_text":
            # Click a button/link by its visible text content using JS (case-insensitive).
            btn_text = action.get("text", "")

            # PRE-CLICK: Capture search count before page transitions (limit already set early)
            expected_search_count = None
            if "add to table" in btn_text.lower():
                expected_search_count = capture_search_count()

            safe_text = btn_text.replace('"', '\\"').lower()
            click_js = f"""
                let btns = document.querySelectorAll('button, a, [role="button"], [class*="button"]');
                let found = null;
                for (let b of btns) {{
                    if (b.textContent.trim().toLowerCase().includes('{safe_text}')) {{
                        found = b;
                        break;
                    }}
                }}
                if (found) {{ found.scrollIntoView(); found.click(); 'Clicked: ' + found.textContent.trim() }}
                else {{ 'Button not found: {safe_text}' }}
            """
            res = run_agent_browser_command(["eval", click_js])
            logger.info(f"click_by_text result: {res}")
            if "Button not found" in res:
                # Auto-recovery: scroll sidebar to top and retry
                logger.info("Button not found — scrolling sidebar to top and retrying...")
                reset_js = """
                    let panels = document.querySelectorAll('[class*="sidebar"], [class*="filter"], [class*="panel"], [class*="scroll"]');
                    for (let p of panels) { p.scrollTop = 0; }
                    window.scrollTo(0, 0);
                    'Reset scroll'
                """
                run_agent_browser_command(["eval", reset_js])
                time.sleep(1)
                # Retry click
                res2 = run_agent_browser_command(["eval", click_js])
                logger.info(f"click_by_text retry result: {res2}")
                if "Button not found" in res2:
                    last_error = f"Button '{btn_text}' not found even after scroll reset"
                else:
                    time.sleep(2)
            else:
                time.sleep(2)  # Wait for UI reaction
                # Auto-complete: if we just clicked "Add to table", the import is triggered
                if "add to table" in btn_text.lower():
                    logger.info("'Add to table' clicked successfully — import triggered.")

                    # Wait for profiles to finish importing into the table
                    import_result = wait_for_import_completion(expected_search_count)

                    # Trigger enrichment after import is verified
                    enrichment_result = trigger_enrichment(
                        expected_count=expected_search_count,
                        import_result=import_result
                    )

                    _result = {
                        "success": True,
                        "profiles_triggered": enrichment_result.get("count", 0),
                        "enrichment_started": enrichment_result.get("started", False),
                        "import_rows": import_result.get("row_count", 0),
                        "import_matched": import_result.get("matched", False),
                    }
                    debug_state.record_turn(turn, snapshot_json[:500], action, "add-to-table", None, _debug_ss_ok)
                    debug_state.complete_run(_result)
                    return _result

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

        # Debug: record this turn's outcome
        debug_state.record_turn(
            turn=turn,
            snapshot_preview=snapshot_json[:500] if snapshot_json else "",
            action=action,
            action_result=last_error if last_error else "success",
            error=last_error,
            has_screenshot=_debug_ss_ok,
        )

    logger.warning("Max turns reached without completion.")
    debug_state.fail_run("Timeout: Max turns reached")
    raise Exception("Timeout: Max turns reached")
