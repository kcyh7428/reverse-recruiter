# Testing Roadmap & Project Status

This document outlines the current progress, completed milestones, and the remaining steps to transition from local development to production-ready automation.

> [!IMPORTANT]
> **Strategy: Validate Production Early!**
> We deploy to Cloud Run with a minimal test (`/test-clay-auth`) *before* building full automation logic. This prevents wasting time on local-only features that might break in production.

---

## 🏁 Phase 1: Local Authentication (COMPLETED ✅)
**Goal:** Prove we can access Clay.com programmatically within a Dockerized environment.

- [x] **Bot Detection Bypass**: Implemented Stealth Mode in `agent_orchestrator.py`.
- [x] **Credential Handling**: Mapped `.env` credentials into Docker container.
- [x] **Auto-Login Flow**: Built a robust, self-healing login mechanism.
- [x] **Workspace Verification**: Confirmed landing on the authenticated workspace dashboard.

---

## 🚀 Phase 2: Production Validation (CURRENT - PRIORITY)
**Goal:** Deploy the **existing Docker image** to Cloud Run and validate that authentication works from Google's infrastructure.

This phase validates the unknowns before we invest more time in local-only development.

### Checklist
- [ ] **Secret Manager Setup**: Migrate `CLAY_EMAIL`, `CLAY_PASSWORD`, `AIRTABLE_API_KEY` to GCP Secret Manager.
- [ ] **Cloud Run Deployment**: Deploy the current `execution/` Docker image to Cloud Run.
- [ ] **Endpoint Test**: Hit `/test-clay-auth` from an external client (e.g., `curl`) and verify `logged_in: true`.
- [ ] **IP/Bot Detection Check**: Confirm Stealth Mode still works from GCP's IP ranges.
- [ ] **Resource Tuning**: If Chrome crashes, increase memory (4GB+) and `--shm-size` equivalent.

### Known Risks
| Risk | Mitigation |
|------|------------|
| GCP IP blocked by Clay | May need a residential proxy service (e.g., Bright Data, Oxylabs) |
| "Verify your email" on first login | User clicks email link once; subsequent logins should be smooth |
| Memory exhaustion | Scale Cloud Run to 4GB RAM, 2 vCPU |

---

## 🏗️ Phase 3: Full Automation Logic
**Goal:** Execute the full "Find & Import" loop for a single JobSeeker.

> [!NOTE]
> This phase should only begin **after** Phase 2 confirms stable production auth.

- [ ] **Filter Automation**: Automate job title, location, and seniority filter clicks.
- [ ] **Import Trigger**: Automate the "Add to table" button click.
- [ ] **Error Handling**: Build resiliency for zero results or limit hit.
- [ ] **Verification**: Successful import of 1 real profile into the Clay workbook.

---

## � Environment Comparison

| Aspect | Local (`local_test.sh`) | Cloud Run |
|--------|-------------------------|-----------|
| **Runtime** | Docker container | Docker container (same image) |
| **Browser** | `agent-browser` (Playwright) | `agent-browser` (Playwright) |
| **Stealth Mode** | ✅ Enabled | ✅ Enabled (same flags) |
| **Network/IP** | Residential | Google Data Center ⚠️ |
| **Credentials** | `.env` / ADC JSON | Secret Manager / Workload Identity |

The environments are **highly similar** now because we're running in Docker locally. The main variable is the **network/IP** origin.
