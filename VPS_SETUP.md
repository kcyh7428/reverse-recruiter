# VPS Infrastructure Setup Guide

**Provider:** Hostinger (KVM4)
**IP Address:** `72.62.253.226`
**OS:** Ubuntu 24.04
**RAM:** 16 GB
**Last Updated:** 2026-01-30

---

## Quick Reference

| Resource | Value |
|----------|-------|
| **VPS IP** | `72.62.253.226` |
| **SSH Access** | `ssh root@72.62.253.226` |
| **Container Name** | `clay-auto` |
| **Service Port** | `8080` |
| **Service URL** | `http://72.62.253.226:8080` |
| **Docker Memory** | 8 GB (container limit) |
| **Docker shm-size** | 2 GB |
| **Restart Policy** | `always` |

---

## SSH Access

```bash
ssh root@72.62.253.226
```

The project is cloned to `/root/reverse-recruiter` on the VPS.

---

## Deployment

### Automated Deploy (from local machine)

```bash
./execution/deploy_vps.sh 72.62.253.226
```

This script handles git pull, Docker build, and container restart automatically.

### Manual Deploy (on the VPS)

```bash
# 1. Pull latest code
cd /root/reverse-recruiter
git pull origin main

# 2. Build Docker image
cd execution
docker build -t clay-automation .

# 3. Stop and remove existing container
docker stop clay-auto && docker rm clay-auto

# 4. Run new container
docker run -d --name clay-auto --restart=always \
  --memory=8g --shm-size=2gb \
  -p 8080:8080 \
  --env-file /root/reverse-recruiter/.env \
  clay-automation
```

---

## Environment Variables (.env file)

The `.env` file lives at `/root/reverse-recruiter/.env` on the VPS. Required variables:

```
OPENAI_API_KEY=sk-...
AIRTABLE_API_KEY=pat...
AIRTABLE_BASE_ID=app8KvRTUVMWeloR8
AIRTABLE_TABLE_NAME=JobSeekers
CLAY_EMAIL=your-clay-email@example.com
CLAY_PASSWORD=your-clay-password
PORT=8080
```

To update environment variables:
```bash
ssh root@72.62.253.226
nano /root/reverse-recruiter/.env
# After editing, restart the container:
docker restart clay-auto
```

---

## Monitoring

### View Logs

```bash
# Last 50 lines
docker logs clay-auto --tail 50

# Follow live logs
docker logs clay-auto -f

# Logs since a specific time
docker logs clay-auto --since 1h

# Search logs for specific patterns
docker logs clay-auto 2>&1 | grep "Turn"
docker logs clay-auto 2>&1 | grep "ERROR"
```

### Container Status

```bash
# Check if running
docker ps | grep clay-auto

# Resource usage
docker stats clay-auto --no-stream

# Inspect container details
docker inspect clay-auto
```

---

## Testing Endpoints

```bash
# Health check
curl http://72.62.253.226:8080/

# Test browser connectivity
curl http://72.62.253.226:8080/test-connectivity

# Test Clay access
curl http://72.62.253.226:8080/test-clay-access

# Test full authentication flow
curl http://72.62.253.226:8080/test-clay-auth

# Trigger automation for a test record
curl -X POST "http://72.62.253.226:8080/run-automation?record_id=recfV7X8d6XccguoL"
```

No authentication tokens required -- the VPS serves HTTP directly.

---

## Updating the Application

```bash
# SSH in
ssh root@72.62.253.226

# Pull latest code
cd /root/reverse-recruiter
git pull origin main

# Rebuild and restart
cd execution
docker build -t clay-automation .
docker stop clay-auto && docker rm clay-auto
docker run -d --name clay-auto --restart=always \
  --memory=8g --shm-size=2gb \
  -p 8080:8080 \
  --env-file /root/reverse-recruiter/.env \
  clay-automation
```

Or use the deploy script from your local machine:
```bash
./execution/deploy_vps.sh 72.62.253.226
```

---

## Server Maintenance

### Docker Cleanup

```bash
# Remove unused images (reclaim disk space)
docker image prune -f

# Remove all stopped containers
docker container prune -f

# Full cleanup (images, containers, volumes, networks)
docker system prune -f
```

### System Updates

```bash
apt update && apt upgrade -y
```

### Disk Space

```bash
df -h
docker system df
```

### Restart Docker Daemon

```bash
systemctl restart docker
# The clay-auto container will auto-restart due to --restart=always policy
```

---

## Known Issues & Workarounds

### 1. `/dev/shm` for Chromium

Chromium requires 1-2GB of shared memory. This is handled by the `--shm-size=2gb` flag on `docker run`. Never remove this flag.

### 2. Container Not Starting

If the container fails to start, check for port conflicts or stale containers:
```bash
docker stop clay-auto && docker rm clay-auto
docker ps -a  # Check no other container is using port 8080
# Then re-run the docker run command
```

### 3. Out of Memory

If the container is OOM-killed, check `docker stats` and consider increasing `--memory` or reducing browser concurrency.

---

## File Structure Reference

```
/root/reverse-recruiter/          (on VPS)
├── .env                          # Environment variables
├── execution/
│   ├── Dockerfile                # Container definition
│   ├── main.py                   # Flask app entrypoint
│   ├── agent_orchestrator.py     # Core automation logic
│   ├── airtable_client.py        # Airtable API wrapper
│   ├── deploy_vps.sh             # Automated deploy script
│   ├── session_cookies.json      # Clay auth cookies
│   ├── requirements.txt          # Python dependencies
│   └── execute_local.py          # Local test runner
├── directives/
│   └── clay_directive.md         # AI agent instructions
└── .agent/skills/
    └── clay-people-search/       # Browser automation skill
```
