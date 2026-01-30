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

## 🚀 Phase 2: Production Validation (COMPLETED ✅)
**Goal:** Deploy the **existing Docker image** to Cloud Run and validate that authentication works from Google's infrastructure.

This phase validated that the agent can bypass bot detection and maintain session persistence (or self-heal login) from GCP.

### Checklist
- [x] **Secret Manager Setup**: Migrated `CLAY_EMAIL`, `CLAY_PASSWORD`, `AIRTABLE_API_KEY` to GCP Secret Manager.
- [x] **Cloud Run Deployment**: Deployed the current `execution/` Docker image to Cloud Run.
- [x] **Endpoint Test**: Hit `/test-clay-auth` and verified `logged_in: true`.
- [x] **IP/Bot Detection Check**: Confirmed Stealth Mode still works from GCP's IP ranges (`webdriver: false`).
- [x] **Resource Tuning**: Increased memory to 4GB and 2 vCPU for stable rendering.

### Lessons Learned
- **Auth Self-Healing**: Automated login handles expired cookies reliably.
- **Domain Restrictions**: Public access (`allUsers`) is restricted; verification requires ID tokens.
- **Memory**: 4GB RAM is the minimum safe threshold for complex Playwright snapshots on Cloud Run.

### Known Risks
| Risk | Mitigation |
|------|------------|
| GCP IP blocked by Clay | May need a residential proxy service (e.g., Bright Data, Oxylabs) |
| "Verify your email" on first login | User clicks email link once; subsequent logins should be smooth |
| "Verify your email" on first login | User clicks email link once; subsequent logins should be smooth |
| Memory exhaustion (`os error 11`) | Scale Cloud Run to 8GB RAM (verified requirement) |

---

## 🏗️ Phase 3: Full Automation Logic
**Goal:** Execute the full "Find & Import" loop for a single JobSeeker.

> [!NOTE]
> This phase should only begin **after** Phase 2 confirms stable production auth.

- [x] **Filter Automation (Infrastructure)**: Verified browser agent runs 20+ turns without crashing (Cloud Run 8GB).
- [ ] **Filter Automation (Logic)**: Fix `Selector matched multiple elements` error for Job Title dropdown.

---

## 🧠 Phase 4: Agent Logic Refinement (CURRENT)
**Goal:** Tuning the AI's interaction logic to handle Clay's complex UI (ambiguous selectors, multi-select dropdowns).

- [ ] **Job Title Selector**: Investigate why `@e21` matches multiple elements.
- [ ] **Retry Logic**: Ensure agent re-snapshots or uses more specific selectors on "matched multiple" error.
- [ ] **Full Loop**: Verify import trigger after filters are applied.

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
