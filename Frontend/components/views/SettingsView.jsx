'use client';
import React, { useState } from 'react';
import { 
  Settings, RefreshCw, Zap, ShieldCheck, Database, 
  Server, Cpu, CheckCircle2, AlertTriangle, Key, Terminal 
} from 'lucide-react';
import { api } from '../../lib/api';

export function SettingsView({ 
  activeFacility, 
  activeUser, 
  facilities = [], 
  users = [],
  onFacilityChange,
  onUserChange,
  onResetDemo,
  isResetting,
  onRefreshData
}) {
  const [stockShockLoading, setStockShockLoading] = useState(false);
  const [stockShockMessage, setStockShockMessage] = useState(null);

  const handleTriggerStockShock = async () => {
    setStockShockLoading(true);
    setStockShockMessage(null);
    try {
      const res = await api.simulateStockChange({
        product_code: 'MED-003',
        facility_key: 'apex',
        new_usable_quantity: 5
      });
      setStockShockMessage({
        type: 'success',
        text: res.message || 'Source stock reduced to 5 units. Pre-reservation inventory conflict is now primed.'
      });
      if (onRefreshData) onRefreshData();
    } catch (err) {
      setStockShockMessage({
        type: 'error',
        text: err.message || 'Failed to simulate stock shock.'
      });
    } finally {
      setStockShockLoading(false);
    }
  };

  return (
    <div className="max-w-4xl space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight">System Configuration & Demonstration Hub</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Inspect backend connectivity, external AI adapter state, and trigger deterministic demonstration scenarios.
        </p>
      </div>

      {/* Demo Controls Section */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 space-y-4">
        <div className="flex items-center space-x-2 border-b border-slate-100 pb-3">
          <Zap className="w-5 h-5 text-amber-500" />
          <div>
            <h2 className="text-sm font-bold text-slate-900">Deterministic Demo Scenarios</h2>
            <p className="text-[11px] text-slate-500">Trigger edge cases to demonstrate self-healing supply networks and safety locks.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Scenario 1: Stock Shock */}
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center space-x-1.5 font-bold text-xs text-slate-900">
                <AlertTriangle className="w-4 h-4 text-amber-600" />
                <span>Scenario B: Concurrency Stock Shock</span>
              </div>
              <p className="text-[11px] text-slate-600 mt-1 leading-relaxed">
                Simulates local consumption reducing source surplus from 100 to 5 units <em>after</em> proposal generation but <em>before</em> reservation.
                Proves that the transfer reservation engine locks rows, detects the conflict, rejects reservation safely, and triggers replanning.
              </p>
            </div>

            <button
              onClick={handleTriggerStockShock}
              disabled={stockShockLoading}
              className="inline-flex items-center justify-center space-x-2 bg-amber-600 hover:bg-amber-700 text-white font-semibold text-xs py-2 px-3 rounded-md transition shadow-sm disabled:opacity-50"
            >
              <Zap className={`w-3.5 h-3.5 ${stockShockLoading ? 'animate-spin' : ''}`} />
              <span>{stockShockLoading ? 'Simulating...' : 'Simulate Stock Shock on Apex'}</span>
            </button>
          </div>

          {/* Scenario 2: Baseline Reset */}
          <div className="p-4 bg-slate-50 rounded-lg border border-slate-200 flex flex-col justify-between space-y-3">
            <div>
              <div className="flex items-center space-x-1.5 font-bold text-xs text-slate-900">
                <RefreshCw className="w-4 h-4 text-emerald-600" />
                <span>Deterministic Demo Reset</span>
              </div>
              <p className="text-[11px] text-slate-600 mt-1 leading-relaxed">
                Resets the synthetic database to the canonical demo baseline: Apex surplus (Enoxaparin / Insulin), Highland deficit, and St. Jude cold-chain rejection.
              </p>
            </div>

            <button
              onClick={onResetDemo}
              disabled={isResetting}
              className="inline-flex items-center justify-center space-x-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs py-2 px-3 rounded-md transition shadow-sm disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isResetting ? 'animate-spin' : ''}`} />
              <span>{isResetting ? 'Resetting Baseline...' : 'Reset Demo to Clean State'}</span>
            </button>
          </div>
        </div>

        {stockShockMessage && (
          <div className={`p-3 rounded-lg text-xs font-medium border flex items-center justify-between ${
            stockShockMessage.type === 'success' 
              ? 'bg-amber-50 text-amber-900 border-amber-200' 
              : 'bg-rose-50 text-rose-900 border-rose-200'
          }`}>
            <span>{stockShockMessage.text}</span>
            <button onClick={() => setStockShockMessage(null)} className="text-xs opacity-60 hover:opacity-100">✕</button>
          </div>
        )}
      </div>

      {/* Role & Facility Persona Switcher */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 space-y-4">
        <div className="flex items-center space-x-2 border-b border-slate-100 pb-3">
          <Terminal className="w-5 h-5 text-indigo-600" />
          <div>
            <h2 className="text-sm font-bold text-slate-900">Role & Facility Persona Emulation</h2>
            <p className="text-[11px] text-slate-500">Test multi-tenant permissions, source/destination approval rights, and scan boundary enforcement.</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700">Active Operational Facility</label>
            <select
              value={activeFacility?.id || ''}
              onChange={(e) => {
                const fac = facilities.find(f => f.id === e.target.value);
                if (fac && onFacilityChange) onFacilityChange(fac);
              }}
              className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-slate-800 font-medium"
            >
              {facilities.map(f => (
                <option key={f.id} value={f.id}>{f.name} ({f.facility_type})</option>
              ))}
            </select>
            <p className="text-[10px] text-slate-400">Scans and approvals executed from this facility context.</p>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-slate-700">Authenticated User Persona</label>
            <select
              value={activeUser?.id || ''}
              onChange={(e) => {
                const usr = users.find(u => u.id === e.target.value);
                if (usr && onUserChange) onUserChange(usr);
              }}
              className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg p-2.5 text-slate-800 font-medium"
            >
              {users.map(u => (
                <option key={u.id} value={u.id}>{u.name} — {u.role}</option>
              ))}
            </select>
            <p className="text-[10px] text-slate-400">Governance requires authorized PHARMACIST or MEDICAL_SUPERINTENDENT role.</p>
          </div>
        </div>
      </div>

      {/* Backend & Integration Stack Status */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 space-y-4">
        <div className="flex items-center space-x-2 border-b border-slate-100 pb-3">
          <Server className="w-5 h-5 text-slate-700" />
          <h2 className="text-sm font-bold text-slate-900">Infrastructure & AI Adapter State</h2>
        </div>

        <div className="divide-y divide-slate-100 text-xs">
          <div className="py-2.5 flex items-center justify-between">
            <div>
              <span className="font-semibold text-slate-800">Operational Database</span>
              <p className="text-[10px] text-slate-500">YugabyteDB YSQL operational source of truth with PostgreSQL compatibility</p>
            </div>
            <span className="inline-flex items-center space-x-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-medium text-[11px]">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Connected / Healthy</span>
            </span>
          </div>

          <div className="py-2.5 flex items-center justify-between">
            <div>
              <span className="font-semibold text-slate-800">Agent Orchestration</span>
              <p className="text-[10px] text-slate-500">LangGraph stateful workflow with human-in-the-loop checkpoint</p>
            </div>
            <span className="inline-flex items-center space-x-1 text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 font-medium text-[11px]">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Stateful Graph Active</span>
            </span>
          </div>

          <div className="py-2.5 flex items-center justify-between">
            <div>
              <span className="font-semibold text-slate-800">Gemini LLM Reasoning</span>
              <p className="text-[10px] text-slate-500">Structured transfer explanation & risk synthesis</p>
            </div>
            <span className="inline-flex items-center space-x-1 text-blue-700 bg-blue-50 px-2 py-0.5 rounded border border-blue-200 font-medium text-[11px]">
              <Cpu className="w-3.5 h-3.5" />
              <span>Adapter Ready (Live / Deterministic Fallback)</span>
            </span>
          </div>

          <div className="py-2.5 flex items-center justify-between">
            <div>
              <span className="font-semibold text-slate-800">MEKO Agent Memory</span>
              <p className="text-[10px] text-slate-500">Shared contextual memory summaries and decision trace cache</p>
            </div>
            <span className="inline-flex items-center space-x-1 text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200 font-medium text-[11px]">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Adapter Ready (Graceful Fallback)</span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
