'use client';
import React, { useState, useEffect } from 'react';
import { History, ShieldCheck, Database, FileText } from 'lucide-react';
import { api } from '../../lib/api';

export function AuditView() {
  const [ledger, setLedger] = useState([]);
  const [auditEvents, setAuditEvents] = useState([]);
  const [activeSubTab, setActiveSubTab] = useState('ledger');

  useEffect(() => {
    api.getLedger({ limit: 50 }).then(res => setLedger(res)).catch(() => {});
    api.getAuditEvents({ limit: 50 }).then(res => setAuditEvents(res)).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Audit history</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Immutable log of all physical stock reservations, custody dispatches, receipts, and administrative approvals.
          </p>
        </div>

        {/* Sub-tab toggle */}
        <div className="flex bg-slate-100 p-1 rounded-lg border border-slate-200">
          <button
            onClick={() => setActiveSubTab('ledger')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition ${
              activeSubTab === 'ledger' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
            }`}
          >
            Inventory Ledger ({ledger.length})
          </button>
          <button
            onClick={() => setActiveSubTab('audit')}
            className={`px-3 py-1 text-xs font-semibold rounded-md transition ${
              activeSubTab === 'audit' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
            }`}
          >
            Governance Audit Log ({auditEvents.length})
          </button>
        </div>
      </div>

      {activeSubTab === 'ledger' ? (
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">Movement Type</th>
                  <th className="px-4 py-3 text-right">Quantity Delta</th>
                  <th className="px-4 py-3">Reference</th>
                  <th className="px-4 py-3">Operational Reason</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {ledger.map((entry) => {
                  const isPositive = entry.quantity_delta > 0;
                  return (
                    <tr key={entry.id} className="hover:bg-slate-50/70 transition">
                      <td className="px-4 py-3 font-mono text-[11px] text-slate-500">
                        {new Date(entry.occurred_at).toLocaleString()}
                      </td>
                      <td className="px-4 py-3">
                        <span className="bg-slate-100 text-slate-800 text-[10px] font-mono font-semibold px-2 py-0.5 rounded border border-slate-200">
                          {entry.movement_type}
                        </span>
                      </td>
                      <td className={`px-4 py-3 text-right font-mono font-bold ${
                        isPositive ? 'text-emerald-700' : 'text-red-600'
                      }`}>
                        {isPositive ? `+${entry.quantity_delta}` : entry.quantity_delta} {entry.unit}
                      </td>
                      <td className="px-4 py-3 text-[11px] text-slate-600 font-mono">
                        {entry.reference_type || 'SYSTEM'}
                      </td>
                      <td className="px-4 py-3 text-[11px] text-slate-600 max-w-md">
                        {entry.reason}
                      </td>
                    </tr>
                  );
                })}
                {ledger.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-400">
                      No ledger transactions recorded.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="px-4 py-3">Timestamp</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Entity Type</th>
                  <th className="px-4 py-3">Entity ID</th>
                  <th className="px-4 py-3">Audit Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 text-slate-700">
                {auditEvents.map((evt) => (
                  <tr key={evt.id} className="hover:bg-slate-50/70 transition">
                    <td className="px-4 py-3 font-mono text-[11px] text-slate-500">
                      {new Date(evt.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-semibold text-slate-800">
                      {evt.action}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {evt.entity_type}
                    </td>
                    <td className="px-4 py-3 font-mono text-[10px] text-slate-500">
                      {evt.entity_id?.substring(0, 8)}...
                    </td>
                    <td className="px-4 py-3 text-[11px] text-slate-600">
                      {evt.reason || JSON.stringify(evt.after_state)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
