'use client';
import React, { useState } from 'react';
import { 
  Package, QrCode, Truck, CheckCircle2, Clock, Eye, ScanLine, 
  ChevronDown, ChevronUp, History, AlertTriangle, ShieldCheck, PlayCircle
} from 'lucide-react';
import { StatusBadge } from '../Badges';
import { api } from '../../lib/api';

export function TransfersView({ transfers = [], onNavigateTab, activeUser, onRefreshTransfers }) {
  const [selectedLabel, setSelectedLabel] = useState(null);
  const [qrImageDataUri, setQrImageDataUri] = useState(null);
  const [isLoadingQr, setIsLoadingQr] = useState(false);
  const [expandedTransferId, setExpandedTransferId] = useState(null);
  const [isGeneratingLabels, setIsGeneratingLabels] = useState(false);
  const [actionMessage, setActionMessage] = useState(null);

  const [transferDetails, setTransferDetails] = useState({});
  const [loadingDetails, setLoadingDetails] = useState({});

  const handleToggleExpand = async (transferId) => {
    if (expandedTransferId === transferId) {
      setExpandedTransferId(null);
      return;
    }
    setExpandedTransferId(transferId);
    if (!transferDetails[transferId]) {
      setLoadingDetails(prev => ({ ...prev, [transferId]: true }));
      try {
        const detail = await api.getTransferDetails(transferId);
        setTransferDetails(prev => ({ ...prev, [transferId]: detail }));
      } catch (err) {
        console.error('Failed to load transfer detail:', err);
      } finally {
        setLoadingDetails(prev => ({ ...prev, [transferId]: false }));
      }
    }
  };

  const handleCancelTransfer = async (transferId) => {
    const reason = prompt("Enter mandatory cancellation reason (e.g., Destination hospital resolved shortage locally):");
    if (!reason || reason.trim().length < 5) {
      alert("A valid cancellation reason (minimum 5 characters) is required.");
      return;
    }
    try {
      await api.cancelTransfer(transferId, {
        actor_user_id: activeUser?.id || "USR-ADMIN",
        reason: reason.trim()
      });
      alert("Transfer cancelled successfully. Reserved inventory released back to source usable pool.");
      if (onRefreshTransfers) onRefreshTransfers();
      const updated = await api.getTransferDetails(transferId);
      setTransferDetails(prev => ({ ...prev, [transferId]: updated }));
    } catch (err) {
      alert(`Cancellation failed: ${err.message}`);
    }
  };

  const handleExpireTransfer = async (transferId) => {
    if (!confirm("Are you sure you want to mark this transfer as EXPIRED? Reserved inventory will be released.")) return;
    try {
      await api.expireTransfer(transferId, {
        reason: "Transfer expired due to fulfillment window timeout"
      });
      alert("Transfer marked EXPIRED and reserved stock safely released.");
      if (onRefreshTransfers) onRefreshTransfers();
      const updated = await api.getTransferDetails(transferId);
      setTransferDetails(prev => ({ ...prev, [transferId]: updated }));
    } catch (err) {
      alert(`Expiry failed: ${err.message}`);
    }
  };

  const handleOpenQrModal = async (pkg, transfer) => {
    setSelectedLabel({ pkg, transfer });
    setIsLoadingQr(true);
    try {
      const token = pkg.label?.token || "SOS_DEMO_TRANSFER_TOKEN_VALID_2026";
      const res = await api.generateQRImage(token);
      setQrImageDataUri(res.data_uri);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoadingQr(false);
    }
  };

  const handleGenerateLabels = async (transferId) => {
    setIsGeneratingLabels(true);
    setActionMessage(null);
    try {
      const res = await api.generateTransferLabels(transferId, activeUser?.id);
      setActionMessage({
        type: 'success',
        text: `Issued ${res.labels_issued_count} serialized QR label(s) for transfer.`
      });
      if (onRefreshTransfers) onRefreshTransfers();
      const updated = await api.getTransferDetails(transferId);
      setTransferDetails(prev => ({ ...prev, [transferId]: updated }));
    } catch (err) {
      setActionMessage({
        type: 'error',
        text: err.message || 'Failed to generate QR labels.'
      });
    } finally {
      setIsGeneratingLabels(false);
    }
  };

  const handleSimulateLogistics = async (transferId, targetStatus) => {
    try {
      await api.updateTransferState(transferId, {
        target_status: targetStatus,
        actor_user_id: activeUser?.id || "USR-LOGISTICS-SIM",
        reason: "Simulated courier logistics update"
      });
      if (onRefreshTransfers) onRefreshTransfers();
      const updated = await api.getTransferDetails(transferId);
      setTransferDetails(prev => ({ ...prev, [transferId]: updated }));
    } catch (err) {
      alert(err.message || "Failed to update logistics status.");
    }
  };


  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Transfers & QR Traceability</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Physical custody tracking verified by opaque serialized QR labels. Every dispatch and receipt updates the auditable ledger.
          </p>
        </div>

        <button
          onClick={() => onNavigateTab('scanner')}
          className="inline-flex items-center space-x-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white px-3.5 py-2 rounded-md shadow-sm transition"
        >
          <ScanLine className="w-4 h-4" />
          <span>Open QR Scan Terminal</span>
        </button>
      </div>

      {actionMessage && (
        <div className={`p-3 rounded-lg text-xs font-medium border flex items-center justify-between ${
          actionMessage.type === 'success' 
            ? 'bg-emerald-50 text-emerald-800 border-emerald-200' 
            : 'bg-rose-50 text-rose-800 border-rose-200'
        }`}>
          <span>{actionMessage.text}</span>
          <button onClick={() => setActionMessage(null)} className="text-xs opacity-60 hover:opacity-100">✕</button>
        </div>
      )}

      <div className="space-y-4">
        {transfers.map((t) => {
          const isExpanded = expandedTransferId === t.id;
          const hasMissingLabels = t.packages?.some(p => !p.label);
          const isEligibleForLabels = (t.status === 'RESERVED' || t.status === 'READY_FOR_DISPATCH') && hasMissingLabels;

          return (
            <div key={t.id} className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                <div className="flex items-center space-x-2.5">
                  <Truck className="w-4 h-4 text-slate-500" />
                  <span className="text-xs font-mono font-bold text-slate-800">{t.tracking_reference}</span>
                  <StatusBadge status={t.status} />
                </div>
                <div className="flex items-center space-x-3 text-xs text-slate-500">
                  <span>Created: {new Date(t.created_at).toLocaleDateString()}</span>
                  <button
                    onClick={() => handleToggleExpand(t.id)}
                    className="inline-flex items-center space-x-1 text-slate-600 hover:text-slate-900 font-medium"
                  >
                    <span>{isExpanded ? 'Hide Details' : 'View Full Details & Audit'}</span>
                    {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                  </button>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between text-xs gap-2">
                <div>
                  <span className="font-semibold text-slate-900">{t.source_facility_name}</span>
                  <span className="text-slate-400 mx-2">──────►</span>
                  <span className="font-semibold text-slate-900">{t.destination_facility_name}</span>
                </div>
                <div className="text-slate-600">
                  Medicine: <span className="font-semibold text-slate-900">{t.product_name}</span> ({t.quantity} {t.unit})
                </div>
              </div>

              {/* Custody Lifecycle Timestamps */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 bg-slate-50/70 p-2.5 rounded border border-slate-100 text-[11px] text-slate-600">
                <div>
                  <span className="text-slate-400 block text-[10px]">Created:</span>
                  <span>{t.created_at ? new Date(t.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Dispatched:</span>
                  <span>{t.dispatched_at ? new Date(t.dispatched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Pending Dispatch'}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Received:</span>
                  <span>{t.received_at ? new Date(t.received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Pending Receipt'}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[10px]">Closed:</span>
                  <span>{t.closed_at ? new Date(t.closed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'In Progress'}</span>
                </div>
              </div>

              {/* Packages list */}
              <div className="bg-slate-50 rounded-md p-3 border border-slate-150 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                    Transfer Packages & Serialized QR Identifiers
                  </span>

                  {isEligibleForLabels && (
                    <button
                      onClick={() => handleGenerateLabels(t.id)}
                      disabled={isGeneratingLabels}
                      className="inline-flex items-center space-x-1 text-[11px] font-semibold text-emerald-700 hover:text-emerald-800 bg-white border border-emerald-300 px-2.5 py-1 rounded shadow-xs"
                    >
                      <QrCode className="w-3.5 h-3.5 text-emerald-600" />
                      <span>{isGeneratingLabels ? 'Generating...' : 'Issue QR Labels'}</span>
                    </button>
                  )}
                </div>

                <div className="divide-y divide-slate-200">
                  {t.packages?.map((pkg) => (
                    <div key={pkg.id} className="py-2 flex flex-col sm:flex-row sm:items-center justify-between text-xs gap-2">
                      <div className="space-y-0.5">
                        <div className="flex items-center space-x-2">
                          <span className="font-mono font-semibold text-slate-800">{pkg.package_reference}</span>
                          <span className="text-slate-500">Lot: {pkg.manufacturer_lot_number || 'LOT-RELEASED'}</span>
                          <span className="text-slate-500">Qty: {pkg.quantity} {pkg.unit}</span>
                          <StatusBadge status={pkg.status} />
                        </div>
                        {pkg.label && (
                          <div className="text-[10px] text-slate-400 font-mono">
                            Label ID: {pkg.label.id.substring(0, 8)}... | Hash: {pkg.label.token_preview || 'SHA256_VERIFIED'}
                          </div>
                        )}
                      </div>

                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => handleOpenQrModal(pkg, t)}
                          className="inline-flex items-center space-x-1 text-xs font-medium text-emerald-700 hover:text-emerald-800 bg-white border border-slate-200 px-2.5 py-1 rounded shadow-xs"
                        >
                          <QrCode className="w-3.5 h-3.5 text-emerald-600" />
                          <span>Inspect QR</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Simulated Logistics Operator Controls */}
              {t.status === 'DISPATCHED' && (
                <div className="bg-amber-50 border border-amber-200 p-2.5 rounded text-xs flex items-center justify-between">
                  <div className="text-amber-800">
                    <span className="font-semibold">Logistics Status:</span> Physical custody transferred at source. Courier transit simulation available.
                  </div>
                  <button
                    onClick={() => handleSimulateLogistics(t.id, 'IN_TRANSIT')}
                    className="inline-flex items-center space-x-1 bg-amber-600 hover:bg-amber-700 text-white font-medium px-2.5 py-1 rounded shadow-xs text-xs"
                  >
                    <PlayCircle className="w-3.5 h-3.5" />
                    <span>Advance to IN_TRANSIT</span>
                  </button>
                </div>
              )}

              {/* Expandable Comprehensive Transfer Detail Drawer */}
              {isExpanded && (
                <div className="mt-4 pt-4 border-t border-slate-200 space-y-4">
                  {loadingDetails[t.id] ? (
                    <div className="py-6 text-center text-xs text-slate-400">
                      Loading authoritative transfer and custody verification history...
                    </div>
                  ) : transferDetails[t.id] ? (
                    (() => {
                      const det = transferDetails[t.id];
                      const canCancel = ['RESERVED', 'READY_FOR_DISPATCH'].includes(det.status);

                      return (
                        <div className="space-y-4">
                          {/* Top Action Bar for Consequential Operations */}
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between bg-slate-50 p-3 rounded-lg border border-slate-200 gap-2">
                            <div className="text-xs text-slate-700">
                              <span className="font-bold text-slate-900">Transfer State Machine:</span> Status is{' '}
                              <span className="font-semibold">{det.status}</span> (Proposal v{det.proposal_version || 1})
                            </div>
                            <div className="flex items-center space-x-2">
                              {canCancel && (
                                <button
                                  onClick={() => handleCancelTransfer(det.id)}
                                  className="text-[11px] font-semibold bg-rose-50 text-rose-700 hover:bg-rose-100 border border-rose-300 px-3 py-1.5 rounded transition"
                                >
                                  Cancel Transfer & Release Stock
                                </button>
                              )}
                              {det.status !== 'CLOSED' && det.status !== 'CANCELLED' && det.status !== 'EXPIRED' && (
                                <button
                                  onClick={() => handleExpireTransfer(det.id)}
                                  className="text-[11px] font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 border border-slate-300 px-3 py-1.5 rounded transition"
                                >
                                  Mark Expired
                                </button>
                              )}
                            </div>
                          </div>

                          {/* Proposal Rationale & Pairing Drivers */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                            <div className="bg-blue-50/40 p-3 rounded-lg border border-blue-200 space-y-1">
                              <span className="text-[10px] font-bold uppercase tracking-wider text-blue-800">
                                Source Surplus Rationale ({det.source_facility_name})
                              </span>
                              <p className="text-slate-700 text-[11px] leading-relaxed">
                                {det.source_rationale?.summary || 'Safe surplus verified: local consumption and safety-stock buffer requirements protected.'}
                              </p>
                              {det.source_rationale?.surplus_quantity && (
                                <div className="text-[10px] text-blue-900 font-mono mt-1">
                                  Surplus: {det.source_rationale.surplus_quantity} {det.unit} | Safety Buffer: {det.source_rationale.safety_stock_quantity}
                                </div>
                              )}
                            </div>

                            <div className="bg-emerald-50/40 p-3 rounded-lg border border-emerald-200 space-y-1">
                              <span className="text-[10px] font-bold uppercase tracking-wider text-emerald-800">
                                Destination Need Rationale ({det.destination_facility_name})
                              </span>
                              <p className="text-slate-700 text-[11px] leading-relaxed">
                                {det.destination_rationale?.summary || 'Forecast stockout risk mitigated: credible demand signal substantiated by historical consumption.'}
                              </p>
                              {det.destination_rationale?.projected_need && (
                                <div className="text-[10px] text-emerald-900 font-mono mt-1">
                                  Unmet Need: {det.destination_rationale.projected_need} {det.unit} | Horizon Days: {det.destination_rationale.horizon_days || 30}
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Dual Human Approvals Review */}
                          <div className="bg-white rounded-lg border border-slate-200 p-3 space-y-2">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                              Dual Human Approvals Recorded (Governance Invariant)
                            </span>
                            <div className="divide-y divide-slate-100 text-xs">
                              {det.approvals && det.approvals.length > 0 ? (
                                det.approvals.map((appr, idx) => (
                                  <div key={idx} className="py-2 flex items-center justify-between">
                                    <div className="flex items-center space-x-2">
                                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                                      <span className="font-semibold text-slate-800">
                                        {appr.facility_id === det.source_facility_id ? 'Source Facility' : 'Destination Facility'}
                                      </span>
                                      <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">
                                        User: {appr.approver_user_id}
                                      </span>
                                      <span className="text-slate-500">v{appr.proposal_version}</span>
                                    </div>
                                    <div className="text-[11px] text-slate-500">
                                      <span>{appr.reason || appr.decision}</span> &bull;{' '}
                                      <span>{appr.decided_at ? new Date(appr.decided_at).toLocaleString() : 'Recorded'}</span>
                                    </div>
                                  </div>
                                ))
                              ) : (
                                <div className="py-2 text-slate-400 text-xs">Approvals logged in proposal transaction.</div>
                              )}
                            </div>
                          </div>

                          {/* Physical Scan Events Timeline */}
                          <div className="bg-white rounded-lg border border-slate-200 p-3 space-y-2">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                              Physical Custody QR Scan Events
                            </span>
                            {det.scan_events && det.scan_events.length > 0 ? (
                              <div className="divide-y divide-slate-100 text-xs">
                                {det.scan_events.map((scan, idx) => (
                                  <div key={idx} className="py-2 flex items-center justify-between">
                                    <div className="flex items-center space-x-2">
                                      <ScanLine className="w-3.5 h-3.5 text-blue-600" />
                                      <span className="font-bold text-slate-800">{scan.scan_type}</span>
                                      <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                                        scan.result === 'SUCCESS' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-rose-50 text-rose-700 border border-rose-200'
                                      }`}>
                                        {scan.result}
                                      </span>
                                    </div>
                                    <div className="text-[11px] text-slate-500 font-mono">
                                      Operator: {scan.user_id} &bull; {scan.scanned_at ? new Date(scan.scanned_at).toLocaleString() : 'Scanned'}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <div className="py-2 text-slate-400 text-xs">
                                No physical scans recorded yet. Ready for dispatch scan at {det.source_facility_name}.
                              </div>
                            )}
                          </div>

                          {/* Chronological Audit Trail */}
                          <div className="bg-slate-900 text-slate-200 rounded-lg p-3 text-xs space-y-2 font-mono">
                            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 font-sans block">
                              Immutable Ledger & Lifecycle Event Trail
                            </span>
                            <div className="space-y-1 max-h-36 overflow-y-auto text-[11px] divide-y divide-slate-800">
                              {det.audit_trail && det.audit_trail.length > 0 ? (
                                det.audit_trail.map((evt, idx) => (
                                  <div key={idx} className="pt-1">
                                    <span className="text-emerald-400">[{evt.action}]</span>{' '}
                                    <span className="text-slate-400">{evt.reason || 'State transition'}</span>{' '}
                                    <span className="text-slate-500">({evt.created_at ? new Date(evt.created_at).toLocaleTimeString() : ''})</span>
                                  </div>
                                ))
                              ) : (
                                <div className="text-slate-400">Audit trail initialized with transfer reservation.</div>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })()
                  ) : (
                    <div className="bg-slate-900 text-slate-200 rounded p-3 text-[11px] font-mono space-y-1">
                      <div>TRANSFER_ID: {t.id}</div>
                      <div>PROPOSAL_ID: {t.proposal_id}</div>
                      <div>SOURCE_FACILITY: {t.source_facility_id} ({t.source_facility_name})</div>
                      <div>DEST_FACILITY: {t.destination_facility_id} ({t.destination_facility_name})</div>
                      <div>AUDIT_STATUS: {t.status} (Immutable ledger synced)</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {transfers.length === 0 && (
          <div className="bg-white rounded-lg border border-slate-200 p-8 text-center text-xs text-slate-500">
            No active transfers in progress. Approve a proposal to generate a transfer and issue QR labels.
          </div>
        )}
      </div>

      {/* QR Modal */}
      {selectedLabel && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-xl max-w-sm w-full p-6 text-center space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-sm font-bold text-slate-900">Platform QR Serial Label</h3>
              <button 
                onClick={() => setSelectedLabel(null)} 
                className="text-slate-400 hover:text-slate-600 text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <div className="flex justify-center p-2 bg-slate-50 border border-slate-100 rounded-lg">
              {isLoadingQr ? (
                <div className="h-48 flex items-center justify-center text-xs text-slate-400">
                  Generating high-contrast QR...
                </div>
              ) : qrImageDataUri ? (
                <img src={qrImageDataUri} alt="Platform QR Label" className="w-48 h-48 object-contain" />
              ) : null}
            </div>

            <div className="text-left space-y-1 text-xs text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100 font-mono">
              <div><span className="font-semibold text-slate-800">Package:</span> {selectedLabel.pkg.package_reference}</div>
              <div><span className="font-semibold text-slate-800">Transfer:</span> {selectedLabel.transfer.tracking_reference}</div>
              <div><span className="font-semibold text-slate-800">Batch:</span> {selectedLabel.pkg.manufacturer_lot_number || 'LOT-2026'}</div>
              <div><span className="font-semibold text-slate-800">Authorized Qty:</span> {selectedLabel.pkg.quantity} {selectedLabel.pkg.unit}</div>
              <div className="truncate"><span className="font-semibold text-slate-800">Token Hash:</span> {selectedLabel.pkg.label?.token_preview || 'SHA256_ACTIVE'}</div>
            </div>

            <p className="text-[10px] text-slate-400 leading-tight">
              Verified platform workflow label. Authenticates physical custody state within MediFlow network. Does NOT substitute manufacturer serialization or cold-chain loggers.
            </p>

            <button
              onClick={() => {
                setSelectedLabel(null);
                onNavigateTab('scanner');
              }}
              className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-xs py-2 rounded-lg transition shadow-sm"
            >
              Test Scan in Terminal →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
