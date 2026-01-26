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
2. Locate "Industries to include" dropdown
3. Click the dropdown to open
4. For each industry value from `TargetIndustries`:
   - Type the industry name in the search box
   - Wait for dropdown options to filter
   - Click the matching option to add as pill
5. Click outside dropdown to close

### Stage 4: Apply Job Title Filters

To set seniority, titles, and exclusions:

1. Find and click "Job title" section header to expand
2. **Seniority dropdown:**
   - Click "Seniority" dropdown
   - Select matching values from: C-suite, Manager, Director, VP, Senior, Lead/Principal, Mid-Level, Entry-Level
3. **Job title "is similar to":**
   - Verify mode dropdown shows "is similar to"
   - Click the job title input field
   - For each title from `TargetTitles`:
     - Type the title
     - Press Enter or click suggestion to add as pill
4. **Job titles to exclude:**
   - Click "Job titles to exclude" input
   - For each keyword from `ExcludeKeywords`:
     - Type the keyword
     - Press Enter to add as pill

### Stage 5: Apply Location Filters

To set target cities:

1. Find and click "Location" section header to expand
2. Locate "Cities to include" dropdown
3. Click to open the dropdown
4. For each city from `TargetGeos`:
   - Type the city name
   - Wait for autocomplete suggestions
   - Click the matching city option
5. Click outside to close dropdown

### Stage 6: Verify and Execute Search

1. Check preview panel for result count
2. Verify reasonable number of results (not 0, not millions unfiltered)
3. **Set Result Limits:**
   - Locate and expand the **"Limit results"** section (usually at the bottom of the left panel).
   - Find the **"Limit"** input field and set it to `100`.
   - Ensure the **"Limit per company"** field is **blank/empty**.
4. Click "Add to table" button
5. **CRITICAL:** A confirmation modal will appear. **Do NOT navigate back** or click away.
6. Wait for the confirmation modal to be visible.
7. Click the primary confirmation button inside the modal (labeled "Add [N] people" or "Add to table").
8. Wait for the import started notification/toast.

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

## Integration with n8n Workflow

After profiles are imported to Clay:
1. Clay table processes new rows through configured enrichment
2. Webhook triggers n8n workflow (DFwKUCHIw3SAVjDF)
3. Profiles flow to Airtable TargetProfiles table with JobSeeker linkage

Webhook endpoint: `https://n8n.talentsignals.ai/webhook/reverse-recruiter`
Action parameter: `create-targetprofile`

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
