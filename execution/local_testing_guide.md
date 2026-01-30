# Local Testing Guide for Clay Automation

This guide explains how to run the browser automation agent locally using Docker. This setup mimics the production VPS environment.

## Prerequisites

1.  **Docker Desktop** installed and running.
2.  **`execution/session_cookies.json`** populated with valid cookies from `app.clay.com`.
3.  **Terminal** access.

## Quick Start

1.  **Open Terminal** and navigate to the project root:
    ```bash
    cd "/Users/keithmbpm2/Projects/Reverse Recruiter"
    ```

2.  **Run the Test Script**:
    ```bash
    ./execution/local_test.sh
    ```
    *This will build the Docker image (may take a few minutes the first time) and start the server on port 8080.*

3.  **Trigger the Automation**:
    In a new terminal window, run:
    ```bash
    curl -X POST http://localhost:8080/run-automation
    ```

4.  **Observe Logs**:
    The logs in the first terminal window will show the agent's progress:
    -   Opening Browser
    -   Injecting Cookies
    -   Navigating to Clay.com
    -   Processing JobSeekers

## Troubleshooting

-   **Build Failures**: Ensure you are in the project root. The script handles directory switching, but running from root is safest.
-   **"Connection Refused"**: The server hasn't started yet. Wait until you see `[INFO] Booting worker with pid: ...` in the logs.
-   **Login Screen**: If the agent gets stuck on the login screen, your cookies might be expired. Refresh `session_cookies.json` using the EditThisCookie extension.

## Troubleshooting & Knowledge Base

### 1. OpenAI API Key
The agent uses OpenAI GPT-4o for its decision loop. The `OPENAI_API_KEY` environment variable must be set.
**Fix:**
Ensure your `.env` file (in the project root or `execution/` directory) contains a valid OpenAI API key:
```
OPENAI_API_KEY=sk-...
```
The `local_test.sh` script loads this automatically from `.env` and passes it into the Docker container. If the key is missing or invalid, the agent will fail to make AI decisions during automation.

### 2. Browser "Executable doesn't exist" (Playwright Version Mismatch)
**Symptoms:** Error logs showing `browserType.launch: Executable doesn't exist` and a message about Playwright v1.58+.
**Cause:** The `agent-browser` package installs the latest Playwright library (e.g., v1.58), but our Docker image (`v1.49.0-jammy`) only has older browser binaries pre-installed.
**Fix (Implemented in Dockerfile):**
We use a "Downgrade Strategy" to pin `playwright-core` to match the Base Image.
```dockerfile
# In Dockerfile:
RUN npm install -g agent-browser \
    && cd "$(npm root -g)/agent-browser" \
    && npm install playwright-core@1.49.0
```

### 3. Browser Crash ("OS Error 11" / Resource temporarily unavailable)
**Symptoms:** The browser fails to open or crashes immediately with `os error 11`.
**Cause:** Docker doesn't have enough RAM/CPU allocated for the headless browser + Python app.
**Fix (Implemented in local_test.sh):**
We explicitly grant more resources to the container:
```bash
docker run ... --memory=2g --cpus=2 ...
```

### 4. Network/SSL Errors ("EOF occurred in violation of protocol")
**Symptoms:** `SSLEOFError` or `Connection timed out` during build or execution.
**Cause:**
*   **Build Time:** Flaky default Ubuntu mirrors. Fixed by adding `--fix-missing` in Dockerfile.
*   **Run Time:** Outdated Python SSL libraries. Fixed by adding `certifi`, `requests`, `urllib3` to `requirements.txt`.
*   **General:** Transient network glitches (like Docker registry `EOF` errors). **Solution:** Just retry the command.

### 5. Docker Build "Network Timed Out"
If `apt-get update` fails consistently:
*   Restart Docker Desktop.
*   Check your internet connection.
*   The Dockerfile already uses `--fix-missing` to handle minor glitches.
