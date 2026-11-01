'use client';
import React, { useState, useEffect } from 'react';
import { 
  Package, Search, Filter, Snowflake, AlertCircle, ShieldAlert, 
  Upload, Sliders, CheckCircle2, RefreshCw, X, FileText 
} from 'lucide-react';
import { api } from '../../lib/api';

export function InventoryView({ 
  inventory = [], 
  facilities = [], 
  activeFacility, 
  activeUser, 
  onRefresh 
}) {
  const [filterFacility, setFilterFacility] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');
  const [summary, setSummary] = useState(null);
  const [isReconciling, setIsReconciling] = useState(false);
  const [reconcileResult, setReconcileResult] = useState(null);

  // Modals state
  const [adjustmentItem, setAdjustmentItem] = useState(null);
  const [adjustmentType, setAdjustmentType] = useState('ADJUSTMENT');
  const [adjustmentDelta, setAdjustmentDelta] = useState('');
  const [adjustmentReason, setAdjustmentReason] = useState('');
  const [isSubmittingAdj, setIsSubmittingAdj] = useState(false);
  const [adjError, setAdjError] = useState(null);

  // Import Modal state
  const [showImportModal, setShowImportModal] = useState(false);
  const [csvContent, setCsvContent] = useState('');
  const [isImporting, setIsImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  // Sync active facility filter
  useEffect(() => {
    if (activeFacility?.id && filterFacility === 'ALL') {
      // Keep option to show all, but default can follow active
    }
  }, [activeFacility]);

  // Load summary metrics
  const loadSummary = async () => {
    try {
      const facId = filterFacility !== 'ALL' ? filterFacility : undefined;
      const data = await api.getInventorySummary(facId);
      setSummary(data);
    } catch (err) {
      console.warn('Failed to load inventory summary:', err.message);
    }
  };

  useEffect(() => {
    loadSummary();
  }, [filterFacility, inventory]);

  const filtered = inventory.filter(item => {
    if (filterFacility !== 'ALL' && item.facility_id !== filterFacility) return false;
    if (searchTerm) {
      const q = searchTerm.toLowerCase();
      return (
        item.product_name.toLowerCase().includes(q) ||
        item.generic_name.toLowerCase().includes(q) ||
        item.manufacturer_lot_number.toLowerCase().includes(q)
      );
    }
    return true;
  });

  // Reconcile Handler
  const handleReconcile = async () => {
    const targetFac = filterFacility !== 'ALL' ? filterFacility : (activeFacility?.id || (facilities[0]?.id));
    if (!targetFac) return;

    setIsReconciling(true);
    try {
      const res = await api.reconcileFacility(targetFac);
      setReconcileResult(res);
      if (onRefresh) await onRefresh();
      await loadSummary();
    } catch (err) {
      alert(`Reconciliation error: ${err.message}`);
    } finally {
      setIsReconciling(false);
    }
  };

  // Submit Adjustment
  const handleSubmitAdjustment = async (e) => {
    e.preventDefault();
    if (!adjustmentItem || !adjustmentDelta || !adjustmentReason) return;

    const delta = parseInt(adjustmentDelta, 10);
    if (isNaN(delta) || delta === 0) {
      setAdjError('Quantity delta must be a non-zero integer.');
      return;
    }

    setIsSubmittingAdj(true);
    setAdjError(null);

    try {
      await api.recordAdjustment({
        facility_id: adjustmentItem.facility_id,
        batch_id: adjustmentItem.batch_id,
        adjustment_type: adjustmentType,
        quantity_delta: delta,
        unit: adjustmentItem.unit || 'UNIT',
        reason: adjustmentReason,
        actor_id: activeUser?.id || 'pharmacist_console',
        idempotency_key: `adj_${Date.now()}_${Math.random().toString(36).substring(7)}`
      });

      setAdjustmentItem(null);
      setAdjustmentDelta('');
      setAdjustmentReason('');
      if (onRefresh) await onRefresh();
      await loadSummary();
    } catch (err) {
      setAdjError(err.message || 'Failed to record adjustment');
    } finally {
      setIsSubmittingAdj(false);
    }
  };

  // Submit CSV Import
  const handleImportCsv = async () => {
    if (!csvContent.trim()) return;
    setIsImporting(true);
    setImportResult(null);

    try {
      const formData = new FormData();
      formData.append('csv_data', csvContent);
      if (activeFacility?.id) {
        formData.append('facility_id', activeFacility.id);
      }
      formData.append('actor_id', activeUser?.id || 'pharmacist_csv');

      const job = await api.importInventoryCsv(formData);
      setImportResult(job);
      if (job.status === 'COMPLETED') {
        if (onRefresh) await onRefresh();
        await loadSummary();
      }
    } catch (err) {
      setImportResult({ status: 'FAILED', error: err.message });
    } finally {
      setIsImporting(false);
    }
  };

  const sampleCsvTemplate = `facility_id,product_code,lot_number,expiry_date,quantity,unit,manufacturer
${activeFacility?.id || 'fac_apex'},MED-001,LOT-SAMPLE-01,2027-06-30,100,VIAL,PharmaCorp India
${activeFacility?.id || 'fac_apex'},MED-002,LOT-SAMPLE-02,2026-12-15,50,VIAL,Apex Formulations`;

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Inventory</h1>
            {summary && (
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${
                summary.data_freshness_status === 'FRESH'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-amber-50 text-amber-700 border-amber-200 animate-pulse'
              }`}>
                {summary.data_freshness_status} DATA
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Operational batch balances, FEFO lot priority, audit reconciliation, and ledger adjustments.
          </p>
        </div>

        {/* Global Actions */}
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowImportModal(true)}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-md text-xs font-medium shadow-2xs transition"
          >
            <Upload className="w-3.5 h-3.5 text-slate-500" />
            <span>Import CSV</span>
          </button>

          <button
            onClick={handleReconcile}
            disabled={isReconciling}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-md text-xs font-medium shadow-2xs transition disabled:opacity-50"
            title="Verify materialized balances against immutable movement ledger"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isReconciling ? 'animate-spin' : ''}`} />
            <span>{isReconciling ? 'Auditing...' : 'Reconcile Ledger'}</span>
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-2xs">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Total On Hand</div>
          <div className="text-lg font-bold text-slate-900 mt-0.5 font-mono">
            {summary ? summary.total_on_hand.toLocaleString() : '—'}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">Across physical stores</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-emerald-200 bg-emerald-50/20 shadow-2xs">
          <div className="text-[11px] font-semibold text-emerald-800 uppercase tracking-wider">Usable Eligible</div>
          <div className="text-lg font-bold text-emerald-700 mt-0.5 font-mono">
            {summary ? summary.total_usable.toLocaleString() : '—'}
          </div>
          <div className="text-[10px] text-emerald-600 mt-0.5">Available for transfer</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-amber-200 bg-amber-50/20 shadow-2xs">
          <div className="text-[11px] font-semibold text-amber-800 uppercase tracking-wider">Reserved Stock</div>
          <div className="text-lg font-bold text-amber-700 mt-0.5 font-mono">
            {summary ? summary.total_reserved.toLocaleString() : '—'}
          </div>
          <div className="text-[10px] text-amber-600 mt-0.5">Committed to transfers</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-rose-200 bg-rose-50/20 shadow-2xs">
          <div className="text-[11px] font-semibold text-rose-800 uppercase tracking-wider">Blocked / Quarantine</div>
          <div className="text-lg font-bold text-rose-700 mt-0.5 font-mono">
            {summary ? (summary.total_quarantined + summary.total_damaged).toLocaleString() : '—'}
          </div>
          <div className="text-[10px] text-rose-600 mt-0.5">Hold or damaged units</div>
        </div>

        <div className="bg-white p-3.5 rounded-lg border border-slate-200 shadow-2xs col-span-2 sm:col-span-1">
          <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">Near Expiry (&le;45d)</div>
          <div className="text-lg font-bold text-slate-900 mt-0.5 font-mono">
            {summary ? summary.near_expiry_batches_count : '—'}
          </div>
          <div className="text-[10px] text-slate-400 mt-0.5">Priority FEFO dispatch</div>
        </div>
      </div>

      {/* Reconciliation Alert Banner if Discrepancies Found */}
      {reconcileResult && (
        <div className={`p-3.5 rounded-lg border text-xs flex items-center justify-between ${
          reconcileResult.discrepancy_count === 0
            ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
            : 'bg-rose-50 border-rose-200 text-rose-800'
        }`}>
          <div className="flex items-center space-x-2">
            {reconcileResult.discrepancy_count === 0 ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            ) : (
              <ShieldAlert className="w-4 h-4 text-rose-600 shrink-0" />
            )}
            <span>
              <strong>Ledger Audit:</strong> Verified {reconcileResult.reconciled_batches_count} batches. 
              {reconcileResult.discrepancy_count === 0 
                ? ' 100% balance integrity with zero discrepancies.' 
                : ` Flagged ${reconcileResult.discrepancy_count} discrepancy mismatch.`}
            </span>
          </div>
          <button onClick={() => setReconcileResult(null)} className="text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white p-3 rounded-lg border border-slate-200 shadow-2xs">
        <div className="relative w-full sm:w-72">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
          <input
            type="text"
            placeholder="Search medicine, generic, lot..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-md text-slate-800 placeholder-slate-400 focus:outline-none focus:border-emerald-500 focus:bg-white transition"
          />
        </div>

        <div className="flex items-center space-x-2 w-full sm:w-auto">
          <select
            className="text-xs bg-slate-50 border border-slate-200 rounded-md px-2.5 py-1.5 text-slate-700 font-medium focus:outline-none focus:bg-white"
            value={filterFacility}
            onChange={(e) => setFilterFacility(e.target.value)}
          >
            <option value="ALL">All Network Facilities</option>
            {facilities.map(f => (
              <option key={f.id} value={f.id}>{f.name}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Inventory Table */}
      <div className="bg-white rounded-lg border border-slate-200 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[10px]">
              <tr>
                <th className="px-4 py-3">Medicine Catalogue</th>
                <th className="px-4 py-3">Facility</th>
                <th className="px-4 py-3">Batch / Lot</th>
                <th className="px-4 py-3">Expiry (FEFO)</th>
                <th className="px-4 py-3">Storage</th>
                <th className="px-4 py-3 text-right">On Hand</th>
                <th className="px-4 py-3 text-right">Reserved</th>
                <th className="px-4 py-3 text-right">Hold / Block</th>
                <th className="px-4 py-3 text-right font-bold text-slate-900">Usable Eligible</th>
                <th className="px-4 py-3 text-center">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-700">
              {filtered.map((item, idx) => {
                const isNearExp = item.days_to_expiry <= 45;
                const isCold = item.storage_requirements === 'COLD_CHAIN_2_8C';
                const isBlocked = item.is_blocked;

                return (
                  <tr key={idx} className="hover:bg-slate-50/70 transition">
                    <td className="px-4 py-3">
                      <div className="font-semibold text-slate-900">{item.product_name}</div>
                      <div className="text-[10px] text-slate-400 font-normal">
                        {item.generic_name} • {item.strength} ({item.dosage_form})
                      </div>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {item.facility_name}
                    </td>
                    <td className="px-4 py-3 font-mono text-slate-800">
                      <div className="flex items-center space-x-1.5">
                        <span>{item.manufacturer_lot_number}</span>
                        {isBlocked && (
                          <span className="text-[9px] font-bold bg-rose-100 text-rose-700 px-1 rounded" title="Batch on hold or blocked">
                            HOLD
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className={isNearExp ? 'text-amber-700 font-bold' : 'text-slate-800 font-medium'}>
                        {item.expiry_date}
                      </div>
                      <div className={`text-[10px] ${isNearExp ? 'text-amber-600 font-semibold' : 'text-slate-400'}`}>
                        {item.days_to_expiry} days left
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {isCold ? (
                        <span className="inline-flex items-center space-x-1 text-[10px] font-semibold text-cyan-800 bg-cyan-50 px-2 py-0.5 rounded border border-cyan-200">
                          <Snowflake className="w-3 h-3 text-cyan-600" />
                          <span>2–8°C</span>
                        </span>
                      ) : (
                        <span className="text-[10px] text-slate-500 font-medium">Ambient</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-medium text-slate-900">
                      {item.on_hand_quantity}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-amber-700">
                      {item.reserved_quantity}
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-rose-700">
                      {(item.quarantined_quantity || 0) + (item.damaged_quantity || 0)}
                    </td>
                    <td className="px-4 py-3 text-right font-mono font-bold text-emerald-700 text-sm">
                      {item.usable_quantity} <span className="text-[10px] font-normal text-slate-400">{item.unit}</span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        onClick={() => setAdjustmentItem(item)}
                        className="text-[11px] font-medium text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 px-2 py-1 rounded transition"
                      >
                        Adjust
                      </button>
                    </td>
                  </tr>
                );
              })}

              {filtered.length === 0 && (
                <tr>
                  <td colSpan={10} className="px-4 py-12 text-center text-slate-400">
                    <Package className="w-8 h-8 mx-auto text-slate-300 mb-2" />
                    <p className="font-medium text-slate-500">No inventory lots found</p>
                    <p className="text-[11px] text-slate-400 mt-0.5">Try adjusting your filters or import a CSV lot file.</p>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Authorised Stock Adjustment Modal */}
      {adjustmentItem && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-md w-full shadow-2xl border border-slate-200 p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Authorised Stock Adjustment</h3>
                <p className="text-xs text-slate-500">{adjustmentItem.product_name} • Lot {adjustmentItem.manufacturer_lot_number}</p>
              </div>
              <button onClick={() => setAdjustmentItem(null)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSubmitAdjustment} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Movement Type</label>
                <select
                  value={adjustmentType}
                  onChange={(e) => setAdjustmentType(e.target.value)}
                  className="w-full text-xs bg-slate-50 border border-slate-200 rounded-md p-2 text-slate-800 font-medium focus:outline-none focus:border-emerald-500"
                >
                  <option value="ADJUSTMENT">Physical Count Adjustment</option>
                  <option value="DAMAGE">Log Damaged Stock</option>
                  <option value="QUARANTINE">Move to Quarantine (Hold)</option>
                  <option value="RELEASE_FROM_QUARANTINE">Release from Quarantine</option>
                  <option value="RETURN">Ward / Pharmacy Return</option>
                  <option value="EXPIRY">Log Expired Disposal</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Quantity Delta ({adjustmentItem.unit})
                </label>
                <input
                  type="number"
                  placeholder="e.g. +10 (add) or -5 (deduct)"
                  value={adjustmentDelta}
                  onChange={(e) => setAdjustmentDelta(e.target.value)}
                  required
                  className="w-full text-xs bg-slate-50 border border-slate-200 rounded-md p-2 text-slate-800 font-mono focus:outline-none focus:border-emerald-500"
                />
                <span className="text-[10px] text-slate-400 mt-1 block">
                  Current On-Hand: <strong>{adjustmentItem.on_hand_quantity}</strong> | Usable: <strong>{adjustmentItem.usable_quantity}</strong>
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Audit Reason (Mandatory)
                </label>
                <textarea
                  rows={2}
                  placeholder="Explain why this stock adjustment is authorized..."
                  value={adjustmentReason}
                  onChange={(e) => setAdjustmentReason(e.target.value)}
                  required
                  className="w-full text-xs bg-slate-50 border border-slate-200 rounded-md p-2 text-slate-800 focus:outline-none focus:border-emerald-500"
                />
              </div>

              {adjError && (
                <div className="text-xs bg-rose-50 border border-rose-200 text-rose-700 p-2 rounded">
                  {adjError}
                </div>
              )}

              <div className="flex justify-end space-x-2 pt-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setAdjustmentItem(null)}
                  className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-md"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmittingAdj}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-md shadow-2xs disabled:opacity-50"
                >
                  {isSubmittingAdj ? 'Recording...' : 'Commit to Ledger'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* CSV Import Modal */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl max-w-lg w-full shadow-2xl border border-slate-200 p-5 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Import Inventory Batch CSV</h3>
                <p className="text-xs text-slate-500">Ingest physical stock, lot expiries, and opening balances.</p>
              </div>
              <button onClick={() => setShowImportModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs">
                <label className="font-semibold text-slate-700">CSV Data or Paste</label>
                <button
                  type="button"
                  onClick={() => setCsvContent(sampleCsvTemplate)}
                  className="text-emerald-700 hover:underline text-[11px]"
                >
                  Load Sample Template
                </button>
              </div>

              <textarea
                rows={7}
                placeholder="Paste CSV lines with headers: facility_id,product_code,lot_number,expiry_date,quantity,unit,manufacturer"
                value={csvContent}
                onChange={(e) => setCsvContent(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 border border-slate-200 rounded-md p-2.5 text-slate-800 focus:outline-none focus:border-emerald-500"
              />

              {importResult && (
                <div className={`p-3 rounded-lg border text-xs ${
                  importResult.status === 'COMPLETED'
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                    : 'bg-rose-50 border-rose-200 text-rose-800'
                }`}>
                  <p className="font-semibold">
                    {importResult.status === 'COMPLETED' ? 'Import Succeeded' : 'Import Alert'}
                  </p>
                  <p className="mt-0.5">
                    Accepted: <strong>{importResult.accepted_count || 0}</strong> | Rejected: <strong>{importResult.rejected_count || 0}</strong>
                  </p>
                  {importResult.error_summary?.errors?.length > 0 && (
                    <div className="mt-2 text-[11px] max-h-24 overflow-y-auto space-y-1 bg-white/60 p-2 rounded">
                      {importResult.error_summary.errors.map((err, i) => (
                        <div key={i} className="text-rose-700 font-mono">
                          Row {err.row}: {err.error}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="flex justify-end space-x-2 pt-2 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowImportModal(false)}
                className="px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 rounded-md"
              >
                Close
              </button>
              <button
                type="button"
                onClick={handleImportCsv}
                disabled={isImporting || !csvContent.trim()}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-slate-900 hover:bg-slate-800 rounded-md shadow-2xs disabled:opacity-50"
              >
                {isImporting ? 'Processing CSV...' : 'Process Import'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
