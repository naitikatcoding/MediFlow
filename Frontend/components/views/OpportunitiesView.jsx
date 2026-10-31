'use client';
import React, { useState } from 'react';
import { ArrowLeftRight, Check, XCircle, ShieldAlert, Sparkles, Send } from 'lucide-react';

export function OpportunitiesView({ 
  opportunitiesData, 
  onCreateProposal, 
  isCreating 
}) {
  const accepted = opportunitiesData?.accepted_opportunities || [];
  const rejected = opportunitiesData?.rejected_candidates || [];
  const [createdMap, setCreatedMap] = useState({});

  const handlePropose = async (opp, idx) => {
    try {
      await onCreateProposal(opp);
      setCreatedMap(prev => ({ ...prev, [idx]: true }));
    } catch (err) {
      alert(`Error creating proposal: ${err.message}`);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight">Redistribution Matching Engine</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Deterministic pairing of verified surplus with urgent destination shortage, constrained by safety-stock buffers and facility storage capabilities.
        </p>
      </div>

      {/* Section 1: Feasible Redistribution Opportunities */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-slate-50/70 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <ArrowLeftRight className="w-4 h-4 text-emerald-600" />
            <h2 className="text-xs font-bold text-slate-900 uppercase tracking-wide">
              Eligible Redistribution Candidates ({accepted.length})
            </h2>
          </div>
          <span className="text-[10px] bg-emerald-50 text-emerald-700 font-semibold px-2 py-0.5 rounded border border-emerald-200">
            Validated Constraints
          </span>
        </div>

        <div className="divide-y divide-slate-100">
          {accepted.map((opp, idx) => {
            const isCreated = createdMap[idx];
            return (
              <div key={idx} className="p-4 hover:bg-slate-50/50 transition flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="space-y-1.5 max-w-2xl">
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-bold text-slate-900">{opp.product_name}</span>
                    <span className="text-xs bg-slate-100 text-slate-700 font-mono px-2 py-0.5 rounded border border-slate-200">
                      {opp.strength}
                    </span>
                    <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                      {opp.matched_quantity} {opp.unit} Feasible
                    </span>
                  </div>

                  <div className="flex items-center space-x-2 text-xs text-slate-700">
                    <span className="font-semibold text-slate-900">{opp.source_facility_name} (Surplus)</span>
                    <span className="text-slate-400">──────►</span>
                    <span className="font-semibold text-slate-900">{opp.destination_facility_name} (Deficit)</span>
                  </div>

                  <div className="text-[11px] text-slate-500 grid grid-cols-1 sm:grid-cols-2 gap-2 pt-1">
                    <div>
                      <span className="font-medium text-slate-700">Source:</span> {opp.source_rationale?.summary}
                    </div>
                    <div>
                      <span className="font-medium text-slate-700">Destination:</span> {opp.destination_rationale?.summary}
                    </div>
                  </div>
                </div>

                <div className="flex flex-col items-end shrink-0 space-y-2">
                  <div className="text-[11px] text-slate-500">
                    Match Confidence: <span className="font-bold text-slate-800">{opp.acceptance_score}%</span>
                  </div>
                  <button
                    onClick={() => handlePropose(opp, idx)}
                    disabled={isCreated || isCreating}
                    className={`inline-flex items-center space-x-1.5 text-xs font-semibold px-3 py-1.5 rounded-md shadow-sm transition ${
                      isCreated
                        ? 'bg-slate-100 text-slate-500 cursor-default'
                        : 'bg-emerald-600 hover:bg-emerald-700 text-white'
                    }`}
                  >
                    {isCreated ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Proposal Created</span>
                      </>
                    ) : (
                      <>
                        <Send className="w-3.5 h-3.5" />
                        <span>Create Proposal</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}

          {accepted.length === 0 && (
            <div className="p-8 text-center text-xs text-slate-500">
              No matching pairs met all feasibility, safety buffer, and storage constraints.
            </div>
          )}
        </div>
      </div>

      {/* Section 2: Deterministic Rejections (Transparent Audit) */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-slate-50/70 border-b border-slate-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <XCircle className="w-4 h-4 text-slate-500" />
            <h2 className="text-xs font-bold text-slate-800 uppercase tracking-wide">
              Deterministic Constraint Rejections ({rejected.length})
            </h2>
          </div>
          <span className="text-[10px] text-slate-500 font-medium">
            Explainable Rejections Log
          </span>
        </div>

        <div className="divide-y divide-slate-100">
          {rejected.map((rej, idx) => (
            <div key={idx} className="p-3.5 text-xs flex items-start justify-between">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-semibold text-slate-900">{rej.product_name}</span>
                  <span className="bg-rose-50 text-rose-800 border border-rose-200 text-[10px] font-mono px-1.5 py-0.5 rounded">
                    {rej.rejected_reason}
                  </span>
                </div>
                <p className="text-[11px] text-slate-600 mt-1">{rej.explanation}</p>
              </div>
              <div className="text-right text-[10px] text-slate-400 shrink-0 ml-4">
                Constraint Enforced
              </div>
            </div>
          ))}

          {rejected.length === 0 && (
            <div className="p-6 text-center text-xs text-slate-500">No candidate rejections recorded.</div>
          )}
        </div>
      </div>
    </div>
  );
}

