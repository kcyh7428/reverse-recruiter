import os
import vertexai
from vertexai.generative_models import GenerativeModel

PROJECT_ID = "reverse-recruiter-prod"
regions = ["us-central1", "us-west1", "us-east4", "us-east1"]

# Candidates to test based on user request
candidates = ["gemini-2.5-flash-preview-09-2025", "gemini-2.5-flash", "gemini-1.5-flash"]

print(f"--- DIAGNOSTIC: Testing Models {candidates} ---")

for REGION in regions:
    print(f"\nTesting Region: {REGION}")
    try:
        vertexai.init(project=PROJECT_ID, location=REGION)
        
        # Test each candidate in this region
        for model_id in candidates:
            print(f"  Testing {model_id}...")
            try:
                model = GenerativeModel(model_id)
                response = model.generate_content("Ping")
                print(f"  ✅ SUCCESS: {REGION} with {model_id} worked!")
                print(f"  Response: {response.text.strip()}")
                exit(0) # Stop on first success
            except Exception as e:
                print(f"  ❌ FAILED: {model_id} error: {e}")

    except Exception as e:
        print(f"❌ Region Init Failed: {REGION} error: {e}")
