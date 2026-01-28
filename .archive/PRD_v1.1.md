# PRD: Clay People Search Browser Automation

**Version:** 1.1  
**Date:** January 21, 2026  
**Author:** Reverse Recruiter Technical Team  
**Status:** Discovery Complete - Ready for Implementation

---

## 1. Executive Summary

### Problem Statement
Career coaches using the Reverse Recruiter system need to discover target profiles (potential networking contacts) for each job seeker. Currently, this requires manual navigation to Clay.com's People Search interface, manually entering filter criteria from the job seeker's Airtable record, importing results, and manually linking profiles to the correct JobSeeker record. This process is time-consuming and error-prone.

### Solution
Build browser automation using Claude in Chrome to automatically:
1. Receive JobSeeker targeting criteria + Record ID from n8n workflow
2. Navigate to Clay's People Search interface
3. Apply appropriate filters and import profiles
4. Link imported profiles to the JobSeeker by editing the RecordID column
5. Trigger the webhook to send profiles back to n8n with correct linkage

### Success Criteria
- Automation completes a full search-import-link cycle in under 3 minutes
- Filters applied match JobSeeker criteria with 100% accuracy
- All imported profiles correctly linked to triggering JobSeeker
- Profiles flow through existing n8n webhook pipeline with correct RecordID
- No manual intervention required after triggering

---

## 1.1 System Integration Flow

### Trigger Flow
```
┌─────────────────────────────────────────────────────────────────┐
│                        n8n WORKFLOW                              │
├─────────────────────────────────────────────────────────────────┤
│  1. JobSeeker profile prepared (Stage 0 complete)               │
│  2. Switch branch triggers HTTP call to Browser Automation      │
│     Payload includes:                                           │
│       - JobSeeker Record ID (e.g., rec4klaksdjfio)              │
│       - TargetIndustries, TargetTitles, Seniority, TargetGeos   │
│       - ExcludeKeywords                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               BROWSER AUTOMATION ENDPOINT                        │
│               (Claude Code / To Be Built)                        │
├─────────────────────────────────────────────────────────────────┤
│  Receives: { jobSeekerId, criteria }                            │
│  Executes: Full automation workflow (see Section 4)             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               CLAY TABLE WEBHOOK                                 │
│               (Triggered by "Create Profile" column)             │
├─────────────────────────────────────────────────────────────────┤
│  Fires HTTP POST to n8n webhook endpoint                        │
│  Payload includes:                                              │
│    - Profile data (LinkedIn URL, Name, Title, Company, etc.)    │
│    - JobSeeker RecordID (set by automation)                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│               n8n WEBHOOK RECEIVER                               │
├─────────────────────────────────────────────────────────────────┤
│  Creates TargetProfile records in Airtable                      │
│  Links each profile to correct JobSeeker via RecordID           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Discovery Findings

### 2.1 Clay Interface URL
```
https://app.clay.com/workspaces/579795/w/find-people?destinationTableId=t_0t6pb5u5rFNYudNfngq&workbookId=wb_0t6pb5rpbgD8nRCHvYh
```

### 2.2 Interface Layout
- **Left Panel:** Collapsible filter sections (accordions)
- **Right Panel:** Preview results table with count indicator
- **Bottom:** "Save search" and "Add to table" action buttons

### 2.3 Filter Sections Discovered

| Section | Status | Fields Available |
|---------|--------|------------------|
| Company attributes | ✅ Mapped | Industries to include/exclude, Company sizes, Description keywords |
| Job title | ✅ Mapped | Seniority, Job functions, Job title (is similar to), Job titles to exclude |
| Location | ✅ Mapped | Countries, Regions, Cities, States (include/exclude for each) |
| Experience | 🔄 Deferred | Years of experience |
| Profile | 🔄 Deferred | Names, Keywords, Connections |
| Others | 🔄 Deferred | Certifications, Languages, Education, Companies, etc. |

### 2.4 Element Interaction Patterns

**Accordion Sections:**
- Collapsed by default
- Click section header to expand
- Click again to collapse
- Element pattern: `find: "{Section Name} section header expand button"`

**Dropdown Fields:**
- Click to open dropdown menu
- Type to filter options (autocomplete)
- Click option to select (appears as pill/tag)
- Multiple selections supported
- Click outside to close

**Text Input Fields:**
- Click input area
- Type value
- Press Enter to confirm (creates pill)
- Repeat for multiple values

---

## 3. Data Mapping

### 3.1 Airtable Source Schema

**Table:** JobSeekers (tblroM0Stc6twKzdP)  
**Base:** appWoqZ7azOoISd93

| Field Name | Type | Example Values |
|------------|------|----------------|
| `TargetIndustries` | Multiline text | "Software Development\nInformation Technology" |
| `TargetTitles` | Multiline text | "VP Sales\nDirector Business Development\nHead of Sales" |
| `ExcludeKeywords` | Multiline text | "Retail\nHospitality\nRestaurant" |
| `TargetGeos` | Multiline text | "San Francisco, CA\nNew York, NY\nLos Angeles, CA" |
| `Seniority` | Multiline text | "VP\nDirector\nSenior" |

### 3.2 Clay Target Mapping

| Airtable Field | Clay Section | Clay Field | Transform |
|----------------|--------------|------------|-----------|
| `TargetIndustries` | Company attributes | Industries to include | Split by newline, trim whitespace |
| `Seniority` | Job title | Seniority | Map to Clay enum values |
| `TargetTitles` | Job title | Job title (is similar to) | Split by newline, trim whitespace |
| `ExcludeKeywords` | Job title | Job titles to exclude | Split by newline, trim whitespace |
| `TargetGeos` | Location | Cities to include | Split by newline, may need format normalization |

### 3.3 Seniority Value Mapping

| Airtable Input | Clay Dropdown Value |
|----------------|---------------------|
| C-Level, C-Suite, Executive, Chief | C-suite |
| VP, Vice President | VP |
| Director | Director |
| Manager | Manager |
| Senior | Senior |
| Lead, Principal | Lead/Principal |
| Mid-Level, Mid Level | Mid-Level |
| Entry-Level, Junior, Entry Level | Entry-Level |

---

## 4. Technical Architecture

### 4.1 Component Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Airtable      │     │  Claude in       │     │    Clay.com     │
│   JobSeekers    │────▶│  Chrome Browser  │────▶│  People Search  │
│   Table         │     │  Automation      │     │  Interface      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                        ┌──────────────────┐     ┌─────────────────┐
                        │   n8n Webhook    │◀────│   Clay Table    │
                        │   Workflow       │     │   (New Rows)    │
                        └──────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │   Airtable       │
                        │   TargetProfiles │
                        └──────────────────┘
```

### 4.2 Automation Sequence

```
1. TRIGGER (from n8n)
   └─▶ JobSeeker profile preparation complete in n8n workflow
   └─▶ n8n sends HTTP request to browser automation endpoint
   └─▶ Payload includes: JobSeeker record ID + targeting criteria

2. DATA VALIDATION
   └─▶ Receive JobSeeker record ID and criteria from n8n
   └─▶ Parse targeting fields (split multiline, normalize values)
   └─▶ Store JobSeeker record ID for later linkage step

3. NAVIGATION TO PEOPLE SEARCH
   └─▶ Open Clay People Search URL in browser tab
   └─▶ Wait for page load (verify "Add search criteria" visible)

4. FILTER APPLICATION (for each section with data)
   ├─▶ Company attributes
   │   └─▶ Expand section
   │   └─▶ Set "Industries to include" from TargetIndustries
   │
   ├─▶ Job title
   │   └─▶ Expand section
   │   └─▶ Set "Seniority" dropdown (mapped values)
   │   └─▶ Set "Job title" input (TargetTitles)
   │   └─▶ Set "Job titles to exclude" (ExcludeKeywords)
   │
   └─▶ Location
       └─▶ Expand section
       └─▶ Set "Cities to include" from TargetGeos

5. SEARCH VALIDATION
   └─▶ Check preview count (should be >0 and <100,000)
   └─▶ Adjust filters if needed

6. IMPORT PROFILES
   └─▶ Set "Limit" if needed (default: 100-500)
   └─▶ Click "Add to table" button
   └─▶ Wait for import completion notification
   └─▶ Navigate back to Clay table view

7. LINK JOBSEEKER ID (Critical Step)
   └─▶ Verify imported profiles appear in table (check row count)
   └─▶ Click on "JobSeeker RecordID" column header to edit
   └─▶ Set static value = JobSeeker record ID from step 1
   └─▶ Confirm edit applies to all imported rows

8. TRIGGER WEBHOOK
   └─▶ Click "Create Profile" column header (play button ▷)
   └─▶ Select "Run all X rows that haven't run or have errors"
   └─▶ Wait for HTTP calls to complete
   └─▶ Verify Status Code: 200 for all rows

9. COMPLETION
   └─▶ Log results: profiles imported, webhook status
   └─▶ Profiles now flow to n8n with correct JobSeeker linkage
   └─▶ n8n webhook creates TargetProfile records in Airtable
```

### 4.3 n8n Integration Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           n8n WORKFLOW                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  JobSeeker Profile Prepared (Stage 0 complete)                          │
│           │                                                              │
│           ▼                                                              │
│  Switch Branch: "trigger-profile-search"                                │
│           │                                                              │
│           ▼                                                              │
│  HTTP Request to Browser Automation Endpoint                            │
│  Payload: {                                                              │
│    "jobSeekerId": "rec4klaksdjfio",                                     │
│    "targetIndustries": ["Software Development", "IT"],                  │
│    "targetTitles": ["VP Sales", "Director BD"],                         │
│    "seniority": ["VP", "Director"],                                     │
│    "targetGeos": ["San Francisco", "New York"],                         │
│    "excludeKeywords": ["Retail", "Hospitality"]                         │
│  }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              BROWSER AUTOMATION (Claude in Chrome)                       │
├─────────────────────────────────────────────────────────────────────────┤
│  1. Receive criteria + JobSeeker ID                                     │
│  2. Navigate to Clay People Search                                      │
│  3. Apply filters                                                       │
│  4. Import profiles to Clay table                                       │
│  5. Edit "JobSeeker RecordID" column → set to received ID              │
│  6. Trigger "Create Profile" → run all rows                            │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    CLAY TABLE WEBHOOK                                    │
├─────────────────────────────────────────────────────────────────────────┤
│  "Create Profile" HTTP column fires for each row                        │
│  Payload includes: profile data + JobSeeker RecordID                    │
│  Endpoint: n8n webhook (action: create-targetprofile)                   │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    n8n WEBHOOK RECEIVER                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  Receives profiles with correct JobSeeker linkage                       │
│  Creates TargetProfile records in Airtable                              │
│  Links each profile to the originating JobSeeker                        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.4 MCP Tools Required

| Tool | Purpose |
|------|---------|
| `Claude in Chrome:navigate` | Open Clay People Search URL, return to table view |
| `Claude in Chrome:find` | Locate filter elements, column headers, buttons |
| `Claude in Chrome:computer` (click) | Expand sections, select options, trigger actions |
| `Claude in Chrome:computer` (type) | Enter filter values, set JobSeeker ID |
| `Claude in Chrome:computer` (screenshot) | Verify state, debug issues |
| `Claude in Chrome:read_page` | Inspect DOM structure, verify row counts |
| `Claude in Chrome:form_input` | Set column static values |

### 4.5 Clay Table Operations (Post-Import)

**Editing JobSeeker RecordID Column:**
1. Click column header "JobSeeker RecordID"
2. Edit panel appears on right side
3. Enter static value (the JobSeeker record ID)
4. Value applies to all rows in the table

**Triggering Create Profile Column:**
1. Click column header "Create Profile" (has play button ▷)
2. Dropdown appears with options:
   - "Run first 10 rows"
   - "Run all X rows that haven't run or have errors"
3. Select "Run all X rows..." option
4. Wait for completion (Status Code: 200 for each row)

---

## 5. Implementation Plan

### Phase 1: People Search Filter Application (MVP)
**Goal:** Demonstrate filter application and profile import

1. Navigate to Clay People Search URL
2. Expand Location section
3. Add cities to "Cities to include"
4. Verify preview shows filtered results
5. Click "Add to table"
6. Confirm profiles appear in Clay table

**Success Criteria:** Successful import with one filter type

### Phase 2: All Core Filters
**Goal:** Implement all mapped filter types

1. Add Company attributes → Industries
2. Add Job title → Seniority, Titles, Exclusions
3. Add Location → Cities
4. Handle empty fields gracefully (skip if no data)
5. Add filter clearing logic (reset before new search)

**Success Criteria:** Full filter application for complete criteria set

### Phase 3: JobSeeker ID Linkage
**Goal:** Automate the JobSeeker record ID association

1. After import, navigate back to Clay table view
2. Locate and click "JobSeeker RecordID" column header
3. Enter the JobSeeker record ID in the edit panel
4. Verify ID applies to all imported rows

**Success Criteria:** All imported rows have correct JobSeeker ID

### Phase 4: Webhook Trigger Automation
**Goal:** Automate the "Create Profile" trigger

1. Locate and click "Create Profile" column header
2. Select "Run all X rows that haven't run or have errors"
3. Wait for HTTP calls to complete
4. Verify Status Code: 200 for all rows

**Success Criteria:** All profiles sent via webhook with JobSeeker ID

### Phase 5: n8n Integration
**Goal:** Complete end-to-end pipeline from n8n trigger

1. Create n8n switch branch for "trigger-profile-search"
2. Build HTTP node to call browser automation endpoint
3. Pass JobSeeker ID + criteria in payload
4. Verify webhook receiver creates TargetProfile records
5. Confirm JobSeeker linkage in Airtable

**Success Criteria:** Zero manual intervention for complete cycle

### Phase 6: Error Handling & Robustness
**Goal:** Production-ready reliability

1. Add retry logic for flaky element interactions
2. Handle "no results" scenario
3. Handle "too many results" scenario
4. Verify import success before proceeding to ID linkage
5. Handle webhook failures (retry logic)
6. Screenshot on failure for debugging
7. Logging for audit trail

**Success Criteria:** Automation recovers gracefully from common failures

---

## 6. Known Limitations & Risks

### Technical Risks

| Risk | Mitigation |
|------|------------|
| Clay UI changes break selectors | Use semantic find queries, not hardcoded refs |
| Autocomplete timing issues | Add explicit waits after typing |
| Rate limiting from Clay | Add delays between operations |
| Session timeout during long operations | Check session validity before starting |
| Webhook failures | Verify Status Code: 200 before proceeding |
| Column edit doesn't propagate | Verify all rows show updated RecordID |

### Data Quality Risks

| Risk | Mitigation |
|------|------------|
| Airtable field format variations | Normalize input data (trim, split, map) |
| City names not matching Clay's format | May need location normalization logic |
| Seniority values not in mapping table | Add fallback handling, log unmapped values |
| Duplicate profiles across searches | Clay table may need deduplication logic |

### Scope Limitations (Phase 1)

- No support for: Experience, Profile keywords, Education, Companies filters
- No "Save search" functionality (just "Add to table")
- No incremental/delta imports (full search each time)
- Requires active Clay session (no automated login)
- One JobSeeker processed at a time (sequential, not parallel)

---

## 7. Testing Strategy

### Manual Testing Checklist

**People Search Interface:**
- [ ] Navigate to People Search URL loads correctly
- [ ] Each filter section expands on click
- [ ] Industries dropdown accepts typed values
- [ ] Seniority dropdown allows multiple selections
- [ ] Job title input creates pills for each value
- [ ] Cities input finds and selects locations
- [ ] Preview count updates after filter changes
- [ ] "Add to table" button triggers import
- [ ] Profiles appear in Clay table after import

**Clay Table Operations:**
- [ ] Navigate to Target Profile Sourcing table
- [ ] Click "JobSeeker RecordID" column header opens edit panel
- [ ] Static value input accepts record ID format (recXXXXXXXXX)
- [ ] Updated value appears in all imported rows
- [ ] Click "Create Profile" column header shows dropdown
- [ ] "Run all X rows" option triggers webhook for all rows
- [ ] Wait for Status Code: 200 on all rows

**End-to-End:**
- [ ] n8n webhook receives profiles with correct JobSeeker RecordID
- [ ] TargetProfile records created in Airtable
- [ ] TargetProfiles correctly linked to JobSeeker record

### Automated Validation

- [ ] Screenshot before and after filter application
- [ ] Compare expected vs actual filter pills
- [ ] Verify preview count is within acceptable range
- [ ] Confirm import completion indicator
- [ ] Verify JobSeeker RecordID column shows expected value
- [ ] Count rows with Status Code: 200 matches import count

---

## 8. Future Enhancements

### Short Term
- Support additional filter sections (Experience, Education)
- Add "Save search" for reusable filter templates
- Implement incremental imports (exclude already-imported profiles)

### Medium Term
- Batch processing for multiple JobSeekers
- Scheduling via n8n trigger
- Result quality scoring and feedback loop

### Long Term
- Direct CrustData PersonDB API integration (bypass Clay UI)
- Custom Clay table with automation-specific columns
- A/B testing of filter strategies per JobSeeker

---

## 9. Appendix

### A. Clay People Search Interface Screenshots

(Screenshots captured during discovery session - January 21, 2026)

1. Full interface with filter panel and preview
2. Company attributes section expanded
3. Job title section expanded
4. Location section expanded

### B. Element Reference IDs (from discovery)

These are session-specific and will change, but patterns are consistent:
- Company attributes header: ~ref_1308
- Job title header: ~ref_1310
- Experience header: ~ref_1312
- Location header: ~ref_1314
- Save search button: ~ref_1333
- Add to table button: ~ref_1335

### C. Related Documentation

- Airtable JobSeekers Schema: See project file `reverse_recruiter_technical_blueprint_v2.md`
- n8n Workflow: ID `DFwKUCHIw3SAVjDF`
- Webhook endpoint: `https://n8n.talentsignals.ai/webhook/reverse-recruiter`
