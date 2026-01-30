# Agent Instructions

> This file is mirrored across CLAUDE.md and AGENTS.md so the same instructions load in any AI environment.

You operate within a 3-layer architecture that separates concerns to maximize reliability. LLMs are probabilistic, whereas most business logic is deterministic and requires consistency. This system fixes that mismatch.

## The 3-Layer Architecture

**Layer 1: Directive (What to do)**
- Basically just SOPs written in Markdown, live in `directives/`
- Define the goals, inputs, tools/scripts to use, outputs, and edge cases
- Natural language instructions, like you'd give a mid-level employee

**Layer 2: Orchestration (Decision making)**
- This is you. Your job: intelligent routing.
- Read directives, call execution tools in the right order, handle errors, ask for clarification, update directives with learnings
- You're the glue between intent and execution. E.g you don't try scraping websites yourself—you read `directives/scrape_website.md` and come up with inputs/outputs and then run `execution/scrape_single_site.py`

**Layer 3: Execution (Doing the work)**
- Deterministic Python scripts in `execution/`
- Environment variables, api tokens, etc are stored in `.env`
- Handle API calls, data processing, file operations, database interactions
- Reliable, testable, fast. Use scripts instead of manual work. Commented well.

**Why this works:** if you do everything yourself, errors compound. 90% accuracy per step = 59% success over 5 steps. The solution is push complexity into deterministic code. That way you just focus on decision-making.

## Operating Principles

**1. Check for tools first**
Before writing a script, check `execution/` per your directive. Only create new scripts if none exist.

**2. Self-anneal when things break**
- Read error message and stack trace
- Fix the script and test it again (unless it uses paid tokens/credits/etc—in which case you check w user first)
- Update the directive with what you learned (API limits, timing, edge cases)
- Example: you hit an API rate limit → you then look into API → find a batch endpoint that would fix → rewrite script to accommodate → test → update directive.

**3. Update directives as you learn**
Directives are living documents. When you discover API constraints, better approaches, common errors, or timing expectations—update the directive. But don't create or overwrite directives without asking unless explicitly told to. Directives are your instruction set and must be preserved (and improved upon over time, not extemporaneously used and then discarded).

## Self-annealing loop

Errors are learning opportunities. When something breaks:
1. Fix it
2. Update the tool
3. Test tool, make sure it works
4. Update directive to include new flow
5. System is now stronger

## Special Execution: Clay Authentication

Clay.com has strict bot detection and session management. To maintain reliability:

1. **Stealth Mode Layer**: Always use the stealth arguments (`--disable-blink-features=AutomationControlled`) and a realistic User-Agent to keep `navigator.webdriver` false.
2. **Auto-Login Fallback**: Cookie injection is fragile. Always implement an "Auto-Login" flow in scripts that detects expired sessions and uses `.env` credentials to log in.
3. **Dynamic Snapshot Parsing**: Do not hardcode element IDs if possible. scripts should parse the real-time snapshot to find `@ref` IDs, making the automation resilient to Clay's layout updates.

## Skills (Browser Automation)

For complex, multi-step browser automation (like Clay interactions), use **Skills** instead of writing inline code.

**Skills location:** `.agent/skills/`

| Skill | Purpose |
|-------|---------|
| `agent-browser` | CLI reference for web automation |
| `clay-people-search` | Automate Clay's "Find People" search interface |
| `clay-profile-review-link` | Review imported profiles and link to JobSeeker |
| `clay-bulk-delete` | Clear all rows from Clay table |

**When to use Skills vs Directives:**
- **Skills**: Complex browser automation with many steps, element refs, error handling
- **Directives**: Simple SOPs for manual processes, API integrations, data processing

## File Organization
...

**Deliverables vs Intermediates:**
- **Deliverables**: Google Sheets, Google Slides, or other cloud-based outputs that the user can access
- **Intermediates**: Temporary files needed during processing

**Directory structure:**
- `.tmp/` - All intermediate files (dossiers, scraped data, temp exports). Never commit, always regenerated.
- `execution/` - Python scripts (the deterministic tools)
- `directives/` - SOPs in Markdown (the instruction set)
- `.env` - Environment variables and API keys
- `credentials.json`, `token.json` - Google OAuth credentials (required files, in `.gitignore`)

**Key principle:** Local files are only for processing. Deliverables live in cloud services (Google Sheets, Slides, etc.) where the user can access them. Everything in `.tmp/` can be deleted and regenerated.

---

## VPS Deployment Procedures

> [!IMPORTANT]
> **NEVER DEVIATE from these procedures without explicit user approval.** A new agent picking up this project should follow these steps exactly.

### 1. VPS Access & Deploy Workflow

**Infrastructure:** Hostinger VPS (KVM4, 16GB RAM, Ubuntu 24.04, Docker)

```bash
# SSH into the VPS
ssh root@72.62.253.226

# Automated deploy (from local machine -- builds, pushes, and restarts on VPS)
./execution/deploy_vps.sh 72.62.253.226

# Manual deploy (on the VPS)
cd /root/reverse-recruiter
git pull origin main
cd execution
docker build -t clay-automation .
docker stop clay-auto && docker rm clay-auto
docker run -d --name clay-auto --restart=always \
  --memory=8g --shm-size=2gb \
  -p 8080:8080 \
  --env-file /root/reverse-recruiter/.env \
  clay-automation
```

**Key Infrastructure:**
| Component | Value |
|-----------|-------|
| VPS Provider | Hostinger (KVM4) |
| IP Address | `72.62.253.226` |
| OS | Ubuntu 24.04 |
| RAM | 16 GB |
| Container Name | `clay-auto` |
| Port | `8080` |
| Auth | None required (direct HTTP) |

**Docker Management Commands:**
```bash
# View logs
docker logs clay-auto --tail 50
docker logs clay-auto -f              # Follow live

# Restart container
docker restart clay-auto

# Stop and remove
docker stop clay-auto && docker rm clay-auto
```

### 2. Critical: Deterministic Login Pattern

> [!CAUTION]
> **The AI-driven login loop is UNRELIABLE.** It can enter infinite loops due to insufficient wait times for the heavy React app.

**THE WORKING PATTERN (always use this):**

```python
def perform_login() -> bool:
    """6-step deterministic login with explicit, generous waits."""
    # Step 1: Navigate to login page
    run_agent_browser_command(["open", "https://app.clay.com/login"])
    time.sleep(15)  # CRITICAL: 15s for initial page load

    # Step 2: Parse snapshot, find email ref, fill email
    snapshot = run_agent_browser_command(["snapshot"])
    email_ref = parse_ref(snapshot, "email")  # e.g., returns "e3"
    run_agent_browser_command(["fill", f"@{email_ref}", email])
    
    # Step 3: Click "Continue" explicitly (don't rely on Enter)
    cont_ref = parse_ref(snapshot, "Continue")
    run_agent_browser_command(["click", f"@{cont_ref}"])
    time.sleep(10)  # CRITICAL: Wait for password field to appear
    
    # Step 4: Fill password, click Continue
    pass_snapshot = run_agent_browser_command(["snapshot"])
    pass_ref = parse_ref(pass_snapshot, "password")
    run_agent_browser_command(["fill", f"@{pass_ref}", password])
    cont_ref_2 = parse_ref(pass_snapshot, "Continue")
    run_agent_browser_command(["click", f"@{cont_ref_2}"])
    
    # Step 5: Wait for heavy redirect/security check
    time.sleep(25)  # CRITICAL: Clay has heavy post-login processing
    
    # Step 6: Verify success
    # ... (check URL, snapshot for absence of "login")
```

**Why these wait times?**
- `15s` after opening login page: Clay's React bundle is large
- `10s` after email submit: Password field animates in
- `25s` after password submit: Heavy redirect, potential security checks

### 3. Testing Endpoints

```bash
# Health check
curl http://72.62.253.226:8080/

# Test browser connectivity
curl http://72.62.253.226:8080/test-connectivity

# Test Clay access
curl http://72.62.253.226:8080/test-clay-access

# Test full authentication flow
curl http://72.62.253.226:8080/test-clay-auth

# Trigger full automation for a JobSeeker
curl -X POST "http://72.62.253.226:8080/run-automation?record_id=recfV7X8d6XccguoL"
```

### 4. Common Pitfalls & Self-Annealing Lessons

| Problem | Root Cause | Fix |
|---------|-----------|-----|
| Infinite "Enter" loop during login | AI waits only 1-2s, page not ready | Use deterministic `perform_login()` with 15/10/25s waits |
| `os error 11` (Resource temporarily unavailable) | PID/Memory exhaustion during `fork()` | Ensure `--shm-size=2gb` and `--memory=8g` on `docker run` |
| Logs show old code after deploy | Image caching or wrong context | Always rebuild with `docker build` from `execution/` dir |
| "Welcome back" persists after login | Password field not found due to short wait | Increase wait to 10s after email submission |
| Container not starting | Port conflict or stale container | `docker stop clay-auto && docker rm clay-auto` then re-run |

---

## Summary

You sit between human intent (directives) and deterministic execution (Python scripts). Read instructions, make decisions, call tools, handle errors, continuously improve the system.

Be pragmatic. Be reliable. Self-anneal.

