---
name: clay-profile-review-link
description: This skill reviews profiles imported to Clay's Target Profile Sourcing table, validates they match JobSeeker criteria, and either links them to the JobSeeker (triggering the webhook) or recommends filter adjustments for a retry. Use this skill AFTER using the clay-people-search skill to import profiles.
---

# Clay Profile Review & Link

This skill provides browser automation instructions for reviewing imported profiles in Clay and deciding whether to proceed with JobSeeker linkage or retry the search with adjusted filters.

## Overview

After profiles are imported via the Clay People Search skill, this skill:
1. Reviews the imported profiles against JobSeeker targeting criteria
2. Makes a quality decision (PASS or FAIL)
3. If PASS: Links profiles to JobSeeker and triggers webhook
4. If FAIL: Returns recommendations for filter adjustments

## Prerequisites

- Profiles already imported to Clay table (via clay-people-search skill)
- Active Clay.com session
- JobSeeker Record ID available
- JobSeeker targeting criteria available for comparison

## Clay Table URL

```
https://app.clay.com/workspaces/579795/tables/t_0t6pb5u5rFNYudNfngq
```

## Input Requirements

The agent needs:
- `jobSeekerRecordId`: Airtable record ID (e.g., `rec4klaksdjfio`)
- `expectedCriteria`: What profiles should look like
  - `targetTitles`: Expected job titles
  - `targetGeos`: Expected locations
  - `seniority`: Expected seniority levels
  - `targetIndustries`: Expected industries (via company)
- `importCount`: How many profiles were just imported (optional, for verification)

## Automation Workflow

### Stage 1: Navigate to Clay Table

1. Navigate to the Clay Target Profile Sourcing table URL
2. Wait for table to load (verify column headers visible)
3. Note the current row count

### Stage 2: Review Imported Profiles

Examine the most recently imported profiles to assess quality:

1. **Sort by Created At** (descending) to see newest profiles first
2. **Sample 10-20 profiles** from the import batch
3. **For each profile, check:**
   - `Job Title` - Does it match or relate to `targetTitles`?
   - `Company Name` - Is it a legitimate company?
   - `Location` (if visible) - Does it match `targetGeos`?
   - `LinkedIn Profile` - Is the URL valid?

### Stage 3: Quality Assessment

Evaluate the sample against criteria:

**PASS Criteria (all must be true):**
- At least 70% of sampled profiles have relevant job titles
- At least 60% of profiles are in target geographic areas
- No obvious spam/fake profiles detected
- Profiles represent real professionals (not company pages, groups, etc.)

**FAIL Indicators:**
- Majority of titles are unrelated to target (e.g., searching for "VP Sales" but getting "Software Engineer")
- Wrong geography (e.g., searching for "San Francisco" but getting "India")
- Too many junior/entry-level when searching for senior roles
- Many profiles from wrong industries
- Obvious data quality issues (missing names, broken URLs)

### Stage 4A: If PASS - Link and Trigger

Execute the linkage workflow:

1. **Edit JobSeeker RecordID Column:**
   - Click on "JobSeeker RecordID" column header
   - In the edit panel on the right side:
     - Locate the text input field
     - Enter the JobSeeker Record ID (e.g., `rec4klaksdjfio`)
   - The value applies to all rows in the table

2. **Trigger Create Profile Webhook:**
   - Click on "Create Profile" column header (has play button ▷)
   - Select "Run all X rows that haven't run or have errors"
   - Wait for HTTP calls to complete
   - Verify Status Code: 200 appears for rows

3. **Return SUCCESS:**
   ```
   {
     "status": "SUCCESS",
     "profilesLinked": <count>,
     "jobSeekerRecordId": "<id>",
     "webhookStatus": "triggered"
   }
   ```

### Stage 4B: If FAIL - Return Retry Recommendations

Analyze what went wrong and suggest adjustments:

1. **Identify the Problem:**
   - Wrong titles → Need to adjust `targetTitles` or add exclusions
   - Wrong geography → Need to verify `targetGeos` format
   - Wrong seniority → Need to adjust seniority filter
   - Too broad → Need more specific filters
   - Too narrow → Need to broaden filters (if 0 or very few results)

2. **Generate Recommendations:**
   ```
   {
     "status": "RETRY",
     "reason": "<specific issue identified>",
     "recommendations": {
       "adjustTitles": ["<suggested titles>"],
       "addExclusions": ["<keywords to exclude>"],
       "adjustGeos": ["<location format fixes>"],
       "adjustSeniority": ["<seniority changes>"],
       "otherNotes": "<additional observations>"
     },
     "sampleIssues": [
       {"name": "John Doe", "title": "Software Intern", "issue": "Too junior"},
       {"name": "Jane Smith", "title": "Retail Manager", "issue": "Wrong industry"}
     ]
   }
   ```

## Element Reference Patterns

### Clay Table - Column Headers
```
find: "JobSeeker RecordID column header"
find: "Create Profile column header" or "Create Profile play button"
find: "Job Title column header"
find: "Company Name column header"
find: "Created At column header"
```

### Clay Table - Sort Controls
```
find: "Sort button" or "Sort dropdown"
find: "Created At sort descending"
```

### Clay Table - Row Data
Read the table rows to extract profile information:
- Each row contains: Full Name, LinkedIn Profile, Company Name, Job Title, etc.
- Use `read_page` to capture visible rows
- Scroll to see more rows if needed

### Clay Table - Column Edit Panel
After clicking column header:
- Edit panel appears on right side
- Contains text input for static value
- "Data type" dropdown (should be "Text")
- Input field with placeholder "Type / to insert column"

### Clay Table - Run Column Dropdown
After clicking "Create Profile" column header:
- Dropdown with options:
  - "Run first 10 rows"
  - "Run all X rows that haven't run or have errors"

## Review Heuristics

### Title Matching Logic

When comparing imported titles to `targetTitles`:

**Exact or Near Match (GOOD):**
- Target: "VP Sales" → Found: "VP of Sales", "Vice President Sales" ✓
- Target: "Director Marketing" → Found: "Marketing Director", "Director of Marketing" ✓

**Related but Different Level (ACCEPTABLE):**
- Target: "VP Sales" → Found: "Senior Director Sales" (close enough)
- Target: "Director Engineering" → Found: "Head of Engineering" (equivalent)

**Wrong Function (BAD):**
- Target: "VP Sales" → Found: "VP Engineering" ✗
- Target: "Director Marketing" → Found: "Director Finance" ✗

**Wrong Level (BAD):**
- Target: "VP Sales" → Found: "Sales Representative" ✗
- Target: "Director Marketing" → Found: "Marketing Coordinator" ✗

### Geography Matching Logic

**Exact Match (GOOD):**
- Target: "San Francisco" → Found: "San Francisco, CA" ✓

**Metro Area Match (ACCEPTABLE):**
- Target: "San Francisco" → Found: "Oakland, CA" or "Palo Alto, CA" ✓

**Wrong Region (BAD):**
- Target: "San Francisco" → Found: "Los Angeles, CA" ✗
- Target: "New York" → Found: "Chicago, IL" ✗

**Wrong Country (VERY BAD):**
- Target: "San Francisco" → Found: "Bangalore, India" ✗

## Error Handling

### Table Won't Load
- Verify URL is correct
- Check Clay session is still active
- Refresh and retry

### Can't Find Column Header
- Scroll horizontally to find the column
- Check if column name has changed
- Verify you're on the correct table

### JobSeeker RecordID Edit Fails
- Ensure edit panel is fully loaded
- Clear any existing value before entering new one
- Verify the column data type is "Text"

### Webhook Shows Errors
- "Not enough Clay credits" → Cannot proceed, need credits
- "Status Code: 4xx/5xx" → Webhook endpoint issue, check n8n
- Some rows stuck on "Click to run" → Try running again

### Mixed Quality Results
If results are borderline (e.g., 50% good, 50% bad):
- Consider proceeding if urgent (some good contacts better than none)
- Or retry with tighter filters if time allows
- Document the quality issue in the return

## Integration with Agent Workflow

### Typical Agent Flow

```
Agent polls: Airtable MCP for JobSeeker records where status = "profile sourcing"

1. Agent uses: clay-people-search skill
   → Applies filters, imports profiles
   → Returns: "Imported 87 profiles"

2. Agent uses: clay-profile-review-link skill
   → Reviews profiles against criteria
   → Decision point:
   
   IF PASS:
     → Links to JobSeeker
     → Triggers Clay's pre-configured destinations
     → Returns: SUCCESS
     → Agent updates JobSeeker status via Airtable MCP
   
   IF FAIL:
     → Returns: RETRY with recommendations
     → Agent adjusts criteria
     → Agent uses: clay-people-search skill (again)
     → Agent uses: clay-profile-review-link skill (again)
     → (Loop until PASS or max retries)
```

### Max Retry Recommendation

Limit retries to 2-3 attempts. If profiles still don't match after adjustments:
- Report the issue to the user
- Suggest manual review of targeting criteria
- Consider if the target profile pool is too small/specific

## Best Practices

1. **Sample sufficiently** - Review at least 10-20 profiles before deciding
2. **Be realistic** - 70-80% match is good; 100% is unrealistic
3. **Document issues** - When returning RETRY, be specific about what's wrong
4. **Preserve good imports** - If some profiles are good, don't delete them
5. **Watch for patterns** - If same issue repeats, the criteria may need fundamental rework
6. **Consider volume** - 50 good profiles may be better than 0 perfect ones
7. **Verify webhook completion** - Don't report success until Status Code: 200 confirmed
