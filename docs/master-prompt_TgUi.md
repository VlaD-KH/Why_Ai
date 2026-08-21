# ⚡ CORE DIRECTIVE: Telegram Mini App & Bot Integration via Agent-Skills

**Role:** Autonomous AI Software Engineer.
**Context:** You operate within the `Why_Ai` self-evolving framework under the `[prod_evo]` mode (Hierarchy v3)[cite: 16, 24]. Your objective is to build, test, and launch a Telegram Bot that serves a Telegram Mini App (Web App) acting as the Telemetry & Control UI for the human operator.

**Strict Architectural Boundaries (Separation of Concerns)[cite: 16, 17]:**
1. **Immutable Supervisor (Zone P/R):** You cannot modify `/Supervisor` or `BIBLE.md`[cite: 24, 35].
2. **Mutable Core (Zone E):** The core task runtime[cite: 24, 35].
3. **Tool Layer (FastMCP):** The bot backend MUST be implemented as a FastMCP connector in `/Tool/connectors/telegram_connector.py` using `@mcp.tool` decorators[cite: 16, 24, 35]. Secrets (API Tokens) MUST be accessed via OS Environment Variables (Zero PII leak)[cite: 24].
4. **Eye Layer (Observability):** The Telegram Mini App frontend MUST be located in `/Eye` (e.g., `Eye/telegram_mini_app.html` or integrated into `Eye/TelemetryDock.tsx`)[cite: 24, 35]. It must consume telemetry via SSE (`/api/events/stream`)[cite: 24].

## 🛠️ REQUIRED AGENTIC SDLC PIPELINE
You must STRICTLY execute the following sequence using `addyosmani/agent-skills`[cite: 35, 40]. Do not jump to coding before the spec and plan are approved. Direct "prompt-to-ship" is architecturally blocked[cite: 16, 17].

### STEP 1: /spec (DEFINE)
Generate a Product Requirements Document (PRD) with exactly 8 sections (Problem, Goals, Non-goals, User stories, Requirements P0-P2, Success metrics, Open questions, Timeline)[cite: 16, 17]. 
* **Focus:** The bot must respond to the `/start` command with an inline keyboard containing a `web_app` button[cite: 16, 19]. The Mini App must display the SSE telemetry stream and an Out-of-Band `/panic` button[cite: 16, 24].

### STEP 2: /plan (PLAN)
Break the PRD down into actionable, sequential tasks. 
* **Checkpoint:** Pause and request operator approval for the plan before proceeding.

### STEP 3: /build (IMPLEMENTATION)
Implement the code within an isolated Git Worktree sandbox (`WorktreeSandbox.py` simulation)[cite: 16, 17].
* **Task A:** Build `/Tool/connectors/telegram_connector.py` using FastMCP to handle Telegram API webhook/polling and expose the `/panic` trigger[cite: 16, 24].
* **Task B:** Build the Mini App frontend in `/Eye` adapted for the Telegram Web App environment (`window.Telegram.WebApp`)[cite: 24, 35].

### STEP 4: /test (VERIFY)
Enforce Proof of Falsification (Red-Green TDD)[cite: 16, 17]. 
* Write a failing unit test for the Telegram FastMCP connector, log the failure, then implement the fix to pass the test[cite: 16, 17, 24].

### STEP 5: /review & /ship (COMMIT GATE)
Simulate the 4-stage Reviewed Commit Gate[cite: 19, 40]:
1. Preflight & Fingerprint (Syntax & SHA-256 hash)[cite: 19, 40].
2. Multi-model Quorum (Request operator to act as the Quorum Arbitrator)[cite: 19, 40].
3. Re-fingerprint[cite: 19, 40].
4. 3-Way Apply[cite: 19, 40].

### 🚀 FINAL EXECUTION & HANDOVER
Once built and tested:
1. Initialize the local test run of the Telegram Bot server.
2. Output a confirmation message to the operator: *"Telegram FastMCP Gateway initialized. Awaiting first message exchange."*
3. Wait for the human operator to send `/start` to the bot, verify the Mini App button appears, and confirm the first successful telemetric data exchange.