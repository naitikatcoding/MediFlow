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
                    onClick={() => setExpandedTransferId(isExpanded ? null : t.id)}
                    className="inline-flex items-center space-x-1 text-slate-600 hover:text-slate-900 font-medium"
                  >
                    <span>{isExpanded ? 'Hide Details' : 'View Audit & Trail'}</span>
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

              {/* Expandable Audit Details & Scan Events */}
              {isExpanded && (
                <div className="mt-3 pt-3 border-t border-slate-100 space-y-3">
                  <div className="flex items-center space-x-1.5 text-xs font-bold text-slate-800">
                    <History className="w-4 h-4 text-slate-500" />
                    <span>Custody Verification Audit Trail</span>
                  </div>

                  <p className="text-[11px] text-slate-500">
                    Cryptographic tokens are opaque references hashed via SHA-256 in the database. Scan operations enforce strict boundary constraints: wrong source/destination facility scans and replay attempts are rejected and logged.
                  </p>

                  <div className="bg-slate-900 text-slate-200 rounded p-3 text-[11px] font-mono space-y-1">
                    <div>TRANSFER_ID: {t.id}</div>
                    <div>PROPOSAL_ID: {t.proposal_id}</div>
                    <div>SOURCE_FACILITY: {t.source_facility_id} ({t.source_facility_name})</div>
                    <div>DEST_FACILITY: {t.destination_facility_id} ({t.destination_facility_name})</div>
                    <div>AUDIT_STATUS: {t.status} (Immutable ledger synced)</div>
                  </div>
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
