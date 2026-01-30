#!/bin/bash

# Configuration
IMAGE_NAME="clay-automation-local"
PORT=8080

# Load environment variables from .env file if it exists
if [ -f "../.env" ]; then
    export $(grep -v '^#' ../.env | xargs)
elif [ -f ".env" ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Validate required environment variables
if [ -z "$AIRTABLE_API_KEY" ] || [ -z "$CLAY_EMAIL" ] || [ -z "$CLAY_PASSWORD" ] || [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: Required environment variables not set."
    echo "   Please create a .env file with:"
    echo "   - AIRTABLE_API_KEY"
    echo "   - AIRTABLE_BASE_ID"
    echo "   - AIRTABLE_TABLE_NAME"
    echo "   - CLAY_EMAIL"
    echo "   - CLAY_PASSWORD"
    echo "   - OPENAI_API_KEY"
    exit 1
fi

# Build environment variable array for Docker
ENV_VARS=(
    -e "AIRTABLE_API_KEY=${AIRTABLE_API_KEY}"
    -e "AIRTABLE_BASE_ID=${AIRTABLE_BASE_ID:-app8KvRTUVMWeloR8}"
    -e "AIRTABLE_TABLE_NAME=${AIRTABLE_TABLE_NAME:-JobSeekers}"
    -e "OPENAI_API_KEY=${OPENAI_API_KEY}"
    -e "AGENT_BROWSER_SESSION=clay_automation_session"
    -e "CLAY_EMAIL=${CLAY_EMAIL}"
    -e "CLAY_PASSWORD=${CLAY_PASSWORD}"
    -e "PORT=$PORT"
)

echo "🏗️  Building Docker image..."
# Build from the directory where this script is located (execution/)
cd "$(dirname "$0")"
docker build -t $IMAGE_NAME .

if [ $? -ne 0 ]; then
    echo "❌ Build failed."
    exit 1
fi

echo "🚀 Running container locally on port $PORT..."
echo "   (Press Ctrl+C to stop)"

# Run in foreground so we see logs immediately
# We mount session_cookies.json so we can edit it locally without rebuilding
# Added memory/cpu limits to prevent resource exhaustion (os error 11)
# Added --shm-size=2gb to prevent Chrome crashing/empty snapshots on memory-intensive sites
docker run --rm -p $PORT:$PORT \
    --memory=4g \
    --pids-limit -1 \
    --shm-size=2gb \
    "${ENV_VARS[@]}" \
    -v "$(pwd)/session_cookies.json:/app/session_cookies.json" \
    -v "$(pwd)/diagnostics:/app/diagnostics" \
    $IMAGE_NAME
