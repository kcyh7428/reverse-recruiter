# Directives

This folder contains SOPs (Standard Operating Procedures) written in Markdown.

## What is a Directive?

A directive is a clear set of instructions for accomplishing a specific task. Think of it as instructions you'd give a mid-level employee.

## Directive Format

Each directive should include:

```markdown
# [Task Name]

## Goal
What this directive accomplishes.

## Inputs
- What information/files are needed to start

## Tools/Scripts
- Which scripts from `execution/` to use
- In what order

## Outputs
- What deliverables should be produced
- Where they should be stored (usually Google Sheets/Slides)

## Edge Cases
- Common errors and how to handle them
- API limits or timing considerations
- Learned gotchas (added over time)
```

## Principles

1. **Living documents** - Update directives as you learn new edge cases
2. **Natural language** - Write clearly, not in code
3. **Specific scripts** - Reference exact scripts from `execution/`
4. **Cloud deliverables** - Final outputs go to Google Sheets/Slides, not local files
