'use client';
import React from 'react';
import { 
  LayoutDashboard, 
  AlertTriangle, 
  ArrowLeftRight, 
  CheckCircle2, 
  QrCode, 
  Package, 
  TrendingUp, 
  History,
  ScanLine
} from 'lucide-react';

export function Sidebar({ currentTab, onSelectTab, counts = {} }) {
  const navItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'risks', label: 'Risk Queue', icon: AlertTriangle, count: counts.risks },
    { id: 'opportunities', label: 'Redistribution Matches', icon: ArrowLeftRight, count: counts.opportunities },
    { id: 'approvals', label: 'Transfer Approvals', icon: CheckCircle2, count: counts.approvals },
    { id: 'transfers', label: 'Transfers & QR Track', icon: Package, count: counts.transfers },
    { id: 'scanner', label: 'QR Scan Terminal', icon: ScanLine },
    { id: 'inventory', label: 'Inventory & Batches', icon: QrCode },
    { id: 'forecasts', label: 'Demand Forecasts', icon: TrendingUp },
    { id: 'audit', label: 'Ledger & Audit Trail', icon: History },
  ];

  return (
    <aside className="w-64 bg-slate-900 text-slate-300 flex flex-col shrink-0 min-h-[calc(100vh-4rem)]">
      <div className="p-4 border-b border-slate-800">
        <span className="text-[11px] font-bold tracking-wider uppercase text-slate-400">
          Command Operations
        </span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2.5 rounded-md text-xs font-medium transition ${
                isActive
                  ? 'bg-emerald-600 text-white font-semibold shadow-sm'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`}
            >
              <div className="flex items-center space-x-2.5">
                <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </div>
              {item.count !== undefined && item.count > 0 && (
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                  isActive ? 'bg-emerald-700 text-white' : 'bg-slate-800 text-slate-300'
                }`}>
                  {item.count}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      <div className="p-4 border-t border-slate-800 bg-slate-950/40 text-[11px] text-slate-400">
        <p className="font-medium text-slate-300 mb-1">Stockout Shield v1.0</p>
        <p>Level 2 Agentic Governance</p>
        <div className="mt-2 flex items-center space-x-1.5 text-emerald-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>Ledger & Security Online</span>
        </div>
      </div>
    </aside>
  );
}

