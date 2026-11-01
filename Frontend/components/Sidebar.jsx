'use client';
import React, { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowLeftRight,
  Bot,
  Building2,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Database,
  History,
  LayoutDashboard,
  Package,
  ScanLine,
  Settings,
  TrendingUp,
  X,
} from 'lucide-react';

const navGroups = [
  {
    label: 'OVERVIEW',
    items: [
      { id: 'overview', label: 'Home', icon: LayoutDashboard },
      { id: 'facilities', label: 'Facilities', icon: Building2 },
      { id: 'inventory', label: 'Inventory', icon: Package },
    ],
  },
  {
    label: 'SUPPLY',
    items: [
      { id: 'risks', label: 'Risks', icon: AlertTriangle, countKey: 'risks' },
      { id: 'opportunities', label: 'Matches', icon: ArrowLeftRight, countKey: 'opportunities' },
      { id: 'approvals', label: 'Approvals', icon: CheckCircle2, countKey: 'approvals' },
      { id: 'transfers', label: 'Transfers', icon: ClipboardCheck, countKey: 'transfers' },
    ],
  },
  {
    label: 'TOOLS',
    items: [
      { id: 'scanner', label: 'QR scanner', icon: ScanLine },
      { id: 'forecasts', label: 'Forecasts', icon: TrendingUp },
      { id: 'data-quality', label: 'Data quality', icon: Database },
      { id: 'agents', label: 'Workflows', icon: Bot },
      { id: 'audit', label: 'Audit log', icon: History },
      { id: 'settings', label: 'Settings', icon: Settings },
    ],
  },
];

export function Sidebar({
  currentTab,
  onSelectTab,
  counts = {},
  mobileOpen = false,
  onCloseMobile,
}) {
  const [isCollapsed, setIsCollapsed] = useState(false);

  useEffect(() => {
    setIsCollapsed(window.localStorage.getItem('mediflow-sidebar-collapsed') === 'true');
  }, []);

  const toggleCollapsed = () => {
    setIsCollapsed((current) => {
      window.localStorage.setItem('mediflow-sidebar-collapsed', String(!current));
      return !current;
    });
  };

  const selectTab = (tab) => {
    onSelectTab(tab);
    onCloseMobile?.();
  };

  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={onCloseMobile}
          className="fixed inset-0 z-40 bg-slate-950/30 md:hidden"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-64 flex-col border-r border-slate-200 bg-white md:sticky md:top-16 md:z-10 md:h-[calc(100vh-4rem)] md:translate-x-0 ${
          isCollapsed ? 'md:w-[4.5rem]' : 'md:w-60'
        } ${mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'}`}
      >
        <div className={`flex h-16 shrink-0 items-center border-b border-slate-100 px-4 ${isCollapsed ? 'md:justify-center md:px-2' : 'justify-between'}`}>
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-700 text-sm font-bold text-white">
              M
            </div>
            <div className={isCollapsed ? 'md:hidden' : ''}>
              <p className="text-sm font-semibold tracking-tight text-slate-900">MediFlow</p>
              <p className="text-[11px] text-slate-500">Care network</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onCloseMobile}
            aria-label="Close navigation"
            className="rounded-md p-2 text-slate-500 hover:bg-slate-100 md:hidden"
          >
            <X className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={toggleCollapsed}
            aria-label={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            className="hidden rounded-md p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 md:block"
          >
            {isCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </button>
        </div>

        <nav aria-label="Main navigation" className="flex-1 space-y-5 overflow-y-auto px-3 py-5">
          {navGroups.map((group) => (
            <section key={group.label}>
              {!isCollapsed && (
                <h2 className="mb-2 px-3 text-[10px] font-semibold tracking-[0.12em] text-slate-400 md:block">
                  {group.label}
                </h2>
              )}
              {isCollapsed && (
                <h2 className="mb-2 hidden px-3 text-[10px] font-semibold tracking-[0.12em] text-slate-400 md:block">
                  {group.label.slice(0, 1)}
                </h2>
              )}
              <div className="space-y-1">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = currentTab === item.id;
                  const count = item.countKey ? counts[item.countKey] : null;
                  return (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => selectTab(item.id)}
                      aria-current={isActive ? 'page' : undefined}
                      title={isCollapsed ? item.label : undefined}
                      className={`flex min-h-10 w-full items-center rounded-lg px-3 text-left text-[13px] font-medium ${
                        isActive
                          ? 'bg-emerald-50 text-emerald-800'
                          : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
                      } ${isCollapsed ? 'md:justify-center md:px-0' : ''}`}
                    >
                      <Icon className={`h-[18px] w-[18px] shrink-0 ${isActive ? 'text-emerald-700' : 'text-slate-400'}`} />
                      <span className={`ml-3 flex-1 ${isCollapsed ? 'md:hidden' : ''}`}>{item.label}</span>
                      {count > 0 && (
                        <span className={`min-w-5 rounded-full px-1.5 py-0.5 text-center text-[10px] font-semibold ${
                          isActive ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
                        } ${isCollapsed ? 'md:hidden' : ''}`}>
                          {count}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
        </nav>

        <div className={`border-t border-slate-100 px-4 py-4 ${isCollapsed ? 'md:px-2 md:text-center' : ''}`}>
          <div className={`flex items-center gap-2 text-xs text-slate-500 ${isCollapsed ? 'md:justify-center' : ''}`}>
            <Activity className="h-3.5 w-3.5 shrink-0 text-emerald-600" />
            <span className={isCollapsed ? 'md:hidden' : ''}>Operations ready</span>
          </div>
          <p className={`mt-1 pl-[22px] text-[10px] text-slate-400 ${isCollapsed ? 'md:hidden' : ''}`}>
            MediFlow · Version 1.0
          </p>
        </div>
      </aside>
    </>
  );
}
