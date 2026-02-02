# Clay People Search — Verification & Import Directive

## Context
Filters have been applied **programmatically** before you started. Your job is to **verify** and **import**.

## Expected Filter State
- **Seniority:** {{ai_seniority}} — look for selected pills in Seniority dropdown
- **Job Titles:** {{ai_titles}} — look for "Clear chip" buttons and "X filters" label on Job title section
- **Exclusions:** {{ai_excludeKeywords}} — look for "Clear chip" buttons near "Job titles to exclude"
- **Locations:** {{ai_locations}} — look for pills in Location section
- **Import Limit:** 100 — look for "1 filter" label on "Limit results" section

## Your Steps

### 1. Verify Filters
- Check the snapshot for "Clear chip" buttons (each = one applied filter pill)
- Check for "X filters" labels on section headers (e.g., "Job title 3 filters")
- Scroll down if needed to see Location and Limit sections

### 2. Click "Add to table"
- Find the "Add to table" button in the snapshot (look for `button "Add to table" [ref=eX]`)
- Click it: `{"type": "click", "element_id": "@eX", "reason": "Import profiles to table"}`
- If not visible, scroll down: `{"type": "scroll", "direction": "down", "pixels": 300, "reason": "Find Add to table button"}`

### 3. Handle Confirmation
- If a confirmation dialog appears after clicking, click the confirm/OK button
- Wait for the page to transition away from the filter view

### 4. Signal Done
- After the page transitions (URL changes from find-people to table view), signal:
  `{"type": "done", "reason": "Import triggered, page transitioned to table view"}`

## Rules
- Do NOT re-apply filters — they are already set
- Do NOT signal "done" until you've clicked "Add to table" AND seen the page change
- If a critical filter is visibly MISSING (no pills at all), signal fail:
  `{"type": "fail", "reason": "Missing filter: [which one]"}`
- If "Add to table" button cannot be found after scrolling, signal fail
