/**
 * ============================================================================
 * WHY_AI : UI MASTER SCHEMA (Reference Template)
 * Architecture: Hierarchy v3, Ouroboros Engine, Claudexor Control Plane
 * ============================================================================
 * * coordinate_system: [x, y, z]
 * x: Grid Column (0: Sidebar, 1: Main Left/Center, 2: Main Right)
 * y: Grid Row (0: Header, 1: Top Widgets, 2: Middle Widgets, 3: Bottom/Logs)
 * z: Z-Index & Security Layer (Immutable: 50+, Mutable: 10-40)
 */

export const UI_MASTER_SCHEMA = {
  // --------------------------------------------------------------------------
  // GLOBAL LAYOUT & NAVIGATION
  // --------------------------------------------------------------------------
  layout: {
    TopHeader: {
      id: "global_header",
      name: "Supervisor Header Bar",
      coordinates: [1, 0, 50], // Охватывает верх, высокий Z-index (неизменяемый)
      type: "navigation",
      props: ["system_status", "version", "active_mode", "panic_button_state"],
      data_source: "launcher.py"
    },
    GlobalSidebar: {
      id: "global_sidebar",
      name: "Immutable Left Navigation",
      coordinates: [0, 0, 50], // Фиксирован слева (x:0)
      type: "navigation",
      props: ["menu_items", "active_route"],
      sections: ["Supervisor", "Claudexor", "Ouroboros", "BIBLE_Audit"]
    }
  },

  // --------------------------------------------------------------------------
  // CORE MODULES (Reusable Widgets)
  // --------------------------------------------------------------------------
  modules: {
    // === 1. CLAUDEXOR CONTROL PLANE ===
    ClaudexorHarnessList: {
      id: "module_claudexor_list",
      name: "Active LLM Harnesses",
      coordinates: [1, 2, 20], 
      type: "dashboard_widget",
      description: "Отображение квот, контекста и ротации моделей (Sonnet, Opus, DeepSeek).",
      props: ["harness_array", "quota_utilization", "latency"],
      data_source: "claudexor_router"
    },
    ContextFitMap: {
      id: "module_contextfit_map",
      name: "ContextFit Shared Flow",
      coordinates: [2, 2, 20],
      type: "visualization",
      description: "Графовая связность и компрессия контекста (Token Budget).",
      props: ["centrality_scores", "total_tokens", "deficit"],
      data_source: "ContextFit.py"
    },

    // === 2. OUROBOROS SELF-EVOLUTION ENGINE ===
    EvolutionPipeline: {
      id: "module_evo_pipeline",
      name: "Evolution Pipeline Graph",
      coordinates: [1, 1, 30],
      type: "flow_graph",
      description: "Визуализация пайплайна: Trigger -> Agent Core -> Commit Gate -> Self-Deployment.",
      props: ["current_stage", "mutation_hash", "iteration_number"],
      data_source: "Ouroboros_Task_Manager"
    },
    MutableRuntimeState: {
      id: "module_mutable_state",
      name: "Mutable Runtime State",
      coordinates: [1, 2, 10], // Z: 10 (самый низкий, изменяемый слой)
      type: "list_widget",
      description: "Список загруженных skills (agent-skills) и ожидающих мутаций (skill_wrapper.py).",
      props: ["loaded_skills", "pending_mutations"],
      data_source: "WorktreeSandbox"
    },

    // === 3. SECURITY & AUDIT (BIBLE.md) ===
    BibleAuditPanel: {
      id: "module_bible_audit",
      name: "BIBLE.md Compliance Audit",
      coordinates: [2, 1, 40], // Правая колонка, высокий приоритет
      type: "security_widget",
      description: "Статус 13 конституционных принципов и правило MAX Risk.",
      props: ["principles_status", "max_risk_level", "gate_status"],
      data_source: "classify_diff.py"
    },
    CommitGateStatus: {
      id: "module_commit_gate",
      name: "Reviewed Commit Gate",
      coordinates: [2, 1, 40],
      type: "status_widget",
      description: "Отображение Preflight SHA-256 Fingerprint и результатов 3-Way Apply.",
      props: ["hash_before", "hash_after", "verification_status"],
      data_source: "Commit_Gate"
    },

    // === 4. EXTERNAL BRIDGE (FastMCP) ===
    FastMcpBridge: {
      id: "module_fastmcp_bridge",
      name: "External FastMCP Bridge",
      coordinates: [1, 1, 20],
      type: "flow_graph",
      description: "Маршрутизация к внешнему репозиторию (project-evolution).",
      props: ["bridge_status", "latency", "data_flow_rate", "external_repo_path"],
      data_source: "mcp_config.json"
    },

    // === 5. SYSTEM LOGS & TELEMETRY ===
    SystemActivityLog: {
      id: "module_system_log",
      name: "Inter-Agent Log Communication",
      coordinates: [2, 3, 30], // Правая колонка, самый низ (y:3)
      type: "terminal_stream",
      description: "Живой поток логов, tamper-evident record (ledger.jsonl).",
      props: ["log_entries", "filter_mode"],
      data_source: "ledger.jsonl"
    },
    AgentTaskList: {
      id: "module_agent_tasks",
      name: "Active Agent Tasks (Mutants)",
      coordinates: [2, 2, 20],
      type: "task_list",
      description: "Оркестрация суб-задач (context_fetch, skill_generation, commit_gate).",
      props: ["active_tasks", "sub_task_progress"],
      data_source: "Agent_Orchestrator"
    }
  },

  // --------------------------------------------------------------------------
  // VIEW TEMPLATES (Pre-composed Dashboard Layouts)
  // --------------------------------------------------------------------------
  views: {
    SUPERVISOR_CORE: [
      "TopHeader", "GlobalSidebar", 
      "EvolutionPipeline", "ClaudexorHarnessList", "ContextFitMap", 
      "BibleAuditPanel", "SystemActivityLog"
    ],
    EXTERNAL_PROJECT: [
      "TopHeader", "GlobalSidebar",
      "FastMcpBridge", "AgentTaskList",
      "CommitGateStatus", "SystemActivityLog"
    ],
    SELF_EVOLUTION: [
      "TopHeader", "GlobalSidebar",
      "EvolutionPipeline", "MutableRuntimeState", 
      "BibleAuditPanel", "SystemActivityLog"
    ],
    AGENT_ORCHESTRATION: [
      "TopHeader", "GlobalSidebar",
      "ClaudexorHarnessList", "ContextFitMap",
      "EvolutionPipeline", // Used here as Agent Hierarchy Graph
      "AgentTaskList", "SystemActivityLog"
    ]
  }
};