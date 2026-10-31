'use client';
import React from 'react';

export function RiskBadge({ level }) {
  const styles = {
    CRITICAL: 'bg-red-50 text-red-700 border-red-200 ring-red-500/10',
    HIGH: 'bg-amber-50 text-amber-800 border-amber-200 ring-amber-500/10',
    MEDIUM: 'bg-yellow-50 text-yellow-800 border-yellow-200 ring-yellow-500/10',
    LOW: 'bg-emerald-50 text-emerald-700 border-emerald-200 ring-emerald-500/10',
    SAFE: 'bg-slate-50 text-slate-700 border-slate-200 ring-slate-500/10',
  };

  const current = styles[level] || styles.SAFE;

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium border ring-1 ${current}`}>
      {level}
    </span>
  );
}

export function StatusBadge({ status }) {
  const styles = {
    PROPOSED: 'bg-blue-50 text-blue-700 border-blue-200',
    PENDING_SOURCE_APPROVAL: 'bg-purple-50 text-purple-700 border-purple-200',
    PENDING_DESTINATION_APPROVAL: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    APPROVED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    RESERVED: 'bg-cyan-50 text-cyan-800 border-cyan-200',
    READY_FOR_DISPATCH: 'bg-sky-50 text-sky-800 border-sky-200',
    DISPATCHED: 'bg-amber-50 text-amber-800 border-amber-200',
    IN_TRANSIT: 'bg-orange-50 text-orange-800 border-orange-200',
    RECEIVED: 'bg-emerald-50 text-emerald-800 border-emerald-200',
    FAILED_INSUFFICIENT_STOCK: 'bg-rose-50 text-rose-800 border-rose-200',
    REJECTED: 'bg-red-50 text-red-700 border-red-200',
    ACTIVE: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    RELEASED: 'bg-slate-50 text-slate-700 border-slate-200',
  };

  const current = styles[status] || 'bg-gray-50 text-gray-700 border-gray-200';

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${current}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

