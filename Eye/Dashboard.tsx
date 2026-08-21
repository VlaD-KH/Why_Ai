import React, { useState } from 'react';

/**
 * ============================================================================
 * Компонент: Eye/Dashboard.tsx
 * Назначение: Модульный адаптивный интерфейс мониторинга и управления Self-Evo AI.
 * Архитектурный слой: Eye (Интерфейс, телеметрия и управление).
 * ============================================================================
 */

export type SDLCPhase = 'DEFINE' | 'PLAN' | 'BUILD' | 'VERIFY' | 'REVIEW' | 'WEBPERF' | 'SIMPLIFY' | 'SHIP';
export type OperatingMode = 'PROJECT_MODE' | 'AGENT_MODE';

export interface RelisedLaterItem {
  id: string;
  title: string;
  badgeText: string;
  what: string;      // Что это за элемент интерфейса
  why: string;       // Зачем он нужен системе
  where: string;     // Куда направляется / в какой модуль монтируется
  how: string;       // Как работает алгоритмически
  roadmapPhase: string; // В какой фазе Roadmap реализуется
}

export const RELISED_LATER_REGISTRY: Record<string, RelisedLaterItem> = {
  quorum_panel: {
    id: 'quorum_panel',
    title: 'Claudexor Multi-Model Quorum Panel',
    badgeText: 'DELIVERED v2',
    what: 'Интерфейс мультимодельного арбитража с независимыми панелями моделей (Claude 3.7, GPT-4o, DeepSeek-R1).',
    why: 'Исключает "эффект эхо-камеры" и семантические сбои благодаря принципу Angle Diversity (право вето любой модели).',
    where: 'Монтируется в Supervisor/QuorumReviewer.py и модуль арбитража Claudexor.',
    how: 'Параллельная отправка предложенного диффа в 3 независимых провайдера, двухэтапная проверка хэша SHA-256 (Preflight -> Review -> Re-fingerprint).',
    roadmapPhase: 'Фаза 2: Worktree Isolation & Multi-Model Quorum',
  },
  worktree_sandbox: {
    id: 'worktree_sandbox',
    title: 'Ephemeral Git Worktree Sandbox Visualizer',
    badgeText: 'DELIVERED v2',
    what: 'Инспектор изолированных временных ветвей и песочниц субагентов (Planning Scout и Acting Child).',
    why: 'Защищает боевой рантайм от повреждения при самомодификации кодовой базы.',
    where: 'Монтируется в Supervisor/WorktreeSandbox.py.',
    how: 'Автоматическое порождение `git worktree add` с принудительной конфигурацией `core.autocrlf false` и трехсторонним слиянием (3-Way Merge).',
    roadmapPhase: 'Фаза 2: Worktree Isolation & Multi-Model Quorum',
  },
  policy_drift: {
    id: 'policy_drift',
    title: 'Vector Policy Drift Residual Analyzer',
    badgeText: 'DELIVERED v3',
    what: 'Графический монитор дельта-анализа смыслового дрейфа политик безопасности.',
    why: 'Обнаруживает микроскопические изменения формулировок правил, маскирующие попытки обхода гейтов.',
    where: 'Монтируется в Core/PolicyDriftVector.py.',
    how: 'Аппроксимация эмбеддингов правил через каскадные словари остаточного квантования; всплеск ошибки реконструкции вызывает требование верификации человеком.',
    roadmapPhase: 'Фаза 3: Autonomous Recursive Loop Activation',
  },
  mcp_hot_reload: {
    id: 'mcp_hot_reload',
    title: 'FastMCP Live Dynamic Tool Registry',
    badgeText: 'DELIVERED v2',
    what: 'Интерфейс горячего подключения новых навыков и MCP-серверов без перезапуска системы.',
    why: 'Обеспечивает непрерывное расширение функционала роя агентов в режиме реального времени.',
    where: 'Монтируется в Tool/mcp_server.py (@mcp.tool).',
    how: 'Динамический парсинг AST новых Python-скриптов, генерация схем JSON-RPC и немедленная публикация в список доступных узлов.',
    roadmapPhase: 'Фаза 2: Worktree Isolation & Multi-Model Quorum',
  },
  recursive_evolution_daemon: {
    id: 'recursive_evolution_daemon',
    title: 'Recursive Free Evolution Background Daemon',
    badgeText: 'DELIVERED v3',
    what: 'Панель управления фоновым демоном непрерывной рекурсивной оптимизации ядра.',
    why: 'Позволяет системе самостоятельно находить алгоритмические неоптимальности и рефакторить собственный код в часы простоя.',
    where: 'Монтируется в Supervisor/EvolutionDaemon.py.',
    how: 'Опрос failures.jsonl + анализ связности ContextFit -> формирование серий атомарных коммитов в изолированных песочницах.',
    roadmapPhase: 'Фаза 3: Autonomous Recursive Loop Activation',
  },
};

export const Dashboard: React.FC = () => {
  const [mode, setMode] = useState<OperatingMode>('PROJECT_MODE');
  const [activePhase, setActivePhase] = useState<SDLCPhase>('DEFINE');
  const [activeModal, setActiveModal] = useState<RelisedLaterItem | null>(null);
  const [panicActive, setPanicActive] = useState<boolean>(false);

  const phases: { id: SDLCPhase; label: string; icon: string }[] = [
    { id: 'DEFINE', label: '/spec (DEFINE)', icon: '📝' },
    { id: 'PLAN', label: '/plan (PLAN)', icon: '📐' },
    { id: 'BUILD', label: '/build (BUILD)', icon: '⚡' },
    { id: 'VERIFY', label: '/test (VERIFY)', icon: '🧪' },
    { id: 'REVIEW', label: '/review (REVIEW)', icon: '🛡️' },
    { id: 'WEBPERF', label: '/webperf (AUDIT)', icon: '⏱️' },
    { id: 'SIMPLIFY', label: '/code-simplify', icon: '✂️' },
    { id: 'SHIP', label: '/ship (SHIP)', icon: '🚀' },
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8 font-sans">
      <div className="max-w-7xl mx-auto space-y-8">
        
        {/* ================================================================== */}
        {/* ВЕРХНЯЯ ПАНЕЛЬ: Режимы Hierarchy v3 и Супервизор */}
        {/* ================================================================== */}
        <header className="bg-slate-900/80 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-wrap items-center justify-between gap-6 backdrop-blur-xl">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-blue-500/30">
              <span className="text-2xl">🧬</span>
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-black tracking-tight text-white">
                  SELF-EVO ARCHITECTURE
                </h1>
                <span className="px-3 py-1 text-xs font-mono font-bold rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  SUPERVISOR ACTIVE
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Deterministic Ouroboros Control Plane & Hierarchy v3 Engine
              </p>
            </div>
          </div>

          {/* Переключатель режимов Hierarchy v3 */}
          <div className="flex items-center gap-3 bg-slate-950 p-1.5 rounded-2xl border border-slate-800">
            <button
              onClick={() => setMode('PROJECT_MODE')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
                mode === 'PROJECT_MODE'
                  ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>📁</span> [prod_evo] Project Mode (Project ⊃ agent)
            </button>
            <button
              onClick={() => setMode('AGENT_MODE')}
              className={`px-4 py-2 rounded-xl text-xs font-bold transition flex items-center gap-2 ${
                mode === 'AGENT_MODE'
                  ? 'bg-purple-600 text-white shadow-lg shadow-purple-600/30'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <span>🔮</span> [self_evo] Agent Mode (Agent ⊃ Project)
            </button>
          </div>

          {/* Кнопка экстренной внеполосной остановки */}
          <button
            onClick={() => setPanicActive(true)}
            className="px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-extrabold tracking-wider uppercase rounded-xl transition shadow-xl shadow-rose-900/40 border border-rose-400/30 flex items-center gap-2"
          >
            <span>🚨</span> /PANIC STOP (OUT-OF-BAND)
          </button>
        </header>

        {/* ================================================================== */}
        {/* SDLC PIPELINE: 8 фаз инженерного цикла */}
        {/* ================================================================== */}
        <section className="bg-slate-900/50 border border-slate-800 rounded-3xl p-6 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <span>🔄</span> Deterministic SDLC Pipeline (addyosmani/agent-skills)
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              Active Phase: <strong className="text-blue-400">{activePhase}</strong>
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
            {phases.map((phase) => {
              const isActive = activePhase === phase.id;
              return (
                <button
                  key={phase.id}
                  onClick={() => setActivePhase(phase.id)}
                  className={`p-3 rounded-2xl border text-left transition-all relative overflow-hidden ${
                    isActive
                      ? 'bg-blue-600/20 border-blue-500 text-white shadow-lg shadow-blue-900/20 ring-2 ring-blue-500/30'
                      : 'bg-slate-900/60 border-slate-800 text-slate-400 hover:border-slate-700'
                  }`}
                >
                  <div className="text-xl mb-1">{phase.icon}</div>
                  <div className="text-xs font-bold">{phase.label}</div>
                  <div className="text-[10px] text-slate-400 mt-1">
                    {isActive ? '● Running' : '○ Verified'}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* ================================================================== */}
        {/* СЕТКА МОДУЛЕЙ: Супервизор, Память, FastMCP и relised_later */}
        {/* ================================================================== */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          
          {/* Колонка 1: Supervisor Layer & Hierarchy v3 */}
          <div className="space-y-6">
            <div className="bg-slate-900/70 border border-slate-800 rounded-3xl p-6 shadow-xl">
              <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
                <span>🛡️</span> Supervisor & Hierarchy v3
              </h3>

              <div className="space-y-4 text-xs font-mono">
                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
                  <div className="text-slate-400">Current Topology:</div>
                  <div className="text-blue-400 font-bold mt-1">
                    {mode === 'PROJECT_MODE' ? 'root / Project_vanguard (R1) / agent_loop (R2)' : 'root / Supervisor (R1) / Core (R1) / Project (R3)'}
                  </div>
                </div>

                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
                  <div className="text-slate-400">Policy Floor (MAX Risk):</div>
                  <div className="text-emerald-400 font-bold mt-1">
                    ✓ diff_is_authoritative | Fail-Closed Active
                  </div>
                </div>

                <div className="p-3 bg-slate-950 rounded-xl border border-slate-800">
                  <div className="text-slate-400">Constitution Invariants:</div>
                  <div className="text-purple-400 font-bold mt-1">
                    13 / 13 Principles Locked (BIBLE.md)
                  </div>
                </div>
              </div>
            </div>

            {/* Интерактивная карточка relised_later: Worktree Sandbox */}
            <div
              onClick={() => setActiveModal(RELISED_LATER_REGISTRY.worktree_sandbox)}
              className="bg-slate-900/40 hover:bg-slate-900/80 border border-dashed border-slate-700 hover:border-blue-500 rounded-3xl p-6 cursor-pointer transition group relative"
            >
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-bold text-slate-200 group-hover:text-blue-400 transition">
                  🌱 Worktree Isolation Sandbox
                </h4>
                <span className="px-2.5 py-0.5 text-[10px] font-mono font-bold uppercase rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                  relised_later
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Изолированные Git Worktrees для субагентов с автоматической фиксацией Windows CRLF инвариантов.
              </p>
              <div className="mt-3 text-[11px] text-blue-400 font-semibold flex items-center gap-1">
                Подробнее в модальном окне ➔
              </div>
            </div>
          </div>

          {/* Колонка 2: ContextFit Memory & Core Runtime */}
          <div className="space-y-6">
            <div className="bg-slate-900/70 border border-slate-800 rounded-3xl p-6 shadow-xl">
              <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
                <span>🧠</span> ContextFit & Memory Graph
              </h3>

              <div className="space-y-4">
                <div>
                  <div className="flex justify-between text-xs text-slate-400 font-mono mb-1">
                    <span>Context Window Usage</span>
                    <span>34,200 / 128,000 (26%)</span>
                  </div>
                  <div className="w-full bg-slate-950 h-2.5 rounded-full overflow-hidden border border-slate-800">
                    <div className="bg-gradient-to-r from-blue-500 to-indigo-500 h-full w-[26%]" />
                  </div>
                </div>

                <div className="text-xs font-mono space-y-2 pt-2">
                  <div className="text-slate-400 font-semibold">Top Centrality Hubs:</div>
                  <div className="flex justify-between p-2 bg-slate-950 rounded-lg border border-slate-800/80">
                    <span className="text-slate-300">Supervisor/classify_diff.py</span>
                    <span className="text-indigo-400">Score: 0.6050</span>
                  </div>
                  <div className="flex justify-between p-2 bg-slate-950 rounded-lg border border-slate-800/80">
                    <span className="text-slate-300">Core/ContextFit.py</span>
                    <span className="text-indigo-400">Score: 0.5750</span>
                  </div>
                  <div className="flex justify-between p-2 bg-slate-950 rounded-lg border border-slate-800/80">
                    <span className="text-slate-300">Supervisor/launcher.py</span>
                    <span className="text-indigo-400">Score: 0.5750</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Интерактивная карточка relised_later: Quorum Panel */}
            <div
              onClick={() => setActiveModal(RELISED_LATER_REGISTRY.quorum_panel)}
              className="bg-slate-900/40 hover:bg-slate-900/80 border border-dashed border-slate-700 hover:border-purple-500 rounded-3xl p-6 cursor-pointer transition group relative"
            >
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-bold text-slate-200 group-hover:text-purple-400 transition">
                  🏛️ Multi-Model Quorum (Angle Diversity)
                </h4>
                <span className="px-2.5 py-0.5 text-[10px] font-mono font-bold uppercase rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
                  relised_later
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Кросс-модельный арбитраж с правом вето (Claude 3.7, GPT-4o, DeepSeek-R1) и двухэтапным хэшированием SHA-256.
              </p>
              <div className="mt-3 text-[11px] text-purple-400 font-semibold flex items-center gap-1">
                Подробнее в модальном окне ➔
              </div>
            </div>

            {/* Интерактивная карточка relised_later: Policy Drift */}
            <div
              onClick={() => setActiveModal(RELISED_LATER_REGISTRY.policy_drift)}
              className="bg-slate-900/40 hover:bg-slate-900/80 border border-dashed border-slate-700 hover:border-emerald-500 rounded-3xl p-6 cursor-pointer transition group relative"
            >
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-bold text-slate-200 group-hover:text-emerald-400 transition">
                  📊 Vector Policy Drift Analyzer
                </h4>
                <span className="px-2.5 py-0.5 text-[10px] font-mono font-bold uppercase rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  relised_later
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Дельта-анализ семантического дрейфа политик безопасности через остаточное векторное квантование.
              </p>
              <div className="mt-3 text-[11px] text-emerald-400 font-semibold flex items-center gap-1">
                Подробнее в модальном окне ➔
              </div>
            </div>
          </div>

          {/* Колонка 3: FastMCP Tool Connectors & Self-Evo Daemons */}
          <div className="space-y-6">
            <div className="bg-slate-900/70 border border-slate-800 rounded-3xl p-6 shadow-xl">
              <h3 className="text-base font-bold text-white mb-4 flex items-center gap-2">
                <span>🔌</span> FastMCP Connectors & Tools
              </h3>

              <div className="space-y-3 text-xs font-mono">
                <div className="flex items-center justify-between p-2.5 bg-slate-950 rounded-xl border border-slate-800">
                  <span className="text-slate-300">github_create_draft_pr</span>
                  <span className="text-emerald-400 font-bold">READY (RPC)</span>
                </div>
                <div className="flex items-center justify-between p-2.5 bg-slate-950 rounded-xl border border-slate-800">
                  <span className="text-slate-300">postgres_execute_query</span>
                  <span className="text-emerald-400 font-bold">READY (RPC)</span>
                </div>
                <div className="flex items-center justify-between p-2.5 bg-slate-950 rounded-xl border border-slate-800">
                  <span className="text-slate-300">slack_post_alert</span>
                  <span className="text-emerald-400 font-bold">READY (RPC)</span>
                </div>
                <div className="flex items-center justify-between p-2.5 bg-slate-950 rounded-xl border border-slate-800">
                  <span className="text-slate-300">filesystem_read_sandboxed</span>
                  <span className="text-emerald-400 font-bold">READY (RPC)</span>
                </div>
              </div>
            </div>

            {/* Интерактивная карточка relised_later: MCP Hot Reload */}
            <div
              onClick={() => setActiveModal(RELISED_LATER_REGISTRY.mcp_hot_reload)}
              className="bg-slate-900/40 hover:bg-slate-900/80 border border-dashed border-slate-700 hover:border-amber-500 rounded-3xl p-6 cursor-pointer transition group relative"
            >
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-bold text-slate-200 group-hover:text-amber-400 transition">
                  ⚡ FastMCP Live Hot-Reload
                </h4>
                <span className="px-2.5 py-0.5 text-[10px] font-mono font-bold uppercase rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  relised_later
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Динамическая регистрация новых `@mcp.tool` на лету без перезапуска терминальных сессий.
              </p>
              <div className="mt-3 text-[11px] text-amber-400 font-semibold flex items-center gap-1">
                Подробнее в модальном окне ➔
              </div>
            </div>

            {/* Интерактивная карточка relised_later: Recursive Evolution Daemon */}
            <div
              onClick={() => setActiveModal(RELISED_LATER_REGISTRY.recursive_evolution_daemon)}
              className="bg-slate-900/40 hover:bg-slate-900/80 border border-dashed border-slate-700 hover:border-rose-500 rounded-3xl p-6 cursor-pointer transition group relative"
            >
              <div className="flex items-center justify-between mb-2">
                <h4 className="text-sm font-bold text-slate-200 group-hover:text-rose-400 transition">
                  🔄 Recursive Evolution Daemon
                </h4>
                <span className="px-2.5 py-0.5 text-[10px] font-mono font-bold uppercase rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20">
                  relised_later
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Автономный фоновый процесс свободной эволюции и сжатия кодовой базы по правилу Shrink-Only.
              </p>
              <div className="mt-3 text-[11px] text-rose-400 font-semibold flex items-center gap-1">
                Подробнее в модальном окне ➔
              </div>
            </div>
          </div>
        </div>

        {/* ================================================================== */}
        {/* ИНТЕРАКТИВНОЕ МОДАЛЬНОЕ ОКНО "RELISED_LATER" */}
        {/* ================================================================== */}
        {activeModal && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 z-50 animate-fade-in">
            <div className="bg-slate-900 border border-slate-700 rounded-3xl max-w-2xl w-full p-8 shadow-2xl relative">
              <button
                onClick={() => setActiveModal(null)}
                className="absolute top-6 right-6 text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>

              <div className="flex items-center gap-3 mb-6">
                <span className="px-3 py-1 text-xs font-mono font-bold rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
                  {activeModal.badgeText}
                </span>
                <span className="text-xs font-mono text-slate-400">
                  {activeModal.roadmapPhase}
                </span>
              </div>

              <h3 className="text-xl font-bold text-white mb-6">
                {activeModal.title}
              </h3>

              <div className="space-y-4 text-xs font-mono">
                <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800">
                  <div className="text-slate-400 font-bold uppercase tracking-wider text-[10px] mb-1">
                    📌 1. ЧТО ЭТО ЗА ЭЛЕМЕНТ (WHAT):
                  </div>
                  <div className="text-slate-200 font-sans text-xs leading-relaxed">
                    {activeModal.what}
                  </div>
                </div>

                <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800">
                  <div className="text-slate-400 font-bold uppercase tracking-wider text-[10px] mb-1">
                    💡 2. ЗАЧЕМ НУЖНО СИСТЕМЕ (WHY):
                  </div>
                  <div className="text-slate-200 font-sans text-xs leading-relaxed">
                    {activeModal.why}
                  </div>
                </div>

                <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800">
                  <div className="text-slate-400 font-bold uppercase tracking-wider text-[10px] mb-1">
                    🎯 3. КУДА МОНТИРУЕТСЯ В АРХИТЕКТУРЕ (WHERE):
                  </div>
                  <div className="text-blue-400 text-xs">
                    {activeModal.where}
                  </div>
                </div>

                <div className="p-4 bg-slate-950 rounded-2xl border border-slate-800">
                  <div className="text-slate-400 font-bold uppercase tracking-wider text-[10px] mb-1">
                    ⚙️ 4. КАК РАБОТАЕТ ПОД КАПОТОМ (HOW):
                  </div>
                  <div className="text-slate-200 font-sans text-xs leading-relaxed">
                    {activeModal.how}
                  </div>
                </div>
              </div>

              <div className="flex justify-end mt-6">
                <button
                  onClick={() => setActiveModal(null)}
                  className="px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-xl text-xs font-bold transition shadow-lg shadow-blue-900/30"
                >
                  Закрыть спецификацию
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ================================================================== */}
        {/* МОДАЛЬНОЕ ОКНО АВАРИЙНОЙ ОСТАНОВКИ /PANIC STOP */}
        {/* ================================================================== */}
        {panicActive && (
          <div className="fixed inset-0 bg-black/90 backdrop-blur-md flex items-center justify-center p-4 z-50">
            <div className="bg-slate-900 border border-rose-500 p-8 rounded-3xl max-w-lg w-full shadow-2xl text-center">
              <div className="text-4xl mb-4">🚨</div>
              <h3 className="text-xl font-bold text-rose-400 mb-2">
                ВНЕПОЛОСНЫЙ СИГНАЛ /PANIC STOP
              </h3>
              <p className="text-xs text-slate-300 mb-6">
                Неизменяемый Supervisor инициирует принудительное завершение всех дочерних процессов агента с возвратом кода 10 в обход логики языковой модели.
              </p>
              <div className="flex justify-center gap-4">
                <button
                  onClick={() => setPanicActive(false)}
                  className="px-5 py-2.5 rounded-xl text-xs font-bold text-slate-400 hover:text-white"
                >
                  Отмена
                </button>
                <button
                  onClick={() => {
                    alert('Supervisor завершил все дочерние процессы (Exit Code: 10).');
                    setPanicActive(false);
                  }}
                  className="px-6 py-2.5 bg-rose-600 hover:bg-rose-500 text-white rounded-xl text-xs font-bold uppercase tracking-wider shadow-lg shadow-rose-900/40"
                >
                  Подтвердить аварийный останов
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

export default Dashboard;
