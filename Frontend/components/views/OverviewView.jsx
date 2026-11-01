'use client';
import React from 'react';
import {
  AlertTriangle,
  ArrowLeftRight,
  Bot,
  Building2,
  CheckCircle2,
  Database,
  Package,
  TrendingDown,
} from 'lucide-react';
import { RiskBadge } from '../Badges';

export function OverviewView({
  overview,
  risks = [],
  opportunities = [],
  proposals = [],
  mekoContext = [],
  mekoStatus,
  isMekoLoading = false,
  mekoError = '',
  dataErrors = [],
  contextError = '',
  onRetry,
  onRunAgentCycle,
  isAgentRunning,
  agentResult,
  onNavigateTab,
}) {
  const stockoutRisks = risks.filter((risk) => risk.risk_type === 'STOCKOUT_RISK');
  const expiryRisks = risks.filter((risk) => risk.risk_type === 'EXPIRY_RISK');
  const pendingApprovals = proposals.filter((proposal) =>
    proposal.status?.includes('PENDING') || proposal.status === 'PROPOSED'
  );

  const summaryCards = [
    {
      label: 'Facilities',
      value: overview?.total_facilities,
      note: 'In your network',
      icon: Building2,
      tone: 'slate',
    },
    {
      label: 'Medicines',
      value: overview?.monitored_products,
      note: 'Being monitored',
      icon: Package,
      tone: 'slate',
    },
    {
      label: 'Low stock alerts',
      value: overview?.active_stockout_risks,
      note: 'Need attention',
      icon: AlertTriangle,
      tone: 'amber',
    },
    {
      label: 'Expiry alerts',
      value: overview?.active_expiry_risks,
      note: 'Batches at risk',
      icon: TrendingDown,
      tone: 'amber',
    },
    {
      label: 'Available to share',
      value: overview?.transferable_surplus_units,
      note: 'Medicine units',
      icon: ArrowLeftRight,
      tone: 'green',
    },
    {
      label: 'Completed transfers',
      value: overview?.completed_redistributions,
      note: 'Received and recorded',
      icon: CheckCircle2,
      tone: 'green',
    },
  ];

  const cardTones = {
    slate: 'bg-slate-100 text-slate-600',
    amber: 'bg-amber-50 text-amber-700',
    green: 'bg-emerald-50 text-emerald-700',
  };

  return (
    <div className="space-y-7">
      {(dataErrors.length > 0 || contextError || mekoError) && (
        <section
          role="alert"
          className="flex flex-col gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="text-sm text-amber-950">
            <p className="font-semibold">Some dashboard data could not be loaded.</p>
            <p className="mt-1 text-xs leading-5">
              {[...dataErrors, contextError, mekoError].filter(Boolean).join(' · ')}
            </p>
          </div>
          <button
            type="button"
            onClick={onRetry}
            className="shrink-0 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-medium text-amber-900 hover:bg-amber-100"
          >
            Retry
          </button>
        </section>
      )}

      {overview && overview.total_facilities === 0 && overview.monitored_products === 0 && (
        <section className="rounded-xl border border-sky-200 bg-sky-50 p-4">
          <p className="text-sm font-semibold text-sky-950">No operational records yet</p>
          <p className="mt-1 text-xs leading-5 text-sky-900">
            These values reflect the connected database. Import facility and inventory data,
            or use the local demo reset to load the synthetic scenario; no live values are fabricated.
          </p>
        </section>
      )}

      <section className="flex flex-col gap-4 border-b border-slate-200 pb-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-800">
            Network overview
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
            Medicine supply at a glance
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
            See what needs attention, find safe ways to share stock, and follow each transfer.
          </p>
        </div>
        <button
          type="button"
          onClick={onRunAgentCycle}
          disabled={isAgentRunning}
          className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-medium text-white hover:bg-emerald-900 disabled:cursor-wait disabled:opacity-60"
        >
          <Bot className="h-4 w-4" />
          {isAgentRunning ? 'Checking supplies…' : 'Run supply check'}
        </button>
      </section>

      <section aria-label="Network summary">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Today at a glance</h2>
            <p className="mt-0.5 text-xs text-slate-500">A simple summary of your network</p>
          </div>
          {pendingApprovals.length > 0 && (
            <button
              type="button"
              onClick={() => onNavigateTab('approvals')}
              className="rounded-lg border border-emerald-200 bg-white px-3 py-2 text-xs font-medium text-emerald-800 hover:bg-emerald-50"
            >
              {pendingApprovals.length} approvals to review
            </button>
          )}
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {summaryCards.map((card) => {
            const Icon = card.icon;
            return (
              <article
                key={card.label}
                className="flex min-h-[112px] items-center gap-4 rounded-xl border border-slate-200 bg-white p-4"
              >
                <span className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${cardTones[card.tone]}`}>
                  <Icon className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-600">{card.label}</p>
                  <div className="mt-1 flex items-baseline gap-2">
                    <span className="text-2xl font-semibold tabular-nums tracking-tight text-slate-950">
                      {typeof card.value === 'number' ? card.value.toLocaleString() : '—'}
                    </span>
                    <span className="truncate text-xs text-slate-500">{card.note}</span>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-700">
              <Database className="h-4 w-4" />
            </span>
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Shared operational context</h2>
              <p className="mt-1 text-xs text-slate-500">
                Meko memory supports coordination; inventory numbers always come from the operational database.
              </p>
            </div>
          </div>
          <span className="w-fit rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-600">
            {mekoStatus?.mode === 'LIVE_MEKO'
              ? 'Meko connected'
              : mekoStatus?.connection === 'ERROR'
                ? 'Meko unavailable · local fallback'
                : mekoStatus?.configured
                  ? 'Meko configured · verifying'
                  : 'Local memory fallback'}
          </span>
        </div>
        {mekoStatus?.connection_error && (
          <p role="status" className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-950">
            {mekoStatus.connection_error}
          </p>
        )}
        {mekoStatus && !mekoStatus.configured && (
          <p className="mt-3 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs leading-5 text-sky-950">
            To enable Meko: create a datapack and generate a full API key in Meko Settings → API Keys.
            Set <code>MEKO_API_KEY</code> and <code>MEKO_DATAPACK_ID</code> in the repository-root
            <code> .env</code>, then restart the backend.
          </p>
        )}
        {mekoContext.length > 0 ? (
          <div className="mt-4 space-y-3">
            {mekoContext.slice(0, 3).map((context, index) => (
              <article
                key={context.ref_id || `context-${index}`}
                className="rounded-lg border border-slate-100 bg-slate-50 p-3"
              >
                <p className="text-sm leading-6 text-slate-700">{context.summary}</p>
                <p className="mt-2 text-[11px] font-medium text-slate-500">
                  {context.provenance === 'LIVE_MEKO'
                    ? 'Meko shared memory'
                    : context.summary?.startsWith('Synthetic operational baseline')
                      ? 'Local synthetic baseline'
                      : 'Local memory fallback'}
                </p>
              </article>
            ))}
          </div>
        ) : isMekoLoading ? (
          <p className="mt-4 rounded-lg bg-slate-50 px-3 py-4 text-sm text-slate-600">
            Retrieving shared context…
          </p>
        ) : (
          <p className="mt-4 rounded-lg bg-slate-50 px-3 py-4 text-sm text-slate-600">
            No shared context has been saved yet. Run a supply check to add a decision trace.
          </p>
        )}
      </section>

      {agentResult && (
        <section className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex gap-3">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-50 text-emerald-800">
                <Bot className="h-4 w-4" />
              </span>
              <div>
                <h2 className="text-sm font-semibold text-slate-900">Supply check results</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Status: {agentResult.workflow_status} · Source: {agentResult.agent_reasoning?.source || 'System'}
                </p>
              </div>
            </div>
            {agentResult.pause_for_human_approval && (
              <button
                type="button"
                onClick={() => onNavigateTab('approvals')}
                className="text-left text-sm font-medium text-emerald-800 hover:text-emerald-950 sm:text-right"
              >
                Review approvals
              </button>
            )}
          </div>
          {agentResult.agent_reasoning?.analysis && (
            <p className="mt-4 border-t border-slate-100 pt-4 text-sm leading-6 text-slate-700">
              {agentResult.agent_reasoning.analysis}
            </p>
          )}
        </section>
      )}

      <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <article className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Low stock alerts</h2>
              <p className="mt-1 text-xs text-slate-500">Facilities that may run short soon</p>
            </div>
            <button
              type="button"
              onClick={() => onNavigateTab('risks')}
              className="shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-50"
            >
              View all ({stockoutRisks.length})
            </button>
          </div>
          <div className="divide-y divide-slate-100">
            {stockoutRisks.slice(0, 4).map((risk, index) => (
              <div key={risk.id || `${risk.product_id}-${risk.facility_id}-${index}`} className="flex items-start justify-between gap-4 px-5 py-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-900">{risk.product_name}</p>
                    <RiskBadge level={risk.risk_level} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{risk.facility_name}</p>
                  {risk.explanation?.summary && (
                    <p className="mt-2 text-xs leading-5 text-slate-600">{risk.explanation.summary}</p>
                  )}
                </div>
                <p className="shrink-0 text-right text-sm font-semibold tabular-nums text-amber-800">
                  {risk.days_of_cover} <span className="text-xs font-normal text-slate-500">days left</span>
                </p>
              </div>
            ))}
            {stockoutRisks.length === 0 && (
              <p className="px-5 py-8 text-center text-sm text-slate-500">No low stock alerts right now.</p>
            )}
          </div>
        </article>

        <article className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Safe stock matches</h2>
              <p className="mt-1 text-xs text-slate-500">Surplus that could help another facility</p>
            </div>
            <button
              type="button"
              onClick={() => onNavigateTab('opportunities')}
              className="shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-medium text-emerald-800 hover:bg-emerald-50"
            >
              View all ({opportunities.length})
            </button>
          </div>
          <div className="divide-y divide-slate-100">
            {opportunities.slice(0, 4).map((opportunity, index) => (
              <div key={`${opportunity.product_id}-${opportunity.source_facility_id}-${opportunity.destination_facility_id}-${index}`} className="flex items-start justify-between gap-4 px-5 py-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-slate-900">{opportunity.product_name}</p>
                    <span className="rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800">
                      {opportunity.matched_quantity} {opportunity.unit}
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-600">
                    {opportunity.source_facility_name} <span className="px-1 text-slate-400">to</span> {opportunity.destination_facility_name}
                  </p>
                  {opportunity.destination_rationale?.summary && (
                    <p className="mt-1 text-xs leading-5 text-slate-500">{opportunity.destination_rationale.summary}</p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => onNavigateTab('opportunities')}
                  className="shrink-0 rounded-lg border border-slate-200 px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50"
                >
                  Create request
                </button>
              </div>
            ))}
            {opportunities.length === 0 && (
              <p className="px-5 py-8 text-center text-sm text-slate-500">No safe stock matches right now.</p>
            )}
          </div>
        </article>
      </section>
    </div>
  );
}
