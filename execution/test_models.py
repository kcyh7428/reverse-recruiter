import os
import vertexai
from vertexai.generative_models import GenerativeModel

# Configuration
PROJECT_ID = "reverse-recruiter-prod"
REGION = "us-central1"

print(f"Initializing Vertex AI for project {PROJECT_ID} in {REGION}...")
try:
    vertexai.init(project=PROJECT_ID, location=REGION)
except Exception as e:
    print(f"Failed to init Vertex AI: {e}")
    exit(1)

# Candidate models to test
candidates = [
    "gemini-1.5-flash-001",
    "gemini-1.5-flash-002",
    "gemini-1.5-flash",
    "gemini-1.5-pro-001",
    "gemini-1.0-pro-001",
    "gemini-1.0-pro",
    "gemini-pro"
]

print("\n--- Testing Model Availability ---")
for model_id in candidates:
    print(f"\nTesting: {model_id}")
    try:
        model = GenerativeModel(model_id)
        # Try a minimal generation to prove access
        response = model.generate_content("Hello")
        print(f"✅ SUCCESS: {model_id} worked! Response: {response.text.strip()}")
    except Exception as e:
        print(f"❌ FAILED: {model_id} - Error: {e}")
