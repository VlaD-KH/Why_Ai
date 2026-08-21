import React, { useState, useEffect } from 'react';

/**
 * Интерфейс метрик телеметрии и безопасности системы Self-Evo.
 */
export interface TelemetryMetrics {
  currentPhase: 'DEFINE' | 'PLAN' | 'BUILD' | 'VERIFY' | 'REVIEW' | 'SHIP';
  mode: 'PROJECT_MODE' | 'AGENT_SELF_EVO_MODE';
  contextTokenUsage: number;
  contextTokenLimit: number;
  lastDiffRisk: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  ledgerChainValid: boolean;
  activeAgentsCount: number;
  recentFailuresCount: number;
  lastCommitHash?: string;
}

interface TelemetryDockProps {
  initialMetrics?: Partial<TelemetryMetrics>;
  onTriggerPanic?: (reason: string) => void;
}

/**
 * React-компонент TelemetryDock: Дашборд телеметрии, гейтов безопасности и состояния рантайма.
 */
export const TelemetryDock: React.FC<TelemetryDockProps> = ({
  initialMetrics,
  onTriggerPanic,
}) => {
  const [metrics, setMetrics] = useState<TelemetryMetrics>({
    currentPhase: 'DEFINE',
    mode: 'PROJECT_MODE',
    contextTokenUsage: 34200,
    contextTokenLimit: 128000,
    lastDiffRisk: 'LOW',
    ledgerChainValid: true,
    activeAgentsCount: 2,
    recentFailuresCount: 0,
    lastCommitHash: 'b3994cd',
    ...initialMetrics,
  });

  const [panicModalOpen, setPanicModalOpen] = useState(false);
  const [panicReason, setPanicReason] = useState('');

  const getRiskColor = (risk: string) => {
    switch (risk) {
      case 'LOW':
        return 'text-emerald-400 bg-emerald-950/40 border-emerald-500/30';
      case 'MEDIUM':
        return 'text-amber-400 bg-amber-950/40 border-amber-500/30';
      case 'HIGH':
        return 'text-orange-400 bg-orange-950/40 border-orange-500/30';
      case 'CRITICAL':
        return 'text-rose-400 bg-rose-950/40 border-rose-500/30';
      default:
        return 'text-slate-400 bg-slate-900 border-slate-700';
    }
  };

  const phases: Array<TelemetryMetrics['currentPhase']> = [
    'DEFINE',
    'PLAN',
    'BUILD',
    'VERIFY',
    'REVIEW',
    'SHIP',
  ];

  const handleExecutePanic = () => {
    if (onTriggerPanic) {
      onTriggerPanic(panicReason || 'UI Operator Emergency Signal');
    }
    setPanicModalOpen(false);
  };

  const usagePercent = Math.min(
    100,
    Math.round((metrics.contextTokenUsage / metrics.contextTokenLimit) * 100)
  );

  return (
    <div className="w-full max-w-5xl mx-auto p-6 bg-slate-950 text-slate-100 rounded-2xl border border-slate-800 shadow-2xl font-sans">
      {/* Верхняя панель заголовка */}
      <div className="flex items-center justify-between pb-6 border-b border-slate-800">
        <div>
          <div className="flex items-center gap-3">
            <span className="h-3 w-3 rounded-full bg-emerald-500 animate-pulse" />
            <h1 className="text-xl font-bold tracking-tight text-white">
              Self-Evo Telemetry Dock
            </h1>
            <span className="px-2.5 py-0.5 text-xs font-mono font-medium rounded-full bg-slate-800 text-slate-300 border border-slate-700">
              {metrics.mode}
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Deterministic Control Plane & Ouroboros Runtime Monitor
          </p>
        </div>

        {/* Кнопка экстренной остановки */}
        <button
          onClick={() => setPanicModalOpen(true)}
          className="px-4 py-2 bg-rose-600/90 hover:bg-rose-500 text-white text-xs font-bold uppercase tracking-wider rounded-lg transition shadow-lg shadow-rose-900/30 border border-rose-400/30 flex items-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          /PANIC STOP
        </button>
      </div>

      {/* Фазы SDLC цикла */}
      <div className="py-6 border-b border-slate-800">
        <div className="text-xs font-medium uppercase tracking-wider text-slate-400 mb-3">
          SDLC Pipeline Phase
        </div>
        <div className="grid grid-cols-6 gap-2">
          {phases.map((phase) => {
            const isActive = metrics.currentPhase === phase;
            return (
              <div
                key={phase}
                className={`py-2 px-3 text-center rounded-lg border text-xs font-mono font-semibold transition ${
                  isActive
                    ? 'bg-blue-600/20 border-blue-500 text-blue-300 shadow-md shadow-blue-900/20 ring-1 ring-blue-400/30'
                    : 'bg-slate-900/50 border-slate-800 text-slate-500'
                }`}
              >
                /{phase.toLowerCase()}
              </div>
            );
          })}
        </div>
      </div>

      {/* Ключевые метрики безопасности и памяти */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-6">
        {/* Контроль риска последнего диффа */}
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800">
          <div className="text-xs text-slate-400 font-medium mb-1">
            Last Git Diff Risk (MAX Rule)
          </div>
          <div className="flex items-center justify-between mt-2">
            <span
              className={`px-3 py-1 text-xs font-mono font-bold rounded-md border ${getRiskColor(
                metrics.lastDiffRisk
              )}`}
            >
              {metrics.lastDiffRisk}
            </span>
            <span className="text-xs text-slate-400 font-mono">
              Gate: {metrics.lastDiffRisk === 'LOW' || metrics.lastDiffRisk === 'MEDIUM' ? 'AUTO' : 'REQUIRE_HUMAN'}
            </span>
          </div>
        </div>

        {/* Управление контекстом ContextFit */}
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium mb-1">
            <span>ContextFit Memory</span>
            <span className="font-mono">{usagePercent}%</span>
          </div>
          <div className="w-full bg-slate-800 rounded-full h-2 mt-3 overflow-hidden">
            <div
              className={`h-2 rounded-full transition-all duration-500 ${
                usagePercent > 80 ? 'bg-rose-500' : usagePercent > 50 ? 'bg-amber-500' : 'bg-blue-500'
              }`}
              style={{ width: `${usagePercent}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] text-slate-500 font-mono mt-2">
            <span>{metrics.contextTokenUsage.toLocaleString()} tokens</span>
            <span>Limit: {metrics.contextTokenLimit.toLocaleString()}</span>
          </div>
        </div>

        {/* Целостность журнала Ledger */}
        <div className="p-4 rounded-xl bg-slate-900/40 border border-slate-800">
          <div className="text-xs text-slate-400 font-medium mb-1">
            Audit Ledger Integrity
          </div>
          <div className="flex items-center gap-2 mt-2">
            {metrics.ledgerChainValid ? (
              <>
                <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-xs font-mono font-medium text-emerald-300">
                  SHA-256 Hash Chain Valid
                </span>
              </>
            ) : (
              <>
                <svg className="w-5 h-5 text-rose-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span className="text-xs font-mono font-bold text-rose-400">
                  CHAIN CORRUPTED (HALT)
                </span>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Модальное окно подтверждения аварийной остановки */}
      {panicModalOpen && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-slate-900 border border-rose-500/40 p-6 rounded-2xl max-w-md w-full shadow-2xl">
            <h3 className="text-lg font-bold text-rose-400 flex items-center gap-2">
              ⚠️ Trigger Out-of-Band /PANIC STOP
            </h3>
            <p className="text-xs text-slate-300 mt-2">
              Данное действие выполнит принудительное завершение всех дочерних процессов
              агента через неизменяемый Supervisor в обход логики языковой модели.
            </p>
            <div className="mt-4">
              <label className="text-xs text-slate-400 font-medium block mb-1">
                Причина остановки:
              </label>
              <input
                type="text"
                value={panicReason}
                onChange={(e) => setPanicReason(e.target.value)}
                placeholder="Например: violation of BIBLE.md invariant #3"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-rose-500"
              />
            </div>
            <div className="flex justify-end gap-3 mt-6">
              <button
                onClick={() => setPanicModalOpen(false)}
                className="px-4 py-2 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
              >
                Отмена
              </button>
              <button
                onClick={handleExecutePanic}
                className="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white rounded-lg text-xs font-bold uppercase tracking-wider shadow-lg shadow-rose-900/40"
              >
                Подтвердить останов
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TelemetryDock;
