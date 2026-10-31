'use client';
import React, { useState } from 'react';
import { Package, Search, Filter, Snowflake, AlertCircle } from 'lucide-react';
import { StatusBadge } from '../Badges';

export function InventoryView({ inventory = [], facilities = [] }) {
  const [filterFacility, setFilterFacility] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  const filtered = inventory.filter(item => {
    if (filterFacility !== 'ALL' && item.facility_id !== filterFacility) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return (
        item.product_name.toLowerCase().includes(q) ||
        item.generic_name.toLowerCase().includes(q) ||
        item.manufacturer_lot_number.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Facility-Batch Inventory</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Materialized operational balances and FEFO lot allocations across network facilities.
          </p>
        </div>

        {/* Filter and Search Bar */}
        <div className="flex items-center space-x-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
            <input
              type="text"
              placeholder="Search medicine or batch..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-8 pr-3 py-1.5 text-xs bg-white border border-slate-200 rounded-md text-slate-800 placeholder-slate-400 focus:outline-none focus:border-emerald-500"
            />
          </div>

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
        </div>
      </div>

      {/* Inventory Table */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
              <tr>
                <th className="px-4 py-3">Medicine</th>
                <th className="px-4 py-3">Facility</th>
                <th className="px-4 py-3">Batch / Lot</th>
                <th className="px-4 py-3">Expiry Date (FEFO)</th>
                <th className="px-4 py-3">Storage</th>
                <th className="px-4 py-3 text-right">On Hand</th>
                <th className="px-4 py-3 text-right">Reserved</th>
                <th className="px-4 py-3 text-right font-bold text-slate-900">Usable Eligible</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filtered.map((item, idx) => {
                const isNearExp = item.days_to_expiry <= 45;
                const isCold = item.storage_requirements === 'COLD_CHAIN_2_8C';

                return (
                  <tr key={idx} className="hover:bg-slate-50/70 transition">
                    <td className="px-4 py-3 font-semibold text-slate-900">
                      <div>{item.product_name}</div>
                      <div className="text-[10px] text-slate-400 font-normal">{item.generic_name} ({item.strength})</div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {item.facility_name}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-700">
                      {item.manufacturer_lot_number}
                    </td>
                    <td className="px-4 py-3">
                      <div className={isNearExp ? 'text-amber-700 font-bold' : 'text-slate-700'}>
                        {item.expiry_date}
                      </div>
                      <div className="text-[10px] text-slate-400">
                        {item.days_to_expiry} days left
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {isCold ? (
                        <span className="inline-flex items-center space-x-1 text-[10px] font-semibold text-cyan-800 bg-cyan-50 px-2 py-0.5 rounded border border-cyan-200">
                          <Snowflake className="w-3 h-3 text-cyan-600" />
                          <span>2–8°C</span>
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500 font-medium">Ambient</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono">
                      {item.on_hand_quantity}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-amber-700">
                      {item.reserved_quantity}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-slate-900">
                      {item.usable_quantity} {item.unit}
                    </td>
                  </tr>
                );
              })}

              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                    No matching inventory records found.
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

