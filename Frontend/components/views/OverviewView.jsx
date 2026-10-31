'use client';
import React, { useState } from 'react';
import { 
  AlertTriangle, 
  Package, 
  TrendingDown, 
  ArrowLeftRight, 
  Bot, 
  Sparkles, 
  CheckCircle, 
  ShieldCheck,
  RefreshCw
} from 'lucide-react';
import { RiskBadge, StatusBadge } from '../Badges';

export function OverviewView({ 
  overview, 
  risks = [], 
  opportunities = [], 
  proposals = [], 
  onRunAgentCycle,
  isAgentRunning,
  agentResult,
  onNavigateTab
}) {
  const stockoutRisks = risks.filter(r => r.risk_type === 'STOCKOUT_RISK');
  const expiryRisks = risks.filter(r => r.risk_type === 'EXPIRY_RISK');

  return (
    <div className="space-y-6">
      {/* Page Title */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Network Command Center</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Real-time multi-facility inventory monitoring, automated surplus matching, and verified custody tracking.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={onRunAgentCycle}
            disabled={isAgentRunning}
            className="inline-flex items-center space-x-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3.5 py-2 rounded-md shadow-sm transition disabled:opacity-50"
          >
            <Bot className={`w-4 h-4 ${isAgentRunning ? 'animate-spin' : ''}`} />
            <span>{isAgentRunning ? 'Orchestrating Agents...' : 'Run Agentic Intelligence Cycle'}</span>
          </button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-sm">
          <div className="text-[11px] font-medium text-slate-500">Participating Facilities</div>
          <div className="text-2xl font-bold text-slate-900 mt-1">{overview?.total_facilities ?? 4}</div>
          <div className="text-[10px] text-slate-400 mt-1">Hospitals & Pharmacies</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-sm">
          <div className="text-[11px] font-medium text-slate-500">Monitored Medicines</div>
          <div className="text-2xl font-bold text-slate-900 mt-1">{overview?.monitored_products ?? 16}</div>
          <div className="text-[10px] text-slate-400 mt-1">Multi-batch catalog</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-red-200 bg-red-50/20 shadow-sm">
          <div className="text-[11px] font-medium text-red-700">Stockout Risk Facilities</div>
          <div className="text-2xl font-bold text-red-600 mt-1">{overview?.active_stockout_risks ?? stockoutRisks.length}</div>
          <div className="text-[10px] text-red-500 mt-1">Critical threshold breaches</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-amber-200 bg-amber-50/20 shadow-sm">
          <div className="text-[11px] font-medium text-amber-800">At-Risk Expiry Batches</div>
          <div className="text-2xl font-bold text-amber-700 mt-1">{overview?.active_expiry_risks ?? expiryRisks.length}</div>
          <div className="text-[10px] text-amber-600 mt-1">Unconsumed before expiry</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-blue-200 bg-blue-50/20 shadow-sm">
          <div className="text-[11px] font-medium text-blue-700">Transferable Surplus</div>
          <div className="text-2xl font-bold text-blue-700 mt-1">{overview?.transferable_surplus_units ?? 350}</div>
          <div className="text-[10px] text-blue-500 mt-1">Units exceeding 37d buffer</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-emerald-200 bg-emerald-50/20 shadow-sm">
          <div className="text-[11px] font-medium text-emerald-800">Verified Transfers</div>
          <div className="text-2xl font-bold text-emerald-700 mt-1">{overview?.completed_redistributions ?? 0}</div>
          <div className="text-[10px] text-emerald-600 mt-1">Ledger confirmed receipts</div>
        </div>
      </div>

      {/* Multi-Agent Orchestration / Gemini Explanation Banner */}
      {agentResult && (
        <div className="bg-white rounded-lg border border-indigo-200 shadow-sm p-4 space-y-3">
          <div className="flex items-center justify-between border-b border-indigo-100 pb-2.5">
            <div className="flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-indigo-600" />
              <h2 className="text-xs font-bold text-indigo-950 uppercase tracking-wide">
                LangGraph Multi-Agent Orchestration & Gemini Synthesis
              </h2>
            </div>
            <div className="flex items-center space-x-2 text-[10px]">
              <span className="bg-indigo-50 text-indigo-700 font-semibold px-2 py-0.5 rounded border border-indigo-200">
                Workflow: {agentResult.workflow_status}
              </span>
              <span className="bg-slate-100 text-slate-700 font-medium px-2 py-0.5 rounded border border-slate-200">
                Source: {agentResult.agent_reasoning?.source || 'GEMINI'}
              </span>
            </div>
          </div>

          <div className="bg-indigo-50/40 p-3 rounded-md text-xs text-indigo-900 leading-relaxed font-sans">
            {agentResult.agent_reasoning?.analysis}
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-500 pt-1">
            <span>Agents involved: Inventory Monitoring, Demand Forecasting, Expiry & Risk, Supply Optimisation.</span>
            {agentResult.pause_for_human_approval && (
              <button 
                onClick={() => onNavigateTab('approvals')}
                className="text-xs font-semibold text-emerald-700 hover:text-emerald-800 underline"
              >
                Inspect pending approvals →
              </button>
            )}
          </div>
        </div>
      )}

      {/* Critical Risk Queues & Matched Opportunities Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Urgent Shortage Queue */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div className="flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 text-red-500" />
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wide">Active Shortage Alerts</h2>
            </div>
            <button 
              onClick={() => onNavigateTab('risks')}
              className="text-[11px] font-medium text-emerald-700 hover:text-emerald-800"
            >
              View all ({stockoutRisks.length})
            </button>
          </div>

          <div className="divide-y divide-slate-100">
            {stockoutRisks.slice(0, 4).map((risk, idx) => (
              <div key={idx} className="p-3.5 hover:bg-slate-50/60 transition flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-semibold text-slate-900">{risk.product_name}</span>
                    <RiskBadge level={risk.risk_level} />
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">{risk.facility_name}</p>
                  <p className="text-[11px] text-slate-600 mt-1">{risk.explanation?.summary}</p>
                </div>
                <div className="text-right shrink-0 ml-4">
                  <div className="text-xs font-bold text-red-600">{risk.days_of_cover} days</div>
                  <div className="text-[10px] text-slate-400">cover remaining</div>
                </div>
              </div>
            ))}
            {stockoutRisks.length === 0 && (
              <div className="p-6 text-center text-xs text-slate-500">No active stockout threshold breaches.</div>
            )}
          </div>
        </div>

        {/* Immediate Redistribution Matches */}
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
            <div className="flex items-center space-x-2">
              <ArrowLeftRight className="w-4 h-4 text-emerald-600" />
              <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wide">Safe Surplus Matches</h2>
            </div>
            <button 
              onClick={() => onNavigateTab('opportunities')}
              className="text-[11px] font-medium text-emerald-700 hover:text-emerald-800"
            >
              View all ({opportunities.length})
            </button>
          </div>

          <div className="divide-y divide-slate-100">
            {opportunities.slice(0, 4).map((opp, idx) => (
              <div key={idx} className="p-3.5 hover:bg-slate-50/60 transition flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-semibold text-slate-900">{opp.product_name}</span>
                    <span className="text-[10px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded font-medium border border-blue-200">
                      {opp.matched_quantity} {opp.unit}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-600 mt-1 flex items-center space-x-1">
                    <span className="font-medium text-slate-700">{opp.source_facility_name}</span>
                    <span>→</span>
                    <span className="font-medium text-slate-700">{opp.destination_facility_name}</span>
                  </div>
                  <p className="text-[10px] text-slate-500 mt-0.5">{opp.destination_rationale?.summary}</p>
                </div>
                <button
                  onClick={() => onNavigateTab('opportunities')}
                  className="text-xs font-medium bg-emerald-50 text-emerald-700 hover:bg-emerald-100 px-2.5 py-1 rounded border border-emerald-200 transition shrink-0 ml-4"
                >
                  Propose
                </button>
              </div>
            ))}
            {opportunities.length === 0 && (
              <div className="p-6 text-center text-xs text-slate-500">No surplus-to-need pairings currently active.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

