---
name: skill-clay-people-search
description: This skill automates Clay.com's "Find People" search interface via browser automation. Use this skill when a JobSeeker record needs target profiles discovered based on their targeting criteria (industries, job titles, seniority, locations). The skill translates Airtable JobSeeker fields into Clay filter interactions and imports matching LinkedIn profiles.
---

# Clay People Search Automation

This skill provides browser automation instructions for Clay.com's People Search interface to discover target profiles for job seekers.

## Overview

The automation translates JobSeeker targeting criteria from Airtable into Clay's People Search filters, executes the search, and imports matching profiles to the Clay table for downstream processing.

## Prerequisites

- Active Clay.com session (user must be logged in)
- Browser automation tools (Claude in Chrome MCP)
- Access to Airtable JobSeekers table (appWoqZ7azOoISd93)

## Clay People Search URL Pattern

```
https://app.clay.com/workspaces/{workspaceId}/w/find-people?destinationTableId={tableId}&workbookId={workbookId}
```

Current workspace configuration:
- Workspace: 579795
- Workbook: wb_0t6pb5rpbgD8nRCHvYh
- Destination Table: t_0t6pb5u5rFNYudNfngq

## Airtable to Clay Field Mapping

| Airtable Field (JobSeekers) | Clay Section | Clay Field | Input Type |
|----------------------------|--------------|------------|------------|
| `TargetIndustries` | Company attributes | Industries to include | Multi-select dropdown |
| `Seniority` | Job title | Seniority | Multi-select dropdown |
| `TargetTitles` | Job title | Job title (is similar to) | Multi-select with text input |
| `ExcludeKeywords` | Job title | Job titles to exclude | Multi-select with text input |
| `TargetGeos` | Location | Cities to include | Multi-select dropdown |

## Interface Structure

The Clay People Search interface has a left filter panel and right preview panel:

### Filter Panel Sections (Collapsible Accordions)

1. **Company attributes** (collapsed by default)
   - Industries to include (dropdown)
   - Industries to exclude (dropdown)
   - Company sizes (dropdown)
   - Description keywords to include (text)
   - Description keywords to exclude (text)

2. **Job title** (collapsed by default)
   - Seniority (dropdown: C-suite, Manager, etc.)
   - Job functions (dropdown: Sales, Engineering, etc.)
   - Job title mode selector ("is similar to" dropdown)
   - Job title values (multi-select text input)
   - Job titles to exclude (multi-select text input)

3. **Location** (collapsed by default)
   - Countries to include/exclude
   - Regions to include/exclude (NAM, LATAM, APAC, EMEA)
   - Cities to include/exclude
   - States/provinces to include/exclude
   - Search raw location field (toggle)

4. **Other sections:** Experience, Profile, Certifications, Languages, Education, Companies, Exclude people, Past experiences, Limit results

### Action Buttons

- **Save search** - Saves the current filter configuration
- **Add to table** - Imports results to the destination Clay table

### Preview Panel

- Shows matching count (e.g., "Previewing 50 of 309,254,106 results")
- Import limit indicator (e.g., "25,000 will be imported")
- Sample results table with Name, Company Name, Job Title, Location, LinkedIn URL

## Automation Workflow

### Stage 1: Navigate to People Search

1. Navigate to the Clay People Search URL
2. Wait for page load (verify "Add search criteria" text visible)
3. Verify preview panel loads with results

### Stage 2: Clear Existing Filters (if any)

Before applying new filters, check if any sections show active filters and clear them.

### Stage 3: Apply Company Attributes Filters

To set industries:

1. Find and click "Company attributes" section header to expand
2. Locate "Industries to include" dropdown (aria-label='Industries to include')
3. Click the dropdown to open
4. For each industry value from `TargetIndustries`:
   - Type the industry name in the search box (e.g., "Technology")
   - Wait for dropdown options to filter (suggestions appear below)
   - Click the matching option to add as pill (e.g., "Information Technology and Services")
   - Pill appears in the input field and header shows "1 filter"
5. **CRITICAL:** Press `ESC` to close the dropdown before moving to the next section
   - Clay dropdowns stay open after selection; pressing ESC ensures clean state

### Stage 4: Apply Job Title Filters

To set seniority, titles, and exclusions:

1. Find and click "Job title" section header to expand
2. **Seniority dropdown:**
   - Click "Seniority" dropdown
   - Select matching values from: C-suite, Manager, Director, VP, Senior, Lead/Principal, Mid-Level, Entry-Level
   - **Press `ESC` to close the dropdown**
3. **Job title "is similar to":**
   - Verify mode dropdown shows "is similar to"
   - Click the job title input field
   - For each title from `TargetTitles`:
     - Type the title
     - Press Enter or click suggestion to add as pill
   - **Press `ESC` to close the input before moving on**
4. **Job titles to exclude:**
   - Click "Job titles to exclude" input
   - For each keyword from `ExcludeKeywords`:
     - Type the keyword
     - Press Enter to add as pill
   - **Press `ESC` to close the input**

### Stage 5: Apply Location Filters

To set target cities:

1. **IMPORTANT:** You may need to scroll DOWN in the filter panel to see the "Location" section when other sections are expanded.
2. Find and click "Location" section header to expand
3. **Scroll again** if needed to see "Cities to include" field (it may be below the viewport after expanding)
4. Locate "Cities to include" dropdown (aria-label='Cities to include')
5. Click to open the dropdown
6. For each city from `TargetGeos`:
   - Type the city name (e.g., "New York")
   - Wait for autocomplete suggestions to appear
   - Click the matching city option (e.g., "New York City")
   - Pill appears in the input field
7. **CRITICAL:** Press `ESC` to close the dropdown before proceeding
   - Do NOT rely on "click outside" — always use ESC for consistent behavior

### Stage 6: Verify and Execute Search

1. Check preview panel for result count
2. Verify reasonable number of results (not 0, not millions unfiltered)
3. **Set Result Limits:**
   - **IMPORTANT:** The "Limit results" section is **always at the bottom** of the left filter panel. When filter sections are expanded, it will be off-screen.
   - **Scroll down** within the filter panel (use large scroll like Dy=1000) to find and expand the **"Limit results"** section.
   - Find the **"Limit"** input field (placeholder='e.g. 10'). It has a default value of **20**.
   - Click the input to focus it
   - **Clear existing value:** Press `Ctrl+A` (or `Cmd+A` on Mac) to select all, then `Backspace` to delete
   - Type the desired limit (e.g., `100`)
   - Press `Enter` to confirm the value
   - Ensure the **"Limit per company"** field is **blank/empty**.
4. **Click "Add to table" button** (the main button, NOT the dropdown arrow next to it)
   - For a new search, only "Add to table" appears (no "Continue" option)
   - Clicking the button will immediately add the number of profiles specified in "Limit Results"
   - The profiles will be imported to the Clay table
5. Wait for import confirmation (toast notification or redirect to table view)

## Element Reference Patterns

When locating elements, use these patterns:

### Section Headers (Accordion Triggers)
```
find: "{Section Name} section header expand button"
Example refs: ref_1308 (Company attributes), ref_1310 (Job title), ref_1314 (Location)
```

### Dropdown Fields
```
find: "{Field name} dropdown" or "{Field name} input"
```

### Multi-select Inputs
After clicking a dropdown:
- Type to filter options
- Click option or press Enter to select
- Pill appears showing selection
- Repeat for multiple values
- **ALWAYS press `ESC` after finishing selections** to close the dropdown before interacting with other elements

## Error Handling

### No Results
If preview shows 0 results after applying filters:
- Broaden filters (remove some exclusions)
- Check for typos in typed values
- Verify location names match Clay's format

### Too Many Results
If results exceed reasonable threshold (e.g., >100,000):
- Add more specific filters
- Narrow geographic scope
- Add seniority constraints

### Element Not Found
If a filter element cannot be located:
- Verify section is expanded
- Scroll within the filter panel
- Check if field name has changed

## Integration with Airtable

After profiles are imported to Clay:
1. Clay table processes new rows through configured enrichment
2. Profiles are sent via Clay's pre-configured destinations
3. The agent uses **Airtable MCP** to poll for JobSeeker records and update status

> [!NOTE]
> The agent polls Airtable for records matching trigger conditions (e.g., JobSeeker status = "✨ Sourcing Profiles") rather than relying on external webhooks.

## Seniority Value Mapping

Map Airtable `Seniority` field values to Clay dropdown options:

| Airtable Value | Clay Seniority Option |
|----------------|----------------------|
| C-Level, C-Suite, Executive | C-suite |
| VP, Vice President | VP |
| Director | Director |
| Manager | Manager |
| Senior | Senior |
| Lead, Principal | Lead/Principal |
| Mid-Level | Mid-Level |
| Entry-Level, Junior | Entry-Level |

## Best Practices

1. **Always expand sections before interacting** - Filter fields are hidden until section is expanded
2. **Wait for autocomplete** - Dropdowns populate dynamically; wait for options before selecting
3. **Verify pill creation** - After entering a value, confirm the pill/tag appears
4. **Check preview counts** - Use preview panel to validate filter effectiveness
5. **Set reasonable limits** - Use "Limit results" to control import volume (recommend 100-500 per search)
