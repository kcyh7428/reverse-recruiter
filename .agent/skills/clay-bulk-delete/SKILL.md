---
name: clay-bulk-delete
description: Clears all rows in a Clay table to ensure a clean state for subsequent automation runs or data processing steps.
---

# Skill: Clay Bulk Delete

This skill provides browser automation instructions for clearing all rows from a Clay table.

## Overview

Use this skill after profiles have been processed and sent via Clay's destinations. Clearing the table ensures a clean state for the next JobSeeker's profile search.

## Prerequisites

- Active Clay.com session
- Access to the target Clay table

## Clay Table URL

```
https://app.clay.com/workspaces/579795/tables/t_0t6pb5u5rFNYudNfngq
```

## Automation Workflow

### Step 1: Navigate to Table
1. Navigate to the Clay table URL
2. Wait for table to load (verify column headers visible)
3. Verify the table name is 'Target Profile Sourcing'
4. Note the current row count

### Step 2: Select All Rows
1. Find the checkbox in the table header row (first column)
2. Click the checkbox to select all rows
3. Verify selection indicator shows "X rows selected"

### Step 3: Delete Selected Rows
1. Look for the "Delete" button or trash icon in the toolbar
2. Click the delete action
3. If a confirmation modal appears, click "Confirm" or "Delete"
4. Wait for deletion to complete

### Step 4: Verify Empty Table
1. Check that row count shows 0 or "No data"
2. Verify no rows remain in the table view

## Agent Browser Commands Example

```bash
# Navigate to table
agent-browser open "https://app.clay.com/workspaces/579795/tables/t_0t6pb5u5rFNYudNfngq"
agent-browser snapshot -i --json

# Select all rows (find the header checkbox ref)
agent-browser click @e5   # Header checkbox

# Snapshot to find delete button
agent-browser snapshot -i --json
agent-browser click @e12  # Delete button

# Confirm deletion if modal appears
agent-browser snapshot -i --json
agent-browser click @e20  # Confirm button

# Verify empty
agent-browser snapshot -i --json
```

## Error Handling

- **No rows to delete**: If table is already empty, skip this skill
- **Delete button not found**: Ensure rows are selected first
- **Confirmation modal stuck**: Try clicking outside or pressing Escape

## Best Practices

1. **Always verify selection** before clicking delete
2. **Wait for deletion to complete** before proceeding
3. **Re-snapshot after deletion** to confirm empty state
4. **Handle empty table gracefully** - not an error condition
