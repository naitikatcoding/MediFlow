'use client';
import React, { useState } from 'react';
import { AlertTriangle, Clock, Calendar, ShieldAlert } from 'lucide-react';
import { RiskBadge } from '../Badges';

export function RisksView({ risks = [], facilities = [] }) {
  const [filterFacility, setFilterFacility] = useState('ALL');
  const [filterType, setFilterType] = useState('ALL');

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
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filtered.map((item, idx) => (
                <tr key={idx} className="hover:bg-slate-50/70 transition">
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
                      <span className="font-semibold text-red-600">
                        {item.days_of_cover} days
                      </span>
                    ) : (
                      <span className="font-semibold text-amber-700">
                        {item.explanation?.days_until_expiry} days to exp
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-semibold text-slate-800">
                    {item.at_risk_quantity ?? '-'} units
                  </td>
                  <td className="px-4 py-3 text-[11px] text-slate-600 max-w-md">
                    {item.explanation?.summary}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                    No matching risk alerts found for the selected filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

