"""
Thread-safe shared debug state for the automation run.
Both agent_orchestrator.py and main.py import this module.
"""

import threading
import time
import os
from typing import Dict, Any, Optional, List

_lock = threading.Lock()

_run_state: Dict[str, Any] = {
    "status": "idle",
    "record_id": None,
    "jobseeker_name": None,
    "started_at": None,
    "current_turn": 0,
    "max_turns": 60,
    "last_action": None,
    "last_action_result": None,
    "last_error": None,
    "completed_at": None,
    "result": None,
    "turns": [],
}

SCREENSHOT_DIR = "/tmp/debug_screenshots"


def _ensure_screenshot_dir():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def screenshot_path(turn: int) -> str:
    _ensure_screenshot_dir()
    return os.path.join(SCREENSHOT_DIR, f"turn_{turn:03d}.png")


def named_screenshot_path(name: str) -> str:
    """Return path for a descriptively-named screenshot (e.g., 'filter_01_seniority')."""
    _ensure_screenshot_dir()
    safe_name = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in name)
    return os.path.join(SCREENSHOT_DIR, f"{safe_name}.png")


def list_screenshots() -> list:
    """Return sorted list of all screenshot filenames in the debug directory."""
    _ensure_screenshot_dir()
    return sorted([f for f in os.listdir(SCREENSHOT_DIR) if f.endswith('.png')])


def reset_run(record_id: str, jobseeker_name: str, max_turns: int = 60):
    with _lock:
        _run_state["status"] = "running"
        _run_state["record_id"] = record_id
        _run_state["jobseeker_name"] = jobseeker_name
        _run_state["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _run_state["current_turn"] = 0
        _run_state["max_turns"] = max_turns
        _run_state["last_action"] = None
        _run_state["last_action_result"] = None
        _run_state["last_error"] = None
        _run_state["completed_at"] = None
        _run_state["result"] = None
        _run_state["turns"] = []
    # Clean up old screenshots
    _ensure_screenshot_dir()
    for f in os.listdir(SCREENSHOT_DIR):
        try:
            os.remove(os.path.join(SCREENSHOT_DIR, f))
        except OSError:
            pass


def record_turn(turn: int, snapshot_preview: str, action: Optional[dict],
                action_result: str, error: Optional[str], has_screenshot: bool):
    turn_record = {
        "turn": turn,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "snapshot_preview": snapshot_preview[:500] if snapshot_preview else "",
        "action": action,
        "action_result": action_result,
        "error": error,
        "has_screenshot": has_screenshot,
        "screenshot_url": f"/debug/screenshot/{turn}" if has_screenshot else None,
    }
    with _lock:
        _run_state["current_turn"] = turn
        _run_state["last_action"] = action
        _run_state["last_action_result"] = action_result
        _run_state["last_error"] = error
        _run_state["turns"].append(turn_record)


def complete_run(result: dict):
    with _lock:
        _run_state["status"] = "completed" if result.get("success") else "failed"
        _run_state["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _run_state["result"] = result


def fail_run(error_message: str):
    with _lock:
        _run_state["status"] = "failed"
        _run_state["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _run_state["last_error"] = error_message
        _run_state["result"] = {"success": False, "error": error_message}


def get_status() -> Dict[str, Any]:
    with _lock:
        return {
            "status": _run_state["status"],
            "record_id": _run_state["record_id"],
            "jobseeker_name": _run_state["jobseeker_name"],
            "started_at": _run_state["started_at"],
            "current_turn": _run_state["current_turn"],
            "max_turns": _run_state["max_turns"],
            "last_action": _run_state["last_action"],
            "last_action_result": _run_state["last_action_result"],
            "last_error": _run_state["last_error"],
            "completed_at": _run_state["completed_at"],
            "result": _run_state["result"],
            "total_turns_recorded": len(_run_state["turns"]),
        }


def get_history() -> List[Dict]:
    with _lock:
        return list(_run_state["turns"])
