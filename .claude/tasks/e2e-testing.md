# E2E Automation Testing Tracker

## Test Environment
- **VPS:** Hostinger KVM4, 72.62.253.226, 16GB RAM
- **Docker:** `--memory=8g --shm-size=2gb`
- **Container:** `clay-auto` (image: `clay-automation`)
- **Test Record:** `recfV7X8d6XccguoL`
- **Trigger:** `POST /run-automation?record_id=recfV7X8d6XccguoL`

## Deployment Checklist
- [x] Code pushed to GitHub (`main` branch)
- [ ] `git pull` on VPS
- [ ] Docker rebuild on VPS
- [ ] Container running with `.env` loaded
- [ ] Health check passes (`GET /`)

## Test Phases

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 1 | Init (browser daemon) | pending | |
| 2 | Login (deterministic) | pending | |
| 3 | AI Interpret (GPT-4o) | pending | |
| 4 | Directive loaded | pending | |
| 5 | Turn loop started | pending | |
| 6 | Filters applied | pending | |
| 7 | Add to table + screen change | pending | |
| 8 | Complete (Airtable updated TO Ready to Launch) | pending | |

## Verification Criteria
- [ ] API returns `{"status":"success"}` for the test record
- [ ] Docker logs show all phases without errors
- [ ] Agent signaled `{"type":"done"}`
- [ ] Airtable status updated TO "Ready to Launch"
- [ ] Screen changes after "Add to table" click

## Known Issues & Resolutions

| Date | Issue | Resolution | Status |
|------|-------|------------|--------|
| 2026-01-29 | `inject_cookies` NameError in `test_clay_auth` | Rewrote to use `perform_login()` | resolved |
| 2026-01-29 | `tenacity` missing from requirements.txt | Added `tenacity>=8.2.0` | resolved |
| 2026-01-29 | SSH rate limiting on VPS | Use single SSH sessions, wait between commands | workaround |
| 2026-01-29 | rsync/scp hang to VPS | Use git push + git pull on VPS instead | workaround |

## Test Run Log

### Run 1 — [pending]
- **Triggered:** TBD
- **Result:** TBD
- **Logs:** TBD
- **Failure Phase:** TBD
- **Action Taken:** TBD
