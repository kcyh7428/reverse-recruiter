# Reverse Recruiter

AI-powered recruiting automation. Takes job seeker profiles from Airtable, uses OpenAI GPT-4o to interpret targeting criteria, then automates Clay.com's People Search via a headless Chromium browser.

## Architecture

3-layer system:
- **Directives** (`directives/`) -- Markdown SOPs that tell the AI what to do step-by-step
- **Orchestration** (`execution/agent_orchestrator.py`) -- OpenAI GPT-4o decision loop: snapshot page, decide action, execute, repeat
- **Execution** (`execution/`) -- Deterministic Python: Flask server, Airtable client, login flow, cookie management

## Key Files

```
execution/
  main.py                  -- Flask entrypoint (health, test, and /run-automation endpoints)
  agent_orchestrator.py    -- Core automation loop (the "brain")
  airtable_client.py       -- Reads/writes JobSeeker records from Airtable
  Dockerfile               -- Playwright + Node.js + Python container
  requirements.txt         -- Python dependencies
  session_cookies.json     -- Clay auth cookies (not committed)
  local_test.sh            -- Run locally with Docker (--shm-size=2gb)
  execute_local.py         -- Run a single JobSeeker locally (headed mode)
directives/
  clay_directive.md        -- Step-by-step instructions for the browser agent
.agent/skills/             -- Browser automation skill definitions
```

## How It Works

1. HTTP POST to `/run-automation?record_id=<ID>` triggers automation
2. Airtable record is fetched with targeting criteria (titles, geos, seniority, industries)
3. GPT-4o interprets raw criteria into optimized search parameters
4. `agent-browser` CLI (Playwright wrapper) opens Clay.com in Chromium
5. Turn loop: snapshot page -> GPT-4o decides next action -> execute (click/fill/press) -> repeat
6. When done, Airtable status updated to "Ready to Launch"

## Environment Variables

```
OPENAI_API_KEY          -- OpenAI API key
AIRTABLE_API_KEY        -- Airtable personal access token
AIRTABLE_BASE_ID        -- Default: app8KvRTUVMWeloR8
AIRTABLE_TABLE_NAME     -- Default: JobSeekers
CLAY_EMAIL              -- Clay.com login email
CLAY_PASSWORD           -- Clay.com login password
PORT                    -- Default: 8080
```

## Run Locally

```bash
# Option 1: Docker (matches production)
cd execution
./local_test.sh

# Option 2: Direct Python (needs agent-browser installed globally)
cd execution
python execute_local.py
```

## Infrastructure

**Infrastructure:** Hostinger VPS (KVM4, 16GB RAM, Ubuntu 24.04, Docker)

The VPS gives native `/dev/shm` support via `--shm-size=2gb`, eliminating the `os error 11` crashes that occurred on the previous Cloud Run deployment due to gVisor's sandbox restrictions.

## Deploy to VPS

```bash
# From local machine
./execution/deploy_vps.sh <vps-ip>
```

## Important Patterns

- **Deterministic login**: Never rely on AI to navigate login. Use `perform_login()` with hardcoded 15/10/25 second waits for Clay's heavy React app.
- **Browser recycling**: Every N turns, close and reopen the browser daemon to prevent resource leaks.
- **Daemon handling**: `agent-browser` runs as a daemon. Always `close` before `open` to apply new args. Handle "daemon already running" warnings gracefully.
- **Stealth mode**: `--disable-blink-features=AutomationControlled` hides `navigator.webdriver` from Clay's bot detection.

## Testing Endpoints

```bash
curl http://<host>:8080/                     # Health check
curl http://<host>:8080/test-connectivity    # Browser can reach internet
curl http://<host>:8080/test-clay-access     # Browser can reach Clay login
curl http://<host>:8080/test-clay-auth       # Full auth flow works
curl -X POST "http://<host>:8080/run-automation?record_id=recfV7X8d6XccguoL"  # Test record
```
