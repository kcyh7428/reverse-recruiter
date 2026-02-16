import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
import os
import requests
import atexit
import time
import scheduler_logger

logger = logging.getLogger(__name__)

# Scheduler instance (module-level singleton)
scheduler = None

def scheduled_poll_job():
    """
    Job function that triggers batch automation via internal HTTP call.
    This avoids import cycles and reuses existing concurrency control.
    Logs all poll activity to persistent JSON Lines log file.
    """
    # Generate unique poll ID
    poll_id = f"poll_{int(time.time())}"

    # Log poll start
    scheduler_logger.log_poll_start(poll_id)

    try:
        # Call the /run-automation endpoint internally
        # Use 127.0.0.1 to avoid DNS overhead
        port = os.environ.get("PORT", 8080)
        url = f"http://127.0.0.1:{port}/run-automation"

        logger.info(f"[SCHEDULER] {poll_id} - Triggering batch automation poll...")

        # Increase timeout to 600 seconds (10 minutes) for long-running automation
        response = requests.post(url, timeout=600)

        if response.status_code == 200:
            data = response.json()
            logger.info(f"[SCHEDULER] {poll_id} - Poll successful: {data}")

            # Log success with results
            scheduler_logger.log_poll_complete(poll_id, {
                'records_found': data.get('processed', 0),
                'records_processed': data.get('details', [])
            })

        elif response.status_code == 409:
            logger.info(f"[SCHEDULER] {poll_id} - Automation already running (409), skipping this poll")

            # Log as skipped (not an error)
            scheduler_logger.log_poll_complete(poll_id, {
                'records_found': 0,
                'status': 'skipped',
                'message': 'Automation already running (409)',
                'records_processed': []
            })

        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.warning(f"[SCHEDULER] {poll_id} - Unexpected response: {error_msg}")

            # Log as error
            scheduler_logger.log_poll_error(poll_id, error_msg)

    except requests.exceptions.Timeout:
        error_msg = "Poll request timed out after 600 seconds (automation may be running)"
        logger.warning(f"[SCHEDULER] {poll_id} - {error_msg}")

        # Log timeout as error
        scheduler_logger.log_poll_error(poll_id, error_msg)

    except Exception as e:
        error_msg = f"Poll job failed: {str(e)}"
        logger.error(f"[SCHEDULER] {poll_id} - {error_msg}", exc_info=True)

        # Log exception as error
        scheduler_logger.log_poll_error(poll_id, error_msg)

def job_listener(event):
    """Log scheduler events for debugging."""
    if event.exception:
        logger.error(f"[SCHEDULER] Job failed: {event.exception}")
    else:
        logger.debug(f"[SCHEDULER] Job completed successfully")

def start_scheduler(interval_minutes=None):
    """
    Initialize and start the background scheduler.

    Args:
        interval_minutes: Polling interval in minutes (default from env or 180)
    """
    global scheduler

    if scheduler is not None:
        logger.warning("[SCHEDULER] Scheduler already running")
        return

    # Read interval from env or use default (180 minutes = 3 hours)
    if interval_minutes is None:
        interval_minutes = int(os.environ.get("POLL_INTERVAL_MINUTES", "180"))

    logger.info(f"[SCHEDULER] Initializing scheduler with {interval_minutes} minute interval")

    # Create scheduler
    scheduler = BackgroundScheduler(
        daemon=True,  # Don't block app shutdown
        timezone='UTC'
    )

    # Add polling job
    scheduler.add_job(
        scheduled_poll_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id='airtable_poll',
        name='Poll Airtable for Pending JobSeekers',
        replace_existing=True,
        max_instances=1,  # Prevent concurrent runs of the job itself
        misfire_grace_time=300  # Allow 5 min grace if server is overloaded
    )

    # Add event listener
    scheduler.add_listener(job_listener, EVENT_JOB_ERROR | EVENT_JOB_EXECUTED)

    # Start scheduler
    scheduler.start()
    logger.info("[SCHEDULER] Scheduler started successfully")

    # Register shutdown hook
    atexit.register(shutdown_scheduler)

def shutdown_scheduler():
    """Gracefully shutdown the scheduler."""
    global scheduler
    if scheduler is not None:
        logger.info("[SCHEDULER] Shutting down scheduler...")
        scheduler.shutdown(wait=False)
        scheduler = None

def get_scheduler_status():
    """Return current scheduler status for debugging."""
    if scheduler is None:
        return {"running": False, "jobs": []}

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger)
        })

    return {
        "running": scheduler.running,
        "jobs": jobs
    }
