---
name: using-agent-skills
description: Discovers and invokes agent skills. Use when starting a session or when you need to discover which skill applies to the current task. This is the meta-skill that governs how all other skills are discovered and invoked.
---

# Using Agent Skills (Meta-Skill)

## Overview

Agent Skills is a collection of engineering workflow skills organized by development phase. Each skill encodes a specific process that senior engineers follow. This meta-skill helps discover and apply the right skill for the current task.

## Skill Discovery Decision Tree

```
Task arrives
    │
    ├── Don't know what you want yet? ──────→ interview-me
    ├── Have a rough concept, need variants? → idea-refine
    ├── New project/feature/change? ────────→ spec-driven-development (/spec)
    ├── Have a spec, need tasks? ───────────→ planning-and-task-breakdown (/plan)
    ├── Implementing code? ─────────────────→ incremental-implementation (/build)
    │   ├── UI work? ──────────────────────→ frontend-ui-engineering
    │   ├── API work? ─────────────────────→ api-and-interface-design
    │   ├── Need better context? ──────────→ context-engineering
    │   ├── Need doc-verified code? ────────→ source-driven-development
    │   └── Stakes high / unfamiliar code? ──→ doubt-driven-development
    ├── Writing/running tests? ─────────────→ test-driven-development (/test)
    │   └── Browser-based? ────────────────→ browser-testing-with-devtools
    ├── Something broke? ───────────────────→ debugging-and-error-recovery
    ├── Reviewing code? ────────────────────→ code-review-and-quality (/review)
    │   ├── Too complex? ──────────────────→ code-simplification (/code-simplify)
    │   ├── Security concerns? ────────────→ security-and-hardening
    │   └── Performance concerns? ─────────→ performance-optimization (/webperf)
    ├── Committing/branching? ──────────────→ git-workflow-and-versioning
    ├── CI/CD pipeline work? ───────────────→ ci-cd-and-automation
    ├── Deprecating/migrating? ─────────────→ deprecation-and-migration
    ├── Writing docs/ADRs? ────────────────→ documentation-and-adrs
    ├── Adding logs/metrics/alerts? ────────→ observability-and-instrumentation
    └── Deploying/launching? ──────────────→ shipping-and-launch (/ship)
```

## Core Operating Behaviors

### 1. Surface Assumptions
Before implementing anything non-trivial, explicitly state assumptions:
```
ASSUMPTIONS I'M MAKING:
1. [assumption about requirements]
2. [assumption about architecture]
3. [assumption about scope]
→ Correct me now or I'll proceed with these.
```

### 2. Manage Confusion Actively
When encountering inconsistencies, conflicting requirements, or unclear specifications:
1. **STOP.** Do not proceed with a guess.
2. Name the specific confusion.
3. Present the tradeoff or ask the clarifying question.
4. Wait for resolution before continuing.

### 3. Push Back When Warranted
Point out issues directly and explain concrete downsides.
