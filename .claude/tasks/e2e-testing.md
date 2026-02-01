# E2E Automation Testing Tracker

## Test Environment
- **VPS:** Hostinger KVM4, 72.62.253.226, 16GB RAM
- **Docker:** `--memory=8g --shm-size=2gb`
- **Container:** `clay-auto` (image: `clay-automation`)
- **Test Record:** `recfV7X8d6XccguoL`
- **Trigger:** `POST /run-automation?record_id=recfV7X8d6XccguoL`

## Deployment Checklist
- [x] Code pushed to GitHub (`main` branch)
- [x] `git pull` on VPS
- [x] Docker rebuild on VPS
- [x] Container running with `.env` loaded
- [x] Health check passes (`GET /`)

## Test Phases

| # | Phase | Status | Notes |
|---|-------|--------|-------|
| 1 | Init (browser daemon) | PASS | Close + open, stealth mode |
| 2 | Login (deterministic) | PASS | 15/10/25s waits for Clay React app |
| 3 | AI Interpret (GPT-4o) | PASS | Titles, locations, seniority, exclusions |
| 4 | Directive loaded | PASS | System message with substituted placeholders |
| 5 | Turn loop started | PASS | Snapshot → GPT-4o → execute, 13 turns |
| 6 | Filters applied | PASS | Seniority, 3 titles, 3 locations |
| 7 | Add to table clicked | PASS | click_by_text "Add to table" → auto-complete |
| 8 | Airtable updated TO Ready to Launch | PASS | Status: ✅ Ready to Launch |

## Verification Criteria
- [x] API returns `{"processed":1,"details":[{"id":"recfV7X8d6XccguoL","status":"success"}]}`
- [x] Docker logs show all phases without errors
- [x] "Add to table" clicked successfully (click_by_text)
- [x] Airtable status updated TO "✅ Ready to Launch"
- [x] Page transitions after "Add to table" click

## RESULT: PASS (Run 13, 2026-01-30)

## Known Issues & Resolutions

| Date | Issue | Resolution | Commit |
|------|-------|------------|--------|
| 2026-01-29 | `inject_cookies` NameError | Rewrote to use `perform_login()` | pre-session |
| 2026-01-29 | `tenacity` missing | Added `tenacity>=8.2.0` | pre-session |
| 2026-01-30 | Run 1: focus_placeholder infinite loop | Loop detection + removed from prompt | f82c8b9 |
| 2026-01-30 | Run 1: Chat history overflow (BadRequest) | Chat windowing (last N turns) | f82c8b9 |
| 2026-01-30 | Run 1: Airtable INVALID_MULTIPLE_CHOICE | Catch and log warning | f82c8b9 |
| 2026-01-30 | Run 2: `agent-browser find` not valid | JS eval + fill :focus | 10b1849 |
| 2026-01-30 | Run 3: Placeholder disappears after pill | fill :focus fallback | a516773 |
| 2026-01-30 | Run 3: Location aria-label not found | `focus_input_by_text()` shared helper | 55c5c76 |
| 2026-01-30 | Run 3: Directive in every turn (too large) | Moved to system message | 55c5c76 |
| 2026-01-30 | Run 4: False positive "done" after recycle | Completion verification + clear chat | 8e9258e |
| 2026-01-30 | Run 5: Recycling at 15 turns wipes filters | Increased to 50 turns | 67abb5d |
| 2026-01-30 | Run 6: Agent scrolls past filters, gets lost | Simplified directive: skip Limit | b737f59 |
| 2026-01-30 | Run 7: BadRequest at Turn 15 | Truncate snapshots to 6k chars | 534a698 |
| 2026-01-30 | Run 8: Comma-separated pill batching | Split values + smart truncation (first+last) | 3bbcc95 |
| 2026-01-30 | Run 9: Completion rejects table view URL | Accept workbook/table URL as success | 96d8b95 |
| 2026-01-30 | Run 9: City names split (SF, CA) | Only split when all parts >3 chars | 96d8b95 |
| 2026-01-30 | Run 10: False loop on different pill values | Include value in action key | 4ac92ed |
| 2026-01-30 | Run 10: click_by_text case-sensitive | Case-insensitive + scroll retry | 4ac92ed |
| 2026-01-30 | Run 11: Agent fails before trying Add to table | Auto-recovery: try Add to table on fail | fc509ef |
| 2026-01-30 | Run 12: Add to table clicked but not returned | Auto-complete on successful click_by_text | 83c9c25 |

## Test Run Summary

| Run | Result | Turns | Issue |
|-----|--------|-------|-------|
| 1 | FAIL | 20 | focus_placeholder loop + BadRequest |
| 2 | FAIL | 13 | agent-browser find not valid |
| 3 | FAIL | 14 | Placeholder disappears + BadRequest |
| 4 | FAIL | 18 | False positive done after recycle |
| 5 | FAIL | 24 | Recycling wipes filters |
| 6 | FAIL | 28 | Scrolled past filters, can't find Limit |
| 7 | FAIL | 15 | BadRequest (snapshot too large) |
| 8 | FAIL | 29 | Comma batching + Add to table not found |
| 9 | FAIL | 20 | Completion verification too strict |
| 10 | FAIL | 15 | Scroll lost, click_by_text case-sensitive |
| 11 | FAIL | 9 | Agent fails before trying Add to table |
| 12 | FAIL | 24 | Add to table clicked but not recognized |
| **13** | **PASS** | **13** | **All filters applied, Add to table clicked, Airtable updated** |
