# Clay People Search Automation Directive

## Goal
Use Clay.com's People Search to find target profiles matching the JobSeeker's criteria, then import them to the Clay table.

## Inputs
- **Target Titles (AI Optimized):** {{ai_titles}}
- **Target Locations (AI Optimized):** {{ai_locations}}
- **Seniority Levels (AI Optimized):** {{ai_seniority}}
- **Industries (AI Optimized):** {{ai_industries}}
- **Keywords to Exclude:** {{ai_excludeKeywords}}
- **AI Confidence:** {{ai_confidence}}
- **AI Reasoning:** {{ai_reasoning}}

### Raw JobSeeker Data (for reference)
- Target Titles: {{targetTitles}}
- Target Geos: {{targetGeos}}
- Seniority: {{seniority}}
- Exclude Keywords: {{excludeKeywords}}

## Instructions

You are controlling a browser on Clay.com's People Search interface. Your goal is to apply filters and import profiles.

### Login (If redirected to login page)
1. **Check if on login page** (look for "Sign in" or email input)
2. **Fill Email:** Type `{{clay_email}}` into the email field
3. **Click Continue** (or press Enter if button reference is ambiguous)
4. **Fill Password:** Type `{{clay_password}}` into the password field
5. **Press Enter** (most reliable for login)
6. **Wait for redirect** to People Search (may take 10-15s)

### Filter Application Steps

#### Company Attributes Section
1. **Expand "Company attributes" section** (click the accordion header)
2. **Set Industries:**
    - Click the "Industries to include" dropdown (aria-label='Industries to include')
    - Type each industry from {{ai_industries}}
    - Wait for suggestions to appear, then click the matching option
    - Pill appears when selected
3. **IMPORTANT:** Press ESC after each dropdown/input to close it before moving to the next

#### Job Title Section
1. **Expand "Job title" section** (click the accordion header)
2. **Set Seniority:** Click the Seniority dropdown (aria-label='Seniority'), select from {{ai_seniority}}
3. **Set Job Titles (MULTI-SELECT - CRITICAL):**
    - For EACH title in {{ai_titles}}, use `type_and_enter` **WITHOUT placeholder** (relies on previous focus):
      `{"type": "type_and_enter", "value": "VP of Sales", "reason": "Add title as pill"}`
      `{"type": "type_and_enter", "value": "Chief Revenue Officer", "reason": "Add title as pill"}`
      ... (repeat for each title)
    - ⚠️ **IMPORTANT:** Do NOT provide `placeholder` here, or it will fail due to duplicate elements. Only provide `value`.
4. **Set Exclusions (also multi-select):**
    - For each keyword in {{ai_excludeKeywords}}, use:
      `{"type": "type_and_enter", "placeholder": "Job titles to exclude", "value": "KEYWORD", "reason": "Add exclusion as pill"}`
5. **IMPORTANT:** Press ESC after completing all entries to close the dropdown before moving to the next section
6. **CRITICAL:** If `fill` fails with "matched multiple elements", DO NOT just press Enter. You MUST select a different element ID or use `find` command.

### Location Filter

1. **IMPORTANT:** You may need to scroll DOWN in the left filter panel to see the Location section.
2. **Expand "Location" section**
3. **Scroll again** if needed to see "Cities to include" field after expanding.
4. **Set Cities:** Click "Cities to include" dropdown (aria-label='Cities to include'), type each location from {{ai_locations}}
5. Wait for autocomplete suggestions, click the matching city option
6. **Press ESC** to close the dropdown

### Import Profiles

1. **Check preview panel** for result count
2. **Set Limit (REQUIRES SCROLLING):**
    - **Scroll down** in the left filter panel (large scroll like 1000px) to find "Limit results" section at the very bottom.
    - Expand "Limit results" section if collapsed
    - Click the "Limit" input field (placeholder='e.g. 10', default value is **20**)
    - **Clear existing value:** Press `Ctrl+A` (or `Cmd+A` on Mac) to select all, then `Backspace` to delete
    - Type "100"
    - Press Enter to confirm
3. **Click "Add to table"** button
    - Action: `{"type": "click", "element_id": "Add to table"}` (or find button with text "Add to table")
4. **Handle confirmation modal:** Click the confirm button if it appears
5. **Wait for import notification**

### Resilience & Error Handling

1. **Ambiguous Selectors:** If you receive an error like "matched X elements", do not just repeat the same command. Instead:
   - Perform a `snapshot` to get updated refs.
   - Look for a different element that might be more specific.
   - Or try to click a parent/related element first to clarify the UI state.
2. **Missing Elements:** If an element from the directive is missing, try expanding sections or scrolling before failing.
