'use client';
import React, { useState } from 'react';
import { CheckCircle2, XCircle, AlertCircle, ShieldCheck, ArrowRight, Zap } from 'lucide-react';
import { StatusBadge } from '../Badges';

export function ApprovalsView({ 
  proposals = [], 
  activeFacility, 
  activeUser, 
  onApprove, 
  onSimulateStockChange,
  onNavigateTab
}) {
  const [processingId, setProcessingId] = useState(null);

  const handleApproveAction = async (proposal, decision = 'APPROVED') => {
    setProcessingId(proposal.id);
    try {
      // Determine which facility needs approval next
      let targetFacilityId = activeFacility?.id;
      if (!targetFacilityId || (targetFacilityId !== proposal.source_facility_id && targetFacilityId !== proposal.destination_facility_id)) {
        targetFacilityId = !proposal.source_approved ? proposal.source_facility_id : proposal.destination_facility_id;
      } else if (targetFacilityId === proposal.source_facility_id && proposal.source_approved && !proposal.destination_approved) {
        // Source already approved, user wants to approve destination
        targetFacilityId = proposal.destination_facility_id;
      }

      await onApprove({
        proposal_id: proposal.id,
        proposal_version: proposal.proposal_version,
        facility_id: targetFacilityId,
        approver_user_id: activeUser?.id,
        decision,
        reason: `${decision} recorded by ${activeUser?.name} (${activeUser?.role})`
      });
    } catch (err) {
      alert(`Approval response: ${err.message}`);
    } finally {
      setProcessingId(null);
    }
  };


  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Transfer Governance & Dual Approvals</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Level 2 Agentic Governance: Transfers require explicit authorization from both Source and Destination clinical leads prior to atomic stock reservation.
          </p>
        </div>

        {/* Edge Case Trigger for Judges / Demo */}
        <button
          onClick={onSimulateStockChange}
          className="inline-flex items-center space-x-1.5 text-xs font-semibold bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-300 px-3 py-1.5 rounded-md shadow-sm transition"
          title="Simulate sudden source inventory drop before reservation to demonstrate safe atomic rollback"
        >
          <Zap className="w-3.5 h-3.5 text-amber-600" />
          <span>Simulate Stock Shock Edge Case</span>
        </button>
      </div>

      <div className="space-y-4">
        {proposals.map((prop) => {
          const isSource = activeFacility?.id === prop.source_facility_id;
          const isDest = activeFacility?.id === prop.destination_facility_id;
          const canAct = (isSource && !prop.source_approved) || (isDest && !prop.destination_approved);
          const isBusy = processingId === prop.id;

          return (
            <div key={prop.id} className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-4">
              {/* Header */}
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2.5">
                  <span className="text-sm font-bold text-slate-900">{prop.product_name}</span>
                  <StatusBadge status={prop.status} />
                  <span className="text-[10px] bg-slate-100 text-slate-600 font-mono px-2 py-0.5 rounded border border-slate-200">
                    Version v{prop.proposal_version}
                  </span>
                </div>
                <div className="text-xs font-bold text-slate-900">
                  {prop.proposed_quantity} {prop.unit}
                </div>
              </div>

              {/* Facility Route & Dual Approvals Status Bar */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-slate-50 p-3.5 rounded-lg border border-slate-150">
                {/* Source Facility Status */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-800">1. Source: {prop.source_facility_name}</span>
                    {prop.source_approved ? (
                      <span className="inline-flex items-center space-x-1 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Source Authorized</span>
                      </span>
                    ) : (
                      <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        Pending Source Review
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-600">{prop.source_rationale?.summary}</p>
                </div>

                {/* Destination Facility Status */}
                <div className="space-y-1.5 border-t md:border-t-0 md:border-l border-slate-200 md:pl-4 pt-2 md:pt-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-slate-800">2. Destination: {prop.destination_facility_name}</span>
                    {prop.destination_approved ? (
                      <span className="inline-flex items-center space-x-1 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        <span>Destination Accepted</span>
                      </span>
                    ) : (
                      <span className="text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                        Pending Destination Acceptance
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-600">{prop.destination_rationale?.summary}</p>
                </div>
              </div>

              {/* Action Buttons for Authorized Actor */}
              <div className="flex items-center justify-between pt-1">
                <div className="text-[11px] text-slate-500">
                  Active Reviewer: <span className="font-semibold text-slate-700">{activeUser?.name}</span> ({activeFacility?.name})
                </div>

                <div className="flex items-center space-x-2">
                  {prop.status === 'RESERVED' ? (
                    <button
                      onClick={() => onNavigateTab('transfers')}
                      className="inline-flex items-center space-x-1.5 text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-1.5 rounded-md hover:bg-emerald-100 transition"
                    >
                      <ShieldCheck className="w-4 h-4 text-emerald-600" />
                      <span>Stock Reserved. View QR Label →</span>
                    </button>
                  ) : (
                    <>
                      <button
                        onClick={() => handleApproveAction(prop, 'REJECTED')}
                        disabled={isBusy || prop.status === 'REJECTED'}
                        className="text-xs font-medium text-red-600 hover:text-red-700 border border-red-200 bg-white hover:bg-red-50 px-3 py-1.5 rounded-md transition disabled:opacity-50"
                      >
                        Reject
                      </button>

                      <button
                        onClick={() => handleApproveAction(prop, 'APPROVED')}
                        disabled={isBusy || (isSource && prop.source_approved) || (isDest && prop.destination_approved)}
                        className="inline-flex items-center space-x-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 px-3.5 py-1.5 rounded-md shadow-sm transition disabled:opacity-50"
                      >
                        <CheckCircle2 className="w-4 h-4" />
                        <span>{isBusy ? 'Processing...' : 'Authorize Clinical Release'}</span>
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}

        {proposals.length === 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-8 text-center text-xs text-slate-500">
            No active proposals requiring approval. Generate proposals from the Redistribution Matches tab.
          </div>
        )}
      </div>
    </div>
  );
}

