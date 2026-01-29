#!/usr/bin/env python3
"""
Test script for Phase 3: AI Criteria Interpretation

Tests the interpret_search_criteria function with the test JobSeeker record.
Run this from the execution/ directory or adjust paths.
"""

import os
import sys
import json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set up environment for Vertex AI
os.environ.setdefault("GCP_PROJECT_ID", "reverse-recruiter-prod")
os.environ.setdefault("GCP_REGION", "us-central1")

from agent_orchestrator import interpret_search_criteria

def main():
    # Test JobSeeker data (mirrors the record we created in Airtable)
    test_jobseeker = {
        "id": "recfV7X8d6XccguoL",
        "name": "Phase 3 Test User",
        "targetTitles": """VP of Sales
Head of Sales
Director of Sales
Senior Director of Revenue
Chief Revenue Officer""",
        "targetGeos": """San Francisco, CA
New York, NY
Los Angeles, CA
Seattle, WA
Austin, TX
Remote (US)""",
        "seniority": "Manager",  # Note: VP wasn't available in test base
        "targetIndustries": """Technology
Software & Services
Financial Services
Healthcare""",
        "includeKeywords": """B2B Sales
Enterprise Sales
SaaS
Revenue Growth
Sales Leadership""",
        "excludeKeywords": """Entry-level
Junior
Retail
Hospitality
Restaurant""",
        "notesForCoach": "Looking for VP-level sales leadership roles in tech. Strong preference for remote-friendly companies. Has experience scaling sales teams from 10 to 100+."
    }
    
    print("=" * 60)
    print("Phase 3 Test: AI Criteria Interpretation")
    print("=" * 60)
    print(f"\nTest JobSeeker: {test_jobseeker['name']} ({test_jobseeker['id']})")
    print(f"Raw Titles: {test_jobseeker['targetTitles'][:50]}...")
    print(f"Raw Geos: {test_jobseeker['targetGeos'][:50]}...")
    
    print("\n" + "-" * 60)
    print("Calling interpret_search_criteria()...")
    print("-" * 60 + "\n")
    
    try:
        criteria = interpret_search_criteria(test_jobseeker)
        
        print("\n" + "=" * 60)
        print("AI Interpretation Result:")
        print("=" * 60)
        print(json.dumps(criteria, indent=2))
        
        # Validate basic expectations
        print("\n" + "-" * 60)
        print("Validation Checks:")
        print("-" * 60)
        
        checks = [
            ("Has titles", bool(criteria.get("titles"))),
            ("Has locations", bool(criteria.get("locations"))),
            ("Has seniority", bool(criteria.get("seniority"))),
            ("Titles contain VP/Director-level", any("VP" in t or "Director" in t or "Head" in t for t in criteria.get("titles", []))),
            ("Locations are in US", any("San Francisco" in l or "New York" in l or "US" in l for l in criteria.get("locations", []))),
            ("Has confidence rating", criteria.get("confidence") in ["high", "medium", "low", "fallback"]),
        ]
        
        all_passed = True
        for check_name, passed in checks:
            status = "✅" if passed else "❌"
            print(f"  {status} {check_name}")
            if not passed:
                all_passed = False
        
        print("\n" + "=" * 60)
        if all_passed:
            print("✅ All validation checks passed!")
        else:
            print("⚠️ Some validation checks failed - review output above")
        print("=" * 60)
        
        return 0 if all_passed else 1
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
