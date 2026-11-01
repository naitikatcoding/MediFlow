'use client';
import React, { useState, useEffect } from 'react';
import { 
  ScanLine, CheckCircle2, AlertTriangle, QrCode, ArrowRight, 
  Camera, CameraOff, Key, ShieldAlert, History, RefreshCw, AlertCircle, Info
} from 'lucide-react';
import { api } from '../../lib/api';

export function ScannerView({ activeFacility, activeUser, onScanSuccess }) {
  const [tokenInput, setTokenInput] = useState('SOS_DEMO_TRANSFER_TOKEN_VALID_2026');
  const [scanType, setScanType] = useState('DISPATCH');
  const [acceptedQty, setAcceptedQty] = useState('');
  const [damagedQty, setDamagedQty] = useState(0);
  const [rejectedQty, setRejectedQty] = useState(0);
  const [quarantinedQty, setQuarantinedQty] = useState(0);
  const [expectedTransferId, setExpectedTransferId] = useState('');
  const [operatorNotes, setOperatorNotes] = useState('');
  
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState(null);
  const [demoTokens, setDemoTokens] = useState([]);
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState(null);
  const [scanHistory, setScanHistory] = useState([]);

  useEffect(() => {
    fetchDemoTokens();
  }, []);

  const fetchDemoTokens = () => {
    api.getDemoTokens().then(res => setDemoTokens(res || [])).catch(() => {});
  };

  // Initialize and handle camera lifecycle with html5-qrcode
  useEffect(() => {
    let html5QrCode = null;
    let isMounted = true;

    if (isCameraActive) {
      setCameraError(null);
      import('html5-qrcode').then(({ Html5Qrcode }) => {
        if (!isMounted) return;
        const qrRegion = document.getElementById('qr-video-reader');
        if (!qrRegion) return;

        html5QrCode = new Html5Qrcode('qr-video-reader');
        html5QrCode.start(
          { facingMode: 'environment' },
          { fps: 10, qrbox: { width: 220, height: 220 } },
          (decodedText) => {
            if (!isMounted) return;
            setTokenInput(decodedText);
            setIsCameraActive(false);
            try {
              html5QrCode.stop().then(() => html5QrCode.clear()).catch(() => {});
            } catch (e) {}
          },
          () => {
            // frame without QR is expected, suppress
          }
        ).catch((err) => {
          if (!isMounted) return;
          setCameraError(err?.message || 'Camera permission denied or camera device unavailable.');
          setIsCameraActive(false);
        });
      }).catch((err) => {
        if (!isMounted) return;
        setCameraError('Camera scanner library failed to load: ' + err.message);
        setIsCameraActive(false);
      });
    }

    return () => {
      isMounted = false;
      if (html5QrCode && html5QrCode.isScanning) {
        try {
          html5QrCode.stop().then(() => html5QrCode.clear()).catch(() => {});
        } catch (e) {}
      }
    };
  }, [isCameraActive]);

  const handleScanSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!tokenInput.trim()) return;

    setIsScanning(true);
    setScanResult(null);

    try {
      const idempotencyKey = `scan_${Date.now()}_${Math.random().toString(36).substring(7)}`;
      const result = await api.submitQRScan({
        token: tokenInput.trim(),
        facility_id: activeFacility?.id,
        user_id: activeUser?.id,
        scan_type: scanType,
        idempotency_key: idempotencyKey,
        accepted_quantity: acceptedQty !== '' ? parseInt(acceptedQty, 10) : null,
        damaged_quantity: parseInt(damagedQty, 10) || 0,
        rejected_quantity: parseInt(rejectedQty, 10) || 0,
        quarantined_quantity: parseInt(quarantinedQty, 10) || 0,
        expected_transfer_id: expectedTransferId.trim() || null,
        notes: operatorNotes.trim() || null,
      });

      setScanResult(result);
      
      // Add to local session audit history
      setScanHistory(prev => [
        {
          timestamp: new Date().toLocaleTimeString(),
          scan_type: scanType,
          status: result.status,
          success: result.success,
          message: result.message,
          product: result.product_name,
          qty: result.verified_quantity || acceptedQty,
          token_preview: tokenInput.substring(0, 16) + '...'
        },
        ...prev.slice(0, 9)
      ]);

      if (result.success && onScanSuccess) {
        onScanSuccess();
        fetchDemoTokens();
      }
    } catch (err) {
      setScanResult({
        success: false,
        status: 'NETWORK_ERROR',
        message: err.message || 'Scan verification failed to reach backend API.'
      });
    } finally {
      setIsScanning(false);
    }
  };

  const getErrorExplanation = (status) => {
    switch (status) {
      case 'WRONG_FACILITY':
        return 'Security Violation: Custody scan location does not match the transfer manifest.';
      case 'ALREADY_DISPATCHED':
        return 'Replay Alert: This package has already completed its dispatch custody scan.';
      case 'ALREADY_RECEIVED':
        return 'Security Violation: Duplicate receipt prohibited. Package has already entered destination stock.';
      case 'WRONG_TRANSFER':
        return 'Context Mismatch: The scanned QR token belongs to a different transfer than selected.';
      case 'OVER_QUANTITY_REJECTED':
        return 'Reconciliation Discrepancy: The sum of accounted quantities exceeds the authorized package count.';
      case 'TOKEN_NOT_FOUND':
        return 'Identity Rejection: The opaque token was not recognized in the platform cryptographic registry.';
      case 'LABEL_REVOKED':
      case 'LABEL_EXPIRED':
        return 'Invalidated Credential: Label has been revoked or expired by an inventory administrator.';
      case 'UNAUTHORIZED_USER':
        return 'Access Denied: Current user credentials are not authorized for this custody transition.';
      default:
        return 'Transfer verification check failed.';
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-slate-900 tracking-tight">Scan a transfer QR code</h1>
        <p className="text-xs text-slate-500 mt-0.5">
          Authoritative physical custody handoff terminal. Validates opaque serialized tokens, prevents replay attacks, checks facility permissions, and enforces multi-category reconciliation on the immutable ledger.
        </p>
      </div>

      {/* Active Scanner Terminal Context */}
      <div className="bg-slate-900 text-slate-200 p-5 rounded-xl shadow-lg border border-slate-800 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center space-x-2">
            <ScanLine className="w-5 h-5 text-emerald-400" />
            <span className="text-xs font-bold uppercase tracking-wider text-white">Custody Handshake Engine</span>
          </div>
          <div className="text-xs text-slate-400">
            Active Facility: <span className="font-semibold text-emerald-400">{activeFacility?.name}</span>
          </div>
        </div>

        <form onSubmit={handleScanSubmit} className="space-y-4">
          {/* Scan Type Toggle */}
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => setScanType('DISPATCH')}
              className={`py-2.5 px-3 text-xs font-bold rounded-lg border transition text-left flex items-center justify-between ${
                scanType === 'DISPATCH'
                  ? 'bg-emerald-600 border-emerald-500 text-white shadow-md'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
              }`}
            >
              <span>1. DISPATCH SCAN (Source Facility)</span>
              {scanType === 'DISPATCH' && <span className="text-[10px] bg-emerald-700 px-2 py-0.5 rounded">Active</span>}
            </button>

            <button
              type="button"
              onClick={() => setScanType('RECEIVE')}
              className={`py-2.5 px-3 text-xs font-bold rounded-lg border transition text-left flex items-center justify-between ${
                scanType === 'RECEIVE'
                  ? 'bg-blue-600 border-blue-500 text-white shadow-md'
                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-white'
              }`}
            >
              <span>2. RECEIVE & RECONCILE (Destination)</span>
              {scanType === 'RECEIVE' && <span className="text-[10px] bg-blue-700 px-2 py-0.5 rounded">Active</span>}
            </button>
          </div>

          {/* Token Input with Live Camera Scanner option */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-semibold text-slate-300">
                Scanned QR Token (Opaque Cryptographic Reference)
              </label>
              <button
                type="button"
                onClick={() => {
                  setIsCameraActive(!isCameraActive);
                  setCameraError(null);
                }}
                className="inline-flex items-center space-x-1.5 text-[11px] font-medium text-emerald-400 hover:text-emerald-300 bg-slate-800 hover:bg-slate-700 px-3 py-1 rounded transition border border-slate-700"
              >
                {isCameraActive ? (
                  <>
                    <CameraOff className="w-3.5 h-3.5" />
                    <span>Close Camera</span>
                  </>
                ) : (
                  <>
                    <Camera className="w-3.5 h-3.5" />
                    <span>Open Device Camera</span>
                  </>
                )}
              </button>
            </div>

            {/* Live Camera Feed Area */}
            {isCameraActive && (
              <div className="bg-black rounded-lg p-3 border border-slate-700 flex flex-col items-center">
                <div id="qr-video-reader" className="w-full max-w-sm rounded overflow-hidden"></div>
                <p className="text-[10px] text-slate-400 mt-2">Point camera directly at printed or screen-displayed QR code</p>
              </div>
            )}

            {cameraError && (
              <div className="text-[11px] text-amber-400 bg-amber-950/40 border border-amber-800/60 p-2.5 rounded-lg flex items-center space-x-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{cameraError} — Use manual input or the test token table below.</span>
              </div>
            )}

            <div className="relative">
              <input
                type="text"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Scan QR or paste opaque token (e.g., MEDIFLOW_...)"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3.5 py-2.5 text-xs text-emerald-300 font-mono focus:border-emerald-500 focus:outline-none"
                required
              />
            </div>
          </div>

          {/* Optional Expected Transfer ID for Context Verification */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-slate-400">
                Expected Transfer ID (Optional manifest validation)
              </label>
              <input
                type="text"
                value={expectedTransferId}
                onChange={(e) => setExpectedTransferId(e.target.value)}
                placeholder="e.g. Leave blank or enter expected transfer ID"
                className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 mt-1 font-mono"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400">Operator Inspection Notes</label>
              <input
                type="text"
                value={operatorNotes}
                onChange={(e) => setOperatorNotes(e.target.value)}
                placeholder="e.g., Cold-chain packaging intact, seals checked"
                className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1.5 text-xs text-slate-200 mt-1"
              />
            </div>
          </div>

          {/* Multi-Category Reconciliation Fields (Receive Scan only) */}
          {scanType === 'RECEIVE' && (
            <div className="bg-slate-950/80 p-3.5 rounded-lg border border-slate-800 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-1.5">
                <span className="text-[11px] font-bold text-slate-300 uppercase tracking-wider">
                  Physical Goods Reconciliation
                </span>
                <span className="text-[10px] text-slate-400">
                  Separates accepted stock from damages, rejections, and quarantine
                </span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                <div>
                  <label className="text-[10px] text-emerald-400 font-medium">Accepted (Usable)</label>
                  <input
                    type="number"
                    value={acceptedQty}
                    onChange={(e) => setAcceptedQty(e.target.value)}
                    placeholder="Auto (Full)"
                    min="0"
                    className="w-full bg-slate-900 border border-emerald-800/80 rounded px-2 py-1 text-xs text-emerald-300 mt-1"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-amber-400 font-medium">Damaged in Transit</label>
                  <input
                    type="number"
                    value={damagedQty}
                    onChange={(e) => setDamagedQty(e.target.value)}
                    placeholder="0"
                    min="0"
                    className="w-full bg-slate-900 border border-amber-800/80 rounded px-2 py-1 text-xs text-amber-300 mt-1"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-purple-400 font-medium">Quarantined</label>
                  <input
                    type="number"
                    value={quarantinedQty}
                    onChange={(e) => setQuarantinedQty(e.target.value)}
                    placeholder="0"
                    min="0"
                    className="w-full bg-slate-900 border border-purple-800/80 rounded px-2 py-1 text-xs text-purple-300 mt-1"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-rose-400 font-medium">Rejected (Returned)</label>
                  <input
                    type="number"
                    value={rejectedQty}
                    onChange={(e) => setRejectedQty(e.target.value)}
                    placeholder="0"
                    min="0"
                    className="w-full bg-slate-900 border border-rose-800/80 rounded px-2 py-1 text-xs text-rose-300 mt-1"
                  />
                </div>
              </div>
            </div>
          )}

          <div className="flex items-center justify-between pt-2">
            <div className="text-[10px] text-slate-400">
              Authenticated Operator: <span className="text-slate-300 font-medium">{activeUser?.name}</span> ({activeUser?.role})
            </div>
            <button
              type="submit"
              disabled={isScanning}
              className={`inline-flex items-center space-x-2 text-white font-bold text-xs px-5 py-2.5 rounded-lg transition shadow-md disabled:opacity-50 ${
                scanType === 'DISPATCH' ? 'bg-emerald-600 hover:bg-emerald-500' : 'bg-blue-600 hover:bg-blue-500'
              }`}
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>{isScanning ? 'Verifying against Ledger...' : `Execute ${scanType} Verification`}</span>
            </button>
          </div>
        </form>
      </div>

      {/* Result Alert Banner */}
      {scanResult && (
        <div className={`p-4 rounded-xl border shadow-sm transition ${
          scanResult.success 
            ? 'bg-emerald-50 border-emerald-300 text-emerald-950'
            : 'bg-rose-50 border-rose-300 text-rose-950'
        }`}>
          <div className="flex items-start space-x-3">
            {scanResult.success ? (
              <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
            ) : (
              <ShieldAlert className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
            )}
            <div className="space-y-1.5 text-xs flex-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-sm">
                  {scanResult.success ? 'Verification & Custody Transition Confirmed' : `Verification Rejected: ${scanResult.status}`}
                </span>
                <span className="font-mono text-[10px] bg-white/80 px-2 py-0.5 rounded border border-slate-300">
                  {scanResult.status}
                </span>
              </div>
              <p className="text-slate-700">{scanResult.message}</p>
              {!scanResult.success && (
                <div className="text-[11px] font-semibold text-rose-800 bg-rose-100/60 p-2 rounded border border-rose-200">
                  {getErrorExplanation(scanResult.status)}
                </div>
              )}

              {scanResult.success && scanResult.product_name && (
                <div className="mt-2 text-[11px] font-mono grid grid-cols-2 sm:grid-cols-4 gap-2 bg-white/80 p-2.5 rounded border border-slate-200">
                  <div><span className="font-semibold text-slate-500">Medicine:</span> {scanResult.product_name}</div>
                  <div><span className="font-semibold text-slate-500">Lot:</span> {scanResult.lot_number}</div>
                  <div><span className="font-semibold text-slate-500">Expiry:</span> {scanResult.expiry_date}</div>
                  <div><span className="font-semibold text-slate-500">Verified Qty:</span> {scanResult.verified_quantity}</div>
                  {scanResult.damaged_quantity > 0 && (
                    <div className="text-amber-700"><span className="font-semibold">Damaged:</span> {scanResult.damaged_quantity}</div>
                  )}
                  {scanResult.quarantined_quantity > 0 && (
                    <div className="text-purple-700"><span className="font-semibold">Quarantined:</span> {scanResult.quarantined_quantity}</div>
                  )}
                  {scanResult.rejected_quantity > 0 && (
                    <div className="text-rose-700"><span className="font-semibold">Rejected:</span> {scanResult.rejected_quantity}</div>
                  )}
                  {scanResult.missing_quantity > 0 && (
                    <div className="text-slate-600"><span className="font-semibold">Missing:</span> {scanResult.missing_quantity}</div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Terminal History / Session Log */}
      {scanHistory.length > 0 && (
        <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm space-y-2">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2">
            <div className="flex items-center space-x-1.5 text-xs font-bold text-slate-800">
              <History className="w-4 h-4 text-slate-500" />
              <span>Current Session Scan Audit Log</span>
            </div>
            <span className="text-[10px] text-slate-400">{scanHistory.length} events</span>
          </div>
          <div className="divide-y divide-slate-100 text-xs">
            {scanHistory.map((h, i) => (
              <div key={i} className="py-2 flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className={`w-2 h-2 rounded-full ${h.success ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                  <span className="font-mono text-[10px] text-slate-400">{h.timestamp}</span>
                  <span className="font-bold text-slate-700">{h.scan_type}</span>
                  <span className="text-slate-500 truncate max-w-xs">{h.message}</span>
                </div>
                <span className={`text-[10px] font-mono px-2 py-0.5 rounded ${h.success ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                  {h.status}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Demo / Development Fallback Section */}
      <div className="bg-white rounded-lg border border-slate-200 p-4 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Key className="w-4 h-4 text-emerald-600" />
            <span className="text-xs font-bold text-slate-800 uppercase tracking-wide">
              Development & Demo Manual Fallback (Full Backend Verification Enforced)
            </span>
          </div>
          <button 
            onClick={fetchDemoTokens} 
            className="text-[11px] text-slate-500 hover:text-slate-700 flex items-center space-x-1"
          >
            <RefreshCw className="w-3 h-3" />
            <span>Refresh</span>
          </button>
        </div>
        <p className="text-[11px] text-slate-500">
          Click any active transfer token below to load it into the terminal. All cryptographic hash lookups, boundary checks, and ledger postings execute identically to camera scans.
        </p>

        <div className="divide-y divide-slate-100 text-xs max-h-60 overflow-y-auto">
          {demoTokens.map((dt, idx) => (
            <div 
              key={idx} 
              onClick={() => {
                setTokenInput(dt.token || dt.token_hash_preview || '');
                if (dt.transfer_id) setExpectedTransferId(dt.transfer_id);
              }}
              className="py-2.5 flex items-center justify-between cursor-pointer hover:bg-slate-50 rounded px-2 transition"
            >
              <div className="space-y-0.5">
                <div className="flex items-center space-x-2">
                  <span className="font-mono font-semibold text-slate-800">{dt.package_reference}</span>
                  <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded font-mono">
                    {dt.label_status || dt.transfer_status}
                  </span>
                </div>
                <div className="text-slate-500 text-[11px]">
                  {dt.source_facility} → {dt.destination_facility}
                </div>
                <p className="text-[10px] text-slate-400">{dt.instructions}</p>
              </div>
              <span className="text-[11px] font-mono text-emerald-700 bg-emerald-50 hover:bg-emerald-100 px-2.5 py-1 rounded border border-emerald-200 shrink-0">
                Load Token →
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
