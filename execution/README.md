# Execution Scripts

This folder contains deterministic Python scripts that perform specific tasks.

## Principles

1. **Single responsibility** - Each script does one thing well
2. **Deterministic** - Same inputs produce same outputs
3. **Well-commented** - Clear docstrings and inline comments
4. **Testable** - Can be run independently for testing
5. **Error handling** - Graceful failures with clear error messages

## Script Template

```python
#!/usr/bin/env python3
"""
Script Name: what_this_does.py
Description: Brief description of what this script accomplishes.

Usage:
    python what_this_does.py [arguments]

Inputs:
    - Description of required inputs

Outputs:
    - Description of what gets produced
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


def main():
    """Main entry point."""
    # Your logic here
    pass


if __name__ == "__main__":
    main()
```

## Common Utilities

Scripts may use these common patterns:
- `python-dotenv` for environment variables
- `google-auth` and `google-api-python-client` for Google APIs
- `requests` for HTTP calls
- `beautifulsoup4` for HTML parsing
