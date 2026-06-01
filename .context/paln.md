# AI-Powered Job Application Agent: Full-Stack Technical Plan (v2)

## 1. Project Overview
A SaaS platform featuring a React frontend and FastAPI backend that deploys autonomous AI agents. The system utilizes LLMs for decision-making, Playwright for browser automation, and a WebSocket-based bridge for Real-time Human-in-the-Loop (HITL) interactions (OTPs).

## 2. Technical Stack
* **Frontend:** React.js (Vite), Tailwind CSS, TanStack Query (State Management).
* **Backend:** FastAPI (Async Python 3.12+).
* **Task Orchestration:** Celery + Redis (Handles long-running browser sessions).
* **Database:** PostgreSQL (User profiles, Job history, Tailored resumes).
* **Browser Engine:** Playwright Stealth (Headless/Headed toggle).
* **AI Models:** * **Claude 3.5 Sonnet:** Reasoning, Resume Tailoring, Question Drafting.
    * **GPT-4o-vision:** UI element mapping and CAPTCHA analysis.
* **Proxy:** Residential Proxy API (USA-based).

## 3. Web Architecture & Data Flow

### A. The Dashboard (React)
* **Application Feed:** Real-time list of active, pending, and completed applications.
* **The "Agent Console":** A WebSocket-driven component that streams agent logs and screenshots.
* **HITL Modal:** A triggered popup for Email OTP/Manual CAPTCHA input.

### B. The API & Workers (FastAPI + Celery)
* **Endpoints:** `/apply` (POST), `/status/{job_id}` (GET), `/otp/submit` (POST).
* **Worker Lifecycle:**
    1.  Worker starts a Playwright instance via a Residential Proxy.
    2.  Worker parses JD -> Generates tailored Resume -> Stores in S3/Local DB.
    3.  Worker navigates to Portal (Workday/iCIMS/Greenhouse).
    4.  **Event: OTP Needed** -> Worker sets state to `AWAITING_OTP` in Redis -> Sends WS message to Frontend.
    5.  Worker pauses using `asyncio.Event` until OTP is received from the API.

## 4. Feature-Specific Logic

### I. ATS Mirroring & Tailoring
* **Extraction:** Identify keywords, required years of experience, and "deal-breaker" tech stacks.
* **Optimization:** The AI modifies the "Professional Summary" and "Skills" section of the resume PDF dynamically for every single application to match the JD scoring.

### II. Autonomous Browser Navigation
* **Workday/iCIMS Handler:** Specialized scripts to handle the "Create Account" vs "Sign In" logic.
* **Drafting:** AI reads custom questions (e.g. "Diversity statements," "Technical challenges") and drafts answers based on the user's specific career history.

### III. Identity & Stealth
* **State-Specific Targeting:** Assigns a proxy IP matching the job's location (e.g., California proxy for a SF-based role).
* **Fingerprint Rotation:** Each application uses a unique User-Agent and browser fingerprint to mimic different computers.

## 5. Implementation Roadmap for Claude Code

### Phase 1: Database & Core API
* Define SQLAlchemy/SQLModel schemas for `User`, `JobApplication`, and `TailoredResume`.
* Setup FastAPI auth (JWT).

### Phase 2: The Agentic Worker (Celery + Playwright)
* Build a generic `BasePortalAgent` class.
* Implement `WorkdayAgent(BasePortalAgent)` with logic for account creation and file uploading.
* Integrate `playwright-stealth`.

### Phase 3: The OTP & WebSocket Bridge
* Implement a Redis Pub/Sub or WebSocket manager in FastAPI.
* Create the React component that listens for `REQUIRE_OTP` signals and updates the UI.

### Phase 4: AI Logic (RAG)
* Create the "Resume Tailor" service using Claude 3.5 Sonnet.
* Ensure "Fact-Checking" logic prevents the AI from hallucinating skills.

## 6. Success Verification
* **Automated Confirmation:** Agent waits for "Application Submitted" text on-screen.
* **Email Sync:** Integration with IMAP/Gmail API to verify receipt of the confirmation email.