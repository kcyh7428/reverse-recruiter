# Reverse Recruiter: Solution Architecture & Infrastructure Guide

## Document Purpose
This document explains how the Reverse Recruiter solution works end-to-end, describes the current VPS infrastructure, and includes historical evaluation of alternative hosting platforms for reference.

---

## Part 1: What the Solution Does

### Business Purpose
Reverse Recruiter is an **AI-powered recruiting automation system**. It takes job seeker profiles from Airtable, uses AI to interpret their targeting criteria, then automates Clay.com's People Search interface to find and import matching professional profiles.

### End-to-End Flow

```
┌──────────────┐     ┌───────────────────┐     ┌──────────────────┐     ┌─────────────┐
│   AIRTABLE   │────▶│  OpenAI GPT-4o    │────▶│  BROWSER AGENT   │────▶│  CLAY.COM   │
│              │     │   (LLM)           │     │                  │     │             │
│ Job Seeker   │     │ Interprets raw    │     │ Controls Clay's  │     │ Stores      │
│ records with │     │ criteria into     │     │ People Search    │     │ imported    │
│ targeting    │     │ optimized search  │     │ UI via Playwright│     │ profiles    │
│ criteria     │     │ parameters        │     │ + Agent Browser  │     │             │
└──────────────┘     └───────────────────┘     └──────────────────┘     └─────────────┘
       │                                                                       │
       │◀──────────────────── Status updated to "Ready to Launch" ◀────────────┘
```

**Step-by-step:**
1. A recruiter adds a job seeker to Airtable with fields like Target Titles, Target Geos, Seniority, Industries, and Exclude Keywords
2. The system is triggered via an HTTP request to the VPS
3. **OpenAI GPT-4o** reads the raw job seeker data and optimizes it (e.g., consolidates 10 locations down to 3, picks the top 5 job titles)
4. The **Agent Browser CLI** (Playwright-based) opens Clay.com in a real Chromium browser
5. GPT-4o acts as the "brain" — it sees a snapshot of the page, decides what to click/type, and issues commands
6. The browser fills in all Clay search filters (titles, locations, seniority, industries)
7. Profiles are imported into the Clay table
8. Airtable status is updated to "Ready to Launch"

### The 3-Layer Architecture

| Layer | Purpose | Technology |
|-------|---------|------------|
| **Directives** | Markdown SOPs that define "what to do" step-by-step | `directives/clay_directive.md` |
| **Orchestration** | AI decision-making loop that reads the page and acts | Python + OpenAI GPT-4o + Agent Browser CLI |
| **Execution** | Deterministic utilities (login, cookies, Airtable API) | Python (Flask, pyairtable) |

### External Services Used

| Service | What It Does | Cost |
|---------|-------------|------|
| **OpenAI API (GPT-4o)** | LLM that interprets search criteria and controls the browser | Pay-per-token (~$0.01-0.05 per automation run) |
| **Airtable** | Database of job seekers and their targeting criteria | Free tier or $20/mo per user |
| **Clay.com** | People search platform with LinkedIn-connected profiles | Paid subscription (varies) |
| **Agent Browser CLI** | Open-source Playwright wrapper by Vercel | Free |
| **Hostinger VPS** | Hosts the Docker container that runs everything | ~$7/mo (fixed) |

### Key Files

```
Reverse Recruiter/
├── execution/
│   ├── main.py                  ← Flask web server (VPS entrypoint)
│   ├── agent_orchestrator.py    ← Core automation loop (the "brain")
│   ├── airtable_client.py       ← Reads/writes job seeker records
│   ├── Dockerfile               ← Container definition
│   ├── requirements.txt         ← Python dependencies
│   ├── session_cookies.json     ← Clay login cookies
│   ├── local_test.sh            ← Script to test locally with Docker
│   └── execute_local.py         ← Run a single job seeker locally
├── directives/
│   └── clay_directive.md        ← Step-by-step instructions for the AI agent
├── .agent/skills/               ← Browser automation skill definitions
├── AGENTS.md                    ← Architecture documentation
└── VPS_SETUP.md                 ← Deployment commands & infrastructure reference
```

---

## Part 2: Current Infrastructure (Hostinger VPS)

### What's Running

| Component | Details |
|-----------|---------|
| **Platform** | Hostinger VPS (KVM4, bare metal Docker) |
| **IP Address** | 72.62.253.226 |
| **OS** | Ubuntu 24.04 |
| **RAM** | 16 GB |
| **Container Memory** | 8 GB limit |
| **Container shm-size** | 2 GB |
| **Container Name** | `clay-auto` |
| **Build System** | Local Docker build on VPS |

### How Deployment Works

From the local machine, a single script deploys the entire system:

```bash
# Automated deploy (from local machine)
./execution/deploy_vps.sh 72.62.253.226

# Or manual deploy (SSH into VPS)
ssh root@72.62.253.226
cd /root/reverse-recruiter && git pull origin main
cd execution && docker build -t clay-automation .
docker stop clay-auto && docker rm clay-auto
docker run -d --name clay-auto --restart=always \
  --memory=8g --shm-size=2gb \
  -p 8080:8080 \
  --env-file /root/reverse-recruiter/.env \
  clay-automation
```

### Why Hostinger VPS

- **Full `/dev/shm` control**: `--shm-size=2gb` eliminates the `os error 11` crashes entirely
- **No gVisor sandbox**: Docker runs on bare metal Linux, so Chromium has full system call access
- **No timeout limits**: Automations can run as long as needed
- **Persistent storage**: Cookies and state persist across restarts
- **Simple deployment**: SSH + Docker commands, or use the deploy script
- **AI via OpenAI API**: GPT-4o is called over HTTPS -- works from any server

### Estimated Monthly Cost

| Resource | Cost |
|----------|------|
| Hostinger VPS (KVM4) | ~$7/mo (fixed) |
| OpenAI API (GPT-4o) | ~$1-5/mo |
| **Total** | **~$8-12/mo** |

---

## Part 3: Infrastructure Alternatives (Historical)

> **Decision completed: Hostinger VPS selected and deployed.** The sections below are retained as historical context from the original infrastructure evaluation.

### What We Need From Any Platform

Before comparing alternatives, here are the hard requirements:

1. **Run Docker containers** — the solution is packaged as a Docker image with Chromium, Playwright, Node.js, and Python
2. **8 GB+ RAM** — Chromium browser + AI processing needs significant memory
3. **Long-running processes** — automation can run 5-15 minutes per job seeker
4. **Proper `/dev/shm` support** — Chromium needs shared memory that isn't artificially capped
5. **HTTP endpoint** — must be triggerable via a web request
6. **Environment variables** — for API keys and credentials
7. **CLI-deployable** — a coding agent must be able to deploy without a web GUI

---

### Option A: Hostinger VPS (Recommended Alternative)

**What it is:** A traditional Virtual Private Server — you get a full Linux machine with root access, running Ubuntu 24.04 with Docker pre-installed.

| Spec | Details |
|------|---------|
| **Plan** | KVM 4 |
| **Resources** | 4 vCPU, 16 GB RAM, 200 GB NVMe SSD |
| **Price** | ~$6.99/mo (promotional) |
| **Docker support** | Pre-installed with visual Docker Manager |
| **`/dev/shm`** | Full control — set `--shm-size=2gb` on `docker run` |
| **Timeout** | None — processes can run indefinitely |
| **AI assistant** | "Kodee" AI for server management via chat |

**Why it works for you:**
- Full `/dev/shm` control eliminates the `os error 11` problem entirely
- Docker is pre-installed — no setup needed
- A coding agent can SSH in and run `docker build` + `docker run` commands
- The "Deploy to Hostinger VPS" GitHub Action enables automated deployments
- Much simpler mental model: it's just a computer in the cloud running your Docker container

**Trade-offs:**
- **Always-on billing**: You pay ~$7/mo whether or not you're running automations (vs Cloud Run's pay-per-use)
- **You manage the server**: Software updates, security patches, disk space monitoring. A coding agent can handle this, but it's more work than a managed service.
- **No auto-scaling**: One VPS handles one thing at a time. If you need to run 10 job seekers simultaneously, you'd need a bigger plan or queue them.
- **AI API access**: OpenAI GPT-4o is called over HTTPS from the VPS -- works from any server
- **No built-in HTTPS**: You'd need to set up a reverse proxy (nginx + Let's Encrypt) or use Cloudflare Tunnel for HTTPS endpoints

**Deployment from a coding agent:**
```bash
# SSH into the VPS
ssh root@<your-hostinger-ip>

# Pull and run the Docker container
docker build -t clay-automation .
docker run -d --restart=always \
  --memory=4g --shm-size=2gb \
  -p 8080:8080 \
  --env-file .env \
  clay-automation
```

**Sources:**
- [Hostinger Docker VPS Hosting](https://www.hostinger.com/docker-hosting)
- [Hostinger VPS Pricing](https://www.hostinger.com/pricing/vps-hosting)
- [Hostinger Docker VPS Review 2026](https://hostadvice.com/hosting-company/hostinger-reviews/hostinger-docker-vps-review/)

---

### Option B: Railway

**What it is:** A developer-friendly PaaS (like a simpler version of Google Cloud Run). You connect a GitHub repo and it builds + deploys automatically.

| Spec | Details |
|------|---------|
| **Resources** | Scales up to 32 GB RAM |
| **Price** | Usage-based, starting at $5/mo (Hobby) or $20/mo (Pro) |
| **Docker support** | Yes — detects Dockerfile automatically |
| **`/dev/shm`** | Limited control (no `--ipc=host` flag) |
| **Timeout** | No hard limit on process duration |
| **CLI** | `railway` CLI for deployment |

**Why it might work:**
- Very simple: `railway up` deploys from your local folder
- GitHub integration for automatic deploys on push
- No server management at all
- Good logging and monitoring dashboard

**Trade-offs:**
- **`/dev/shm` concerns**: Same Chromium memory issues as Cloud Run — Railway doesn't expose `--ipc=host` or `--shm-size` controls easily
- **Workers getting killed**: Multiple reports of Gunicorn + Playwright workers being SIGKILL'd due to memory pressure
- **No free tier**: $5/mo minimum after 30-day trial
- **Less control**: Can't tune Linux kernel parameters

**Sources:**
- [Railway Pricing](https://railway.com/pricing)
- [Railway Playwright Issues](https://station.railway.com/questions/worker-timeouts-and-playwright-browser-e-d6499ade)

---

### Option C: Fly.io

**What it is:** A Docker-native platform with a powerful CLI (`flyctl`). Runs containers on bare-metal servers worldwide.

| Spec | Details |
|------|---------|
| **Resources** | Up to 16 GB RAM per machine |
| **Price** | Usage-based, ~$0.015/hr for 2GB RAM machine |
| **Docker support** | Native — deploys any Dockerfile |
| **`/dev/shm`** | Better than Cloud Run — runs on Firecracker microVMs with more system call support |
| **Timeout** | Configurable, no hard cap |
| **CLI** | `flyctl` — very coding-agent friendly |

**Why it might work:**
- `fly deploy` is a single command
- Better Chromium compatibility than Cloud Run (no gVisor restrictions)
- Persistent volumes available for cookie storage
- Good community documentation for Playwright deployments

**Trade-offs:**
- **Smaller community**: Less documentation than GCP or AWS
- **Chromium path issues**: Some users report browser executable path problems that require Dockerfile tweaks
- **No built-in AI integration**: You'd call the AI API externally (e.g., OpenAI)

**Sources:**
- [Running Playwright on Fly.io](https://stephenhaney.com/2024/playwright-on-fly-io-with-bun/)
- [Fly.io Playwright Community Thread](https://community.fly.io/t/playwright-not-working/6784)

---

### Option D: DigitalOcean (Droplet or App Platform)

**What it is:** Two options — App Platform (managed PaaS like Cloud Run) or Droplets (VPS like Hostinger).

| Spec | App Platform | Droplet |
|------|-------------|---------|
| **Resources** | Up to 8 GB RAM | Up to 32 GB RAM |
| **Price** | $25-39/mo for 2GB | ~$48/mo for 8GB |
| **Docker** | Yes | Yes (manual install) |
| **`/dev/shm`** | Limited | Full control |
| **Deployment** | Git push or `doctl` CLI | SSH + Docker commands |

**Trade-offs:**
- App Platform has the same `/dev/shm` limitations as Cloud Run
- Droplets work well but cost more than Hostinger for equivalent specs
- Strong CLI (`doctl`) that coding agents can use

**Sources:**
- [DigitalOcean App Platform Pricing](https://docs.digitalocean.com/products/app-platform/details/pricing/)
- [DigitalOcean vs Google Cloud](https://www.digitalocean.com/resources/articles/digitalocean-vs-google-cloud-platform)

---

## Part 4: Comparison Matrix

| Criteria | Google Cloud Run (Former) | Hostinger VPS (Current) | Railway | Fly.io | DigitalOcean Droplet |
|----------|---------------------------|---------------|---------|--------|---------------------|
| **Monthly cost** | ~$5-15 (pay-per-use) | ~$7 (fixed) | ~$10-20 (usage) | ~$10-15 (usage) | ~$48 (fixed) |
| **`/dev/shm` support** | Poor (64MB cap) | Full control | Poor | Moderate | Full control |
| **Chromium stability** | Fragile (gVisor) | Stable (native) | Fragile | Moderate | Stable (native) |
| **Agent-deployable** | Yes (`gcloud` CLI) | Yes (SSH + Docker) | Yes (`railway` CLI) | Yes (`flyctl` CLI) | Yes (`doctl` CLI) |
| **Server management** | None | Some (updates, etc.) | None | Minimal | Some |
| **Max process duration** | 15 minutes | Unlimited | Unlimited | Configurable | Unlimited |
| **Scale to zero** | Yes | No | Yes | Yes | No |
| **Setup complexity** | Medium | Low | Low | Medium | Medium |
| **AI integration** | External API call | OpenAI API (selected) | External API call | External API call | External API call |

---

## Part 5: Decision Outcome

> **Decision completed: Hostinger VPS selected and deployed.**

### Chosen: Hostinger VPS (KVM4)

Reasons:
1. **Eliminates the `os error 11` problem entirely** -- full `/dev/shm` control with `--shm-size=2gb`
2. **Simplest mental model** -- it's just a computer in the cloud. The coding agent SSHs in, builds the Docker image, and runs it.
3. **Cost-effective at ~$7/mo** for 16 GB RAM
4. **No timeout limits** -- automations can run as long as needed
5. **Docker pre-installed** -- zero setup friction
6. **The coding agent can manage everything** -- deployments, updates, monitoring, all via SSH commands

### What changed in the code:
- **AI provider**: Switched from Vertex AI (Gemini 2.5 Flash) to OpenAI API (GPT-4o). Updated `agent_orchestrator.py` to use the OpenAI SDK.
- **Environment variables**: `GEMINI_API_KEY` replaced by `OPENAI_API_KEY`
- **Trigger mechanism**: `http://72.62.253.226:8080/run-automation` (no auth token needed)
- **Deployment**: `deploy_vps.sh` script replaces `gcloud` CLI commands
- **Dockerfile, Flask app, Airtable client**: Unchanged
