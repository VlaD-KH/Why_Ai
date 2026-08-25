# MASTER PROMPT: MVP Bootstrapping via Agent-Skills & Self-Evo Preparation

## Context & Objective
Initialize the production-grade MVP skeleton for our self-evolving multi-agent system (formerly codenamed `_Ai`, incorporating Ouroboros security paradigms and Claudexor control plane orchestrations). 

You are an expert systems architect and autonomous agent engineer. Your task is to generate a comprehensive, syntactically perfect, and ready-to-run file and folder structure along with the complete core documentation files for the bootstrap phase. 

This bootstrap phase uses the methodology defined in `https://github.com/addyosmani/agent-skills` to establish developer workflows and strict static guardrails (Hierarchy v3, 13 principles of BIBLE.md, and FastMCP definitions) *prior* to activating or implementing the mutable, self-modifying runtime (`[self_evo]`).

---

## Target Project Directory Structure
Before executing any generation, visualize and enforce the target bootstrap layout:
```text
/System_Root/
├── /Supervisor/                       # Immutable Core Lifecycle & Process Controller
│   ├── /Constitution/
│   │   └── BIBLE.md                   # Immutable 13 Constitutional Principles
│   ├── launcher.py                    # Process manager, out-of-band panic handler
│   └── guard-policy-plane.sh          # Deep file-system read-only locker
├── /Core/                             # Mutable Task Runtime & Logic Core (Future [self_evo] target)
│   ├── ContextFit.py                  # Graph-based memory & central centrality manager
│   ├── classify_diff.py               # Risk classifier enforcing MAX risk policy chains
│   └── failures.jsonl                 # Failures pattern register (Meta-over-Patch)
├── /Eye/                              # Interface, Monitoring, and Metrics Surface
│   └── TelemetryDock.tsx              # Local metrics visualization layer
├── /Tool/                             # Installed Agent-Skills & FastMCP Connectors
│   ├── /skills/                       # Local copy of selected addyosmani/agent-skills
│   └── mcp_config.json                # FastMCP server registration schemas
└── /Project/                          # External Module Target Workspace (Prod_evo sandbox)
    └── .ai-loop/
        └── policy/
            └── local_policy.yaml      # Project-specific strict overrides
```

---

## Required Artifacts & Generation Specs

You must generate the complete, production-grade text contents for the following 5 files. Each file must be output as a separate, fully realized block with no summaries, placeholding comments (`// TODO`), or truncation.

### 1. `project_vision.md` (Project Vision & Scope)
- **Primary Value Proposition**: Secure, deterministic, and self-improving development framework. Explain how it eliminates the "God Prompt" antipattern and controls the "Verification Tax".
- **Sovereign Separation**: Establish the strict boundaries between the Immutable Supervisor (Zone P/R - absolute write block) and the Mutable Runtime (Zone E - controlled modifications).
- **Target Users & Non-Functional Requirements**: Enterprise-grade security, mathematical "fail-closed" determinism, air-gapped safe executions, and sub-100ms telemetry processing.

### 2. `PRD.md` (Product Requirements Document)
- **Process Sequence**: Ground the product requirements in the 6-stage pipeline: `DEFINE -> PLAN -> BUILD -> VERIFY -> REVIEW -> SHIP`.
- **FastMCP Transport Integrations**: Define schemas for external data transport (Google Drive, Slack, GitHub, local Postgres) using the Model Context Protocol. Specify that raw database credentials never enter LLM prompts; instead, they are accessed through FastMCP schemas.
- **Verification Gates**: Highlight why "prompt-to-ship" is banned. Design strict green-status requirements ( TDD Red-Green-Refactor with verified prior failures, 5-axis Quorum review).

### 3. `roadmap.md` (Roadmap & Milestones)
- **Phase 1: Static Guardrails & Skills Integration (Current Phase)**: Focus on mounting `addyosmani/agent-skills` to `/Tool/skills` and configuring static check scripts (`classify_diff.py` and `guard-policy-plane.sh`).
- **Phase 2: Worktree Isolation & Multi-Model Quorum**: Implement temporary `Git Worktrees` for candidate changesets, SHA-256 fingerprinting (Preflight and Re-fingerprint), and cross-model кворум via Claudexor-like reviewers.
- **Phase 3: Autonomous Recursive Loop Activation**: Activate `failures.jsonl` log parsing, `Size Ratchets` (shrink-only limits) enforcing, and `Recursive Free Evolution` mode.

### 4. `todo.md` (Task Breakdown)
- Create a highly granular, checklist-based todo task matrix mapped to the `/Supervisor`, `/Core`, `/Eye`, `/Tool`, and `/Project` directory structure.
- Every task must have clear, measurable acceptance criteria (e.g., "Returns exit code 10 on safety-floor violation", "Maintains file size ceiling under shrink-only mandate").

### 5. `function_list.md` (Functional Specification & API Surface)
- Specify exact Python/TypeScript interface signatures, CLI entry points, and schema definitions for the bootstrap phase.
- Must include the exact CLI input/output parameters for:
  - `classify_diff.py --repo <path> --diff <patch>`
  - `guard-policy-plane.sh --path <dir>`
  - `ContextFit.py --compact --deficit <tokens>`
  - `launcher.py --panic-stop`

---

## Constraint Enforcement Rules
You must strictly inject and enforce these core constraints within the generated codebase:

1. **MAX Risk Policy Chain**: 
   $$\text{Risk}_{\text{final}}(\text{path}) = \max(\text{Risk}_{\text{layer}\_0}(\text{path}), \dots, \text{Risk}_{\text{layer}\_n}(\text{path}))$$
   Nested policies can only tighten security constraints, never loosen them. Any nested policy attempting to override a parent constraint with a lower risk level must trigger an immediate fatal exit with **code 10** via `--self-check`.
2. **Strict Non-Self-Reference**:
   The active `Task Runtime` is prohibited from reading or modifying its own review logic or the BIBLE.md file. This block is enforced by the filesystem locks in `guard-policy-plane.sh`.
3. **No Hardcoded Secrets or PII**:
   Enforce zero PII leaks. Every external credential must be fetched via FastMCP schema lookups or environment-bound variable lookups (`process.env` / `os.getenv`). Prevent any plaintext auth token storage.

Generate the directory structure and files now to begin the MVP compilation.
