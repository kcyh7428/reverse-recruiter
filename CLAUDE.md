# Reverse Recruiter

AI-powered recruiting automation. Takes job seeker profiles from Airtable, uses OpenAI GPT-4o to interpret targeting criteria, then automates Clay.com's People Search via a headless Chromium browser.

## Architecture

3-layer system:
- **Directives** (`directives/`) -- Markdown SOPs that tell the AI what to do step-by-step
- **Orchestration** (`execution/agent_orchestrator.py`) -- OpenAI GPT-4o decision loop + deterministic filter/import/enrichment pipeline
- **Execution** (`execution/`) -- Deterministic Python: Flask server, Airtable client, login flow, cookie management

## Key Files

```
execution/
  main.py                  -- Flask entrypoint (health, test, /run-automation, /debug/* endpoints)
  agent_orchestrator.py    -- Core automation loop (the "brain")
  airtable_client.py       -- Reads/writes JobSeeker records from Airtable
  debug_state.py           -- Thread-safe debug state: screenshots, run history, status tracking
  Dockerfile               -- Playwright + Node.js + Python container
  requirements.txt         -- Python dependencies
  session_cookies.json     -- Clay auth cookies (not committed)
  local_test.sh            -- Run locally with Docker (--shm-size=2gb)
  execute_local.py         -- Run a single JobSeeker locally (headed mode)
docker-compose.yml         -- Root compose file (used by Hostinger API deployment)
execution/docker-compose.yml -- Local development compose file
directives/
  clay_directive.md        -- Step-by-step instructions for the browser agent
.agent/skills/             -- Browser automation skill definitions
```

## How It Works

1. HTTP POST to `/run-automation?record_id=<ID>` triggers automation
2. Airtable record is fetched with targeting criteria (titles, geos, seniority, industries)
3. GPT-4o interprets raw criteria into optimized search parameters
4. `agent-browser` CLI (Playwright wrapper) opens Clay.com in Chromium
5. **Deterministic filter application** (`apply_filters_deterministic()`):
   - Seniority pills (e.g., VP, Director)
   - Job title pills (one at a time, no Escape between pills)
   - Exclusion titles (one at a time)
   - Country autocomplete (fuzzy match + click dropdown option)
   - City pills (one at a time)
   - Limit (e.g., 100)
   - Per-step screenshots saved for debugging
6. "Add to table" click → `wait_for_import_completion()` polls until row count matches expected
7. `trigger_enrichment()` clicks "Create Profile" column header → "Run column" → "Run all X rows" to send profiles to n8n webhook
8. Airtable status updated to "Ready to Launch"

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

## Infrastructure

**Hostinger VPS** (KVM4, 16GB RAM, Ubuntu 24.04, Docker)
- **VM ID:** 1311295
- **IP:** 72.62.253.226
- **Project name:** `clay-automation`
- **GitHub repo:** `https://github.com/kcyh7428/reverse-recruiter`

The VPS gives native `/dev/shm` support via `--shm-size=2gb`, eliminating the `os error 11` crashes that occurred on the previous Cloud Run deployment due to gVisor's sandbox restrictions.

## Deploy to VPS (Hostinger API)

Deployment uses GitHub-based deployment via Hostinger VPS API. No SSH required.

```bash
# 1. Commit and push changes
git add <files> && git commit -m "your message" && git push origin main

# 2. Deploy via Hostinger MCP tools (from Claude Code)
#    Call VPS_createNewProjectV1:
#      virtualMachineId: 1311295
#      project_name: "clay-automation"
#      content: "https://github.com/kcyh7428/reverse-recruiter"
#      environment: (env vars from execution/.env)
#
#    The API clones the repo, finds root docker-compose.yml, builds Docker image, starts container.

# 3. Verify
curl http://72.62.253.226:8080/
```

**SSH fallback** (may hit rate limits): `./execution/deploy_vps.sh <vps-ip>`

**View logs:** Use `VPS_getProjectLogsV1(virtualMachineId=1311295, project_name="clay-automation")`

## Debug Dashboard

The `/debug/*` endpoints provide real-time visibility into automation runs:

```bash
curl http://72.62.253.226:8080/debug/status          # Current run status + recent history
curl http://72.62.253.226:8080/debug/screenshots      # List all named screenshots
curl http://72.62.253.226:8080/debug/screenshot/<name> # View a specific screenshot
curl http://72.62.253.226:8080/debug/download          # Download all screenshots as tar.gz
```

Screenshots are taken at each filter step (`filter_01_seniority`, `filter_02_title_1`, etc.), during import polling (`import_poll_22`, `import_complete`), and at each enrichment step (`enrichment_01_header_click`, `enrichment_02_run_column`, `enrichment_03_run_all`).

## Important Patterns

- **Deterministic login**: Never rely on AI to navigate login. Use `perform_login()` with hardcoded 15/10/25 second waits for Clay's heavy React app.
- **Deterministic filters**: `apply_filters_deterministic()` handles all filter types with hardcoded selectors. No AI decision-making needed for filters.
- **No Escape between pills**: Pressing Escape between title/exclusion pills kills the combobox. Only press Escape AFTER finishing all selections in a category.
- **Country autocomplete**: Free-text Enter does NOT create valid country filters. Must use fuzzy matching + click the dropdown option.
- **Import stabilization**: `wait_for_import_completion()` resets its stable streak when count is below expected, preventing early exit at partial counts (e.g., 22/100).
- **Browser recycling**: Every N turns, close and reopen the browser daemon to prevent resource leaks.
- **Daemon handling**: `agent-browser` runs as a daemon. Always `close` before `open` to apply new args. Handle "daemon already running" warnings gracefully.
- **Stealth mode**: `--disable-blink-features=AutomationControlled` hides `navigator.webdriver` from Clay's bot detection.
- **Hostinger deployment**: Always use GitHub push + `VPS_createNewProjectV1` API. Avoid SSH to prevent rate limiting.

## Agent Operating Principles

1. **Check for tools first** — Before writing a script, check `execution/` for existing tools per the directive. Only create new scripts if none exist.
2. **Self-anneal when things break** — Read error message and stack trace → fix the script → test again → update the directive with what you learned (API limits, timing, edge cases).
3. **Update directives as you learn** — Directives are living documents. When you discover API constraints, better approaches, or common errors, update the directive. Don't create or overwrite directives without asking.

## Skills (Browser Automation)

For complex, multi-step browser automation, use **Skills** (`.agent/skills/`) instead of writing inline code.

| Skill | Purpose |
|-------|---------|
| `agent-browser` | CLI reference for web automation |
| `clay-people-search` | Automate Clay's "Find People" search interface |
| `clay-profile-review-link` | Review imported profiles and link to JobSeeker |
| `clay-bulk-delete` | Clear all rows from Clay table |

**When to use Skills vs Directives:**
- **Skills**: Complex browser automation with many steps, element refs, error handling
- **Directives**: Simple SOPs for manual processes, API integrations, data processing

## Testing Endpoints

```bash
curl http://72.62.253.226:8080/                     # Health check
curl http://72.62.253.226:8080/test-connectivity    # Browser can reach internet
curl http://72.62.253.226:8080/test-clay-access     # Browser can reach Clay login
curl http://72.62.253.226:8080/test-clay-auth       # Full auth flow works
curl -X POST "http://72.62.253.226:8080/run-automation?record_id=recfV7X8d6XccguoL"  # Test record
```

## Server Maintenance

```bash
# Docker cleanup (reclaim disk space)
docker system prune -f

# View logs via SSH (fallback if Hostinger API logs insufficient)
ssh root@72.62.253.226
docker logs clay-auto -f
docker logs clay-auto --since 1h

# Container resource usage
docker stats clay-auto --no-stream

# Disk space
df -h && docker system df
```
