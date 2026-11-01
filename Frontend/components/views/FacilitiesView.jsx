'use client';
import React, { useState } from 'react';
import { 
  Building2, ThermometerSnowflake, ShieldCheck, Clock, MapPin, 
  Activity, AlertTriangle, ArrowRight, CheckCircle2 
} from 'lucide-react';

export function FacilitiesView({ facilities = [], inventory = [], risks = [], onNavigateTab, onSelectFacility }) {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('ALL');

  const filteredFacilities = facilities.filter(f => {
    if (filterType !== 'ALL' && f.facility_type !== filterType) return false;
    if (searchTerm.trim() && !f.name.toLowerCase().includes(searchTerm.toLowerCase())) return false;
    return true;
  });

  // Calculate metrics per facility
  const getFacilityStats = (facilityId) => {
    const facInv = inventory.filter(i => i.facility_id === facilityId);
    const totalOnHand = facInv.reduce((sum, item) => sum + (item.on_hand_quantity || 0), 0);
    const totalReserved = facInv.reduce((sum, item) => sum + (item.reserved_quantity || 0), 0);
    const facRisks = risks.filter(r => r.facility_id === facilityId);
    const stockoutCount = facRisks.filter(r => r.risk_type === 'STOCKOUT_RISK').length;
    const expiryCount = facRisks.filter(r => r.risk_type === 'EXPIRY_RISK').length;

    return {
      totalOnHand,
      totalReserved,
      skuCount: facInv.length,
      stockoutCount,
      expiryCount
    };
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Facilities</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Registered hospitals, diagnostic clinics, and regional pharmacies with verified storage capabilities.
          </p>
        </div>

        {/* Filters */}
        <div className="flex items-center space-x-2">
          <input
            type="text"
            placeholder="Search facility name..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="text-xs bg-white border border-slate-200 rounded-md px-3 py-1.5 text-slate-700 placeholder-slate-400 focus:outline-none focus:border-emerald-500"
          />

          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="text-xs bg-white border border-slate-200 rounded-md px-2.5 py-1.5 text-slate-700 font-medium"
          >
            <option value="ALL">All Facility Types</option>
            <option value="HOSPITAL">Hospitals</option>
            <option value="PHARMACY">Pharmacies</option>
            <option value="CLINIC">Diagnostic Clinics</option>
          </select>
        </div>
      </div>

      {/* Facility Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {filteredFacilities.map((fac) => {
          const stats = getFacilityStats(fac.id);
          const caps = fac.storage_capabilities || {};

          return (
            <div 
              key={fac.id}
              className="bg-white rounded-lg border border-slate-200 p-5 shadow-sm space-y-4 hover:border-slate-300 transition"
            >
              {/* Facility Header */}
              <div className="flex items-start justify-between border-b border-slate-100 pb-3">
                <div className="flex items-start space-x-3">
                  <div className="p-2.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 mt-0.5">
                    <Building2 className="w-5 h-5" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <h2 className="text-sm font-bold text-slate-900">{fac.name}</h2>
                      <span className="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-700 border border-slate-200">
                        {fac.facility_type}
                      </span>
                    </div>
                    <div className="flex items-center space-x-3 text-[11px] text-slate-500 mt-1">
                      <span className="flex items-center space-x-1">
                        <MapPin className="w-3.5 h-3.5 text-slate-400" />
                        <span>{fac.city || 'Regional Sector'}</span>
                      </span>
                      <span className="flex items-center space-x-1">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        <span>{fac.timezone || 'UTC'}</span>
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-1 text-emerald-600 text-xs font-medium">
                  <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                  <span>Active</span>
                </div>
              </div>

              {/* Storage Capabilities */}
              <div className="space-y-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Verified Storage & Handling Capabilities
                </span>
                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  <span className={`px-2 py-0.5 rounded border font-medium flex items-center space-x-1 ${
                    caps.cold_chain 
                      ? 'bg-blue-50 text-blue-700 border-blue-200' 
                      : 'bg-slate-50 text-slate-400 border-slate-200'
                  }`}>
                    <ThermometerSnowflake className="w-3 h-3" />
                    <span>Cold Chain (2°C – 8°C): {caps.cold_chain ? 'Certified' : 'Not Available'}</span>
                  </span>

                  <span className="px-2 py-0.5 rounded border font-medium bg-slate-50 text-slate-700 border-slate-200">
                    Ambient Max: {caps.ambient_max_c ? `${caps.ambient_max_c}°C` : '25°C'}
                  </span>

                  {caps.narcotics_vault && (
                    <span className="px-2 py-0.5 rounded border font-medium bg-purple-50 text-purple-700 border-purple-200 flex items-center space-x-1">
                      <ShieldCheck className="w-3 h-3" />
                      <span>Narcotics Vault</span>
                    </span>
                  )}

                  {caps.cleanroom && (
                    <span className="px-2 py-0.5 rounded border font-medium bg-emerald-50 text-emerald-700 border-emerald-200">
                      Cleanroom Certified
                    </span>
                  )}
                </div>
              </div>

              {/* Operational Footprint Stats */}
              <div className="grid grid-cols-4 gap-2 bg-slate-50 p-2.5 rounded-lg border border-slate-100 text-center text-xs">
                <div>
                  <span className="text-slate-400 block text-[10px]">Tracked SKUs</span>
                  <strong className="text-slate-900">{stats.skuCount}</strong>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">On-Hand Stock</span>
                  <strong className="text-slate-900">{stats.totalOnHand}</strong>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Shortage Alerts</span>
                  <strong className={stats.stockoutCount > 0 ? 'text-rose-600' : 'text-slate-900'}>
                    {stats.stockoutCount}
                  </strong>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Expiry Risks</span>
                  <strong className={stats.expiryCount > 0 ? 'text-amber-600' : 'text-slate-900'}>
                    {stats.expiryCount}
                  </strong>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-1 text-xs">
                <span className="text-[10px] text-slate-400 font-mono">
                  ID: {fac.id.substring(0, 8)}...
                </span>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => {
                      if (onSelectFacility) onSelectFacility(fac);
                      onNavigateTab('inventory');
                    }}
                    className="inline-flex items-center space-x-1 text-emerald-700 hover:text-emerald-800 font-semibold text-xs"
                  >
                    <span>View Facility Stock</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          );
        })}

        {filteredFacilities.length === 0 && (
          <div className="col-span-2 bg-white rounded-lg border border-slate-200 p-8 text-center text-xs text-slate-500">
            No facilities matching search criteria.
          </div>
        )}
      </div>
    </div>
  );
}
