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
            logger.error(f"Command failed: {cmd}\nStderr: {result.stderr}")
            return f"Error: {result.stderr}"
        return result.stdout
    except Exception as e:
        logger.error(f"Command exception: {e}")
        return str(e)

def run_automation_for_jobseeker(jobseeker: Dict[str, Any]):
    """
    Main agent loop for a single job seeker.
    """
    logger.info(f"Starting automation for JobSeeker: {jobseeker.get('id')}")
    
    # 1. Initialize Browser
    # Assuming agent-browser keeps state internally or via a session file. 
    # For concurrent Cloud Run requests, this simple CLI usage might conflict if it uses a singleton global state 
    # but Vercel agent-browser usually spins up a browser process.
    # We start by opening the URL.
    
    # NOTE: The directive has the URL, but we need to open it first.
    # Hardcoded URL for initialization (matches directive)
    CLAY_URL = "https://app.clay.com/workspaces/579795/w/find-people?destinationTableId=t_0t6pb5u5rFNYudNfngq&workbookId=wb_0t6pb5rpbgD8nRCHvYh"
    
    logger.info("Opening Clay...")
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
        if action_type == "done":
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
