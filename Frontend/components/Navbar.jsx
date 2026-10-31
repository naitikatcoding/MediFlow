'use client';
import React, { useState } from 'react';
import { Shield, RefreshCw, AlertCircle, Building2, User, Activity, CheckCircle2, XCircle } from 'lucide-react';
import { useApiHealth } from '../hooks/useApiHealth';

export function Navbar({ 
  facilities = [], 
  users = [], 
  activeFacility, 
  activeUser, 
  onFacilityChange, 
  onUserChange,
  onResetDemo,
  isResetting
}) {
  const { health, status: apiStatus, error: apiError, refetch } = useApiHealth();
  const [showHealthTooltip, setShowHealthTooltip] = useState(false);

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Brand */}
          <div className="flex items-center space-x-3">
            <div className="bg-emerald-600 text-white p-2 rounded-lg flex items-center justify-center shadow-sm">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-slate-900 text-lg tracking-tight">MediFlow</span>
                <span className="bg-slate-100 text-slate-600 text-[10px] font-semibold px-2 py-0.5 rounded border border-slate-200">
                  SIMULATION
                </span>
              </div>
              <p className="text-xs text-slate-500 hidden sm:block">Multi-Facility Medicine Inventory Intelligence & Traceability</p>
            </div>
          </div>

          {/* Center / Right Control Panel */}
          <div className="flex items-center space-x-3">
            {/* API Connectivity Indicator */}
            <div 
              className="relative"
              onMouseEnter={() => setShowHealthTooltip(true)}
              onMouseLeave={() => setShowHealthTooltip(false)}
            >
              <button
                onClick={() => refetch()}
                className={`inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors shadow-xs ${
                  apiStatus === 'healthy' 
                    ? 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                    : apiStatus === 'checking'
                    ? 'bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100'
                    : 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100 animate-pulse'
                }`}
                title="Backend API Connection Status"
              >
                <span className="relative flex h-2 w-2">
                  {apiStatus === 'healthy' && (
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  )}
                  <span className={`relative inline-flex rounded-full h-2 w-2 ${
                    apiStatus === 'healthy' ? 'bg-emerald-500' : apiStatus === 'checking' ? 'bg-amber-500' : 'bg-rose-500'
                  }`}></span>
                </span>
                <span className="font-semibold">
                  {apiStatus === 'healthy' ? 'API Online' : apiStatus === 'checking' ? 'Connecting...' : 'API Offline'}
                </span>
              </button>

              {/* Status Details Tooltip */}
              {showHealthTooltip && (
                <div className="absolute right-0 mt-2 w-64 bg-slate-900 text-slate-100 rounded-lg p-3 text-xs shadow-xl z-50 border border-slate-800">
                  <div className="flex items-center justify-between pb-1.5 border-b border-slate-800 mb-2">
                    <span className="font-semibold text-slate-200">System Connectivity</span>
                    <span className="text-[10px] text-slate-400">/api/v1/health</span>
                  </div>
                  <div className="space-y-1 text-slate-300">
                    <div className="flex justify-between">
                      <span className="text-slate-400">Status:</span>
                      <span className={apiStatus === 'healthy' ? 'text-emerald-400 font-medium' : 'text-rose-400 font-medium'}>
                        {apiStatus.toUpperCase()}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Database:</span>
                      <span className="font-mono text-[11px] text-slate-200">
                        {health?.database?.engine || 'Checking...'}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">Storage Mode:</span>
                      <span className="text-slate-200">
                        {health?.database?.is_fallback ? 'SQLite (Dev Fallback)' : 'YugabyteDB'}
                      </span>
                    </div>
                    {apiError && (
                      <div className="mt-2 text-rose-300 text-[11px] bg-rose-950/60 p-1.5 rounded border border-rose-800">
                        {apiError}
                      </div>
                    )}
                  </div>
                  <div className="mt-2 pt-2 border-t border-slate-800 flex justify-between items-center text-[10px] text-slate-400">
                    <span>Click badge to refresh</span>
                    <span className="text-emerald-400 font-mono">v1.0.0</span>
                  </div>
                </div>
              )}
            </div>

            {/* Active Facility Selector */}
            <div className="flex items-center space-x-1.5 bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1">
              <Building2 className="w-3.5 h-3.5 text-slate-500" />
              <select
                className="bg-transparent text-xs text-slate-700 font-medium focus:outline-none cursor-pointer"
                value={activeFacility?.id || ''}
                onChange={(e) => {
                  const fac = facilities.find(f => f.id === e.target.value);
                  if (fac) onFacilityChange(fac);
                }}
              >
                {facilities.map(f => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
            </div>

            {/* Active User Selector */}
            <div className="flex items-center space-x-1.5 bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1">
              <User className="w-3.5 h-3.5 text-slate-500" />
              <select
                className="bg-transparent text-xs text-slate-700 font-medium focus:outline-none cursor-pointer"
                value={activeUser?.id || ''}
                onChange={(e) => {
                  const usr = users.find(u => u.id === e.target.value);
                  if (usr) onUserChange(usr);
                }}
              >
                {users.map(u => (
                  <option key={u.id} value={u.id}>{u.name} ({u.role})</option>
                ))}
              </select>
            </div>

            {/* Re-seed / Reset button */}
            <button
              onClick={onResetDemo}
              disabled={isResetting}
              className="inline-flex items-center space-x-1.5 text-xs font-medium text-slate-700 bg-white border border-slate-200 hover:bg-slate-50 px-3 py-1.5 rounded-md transition shadow-sm disabled:opacity-50"
              title="Reset deterministic synthetic scenario"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-slate-500 ${isResetting ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">{isResetting ? 'Resetting...' : 'Reset Demo'}</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}
