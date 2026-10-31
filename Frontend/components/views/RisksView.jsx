'use client';
import React, { useState } from 'react';
import { AlertTriangle, Clock, Calendar, ShieldAlert, Info, X, CheckCircle, Database } from 'lucide-react';
import { RiskBadge } from '../Badges';

export function RisksView({ risks = [], facilities = [] }) {
  const [filterFacility, setFilterFacility] = useState('ALL');
  const [filterType, setFilterType] = useState('ALL');
  const [selectedRisk, setSelectedRisk] = useState(null);

  const filtered = risks.filter(r => {
    if (filterFacility !== 'ALL' && r.facility_id !== filterFacility) return false;
    if (filterType !== 'ALL' && r.risk_type !== filterType) return false;
    return true;
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Supply Risk & Expiry Monitor</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Deterministic detection of imminent stockouts, buffer violations, and near-expiry batch vulnerabilities.
          </p>
        </div>

        {/* Filters */}
        <div className="flex items-center space-x-2">
          <select
            className="text-xs bg-white border border-slate-200 rounded-md px-2.5 py-1.5 text-slate-700 font-medium"
            value={filterFacility}
            onChange={(e) => setFilterFacility(e.target.value)}
          >
            <option value="ALL">All Facilities</option>
            {facilities.map(f => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>

          <select
            className="text-xs bg-white border border-slate-200 rounded-md px-2.5 py-1.5 text-slate-700 font-medium"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="ALL">All Risk Types</option>
            <option value="STOCKOUT_RISK">Stockout Risks</option>
            <option value="EXPIRY_RISK">Expiry Risks</option>
            <option value="SURPLUS_AVAILABLE">Surplus Available</option>
          </select>
        </div>
      </div>

      {/* Risks Table */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
              <tr>
                <th className="px-4 py-3">Medicine & Presentation</th>
                <th className="px-4 py-3">Facility</th>
                <th className="px-4 py-3">Risk Assessment</th>
                <th className="px-4 py-3">Days Cover / Shelf Life</th>
                <th className="px-4 py-3">At-Risk Quantity</th>
                <th className="px-4 py-3">Deterministic Rationale</th>
                <th className="px-4 py-3 text-right">Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filtered.map((item, idx) => (
                <tr key={item.id || idx} className="hover:bg-slate-50/70 transition">
                  <td className="px-4 py-3 font-semibold text-slate-900">
                    {item.product_name}
                  </td>
                  <td className="px-4 py-3 text-slate-600">
                    {item.facility_name}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center space-x-1.5">
                      <span className="text-[10px] font-mono uppercase text-slate-500">
                        {item.risk_type.replace('_RISK', '')}
                      </span>
                      <RiskBadge level={item.risk_level} />
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {item.risk_type === 'STOCKOUT_RISK' ? (
                      <span className={`font-semibold ${item.days_of_cover <= 4 ? 'text-rose-600' : 'text-amber-600'}`}>
                        {item.days_of_cover} days
                      </span>
                    ) : item.risk_type === 'EXPIRY_RISK' ? (
                      <span className="font-semibold text-amber-700">
                        {item.explanation?.days_until_expiry} days to exp
                      </span>
                    ) : (
                      <span className="font-semibold text-emerald-600">
                        {item.days_of_cover} days cover
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-semibold text-slate-800">
                    {item.at_risk_quantity ?? '-'} units
                  </td>
                  <td className="px-4 py-3 text-[11px] text-slate-600 max-w-md">
                    {item.explanation?.summary}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setSelectedRisk(item)}
                      className="inline-flex items-center px-2 py-1 text-[11px] font-medium text-blue-700 bg-blue-50 border border-blue-200 rounded hover:bg-blue-100 transition"
                    >
                      Inspect Inputs
                    </button>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    No matching risk alerts found for the selected filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence & Driver Inputs Modal */}
      {selectedRisk && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-lg w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
              <div className="flex items-center space-x-2">
                <ShieldAlert className="w-5 h-5 text-indigo-600" />
                <h3 className="font-bold text-slate-900 text-sm">Deterministic Risk Evidence Breakdown</h3>
              </div>
              <button
                onClick={() => setSelectedRisk(null)}
                className="text-slate-400 hover:text-slate-600 rounded-lg p-1 hover:bg-slate-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs text-slate-700">
              {/* Header Info */}
              <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 space-y-1">
                <div className="flex justify-between items-center">
                  <span className="font-bold text-slate-900 text-sm">{selectedRisk.product_name}</span>
                  <RiskBadge level={selectedRisk.risk_level} />
                </div>
                <div className="text-slate-500 text-[11px]">
                  Facility: <strong className="text-slate-700">{selectedRisk.facility_name}</strong> &bull; Type: <strong className="text-slate-700">{selectedRisk.risk_type}</strong>
                </div>
              </div>

              {/* Driver Parameters */}
              <div>
                <h4 className="font-bold text-slate-900 uppercase tracking-wider text-[10px] mb-2 text-slate-500">
                  Mathematical Driving Inputs
                </h4>
                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  {selectedRisk.risk_type === 'STOCKOUT_RISK' ? (
                    <>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Usable Stock</span>
                        <strong className="text-slate-900 text-sm">{selectedRisk.explanation?.usable_stock ?? '-'} units</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Daily Demand</span>
                        <strong className="text-slate-900 text-sm">{selectedRisk.explanation?.daily_demand ?? '-'} units/day</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Days of Cover</span>
                        <strong className="text-rose-600 text-sm">{selectedRisk.days_of_cover ?? '-'} days</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Safety Stock Required</span>
                        <strong className="text-slate-900 text-sm">{selectedRisk.explanation?.safety_stock_required ?? '-'} units</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Replenishment Lead Time</span>
                        <strong className="text-slate-900">{selectedRisk.explanation?.lead_time_days ?? 4} days</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Confirmed Inbound</span>
                        <strong className="text-emerald-700">{selectedRisk.explanation?.confirmed_inbound ?? 0} units</strong>
                      </div>
                    </>
                  ) : selectedRisk.risk_type === 'EXPIRY_RISK' ? (
                    <>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Batch Lot Number</span>
                        <strong className="text-slate-900 font-mono">{selectedRisk.explanation?.lot_number ?? '-'}</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Expiry Date</span>
                        <strong className="text-slate-900">{selectedRisk.explanation?.expiry_date ?? '-'}</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Days Until Expiry</span>
                        <strong className="text-amber-700 text-sm">{selectedRisk.explanation?.days_until_expiry ?? '-'} days</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Projected Leftover</span>
                        <strong className="text-rose-600 text-sm">{selectedRisk.at_risk_quantity ?? '-'} units</strong>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Usable Stock</span>
                        <strong className="text-slate-900 text-sm">{selectedRisk.explanation?.usable_stock ?? '-'} units</strong>
                      </div>
                      <div className="p-2 bg-slate-50 rounded border border-slate-200">
                        <span className="text-slate-500 block">Transferable Surplus</span>
                        <strong className="text-emerald-700 text-sm">{selectedRisk.at_risk_quantity ?? '-'} units</strong>
                      </div>
                    </>
                  )}
                </div>
              </div>

              {/* Rationale & Formula Details */}
              <div className="bg-blue-50 border border-blue-200 p-3 rounded-lg space-y-1">
                <span className="font-semibold text-blue-900 block text-[11px]">Deterministic Formula & Logic:</span>
                <p className="text-blue-800 text-[11px] leading-relaxed">
                  {selectedRisk.explanation?.summary}
                </p>
                <div className="text-[10px] text-blue-600 pt-1 border-t border-blue-100 flex items-center space-x-1">
                  <Database className="w-3 h-3" />
                  <span>Calculated via deterministic domain engine. Score: {selectedRisk.score}/100.</span>
                </div>
              </div>
            </div>

            <div className="bg-slate-50 px-5 py-3 border-t border-slate-100 text-right">
              <button
                onClick={() => setSelectedRisk(null)}
                className="px-3 py-1.5 text-xs font-semibold text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-100 transition shadow-sm"
              >
                Close Breakdown
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
