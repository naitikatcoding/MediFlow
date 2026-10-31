'use client';
import React, { useState } from 'react';
import { Package, QrCode, Truck, CheckCircle2, Clock, Eye, ScanLine } from 'lucide-react';
import { StatusBadge } from '../Badges';
import { api } from '../../lib/api';

export function TransfersView({ transfers = [], onNavigateTab }) {
  const [selectedLabel, setSelectedLabel] = useState(null);
  const [qrImageDataUri, setQrImageDataUri] = useState(null);
  const [isLoadingQr, setIsLoadingQr] = useState(false);

  const handleOpenQrModal = async (pkg, transfer) => {
    setSelectedLabel({ pkg, transfer });
    setIsLoadingQr(true);
    try {
      // Use demo token or token preview
      const token = pkg.label?.token || "SOS_DEMO_TRANSFER_TOKEN_VALID_2026";
      const res = await api.generateQRImage(token);
      setQrImageDataUri(res.data_uri);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoadingQr(false);
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

      <div className="space-y-4">
        {transfers.map((t) => (
          <div key={t.id} className="bg-white rounded-lg border border-slate-200 shadow-sm p-4 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center space-x-2.5">
                <Truck className="w-4 h-4 text-slate-500" />
                <span className="text-xs font-mono font-bold text-slate-800">{t.tracking_reference}</span>
                <StatusBadge status={t.status} />
              </div>
              <div className="text-xs text-slate-500">
                Created: {new Date(t.created_at).toLocaleString()}
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

            {/* Packages list */}
            <div className="bg-slate-50 rounded-md p-3 border border-slate-150 space-y-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                Transfer Packages & QR Serial Labels
              </span>
              <div className="divide-y divide-slate-200">
                {t.packages.map((pkg) => (
                  <div key={pkg.id} className="py-2 flex items-center justify-between text-xs">
                    <div>
                      <span className="font-mono font-semibold text-slate-800">{pkg.package_reference}</span>
                      <span className="text-slate-500 ml-2">Batch: {pkg.manufacturer_lot_number || 'LOT-2026'}</span>
                      <span className="text-slate-500 ml-2">Qty: {pkg.quantity} {pkg.unit}</span>
                      <span className="ml-2">
                        <StatusBadge status={pkg.status} />
                      </span>
                    </div>

                    <button
                      onClick={() => handleOpenQrModal(pkg, t)}
                      className="inline-flex items-center space-x-1 text-xs font-medium text-emerald-700 hover:text-emerald-800 bg-white border border-slate-200 px-2.5 py-1 rounded shadow-xs"
                    >
                      <QrCode className="w-3.5 h-3.5 text-emerald-600" />
                      <span>Inspect QR Label</span>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}

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
                  Generating QR image...
                </div>
              ) : qrImageDataUri ? (
                <img src={qrImageDataUri} alt="Platform QR Label" className="w-48 h-48 object-contain" />
              ) : null}
            </div>

            <div className="text-left space-y-1 text-xs text-slate-600 bg-slate-50 p-3 rounded-lg border border-slate-100 font-mono">
              <div><span className="font-semibold text-slate-800">Package:</span> {selectedLabel.pkg.package_reference}</div>
              <div><span className="font-semibold text-slate-800">Transfer:</span> {selectedLabel.transfer.tracking_reference}</div>
              <div><span className="font-semibold text-slate-800">Batch:</span> {selectedLabel.pkg.manufacturer_lot_number}</div>
              <div><span className="font-semibold text-slate-800">Authorized Qty:</span> {selectedLabel.pkg.quantity} {selectedLabel.pkg.unit}</div>
              <div className="truncate"><span className="font-semibold text-slate-800">Token Hash:</span> {selectedLabel.pkg.label?.token_preview || 'SHA256_ACTIVE'}</div>
            </div>

            <p className="text-[10px] text-slate-400 leading-tight">
              Verified platform workflow label. Authenticates physical custody state within MediFlow network.
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

