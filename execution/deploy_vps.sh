#!/bin/bash
# Usage: ./deploy_vps.sh <vps-ip>
set -e
VPS_IP=$1
if [ -z "$VPS_IP" ]; then echo "Usage: ./deploy_vps.sh <vps-ip>"; exit 1; fi

rsync -avz --exclude='*.pyc' --exclude='__pycache__' \
  ./execution/ root@$VPS_IP:/opt/clay-automation/

ssh root@$VPS_IP << 'EOF'
  cd /opt/clay-automation
  docker build -t clay-automation .
  docker stop clay-auto 2>/dev/null; docker rm clay-auto 2>/dev/null
  docker run -d --name clay-auto --restart=always \
    --memory=8g --shm-size=2gb \
    -p 8080:8080 \
    --env-file .env \
    clay-automation
  docker logs -f clay-auto --tail 20
EOF
