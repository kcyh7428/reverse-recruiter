"""
Persistent logging for scheduler polling activity.
Logs are stored in JSON Lines format for easy parsing and querying.
"""
import json
import os
import fcntl
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Log file location
LOG_DIR = Path("/app/logs")
LOG_FILE = LOG_DIR / "scheduler_runs.jsonl"
MAX_LOG_ENTRIES = 1000  # Keep last 1000 entries
MAX_LOG_SIZE_MB = 10  # Rotate if file exceeds 10MB

# In-memory cache for current poll (used for updating start -> complete)
_current_polls: Dict[str, Dict[str, Any]] = {}


def _ensure_log_directory():
    """Create log directory if it doesn't exist."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"[SCHEDULER_LOGGER] Log directory ensured: {LOG_DIR}")
    except Exception as e:
        logger.error(f"[SCHEDULER_LOGGER] Failed to create log directory: {e}")


def _write_log_entry(entry: Dict[str, Any]):
    """
    Write a single log entry to the JSON Lines file.
    Uses file locking to ensure thread-safe writes.
    """
    _ensure_log_directory()

    try:
        # Append to log file with file locking
        with open(LOG_FILE, 'a') as f:
            # Acquire exclusive lock
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                # Write JSON line
                f.write(json.dumps(entry) + '\n')
                f.flush()
            finally:
                # Release lock
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        logger.debug(f"[SCHEDULER_LOGGER] Logged entry: {entry.get('poll_id')}")

        # Check if rotation is needed
        _rotate_logs_if_needed()

    except Exception as e:
        logger.error(f"[SCHEDULER_LOGGER] Failed to write log entry: {e}")


def _rotate_logs_if_needed():
    """
    Rotate logs if file size exceeds limit or entry count exceeds max.
    Keeps only the most recent entries.
    """
    try:
        if not LOG_FILE.exists():
            return

        # Check file size
        file_size_mb = LOG_FILE.stat().st_size / (1024 * 1024)

        if file_size_mb > MAX_LOG_SIZE_MB:
            logger.info(f"[SCHEDULER_LOGGER] Rotating logs (size: {file_size_mb:.2f}MB)")
            _perform_rotation()
            return

        # Check entry count
        with open(LOG_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                line_count = sum(1 for _ in f)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        if line_count > MAX_LOG_ENTRIES:
            logger.info(f"[SCHEDULER_LOGGER] Rotating logs (entries: {line_count})")
            _perform_rotation()

    except Exception as e:
        logger.error(f"[SCHEDULER_LOGGER] Error checking log rotation: {e}")


def _perform_rotation():
    """
    Perform log rotation by keeping only the most recent MAX_LOG_ENTRIES.
    """
    try:
        # Read all entries
        with open(LOG_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                entries = [line.strip() for line in f if line.strip()]
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Keep only last MAX_LOG_ENTRIES
        entries_to_keep = entries[-MAX_LOG_ENTRIES:]

        # Write back to file
        with open(LOG_FILE, 'w') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                for entry in entries_to_keep:
                    f.write(entry + '\n')
                f.flush()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        logger.info(f"[SCHEDULER_LOGGER] Log rotation complete. Kept {len(entries_to_keep)} entries.")

    except Exception as e:
        logger.error(f"[SCHEDULER_LOGGER] Error performing log rotation: {e}")


def log_poll_start(poll_id: str):
    """
    Log the start of a scheduler poll.

    Args:
        poll_id: Unique identifier for this poll (e.g., "poll_1234567890")
    """
    start_time = datetime.now(timezone.utc)

    entry = {
        "poll_id": poll_id,
        "timestamp": start_time.isoformat(),
        "status": "started",
        "records_found": None,
        "records_processed": [],
        "duration_seconds": None,
        "error": None
    }

    # Store in memory for later update
    _current_polls[poll_id] = {
        "start_time": start_time,
        "entry": entry
    }

    _write_log_entry(entry)
    logger.info(f"[SCHEDULER_LOGGER] Poll started: {poll_id}")


def log_poll_complete(poll_id: str, results: Dict[str, Any]):
    """
    Log the completion of a scheduler poll.

    Args:
        poll_id: Unique identifier for this poll
        results: Dictionary containing poll results:
            - records_found (int): Number of records found
            - records_processed (list): List of processed record details
            - status (str, optional): 'skipped' if automation was already running
            - message (str, optional): Additional message (e.g., "Automation already running")
    """
    end_time = datetime.now(timezone.utc)

    # Calculate duration
    duration_seconds = None
    if poll_id in _current_polls:
        start_time = _current_polls[poll_id]["start_time"]
        duration_seconds = (end_time - start_time).total_seconds()

    entry = {
        "poll_id": poll_id,
        "timestamp": end_time.isoformat(),
        "status": results.get("status", "success"),
        "records_found": results.get("records_found", 0),
        "records_processed": results.get("records_processed", []),
        "duration_seconds": duration_seconds,
        "error": None,
        "message": results.get("message")
    }

    _write_log_entry(entry)
    logger.info(f"[SCHEDULER_LOGGER] Poll completed: {poll_id} - {entry['status']}")

    # Clean up in-memory cache
    if poll_id in _current_polls:
        del _current_polls[poll_id]


def log_poll_error(poll_id: str, error: str):
    """
    Log an error during a scheduler poll.

    Args:
        poll_id: Unique identifier for this poll
        error: Error message or exception string
    """
    end_time = datetime.now(timezone.utc)

    # Calculate duration
    duration_seconds = None
    if poll_id in _current_polls:
        start_time = _current_polls[poll_id]["start_time"]
        duration_seconds = (end_time - start_time).total_seconds()

    entry = {
        "poll_id": poll_id,
        "timestamp": end_time.isoformat(),
        "status": "failure",
        "records_found": 0,
        "records_processed": [],
        "duration_seconds": duration_seconds,
        "error": str(error)
    }

    _write_log_entry(entry)
    logger.error(f"[SCHEDULER_LOGGER] Poll failed: {poll_id} - {error}")

    # Clean up in-memory cache
    if poll_id in _current_polls:
        del _current_polls[poll_id]


def get_recent_logs(limit: int = 50, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve recent log entries.

    Args:
        limit: Maximum number of entries to return (default: 50)
        status_filter: Optional status filter ('success', 'failure', 'skipped', 'started')

    Returns:
        List of log entries (most recent first)
    """
    _ensure_log_directory()

    if not LOG_FILE.exists():
        logger.warning("[SCHEDULER_LOGGER] Log file does not exist yet")
        return []

    try:
        entries = []

        with open(LOG_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)

                        # Apply status filter if provided
                        if status_filter and entry.get("status") != status_filter:
                            continue

                        entries.append(entry)

                    except json.JSONDecodeError as e:
                        logger.warning(f"[SCHEDULER_LOGGER] Malformed JSON line: {e}")
                        continue

            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Return most recent first, limited
        return entries[-limit:][::-1]

    except Exception as e:
        logger.error(f"[SCHEDULER_LOGGER] Error reading logs: {e}")
        return []


def get_log_stats() -> Dict[str, Any]:
    """
    Get statistics about scheduler logs.

    Returns:
        Dictionary with stats: total_polls, success_count, failure_count, etc.
    """
    _ensure_log_directory()

    if not LOG_FILE.exists():
        return {
            "total_polls": 0,
            "success_count": 0,
            "failure_count": 0,
            "skipped_count": 0,
            "file_size_mb": 0
        }

    try:
        stats = {
            "total_polls": 0,
            "success_count": 0,
            "failure_count": 0,
            "skipped_count": 0,
            "started_count": 0
        }

        with open(LOG_FILE, 'r') as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        status = entry.get("status", "unknown")

                        stats["total_polls"] += 1

                        if status == "success":
                            stats["success_count"] += 1
                        elif status == "failure":
                            stats["failure_count"] += 1
                        elif status == "skipped":
                            stats["skipped_count"] += 1
                        elif status == "started":
                            stats["started_count"] += 1

                    except json.JSONDecodeError:
                        continue

            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

        # Add file size
        stats["file_size_mb"] = round(LOG_FILE.stat().st_size / (1024 * 1024), 2)

        return stats

    except Exception as e:
        logger.error(f"[SCHEDULER_LOGGER] Error getting log stats: {e}")
        return {"error": str(e)}
