'use client';
import React from 'react';
import { Shield, RefreshCw, AlertCircle, Building2, User } from 'lucide-react';

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
                <span className="font-bold text-slate-900 text-lg tracking-tight">Stockout Shield</span>
                <span className="bg-slate-100 text-slate-600 text-[10px] font-semibold px-2 py-0.5 rounded border border-slate-200">
                  SIMULATION
                </span>
              </div>
              <p className="text-xs text-slate-500">Multi-Facility Medicine Inventory Intelligence & Traceability</p>
            </div>
          </div>

          {/* Quick Context Switchers & Demo Reset */}
          <div className="flex items-center space-x-4">
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
              <span>{isResetting ? 'Resetting...' : 'Reset Demo'}</span>
            </button>
          </div>
        </div>
      </div>
    </header>
  );
}

