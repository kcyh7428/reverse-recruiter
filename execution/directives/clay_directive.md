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

1. **Expand "Job title" section** (click the accordion header)
2. **Set Seniority:** Click the Seniority dropdown, select from {{ai_seniority}}
3. **Set Job Titles:** Click the "Job title (is similar to)" input, type each title from {{ai_titles}}, press Enter after each
4. **Set Exclusions:** Click "Job titles to exclude", type each from {{ai_excludeKeywords}}
5. **IMPORTANT:** Press ESC after each dropdown/input to close it before moving to the next

### Location Filter

1. **Expand "Location" section**
2. **Set Cities:** Click "Cities to include", type each location from {{ai_locations}}
3. **Press ESC** to close the dropdown

### Import Profiles

1. **Check preview panel** for result count
2. **Set Limit:** Expand "Limit results" section, set limit to 100
3. **Click "Add to table"** button
4. **Handle confirmation modal:** Click the confirm button
5. **Wait for import notification**

## Completion Signals

- Return `{"type": "done", "reason": "Profiles imported successfully"}` when import is confirmed
- Return `{"type": "fail", "reason": "..."}` if:
  - Zero results after applying filters
  - Cannot find expected UI elements
  - Import fails
