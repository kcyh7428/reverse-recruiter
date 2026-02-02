#!/bin/bash
# Deploy to VPS via Hostinger API (no SSH required)
#
# PRIMARY METHOD: GitHub-based deployment via Hostinger VPS API
#   1. Commit and push changes to GitHub
#   2. Use Hostinger MCP tool VPS_createNewProjectV1 to deploy:
#      - virtualMachineId: (discover via VPS_getVirtualMachinesV1)
#      - project_name: "clay-automation"
#      - content: "https://github.com/kcyh7428/reverse-recruiter"
#      - environment: (env vars from execution/.env)
#
# FALLBACK: SSH-based deployment (may hit rate limits)
#   ./deploy_vps.sh <vps-ip>

set -e

if [ -z "$1" ]; then
    echo "=== Hostinger API Deployment (Recommended) ==="
    echo ""
    echo "1. git add . && git commit -m 'your message' && git push origin main"
    echo "2. Use Claude Code / Hostinger MCP to call VPS_createNewProjectV1:"
    echo "   - project_name: clay-automation"
    echo "   - content: https://github.com/kcyh7428/reverse-recruiter"
    echo "   - environment: (from execution/.env)"
    echo ""
    echo "=== SSH Fallback ==="
    echo "Usage: ./deploy_vps.sh <vps-ip>"
    exit 0
fi

VPS_IP=$1
echo "Deploying via SSH to $VPS_IP (fallback method)..."

rsync -avz --exclude='*.pyc' --exclude='__pycache__' \
  ./execution/ root@$VPS_IP:/opt/clay-automation/

ssh root@$VPS_IP << 'EOF'
  cd /opt/clay-automation
  docker compose down 2>/dev/null
  docker compose up --build -d
  docker compose logs -f --tail 20
EOF
