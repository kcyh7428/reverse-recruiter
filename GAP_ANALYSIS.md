# PRD Gap Analysis - February 2026

**Status**: E2E automation working (Run 13 success). Now adding missing PRD features.

## Current State (What Works)

✅ Airtable → GPT-4o interpretation → Clay People Search filters → "Add to table" import
✅ Deterministic login with stealth mode
✅ Smart snapshot truncation + chat windowing
✅ Loop detection + auto-recovery
✅ All 18 known bugs from Runs 1-13 fixed

## Gaps vs PRD (8 total)

| # | PRD Req | What's Missing | Priority |
|---|---------|----------------|----------|
| **G1** | FR-8 | After import, click ▶ "Create Profile" → "Run all rows" to trigger n8n webhook | **HIGH** |
| **G2** | FR-10 | Delete all rows from table after enrichment completes | **HIGH** (after G1) |
| **G3** | FR-11 | Write profile count + timestamp to Airtable | MEDIUM |
| **G4** | FR-12 | Write error messages to Airtable ErrorNotes field | MEDIUM |
| **G5** | FR-13 | Batch size limit (env var, default 10) | LOW |
| **G6** | FR-14 | Scheduled mode (recommend cron + curl) | LOW |
| **G7** | FR-3 | Configurable field names via env vars | LOW |
| **G8** | NFR-4 | Per-jobseeker wall-clock timeout (600s) | MEDIUM |

## Implementation Phases

### Phase 1: Trigger Enrichment (G1) ⭐ START HERE

**Goal**: Click the "Create Profile" play button after import to send profiles to n8n.

**Current flow ends at**:
```
"Add to table" → page transitions to table view → return True → Airtable status updated
```

**New flow adds**:
```
→ Wait for table view (5s)
→ Find "Create Profile" column header with ▶ button
→ Click play button via JS eval
→ Wait for dropdown (2s)
→ Click "Run all X rows that haven't run or have errors"
→ Parse X to get profile count
→ Wait for enrichment to start (3s)
→ Return {"profiles_triggered": X}
```

**Files to modify**:
- [execution/agent_orchestrator.py](execution/agent_orchestrator.py) - Add `trigger_enrichment()` function
- [execution/main.py](execution/main.py) - Capture result dict, log profiles_triggered

**Key code pattern** (from screenshot analysis):
```javascript
// Find header with "Create Profile", then click the play button within it
let headers = document.querySelectorAll('th, [role="columnheader"], [class*="header"]');
for (let h of headers) {
  if (h.textContent.includes('Create Profile')) {
    let btn = h.querySelector('button, svg, [role="button"], [class*="play"]');
    if (btn) { btn.click(); return 'Clicked'; }
  }
}
```

### Phase 2: Clear Table Rows (G2)

After enrichment triggered, delete all rows to prepare for next run.

**Open question**: Wait for enrichment to complete, or delete immediately after triggering?
**Answer depends on**: How long does Clay enrichment take per row?

### Phase 3: Airtable Enhancements (G3, G4)

- Modify `update_jobseeker_status()` to accept `extra_fields` dict
- Write ProfilesSent count, CompletedAt timestamp, ErrorNotes on failure
- Requires manual Airtable schema updates (add those fields)

### Phase 4: Safety (G5, G8)

- `BATCH_SIZE` env var + slice
- Wall-clock timeout via `signal.alarm()` or threading

### Phase 5: Configuration (G6, G7)

- Field name env vars
- Cron job documentation (no code change needed)

## Next Actions

1. **Restart Claude session** to load Airtable MCP tools
2. **Fetch 2-3 sample job seeker profiles** to analyze AI interpretation quality
3. **Implement Phase 1** (enrichment trigger)
4. **Test on VPS** with Run 14

## Questions for User

- **Row cleanup timing**: Should we wait for enrichment to complete before deleting rows, or delete immediately after triggering "Run all"?
- **AI interpretation**: Are there specific job seeker profiles where the AI is mis-interpreting the targeting criteria?
