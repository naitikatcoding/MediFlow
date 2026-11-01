'use client';
import React, { useState } from 'react';
import {
  Activity,
  Building2,
  Database,
  Menu,
  RefreshCw,
  Shield,
  UserRound,
} from 'lucide-react';
import { useApiHealth } from '../hooks/useApiHealth';

export function Navbar({
  facilities = [],
  users = [],
  activeFacility,
  activeUser,
  onFacilityChange,
  onUserChange,
  onResetDemo,
  isResetting,
  onOpenMenu,
}) {
  const { health, status: apiStatus, error: apiError, refetch } = useApiHealth();
  const [showHealthDetails, setShowHealthDetails] = useState(false);
  const databaseName = health?.database?.engine === 'postgresql/yugabyte'
    ? 'YugabyteDB'
    : health?.database?.is_fallback
      ? 'SQLite fallback'
      : health?.database?.engine === 'sqlite'
        ? 'SQLite'
        : 'Checking database';

  const refreshHealth = () => {
    setShowHealthDetails((visible) => !visible);
    refetch();
  };

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white">
      <div className="flex min-h-16 items-center justify-between gap-3 px-4 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onOpenMenu}
            aria-label="Open navigation"
            className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 md:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-700 text-white">
              <Shield className="h-[18px] w-[18px]" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold tracking-tight text-slate-900">MediFlow</p>
              <p className="hidden text-[11px] text-slate-500 sm:block">Medicine supply, made clear</p>
            </div>
          </div>
        </div>

        <div className="flex min-w-0 items-center justify-end gap-2 sm:gap-3">
          <label className="flex min-w-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-2 sm:px-3">
            <Building2 className="h-4 w-4 shrink-0 text-slate-400" />
            <span className="sr-only">Active facility</span>
            <select
              aria-label="Active facility"
              className="max-w-[8rem] cursor-pointer truncate bg-transparent text-xs font-medium text-slate-700 outline-none sm:max-w-[12rem]"
              value={activeFacility?.id || ''}
              onChange={(event) => {
                const facility = facilities.find((item) => item.id === event.target.value);
                if (facility) onFacilityChange(facility);
              }}
            >
              {facilities.map((facility) => (
                <option key={facility.id} value={facility.id}>{facility.name}</option>
              ))}
            </select>
          </label>

          <label className="flex min-w-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-2 sm:px-3">
            <UserRound className="h-4 w-4 shrink-0 text-slate-400" />
            <span className="sr-only">Active user</span>
            <select
              aria-label="Active user"
              className="max-w-[6.5rem] cursor-pointer truncate bg-transparent text-xs font-medium text-slate-700 outline-none sm:max-w-[10rem]"
              value={activeUser?.id || ''}
              onChange={(event) => {
                const user = users.find((item) => item.id === event.target.value);
                if (user) onUserChange(user);
              }}
            >
              {users.map((user) => (
                <option key={user.id} value={user.id}>{user.name} · {user.role}</option>
              ))}
            </select>
          </label>

          <div className="relative hidden sm:block">
            <button
              type="button"
              onClick={refreshHealth}
              aria-expanded={showHealthDetails}
              aria-label={`API ${apiStatus}; database ${databaseName}. Refresh status.`}
              title="Refresh connection status"
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-xs font-medium ${
                apiStatus === 'healthy'
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                  : apiStatus === 'checking'
                    ? 'border-amber-200 bg-amber-50 text-amber-800'
                    : 'border-rose-200 bg-rose-50 text-rose-800'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${
                apiStatus === 'healthy' ? 'bg-emerald-600' : apiStatus === 'checking' ? 'bg-amber-500' : 'bg-rose-600'
              }`} />
              <span className="hidden lg:inline">{apiStatus === 'healthy' ? 'Connected' : apiStatus === 'checking' ? 'Checking' : 'Offline'}</span>
              <span className="hidden items-center gap-1 border-l border-current/20 pl-2 md:inline-flex">
                <Database className="h-3.5 w-3.5" />
                {databaseName}
              </span>
            </button>
            {showHealthDetails && (
              <div className="absolute right-0 top-full mt-2 w-64 rounded-lg border border-slate-200 bg-white p-4 text-xs shadow-lg">
                <div className="flex items-center gap-2 font-semibold text-slate-900">
                  <Activity className="h-4 w-4 text-emerald-700" />
                  System status
                </div>
                <p className="mt-2 text-slate-600">API: {apiStatus}</p>
                <p className="mt-1 text-slate-600">Database: {databaseName}</p>
                {apiError && <p className="mt-2 break-words text-rose-700">{apiError}</p>}
                <button
                  type="button"
                  onClick={refreshHealth}
                  className="mt-3 font-medium text-emerald-800 hover:text-emerald-900"
                >
                  Refresh status
                </button>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={onResetDemo}
            disabled={isResetting}
            className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-200 bg-white px-2.5 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50 sm:px-3"
            title="Reset demo data"
          >
            <RefreshCw className={`h-4 w-4 ${isResetting ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{isResetting ? 'Resetting' : 'Reset demo'}</span>
          </button>
        </div>
      </div>
    </header>
  );
}
