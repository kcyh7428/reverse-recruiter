---
name: agent-browser
description: A skill that enables web browsing and interaction using the Vercel Agent Browser CLI. Use this to navigate to websites, take snapshots of the page structure (accessibility tree), and interact with elements using short references (@e1, @e2, etc.) rather than complex CSS selectors.
---

# Agent Browser CLI Skill

This skill provides the documentation and workflow for using the `agent-browser` CLI tool, as recommended by Cole Medin for high-reliability agentic browsing.

## Core Philosophy: Snapshot-First

AI agents perform best when they have a clean, deterministic view of the page. THE `agent-browser` tool provides this by mapping complex DOM elements to simple "refs" (e.g., `@e5`).

**ALWAYS** take a snapshot after any action that might change the page state. Rely on the refs returned by the snapshot for all subsequent interactions.

## Installation & Setup

```bash
# 1. Install globally
npm install -g agent-browser

# 2. Install browsers (Chromium)
agent-browser install

# 3. Pin version (if required for specific Docker images)
cd "$(npm root -g)/agent-browser" && npm install playwright-core@1.49.0
```

## Common Commands

### 1. Navigation
```bash
# Open a URL
agent-browser open "https://example.com"

# Open with Stealth Mode (bypass bot detection)
agent-browser open "https://app.clay.com" --disable-blink-features=AutomationControlled --user-agent="Realistic-UA-String"
```

### 2. Observation (Critical)
```bash
# Get a snapshot of interactive elements with refs (@e1, @e2, ...)
agent-browser snapshot -i --json

# Take a screenshot for visual debugging
agent-browser screenshot "debug_view.png"
```

### 3. Interaction
```bash
# Click an element by its ref
agent-browser click @e1

# Fill an input field
agent-browser fill @e2 "Text to type"

# Press a key (e.g., Enter, Tab, Escape)
agent-browser press Enter

# Scroll the page or an element
agent-browser scroll down
agent-browser scroll @e5 up
```

### 4. Session Management
```bash
# Get/Set cookies
agent-browser cookies
agent-browser cookies set "name" "value"

# Close the browser
agent-browser close
```

## Optimal Workflow for AI Agents

1.  **Open**: `agent-browser open <URL>`
2.  **Snapshot**: `agent-browser snapshot -i --json`
3.  **Analyze**: Parse the JSON to find the `@eN` ref for your target element.
4.  **Act**: `agent-browser click @eN` or `agent-browser fill @eN "value"`
5.  **Re-Snapshot**: If the page changed, goto step 2.
6.  **Verify**: Use `agent-browser snapshot` or `screenshot` to confirm success.

## Error Handling
- **LOGIN_REQUIRED**: If you see a login screen, check for existing cookies or return an error.
- **ELEMENT_NOT_FOUND**: If a ref is missing, take a fresh snapshot.
- **TIMEOUT**: If the page hasn't loaded, try `agent-browser wait --selector "@eX"` or `agent-browser wait --time 2000`.
